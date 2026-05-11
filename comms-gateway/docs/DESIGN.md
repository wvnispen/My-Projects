# CommsGateway — Design Document

**Version:** 0.2  
**Date:** 2026-05-11  
**Author:** Wynand van Nispen  
**Status:** Draft — hardware confirmed, firmware pending

---

## 1. Overview

CommsGateway is a self-hosted, locally-run messaging gateway that replaces external services like CallmeBot. It allows Home Assistant (and any other internal system) to send **SMS, Telegram, and WhatsApp** messages via a single REST API, with no dependency on third-party relay services.

### Goals

- No external relay services — all message delivery is local or via official APIs
- Single API endpoint for Home Assistant, regardless of channel
- ESP32-based SMS hardware — low power, no server required for SMS
- WhatsApp via a local bridge (WAHA) running on Proxmox
- Telegram via the official Bot API (no bridge needed)
- Easy to swap ESP32 hardware without changing any other component
- API-key authenticated — no unauthenticated access even on the local network

### Out of scope (v1)

- Inbound message handling / two-way messaging
- Voice calls
- Signal, iMessage, or other channels
- Multi-tenant / multi-user access

---

## 2. Hardware

### Confirmed: LILYGO T-A7670G-S3-Standard (ordered)

| Spec | Value |
|------|-------|
| MCU | ESP32-S3, dual-core Xtensa LX7 240MHz |
| Modem | A7670G — LTE **Cat-1**, global bands |
| LTE bands | B1/B2/B3/B4/B5/B7/B8/B12/B13/B18/B19/B20/B25/B26/**B28**/B66 |
| SA networks | Vodacom ✓ MTN ✓ Cell C ✓ (Band 28 700MHz confirmed) |
| GNSS | Separate GPS UART (NMEA on GPIO 48/45) — independent of modem UART |
| Battery | 18650 holder + solar charge input |
| WiFi | 802.11 b/g/n |
| Bluetooth | 5.0 LE |
| Camera | OV2640 interface (Standard variant) |
| Data rate | 10 Mbps down / 5 Mbps up (Cat-1 — sufficient for all messaging) |

### Confirmed GPIO pin map (from LilyGO-T-A76XX utilities.h, `LILYGO_A7670X_S3_STAN`)

| Function | GPIO |
|----------|------|
| Modem TX (ESP→modem) | **4** |
| Modem RX (modem→ESP) | **5** |
| Modem DTR | 7 |
| Modem RING | 6 |
| Modem PWRKEY | **46** |
| Modem power-save | 42 |
| GPS RX (NMEA in) | **48** |
| GPS TX | 45 |
| GPS PPS | 17 |
| GPS enable | 1 (active HIGH) |
| Audio PA enable | 3 (active HIGH) |
| Battery ADC | 8 |
| Solar ADC | 18 |
| I2C SDA | 3 |
| I2C SCL | 2 |
| SD MISO | 13 |
| SD MOSI | 11 |
| SD SCK | 12 |
| SD CS | 10 |

> Note: The Standard board has GPS on its **own UART** (GPIO 48/45), separate from the modem AT command UART (GPIO 4/5). This means clean NMEA sentences without AT command interleaving — read GPS as a normal serial stream.

### Porting effort between boards

All hardware-specific values (UART pins, power key, reset pin, modem AT variant) live in a single `config/board.h`. Switching is a single `#define` change and a rebuild. See Section 5.

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Home Assistant (192.168.1.x)                           │
│                                                         │
│  notify.comms_sms / notify.comms_telegram /             │
│  notify.comms_whatsapp                                  │
└───────────────────────┬─────────────────────────────────┘
                        │ HTTPS POST /api/v1/send
                        │ X-API-Key: <secret>
                        ▼
┌─────────────────────────────────────────────────────────┐
│  Proxmox LXC — commsgateway-bridge                      │
│  Ubuntu 24.04 LXC  |  192.168.1.Y  |  port 8080        │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  CommsGateway API  (Python FastAPI)              │   │
│  │  - Auth middleware (API key validation)          │   │
│  │  - Rate limiting                                 │   │
│  │  - Channel router                                │   │
│  └────────┬──────────────┬──────────────────────────┘   │
│           │              │                               │
│           │ HTTP POST    │ python-telegram-bot           │
│           ▼              ▼                               │
│  ┌─────────────┐  ┌─────────────────────────────────┐   │
│  │ WAHA        │  │  Telegram Bot API               │   │
│  │ (Docker)    │  │  api.telegram.org               │   │
│  │ port 3000   │  │  (official, no bridge needed)   │   │
│  │             │  └─────────────────────────────────┘   │
│  │ WhatsApp    │                                         │
│  │ Web session │                                         │
│  └─────────────┘                                         │
└─────────────────────────────────────────────────────────┘
                        │ HTTP POST /send/sms
                        │ (internal network only)
                        ▼
┌─────────────────────────────────────────────────────────┐
│  ESP32 Device  (192.168.1.Z, WiFi)                      │
│  LILYGO T-SIM7600G-H  or  WVS A7670E                   │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  ESP32 Firmware  (Arduino/PlatformIO)            │   │
│  │  - HTTP server (port 80)                         │   │
│  │  - IP whitelist (bridge LXC IP only)             │   │
│  │  - AT command driver                             │   │
│  └───────────────────────┬──────────────────────────┘   │
│                          │ UART (AT commands)            │
│                          ▼                               │
│              SIM7600G-H / A7670E modem                  │
│                          │                               │
└──────────────────────────┼──────────────────────────────┘
                           │ LTE (Vodacom/MTN/Cell C)
                           ▼
                    Recipient's phone (SMS)
```

### Channel routing summary

| Channel | Path |
|---------|------|
| SMS | HA → Bridge API → ESP32 HTTP → AT+CMGS → cellular |
| Telegram | HA → Bridge API → python-telegram-bot → api.telegram.org |
| WhatsApp | HA → Bridge API → WAHA (local Docker) → WA Web protocol |

### Fallback behaviour

| Failure | Fallback |
|---------|---------|
| ESP32 unreachable | Bridge returns `503`, logs error, no silent drop |
| WAHA session expired | Bridge returns `503` with reason `whatsapp_session_expired` |
| Telegram Bot API unreachable | Bridge returns `503`, HA automation can retry |
| Bridge LXC down | HA automations fail — considered acceptable for v1 |

---

## 4. Component Specifications

### 4.1 CommsGateway Bridge (Proxmox LXC)

**Runtime:** Python 3.12, FastAPI, uvicorn  
**Process manager:** systemd  
**LXC:** Ubuntu 24.04, 1 CPU, 512MB RAM, 4GB disk

#### Directory layout

```
/opt/commsgateway/
├── main.py              # FastAPI app, startup
├── config.py            # Settings loaded from .env
├── routers/
│   ├── send.py          # POST /api/v1/send
│   └── health.py        # GET /api/v1/health, /api/v1/status
├── channels/
│   ├── sms.py           # Forwards to ESP32 HTTP
│   ├── telegram.py      # python-telegram-bot
│   └── whatsapp.py      # WAHA REST client
├── middleware/
│   ├── auth.py          # API key header validation
│   └── ratelimit.py     # Per-key rate limiting
├── .env                 # Secrets — never committed
└── requirements.txt
```

#### Environment variables (.env)

```env
API_KEY=<random 32-byte hex>
ESP32_URL=http://192.168.1.Z
ESP32_TIMEOUT=10

TELEGRAM_BOT_TOKEN=<from BotFather>
TELEGRAM_DEFAULT_CHAT_ID=<your chat ID>

WAHA_URL=http://127.0.0.1:3000
WAHA_API_KEY=<waha api key>
WAHA_SESSION=default
WAHA_DEFAULT_NUMBER=27821234567

RATE_LIMIT_PER_MINUTE=30
LOG_LEVEL=INFO
```

#### API endpoints

```
POST /api/v1/send
GET  /api/v1/health
GET  /api/v1/status
```

**POST /api/v1/send — request**

```json
{
  "channel": "sms | telegram | whatsapp",
  "to": "+27821234567",
  "message": "Your alarm triggered at 03:14"
}
```

- `to` is optional — falls back to the default configured per channel
- `channel` is required

**POST /api/v1/send — response**

```json
{
  "status": "ok",
  "channel": "sms",
  "delivery_id": "abc123"
}
```

On error:

```json
{
  "status": "error",
  "channel": "sms",
  "reason": "esp32_unreachable"
}
```

**GET /api/v1/status — response**

```json
{
  "esp32": { "reachable": true, "signal_dbm": -73, "operator": "Vodacom" },
  "telegram": { "ok": true, "bot_name": "CommsBot" },
  "whatsapp": { "ok": true, "session": "CONNECTED" }
}
```

---

### 4.2 ESP32 Firmware

**Framework:** Arduino (PlatformIO)  
**Libraries:** `TinyGSM`, `ArduinoJson`, `ESPAsyncWebServer` (or `WebServer`)

#### Features

- HTTP server on port 80, LAN-only
- IP whitelist — accepts requests only from the bridge LXC IP
- AT command driver via TinyGSM (abstracts modem differences)
- SMS send via `AT+CMGS`
- Status endpoint: signal strength, operator, registration state
- Watchdog timer — reboots if modem becomes unresponsive
- Static IP via WiFi config (or DHCP reservation)

#### Firmware endpoint

```
POST /send/sms
Content-Type: application/json

{ "to": "+27821234567", "message": "Test" }
```

```
GET /status

{ "signal": -73, "operator": "Vodacom ZA", "registered": true, "uptime": 3600 }
```

#### Board config header

```cpp
// config/board.h — only file that changes between hardware variants

#define BOARD_LILYGO_A7670G_S3_STANDARD   // ← active board

// ── LILYGO T-A7670G-S3-Standard (confirmed, ordered) ──────────────
#ifdef BOARD_LILYGO_A7670G_S3_STANDARD
  #define MODEM_TX              4
  #define MODEM_RX              5
  #define MODEM_DTR             7
  #define MODEM_RING            6
  #define MODEM_PWRKEY         46
  #define MODEM_POWER_SAVE     42
  #define MODEM_RST            -1   // not broken out on Standard
  #define GPS_RX               48   // separate GPS UART (NMEA)
  #define GPS_TX               45
  #define GPS_PPS              17
  #define GPS_ENABLE            1   // drive HIGH to enable GPS
  #define BOARD_BAT_ADC         8
  #define BOARD_SOLAR_ADC      18
  #define BOARD_SDA             3
  #define BOARD_SCL             2
  #define TINY_GSM_MODEM_A7670
#endif

// ── WVS ESP32-S3-A7670E (Communica, if/when acquired) ─────────────
#ifdef BOARD_WAVESHARE_A7670E_S3
  #define MODEM_TX             17
  #define MODEM_RX             18
  #define MODEM_DTR            -1
  #define MODEM_RING           -1
  #define MODEM_PWRKEY          5
  #define MODEM_RST            -1
  #define GPS_RX               -1   // GPS via AT commands on modem UART
  #define BOARD_BAT_ADC        -1
  #define BOARD_SOLAR_ADC      -1
  #define TINY_GSM_MODEM_A7670
#endif
```

---

### 4.3 WhatsApp Bridge — WAHA

**What:** WAHA (WhatsApp HTTP API) — open source, self-hosted, Docker-based.  
**Why not Baileys/whatsapp-web.js directly:** WAHA wraps both and exposes a stable REST API, survives session drops, and is actively maintained. No need to write session management code ourselves.

**Deployment:** Docker container on the Proxmox host, or inside the same LXC as the bridge if the LXC has Docker installed.

```
docker run -d \
  --name waha \
  --restart unless-stopped \
  -p 127.0.0.1:3000:3000 \
  -v /opt/waha/sessions:/app/.sessions \
  -e WHATSAPP_API_KEY=<secret> \
  devlikeapro/waha:latest
```

Key points:
- Bound to `127.0.0.1:3000` only — not exposed on the LAN
- Session persists across restarts via volume mount
- First run: scan QR code once via `http://localhost:3000/dashboard`
- The phone that scans must remain connected to WhatsApp — use a dedicated number/account
- Free core tier supports one session, which is all we need

**WAHA send call (made by bridge):**

```
POST http://127.0.0.1:3000/api/sendText
X-Api-Key: <secret>

{
  "chatId": "27821234567@c.us",
  "text": "Your alarm triggered",
  "session": "default"
}
```

---

### 4.4 Telegram Bot

No bridge needed. The bot sends messages directly to the Telegram Bot API via HTTPS.

**Setup:**
1. Create bot via @BotFather → get `BOT_TOKEN`
2. Start a conversation with the bot → get your `CHAT_ID` (via `api.telegram.org/bot<token>/getUpdates`)
3. Store both in `.env`

The bridge's `channels/telegram.py` uses `python-telegram-bot` (async) to call `bot.send_message(chat_id, text)`.

Group chats, channels, and individual chats are all supported — just change the `chat_id`.

---

## 5. Home Assistant Integration

Add to `configuration.yaml` (or a split `rest_commands.yaml`):

```yaml
rest_command:
  comms_send_sms:
    url: "https://192.168.1.Y:8080/api/v1/send"
    method: POST
    headers:
      X-API-Key: !secret commsgateway_api_key
      Content-Type: application/json
    payload: >
      {"channel": "sms", "to": "{{ to }}", "message": "{{ message }}"}

  comms_send_telegram:
    url: "https://192.168.1.Y:8080/api/v1/send"
    method: POST
    headers:
      X-API-Key: !secret commsgateway_api_key
      Content-Type: application/json
    payload: >
      {"channel": "telegram", "message": "{{ message }}"}

  comms_send_whatsapp:
    url: "https://192.168.1.Y:8080/api/v1/send"
    method: POST
    headers:
      X-API-Key: !secret commsgateway_api_key
      Content-Type: application/json
    payload: >
      {"channel": "whatsapp", "to": "{{ to }}", "message": "{{ message }}"}
```

`secrets.yaml`:

```yaml
commsgateway_api_key: <your 32-byte hex key>
```

Example automation:

```yaml
automation:
  - alias: "Alert - Front door after midnight"
    trigger:
      - platform: state
        entity_id: binary_sensor.front_door
        to: "on"
    condition:
      - condition: time
        after: "00:00:00"
        before: "06:00:00"
    action:
      - service: rest_command.comms_send_sms
        data:
          to: "+27821234567"
          message: "Front door opened at {{ now().strftime('%H:%M') }}"
      - service: rest_command.comms_send_whatsapp
        data:
          to: "+27821234567"
          message: "⚠ Front door opened at {{ now().strftime('%H:%M') }}"
```

---

## 6. Network & Deployment

### IP assignments (static / DHCP reservation)

| Device | IP | Notes |
|--------|----|-------|
| Home Assistant VM | 192.168.1.x | existing |
| Proxmox host | 192.168.1.x | existing |
| commsgateway-bridge LXC | 192.168.1.Y | new, DHCP reservation |
| ESP32 device | 192.168.1.Z | DHCP reservation by MAC |

### Proxmox LXC spec

```
CT ID:      <next available>
Hostname:   commsgateway-bridge
OS:         Ubuntu 24.04 LXC template
CPU:        1 core
RAM:        512 MB
Disk:       8 GB (for WAHA session data)
Network:    vmbr0, static or DHCP reservation
Features:   nesting=1 (required if running Docker inside LXC)
```

### Systemd unit — bridge service

```ini
# /etc/systemd/system/commsgateway.service
[Unit]
Description=CommsGateway Bridge API
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=comms
WorkingDirectory=/opt/commsgateway
EnvironmentFile=/opt/commsgateway/.env
ExecStart=/opt/commsgateway/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8080
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## 7. Security

| Concern | Mitigation |
|---------|-----------|
| Unauthenticated API calls | `X-API-Key` header required on every request |
| API key in HA config | Stored in `secrets.yaml`, not inline |
| WAHA exposed on LAN | Bound to `127.0.0.1` only, not reachable externally |
| ESP32 called by anyone | IP whitelist — only accepts from bridge LXC IP |
| SMS cost abuse | Rate limit: 30 requests/minute per API key |
| Secrets in code | All secrets via `.env`, `.env` in `.gitignore` |
| HTTPS for bridge | Self-signed cert via uvicorn, or nginx reverse proxy with Let's Encrypt |
| WhatsApp ToS | WAHA uses WhatsApp Web protocol — unofficial, same risk as WhatsApp Web on a browser. Use a dedicated number. |

---

## 8. Build Phases

### Phase 1 — ESP32 SMS (hardware arrives)
- [ ] Flash firmware to LILYGO T-SIM7600G-H
- [ ] Verify SIM, LTE registration, signal on Vodacom
- [ ] Test `POST /send/sms` from curl
- [ ] Set static IP / DHCP reservation

### Phase 2 — Proxmox bridge + Telegram
- [ ] Create Ubuntu 24.04 LXC on Proxmox
- [ ] Deploy FastAPI bridge service
- [ ] Configure Telegram bot, verify send
- [ ] Wire up SMS routing to ESP32 endpoint
- [ ] Add API key auth + rate limiter

### Phase 3 — WhatsApp via WAHA
- [ ] Install Docker in LXC (or on Proxmox host)
- [ ] Deploy WAHA container, scan QR, verify session
- [ ] Implement WhatsApp channel in bridge
- [ ] Test end-to-end from curl

### Phase 4 — Home Assistant integration
- [ ] Add `rest_command` entries
- [ ] Add `commsgateway_api_key` to `secrets.yaml`
- [ ] Test from HA developer tools
- [ ] Wire into existing alarm/alert automations

### Phase 5 — Hardware swap (optional, if Communica WVS A7670E restocks)
- [ ] Update `board.h` — flip `#define` to `BOARD_WAVESHARE_A7670E_S3`
- [ ] Verify Waveshare pinout from their schematic PDF (GPIO 17/18 assumed, confirm)
- [ ] Rebuild and flash
- [ ] Smoke test SMS — no other changes needed

---

## 9. Open Questions

| Question | Decision needed |
|----------|----------------|
| Which Proxmox node hosts the LXC? | Baobab cluster — which node has the most headroom? |
| WhatsApp number | Dedicated SIM for WA, or existing personal number? Dedicated is safer (won't get primary number banned) |
| Telegram chat ID | Personal chat, group, or channel? |
| HTTPS for bridge | Self-signed (HA can verify with `verify_ssl: false`) or nginx + Let's Encrypt? |
| SMS SIM provider | Vodacom/MTN PAYG — which has better data+SMS bundle for the board SIM? |

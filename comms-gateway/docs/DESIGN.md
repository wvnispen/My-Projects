# CommsGateway — Design Document

**Version:** 0.3  
**Date:** 2026-05-11  
**Author:** Wynand van Nispen  
**Status:** Bridge deployed — Telegram live ✓ | WhatsApp pending QR | SMS pending hardware

---

## 1. Overview

CommsGateway is a self-hosted, locally-run messaging gateway that replaces external services like CallmeBot. It allows Home Assistant (and any other internal system) to send **SMS, Telegram, and WhatsApp** messages via a single REST API, with no dependency on third-party relay services.

### Goals

- No external relay services — all message delivery is local or via official APIs
- Single API endpoint for Home Assistant, regardless of channel
- ESP32-based SMS hardware — low power, no server required for SMS
- WhatsApp via a local WAHA bridge (Docker) on the commsgateway VM
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

### Confirmed: LILYGO T-A7670G-S3-Standard (ordered, not yet arrived)

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
| Camera | OV2640 interface (Standard variant) — not used in v1 |
| Data rate | 10 Mbps down / 5 Mbps up (Cat-1 — sufficient for all messaging) |

### Confirmed GPIO pin map (from LilyGO-T-A76XX utilities.h, `LILYGO_A7670X_S3_STAN`)

| Function | GPIO | Notes |
|----------|------|-------|
| Modem TX (ESP→modem) | **4** | |
| Modem RX (modem→ESP) | **5** | |
| Modem DTR | 7 | |
| Modem RING | 6 | |
| Modem PWRKEY | **46** | pulse LOW to power on/off |
| Modem power-save | 42 | |
| Modem RST | — | not broken out on Standard variant |
| GPS RX (NMEA in) | **48** | separate UART — raw NMEA stream |
| GPS TX | 45 | |
| GPS PPS | 17 | |
| GPS enable | 1 | drive HIGH to enable |
| Audio PA enable | 3 | drive HIGH to enable speaker |
| Battery ADC | 8 | |
| Solar ADC | 18 | |
| I2C SDA | 3 | |
| I2C SCL | 2 | |
| SD MISO/MOSI/SCK/CS | 13/11/12/10 | |

> Note: GPS is on its **own UART** (GPIO 48/45), separate from the modem AT command UART (GPIO 4/5). Read GPS as a normal NMEA serial stream — no AT command interleaving.

### Board portability

All hardware-specific pin values live in `firmware/config/board.h`. Switching boards is a single `#define` change and rebuild — no other code changes needed.

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Home Assistant (192.168.x.x)                           │
│  rest_command.comms_send_sms / telegram / whatsapp      │
└───────────────────────┬─────────────────────────────────┘
                        │ HTTP POST /api/v1/send
                        │ X-API-Key: <secret>
                        ▼
┌─────────────────────────────────────────────────────────┐
│  commsgateway VM — Ubuntu 26.04                         │
│  192.168.8.18  |  nginx → uvicorn port 8080             │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  CommsGateway API  (Python FastAPI)              │   │
│  │  /opt/commsgateway/comms-gateway/bridge/         │   │
│  │  - X-API-Key auth middleware                     │   │
│  │  - Channel router                                │   │
│  └────────┬──────────────┬──────────────────────────┘   │
│           │              │                               │
│           ▼              ▼                               │
│  ┌─────────────┐  ┌─────────────────────────────────┐   │
│  │ WAHA        │  │  Telegram Bot API               │   │
│  │ (Docker)    │  │  api.telegram.org  ✓ live       │   │
│  │ :3000       │  │  Bot: @commsgateway_bot          │   │
│  │ session:    │  └─────────────────────────────────┘   │
│  │ STOPPED     │                                         │
│  │ (needs QR)  │                                         │
│  └─────────────┘                                         │
└─────────────────────────────────────────────────────────┘
                        │ HTTP POST /send/sms
                        │ (internal network only)
                        ▼
┌─────────────────────────────────────────────────────────┐
│  ESP32 Device  (IP TBD — DHCP reservation pending)      │
│  LILYGO T-A7670G-S3-Standard  ← not yet arrived        │
│                                                         │
│  ESP32 firmware → UART → A7670G modem → LTE cellular   │
└─────────────────────────────────────────────────────────┘
```

### Channel status

| Channel | Status | Notes |
|---------|--------|-------|
| Telegram | ✓ **Live** | @commsgateway_bot, chat_id 685138995 |
| WhatsApp | ⏳ Pending | WAHA running, QR scan needed — dedicated SIM + phone required |
| SMS | ⏳ Pending | Board not yet arrived |

### Fallback behaviour

| Failure | Response |
|---------|---------|
| ESP32 unreachable | `{"status":"error","reason":"esp32_unreachable"}` |
| WAHA session expired | `{"status":"error","reason":"..."}` |
| Telegram API unreachable | `{"status":"error","reason":"..."}` |

---

## 4. Component Specifications

### 4.1 CommsGateway Bridge (VM)

**Runtime:** Python 3.14, FastAPI, uvicorn
**Process manager:** systemd (`commsgateway.service`)
**Reverse proxy:** nginx on port 80
**VM:** Ubuntu 26.04, 192.168.8.18, hostname: commsgateway, user: netadmin

#### Actual directory layout on server

```
/opt/commsgateway/                    ← git clone of My-Projects repo
└── comms-gateway/
    └── bridge/                       ← uvicorn WorkingDirectory
        ├── main.py
        ├── config.py
        ├── requirements.txt
        ├── .env                      ← secrets, gitignored
        ├── venv/                     ← Python venv, gitignored
        ├── logs/gateway.log
        ├── routers/
        │   ├── send.py               ← POST /api/v1/send
        │   ├── health.py             ← GET /api/v1/health, /api/v1/status
        │   └── ui.py                 ← GET / → web test UI
        ├── channels/
        │   ├── sms.py                ← → ESP32 HTTP
        │   ├── telegram.py           ← → api.telegram.org
        │   └── whatsapp.py           ← → WAHA :3000
        ├── middleware/
        │   └── auth.py               ← X-API-Key validation
        └── static/
            └── index.html            ← web test UI
```

#### API endpoints

```
POST /api/v1/send        ← requires X-API-Key header
GET  /api/v1/health      ← no auth
GET  /api/v1/status      ← requires X-API-Key header
GET  /                   ← web test UI
```

**POST /api/v1/send**

```json
{ "channel": "sms | telegram | whatsapp", "to": "+27821234567", "message": "text" }
```
`to` is optional — falls back to the default configured per channel in `.env`.

#### Environment variables (.env)

```env
API_KEY=<auto-generated 32-byte hex>

ESP32_URL=http://<TBD>       # set when board arrives and gets DHCP reservation
ESP32_TIMEOUT=10

TELEGRAM_BOT_TOKEN=<configured>
TELEGRAM_DEFAULT_CHAT_ID=685138995

WAHA_URL=http://127.0.0.1:3000
WAHA_API_KEY=<auto-generated>
WAHA_SESSION=default
WAHA_DEFAULT_NUMBER=<TBD — dedicated WA number>

RATE_LIMIT_PER_MINUTE=30
```

#### Useful commands on server

```bash
sudo systemctl status commsgateway       # service status
sudo systemctl restart commsgateway      # restart after .env changes
sudo tail -f /opt/commsgateway/comms-gateway/bridge/logs/gateway.log
docker ps                                # WAHA container status
docker logs -f waha                      # WAHA logs
```

---

### 4.2 ESP32 Firmware

**Framework:** Arduino (PlatformIO)
**Libraries:** `TinyGSM`, `ArduinoJson`, `ESPAsyncWebServer`, `AsyncTCP`
**Status:** Not written yet — starts when board arrives

Firmware responsibilities:
1. PWRKEY pulse on GPIO 46 → power on modem
2. TinyGSM on Serial1 (GPIO 4/5) at 115200
3. Wait for network registration
4. Connect to WiFi
5. `POST /send/sms` → AT+CMGS → cellular
6. `GET /status` → signal, operator, uptime, battery ADC

Board config is in `firmware/config/board.h` — single `#define` controls all pin assignments.

---

### 4.3 WhatsApp — WAHA

**Container:** `devlikeapro/waha:latest`, running as Docker on commsgateway VM
**Status:** Container up, session STOPPED — QR scan pending

```
docker run -d --name waha --restart unless-stopped \
  -p 127.0.0.1:3000:3000 \
  -v /opt/waha/sessions:/app/.sessions \
  -e WHATSAPP_API_KEY=<key> \
  devlikeapro/waha:latest
```

To complete WhatsApp setup:
1. Get a dedicated SIM + old Android phone
2. Register WhatsApp on that number
3. SSH tunnel: `ssh -L 3000:127.0.0.1:3000 netadmin@192.168.8.18`
4. Open `http://localhost:3000/dashboard` → start session → scan QR
5. Session persists in `/opt/waha/sessions/` across restarts

---

### 4.4 Telegram Bot ✓

**Bot:** @commsgateway_bot
**Chat ID:** 685138995 (Wynand van Nispen — personal chat)
**Status:** Fully configured and tested — messages delivering

---

## 5. Home Assistant Integration

```yaml
# configuration.yaml
rest_command:
  comms_send_sms:
    url: "http://192.168.8.18/api/v1/send"
    method: POST
    headers:
      X-API-Key: !secret commsgateway_api_key
      Content-Type: application/json
    payload: '{"channel":"sms","to":"{{ to }}","message":"{{ message }}"}'

  comms_send_telegram:
    url: "http://192.168.8.18/api/v1/send"
    method: POST
    headers:
      X-API-Key: !secret commsgateway_api_key
      Content-Type: application/json
    payload: '{"channel":"telegram","message":"{{ message }}"}'

  comms_send_whatsapp:
    url: "http://192.168.8.18/api/v1/send"
    method: POST
    headers:
      X-API-Key: !secret commsgateway_api_key
      Content-Type: application/json
    payload: '{"channel":"whatsapp","to":"{{ to }}","message":"{{ message }}"}'
```

```yaml
# secrets.yaml
commsgateway_api_key: <from /opt/commsgateway/comms-gateway/bridge/.env>
```

---

## 6. Network & Infrastructure

| Device | Hostname | IP | User | Notes |
|--------|----------|----|------|-------|
| Dev PC | castelvania | 192.168.8.11 | devadmin | Claude Code runs here |
| CommsGateway VM | commsgateway | 192.168.8.18 | netadmin | Ubuntu 26.04 VM |
| ESP32 board | — | TBD | — | DHCP reservation when board arrives |

### SSH access

```bash
# From castelvania (already configured in ~/.ssh/config)
ssh commsgateway        # → netadmin@192.168.8.18

# WAHA dashboard tunnel
ssh -L 3000:127.0.0.1:3000 commsgateway
# then open http://localhost:3000/dashboard
```

### Code repository

**Repo:** `github.com/wvnispen/My-Projects`
**Path:** `comms-gateway/` subdirectory
**Clone on server:** `/opt/commsgateway/` (full repo clone)

**Update deployed code:**
```bash
sudo bash /opt/commsgateway/comms-gateway/bridge/deploy.sh --update
```

---

## 7. Security

| Concern | Mitigation |
|---------|-----------|
| Unauthenticated API calls | `X-API-Key` header required on every request |
| API key in HA config | Stored in `secrets.yaml`, not inline |
| WAHA exposed on LAN | Bound to `127.0.0.1:3000` only |
| ESP32 open to LAN | IP whitelist — bridge IP only (when firmware written) |
| SMS cost abuse | Rate limit: 30 requests/minute |
| Secrets in git | `.env` and `secrets.h` in `.gitignore` — never committed |
| WhatsApp ToS | WAHA uses WA Web protocol — use a dedicated number |

---

## 8. Build Phases

### Phase 1 — Bridge + Telegram ✓ Complete
- [x] Ubuntu 26.04 VM deployed on Proxmox (192.168.8.18)
- [x] FastAPI bridge deployed via deploy.sh
- [x] WAHA Docker container running
- [x] Telegram bot created (@commsgateway_bot)
- [x] Telegram tested end-to-end ✓
- [x] Web UI live at http://192.168.8.18/
- [x] Code pushed to github.com/wvnispen/My-Projects

### Phase 2 — WhatsApp ⏳ In progress
- [ ] Get dedicated SIM + old Android phone
- [ ] Register WhatsApp on dedicated number
- [ ] SSH tunnel to WAHA dashboard, scan QR
- [ ] Test WhatsApp send via web UI
- [ ] Add `WAHA_DEFAULT_NUMBER` to `.env`

### Phase 3 — ESP32 SMS ⏳ Awaiting hardware
- [ ] Board arrives (LILYGO T-A7670G-S3-Standard)
- [ ] Insert SIM, run AT smoke test
- [ ] Write `firmware/src/main.cpp`
- [ ] Flash and verify SMS send
- [ ] Set DHCP reservation, update `ESP32_URL` in `.env`

### Phase 4 — Home Assistant integration
- [ ] Add `rest_command` entries (IPs now confirmed — see Section 5)
- [ ] Add API key to `secrets.yaml`
- [ ] Test from HA developer tools
- [ ] Wire into alarm/alert automations

### Phase 5 — Hardware swap (optional)
- [ ] If WVS A7670E restocks at Communica (R1,090)
- [ ] Flip `#define` in `board.h`, rebuild, flash
- [ ] No other changes needed

---

## 9. Open Items

| Item | Status |
|------|--------|
| WhatsApp dedicated SIM + phone | ⏳ Pending |
| `WAHA_DEFAULT_NUMBER` in .env | ⏳ Set after WA setup |
| ESP32 board delivery | ⏳ Ordered |
| ESP32 DHCP reservation + `ESP32_URL` | ⏳ Set when board arrives |
| HA `rest_command` config | ⏳ Ready to add (IP confirmed: 192.168.8.18) |

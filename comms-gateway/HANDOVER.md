# CommsGateway — Handover Doc

**Last updated:** 2026-05-11  
**Status:** Hardware ordered — awaiting delivery, then start firmware  
**Full design doc:** `docs/DESIGN.md`

---

## What we're building

A self-hosted messaging gateway for Home Assistant.  
Single REST API → routes to **SMS**, **Telegram**, or **WhatsApp**.  
No CallmeBot, no external relay services.

```
Home Assistant
      │  POST /api/v1/send  +  X-API-Key header
      ▼
Proxmox LXC — FastAPI bridge  (192.168.1.Y : 8080)
      │
      ├── SMS       → HTTP → ESP32 → AT commands → A7670G → cellular
      ├── Telegram  → python-telegram-bot → api.telegram.org (official API)
      └── WhatsApp  → WAHA (local Docker) → WhatsApp Web protocol
```

---

## Hardware — confirmed

**Board ordered:** LILYGO T-A7670G-S3-Standard

| Spec | Value |
|------|-------|
| MCU | ESP32-S3, dual-core LX7 @ 240 MHz |
| Modem | A7670G — LTE Cat-1, **Global bands** |
| Band 28 (700 MHz) | ✓ Confirmed — Vodacom / MTN / Cell C all covered |
| GPS | Separate UART — raw NMEA, independent of modem |
| Battery | 18650 holder + solar charge input |
| Camera | OV2640 interface (Standard variant) — not used in v1 |
| WiFi | 802.11 b/g/n |
| Bluetooth | 5.0 LE |

### Exact GPIO pin map

> Source: `LilyGO-T-A76XX/examples/ATdebug/utilities.h`, define `LILYGO_A7670X_S3_STAN`

| Signal | GPIO | Notes |
|--------|------|-------|
| Modem TX (ESP→modem) | **4** | |
| Modem RX (modem→ESP) | **5** | |
| Modem DTR | 7 | |
| Modem RING | 6 | |
| Modem PWRKEY | **46** | pulse LOW to power on/off |
| Modem power-save | 42 | |
| Modem RST | — | not broken out on Standard |
| GPS RX (NMEA in) | **48** | separate UART, not AT commands |
| GPS TX | 45 | |
| GPS PPS | 17 | |
| GPS enable | 1 | drive HIGH to enable |
| Audio PA enable | 3 | drive HIGH to enable speaker |
| Battery ADC | 8 | read voltage |
| Solar ADC | 18 | read solar input |
| I2C SDA | 3 | shared with GPS enable — check if conflict |
| I2C SCL | 2 | |
| SD MISO/MOSI/SCK/CS | 13/11/12/10 | |

### platformio.ini target

```ini
platform  = espressif32
board     = esp32-s3-devkitc-1
framework = arduino
board_build.mcu        = esp32s3
board_build.flash_mode = qio
board_build.psram_type = opi
build_flags = -DBOARD_LILYGO_A7670G_S3_STANDARD -DARDUINO_USB_CDC_ON_BOOT=1
```

### Libraries needed

```
vshymanskyy/TinyGSM          ^0.11.7
bblanchon/ArduinoJson        ^7.0.0
me-no-dev/ESPAsyncWebServer  ^1.2.3
me-no-dev/AsyncTCP           ^1.1.1
```

---

## Files already created

```
CommsGateway/
├── HANDOVER.md                  ← this file
├── docs/
│   └── DESIGN.md                ← full architecture, API spec, security, phases
└── firmware/
    ├── platformio.ini           ← ESP32-S3 build config, lib deps
    └── config/
        └── board.h              ← all GPIO defines for both board variants
```

Nothing else exists yet — all code writing starts when hardware arrives.

---

## What to do the moment the board arrives

### Step 1 — First boot test (no code needed)
1. Insert SIM card (Vodacom or MTN PAYG)
2. Attach LTE antenna to modem port, GPS antenna to GPS port
3. Connect USB-C to PC
4. Open serial monitor at 115200 baud
5. Board should enumerate as USB-CDC (`/dev/ttyACM0` on Linux)
6. Verify the board boots — LED behaviour on GPIO 12 (LED_ON = LOW)

### Step 2 — AT command smoke test
Open a serial terminal to `/dev/ttyACM0`:
```
AT              → should reply OK
AT+CPIN?        → should reply +CPIN: READY  (SIM detected)
AT+CREG?        → should reply +CREG: 0,1 or 0,5  (registered on network)
AT+COPS?        → should show operator name (e.g. Vodacom, MTN)
AT+CSQ          → signal quality, e.g. +CSQ: 18,0  (anything >10 is usable)
AT+CMGF=1       → set SMS text mode, should reply OK
```
If `AT+CPIN?` returns `+CPIN: SIM not inserted` — reseat SIM card.

### Step 3 — Send a test SMS manually via AT
```
AT+CMGF=1
AT+CMGS="+27821234567"
> Hello from CommsGateway
<Ctrl+Z>        → sends the message
```
If this works, the hardware stack is good. Start firmware coding.

### Step 4 — Flash firmware (Phase 1 goal)
- Clone/open the `firmware/` folder in PlatformIO (VS Code extension)
- The `firmware/src/main.cpp` is what gets written next session
- Build target: `lilygo-a7670g-s3-standard`
- Upload via USB-C

---

## Firmware to write (Phase 1)

`firmware/src/main.cpp` — does not exist yet. When writing it:

```
main.cpp responsibilities:
  1. Power on modem (PWRKEY pulse on GPIO 46)
  2. Init TinyGSM on Serial1 (GPIO 4/5) at 115200
  3. Wait for network registration
  4. Connect to WiFi (credentials from config)
  5. Start AsyncWebServer on port 80
  6. POST /send/sms  → send SMS via TinyGSM
  7. GET  /status    → return signal, operator, uptime, battery voltage
  8. IP whitelist middleware — only accept from bridge LXC IP
```

Key TinyGSM pattern for A7670G:
```cpp
#define TINY_GSM_MODEM_A7670
#include <TinyGsmClient.h>

HardwareSerial modemSerial(1);
TinyGsm modem(modemSerial);

// in setup():
modemSerial.begin(115200, SERIAL_8N1, MODEM_RX, MODEM_TX);
// pulse PWRKEY to wake modem
pinMode(MODEM_PWRKEY, OUTPUT);
digitalWrite(MODEM_PWRKEY, LOW);
delay(1000);
digitalWrite(MODEM_PWRKEY, HIGH);
delay(2000);
// wait for modem to respond
modem.restart();
modem.waitForNetwork();
```

WiFi credentials and bridge IP go in `config/secrets.h` (gitignored).

---

## Proxmox bridge — to set up in parallel (doesn't need hardware)

Can be done now while waiting for board:

1. **Create LXC** on Proxmox (Ubuntu 24.04, 1 CPU, 512MB RAM, 8GB disk, nesting=1)
2. **Install:** `python3.12`, `python3-venv`, `docker.io`
3. **Clone gateway code** to `/opt/commsgateway/`
4. **Deploy WAHA:**
   ```bash
   docker run -d --name waha --restart unless-stopped \
     -p 127.0.0.1:3000:3000 \
     -v /opt/waha/sessions:/app/.sessions \
     -e WHATSAPP_API_KEY=<secret> \
     devlikeapro/waha:latest
   ```
5. **Create Telegram bot** via @BotFather → get token → send a message to the bot → get your chat_id
6. **Write `.env`** with all secrets (see `docs/DESIGN.md` section 4.1)
7. **Write FastAPI bridge** — `main.py`, `channels/sms.py`, `channels/telegram.py`, `channels/whatsapp.py`

The bridge can be written and tested (Telegram + WhatsApp) before the ESP32 arrives. Just mock the SMS channel with a stub that logs the call.

---

## Open questions — answer before coding starts

| Question | Why it matters |
|----------|---------------|
| Which Proxmox node hosts the LXC? | Need node name/IP to set up bridge |
| Which SIM goes in the board? | Vodacom or MTN PAYG — affects APN setting in firmware (`web.vodacom.net` vs `internet`) |
| Dedicated WhatsApp number? | Strongly recommended — scanning with your personal number risks a ban. A cheap Telkom/Cell C PAYG SIM works |
| Telegram: personal chat or group? | Determines the `chat_id` value |
| Bridge LXC IP? | Needs to be static / DHCP reservation so ESP32 whitelist doesn't break on reboot |
| HA IP? | Needs to call the bridge — confirm it can reach 192.168.1.Y:8080 |

### APN settings by SA carrier

| Carrier | APN |
|---------|-----|
| Vodacom | `web.vodacom.net` |
| MTN | `internet` |
| Cell C | `internet` |
| Telkom | `lte.telkom.co.za` |

These go in `config/secrets.h` as `MODEM_APN`.

---

## Reference links

| Resource | URL |
|----------|-----|
| LilyGO-T-A76XX GitHub | https://github.com/Xinyuan-LilyGO/LilyGO-T-A76XX |
| Pin definitions (source of truth) | `LilyGO-T-A76XX/examples/ATdebug/utilities.h` |
| TinyGSM library | https://github.com/vshymanskyy/TinyGSM |
| WAHA WhatsApp bridge | https://waha.devlike.pro |
| Telegram Bot API | https://core.telegram.org/bots/api |
| Waveshare A7670E HAT (future DIY option) | https://www.robotics.org.za/W20049 |

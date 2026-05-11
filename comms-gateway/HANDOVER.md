# CommsGateway — Handover Doc

**Last updated:** 2026-05-11 (v0.4)
**Full design doc:** `docs/DESIGN.md`

---

## Current state

| Component | Status | Detail |
|-----------|--------|--------|
| Bridge VM | ✓ Running | Ubuntu 26.04, 192.168.8.18 |
| FastAPI service | ✓ Running | systemd, auto-restart |
| nginx | ✓ Running | port 80 → uvicorn :8080 |
| WAHA (WhatsApp) | ✓ Container up | Session STOPPED — needs QR scan |
| Telegram | ✓ **Live** | @commsgateway_bot, tested |
| WhatsApp | ⏳ Pending | Need dedicated SIM + phone |
| SMS / ESP32 | ⏳ Pending | Board ordered, not arrived |
| Web UI | ✓ Live | http://192.168.8.18/ — auto-loads API key |

---

## Infrastructure

| Machine | IP | User | SSH alias |
|---------|----|------|-----------|
| Dev PC (castelvania) | 192.168.8.11 | devadmin | — |
| CommsGateway VM | 192.168.8.18 | netadmin | `ssh commsgateway` |

**SSH config on castelvania** (`~/.ssh/config`):
```
Host commsgateway
    HostName 192.168.8.18
    User netadmin
    IdentityFile ~/.ssh/id_ed25519
```

**netadmin** has passwordless sudo and is in the docker group.

---

## Code

**Repo:** `github.com/wvnispen/My-Projects` — `comms-gateway/` subdirectory
**Clone on server:** `/opt/commsgateway/` (full repo)
**App root:** `/opt/commsgateway/comms-gateway/bridge/`

```
comms-gateway/
├── HANDOVER.md              ← this file
├── docs/DESIGN.md           ← full architecture reference
├── bridge/                  ← FastAPI app
│   ├── deploy.sh            ← deployment + update script
│   ├── .env.example         ← template (no inline comments)
│   ├── main.py
│   ├── config.py
│   ├── requirements.txt
│   ├── routers/             ← send, health, ui
│   ├── channels/            ← sms, telegram, whatsapp
│   ├── middleware/           ← auth
│   └── static/index.html    ← web test UI
└── firmware/
    ├── platformio.ini        ← ESP32-S3 build config
    └── config/board.h        ← all GPIO defines
```

**Deploy first time:**
```bash
# tarball method (no git auth needed)
scp comms-gateway.tar.gz netadmin@192.168.8.18:~
tar -xzf comms-gateway.tar.gz
sudo bash comms-gateway/bridge/deploy.sh
```

**Update after git push:**
```bash
ssh commsgateway 'sudo bash /opt/commsgateway/comms-gateway/bridge/deploy.sh --update'
```

---

## Telegram — configured ✓

- **Bot:** @commsgateway_bot
- **Token:** in `/opt/commsgateway/comms-gateway/bridge/.env`
- **Default chat ID:** 685138995 (Wynand van Nispen — Telegram username @NosferatuZA)
- **Test:**
  ```bash
  ssh commsgateway '
  KEY=$(sudo grep "^API_KEY=" /opt/commsgateway/comms-gateway/bridge/.env | cut -d= -f2)
  curl -s -X POST http://localhost/api/v1/send \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $KEY" \
    -d "{\"channel\":\"telegram\",\"message\":\"test\"}"'
  ```

**Sending to other people:**
- They must message @commsgateway_bot first
- Use their **numeric chat ID** (not @username — that only works for public channels)
- Find their ID via: `https://api.telegram.org/bot<TOKEN>/getUpdates`

---

## WhatsApp — next step

1. Get a dedicated SIM + old Android phone
2. Register WhatsApp on that number
3. Open SSH tunnel from your PC:
   ```bash
   ssh -L 3000:127.0.0.1:3000 commsgateway
   ```
4. Open `http://localhost:3000/dashboard` in browser
5. Click **Start session** → scan QR with the dedicated phone
6. Add the number to `.env` and restart:
   ```bash
   ssh commsgateway 'sudo sed -i "s|^WAHA_DEFAULT_NUMBER=.*|WAHA_DEFAULT_NUMBER=27821234567|" \
     /opt/commsgateway/comms-gateway/bridge/.env && sudo systemctl restart commsgateway'
   ```

---

## ESP32 — when board arrives

**Board:** LILYGO T-A7670G-S3-Standard

### Step 1 — AT smoke test (before flashing anything)
```
# Connect USB-C, open serial monitor at 115200 (/dev/ttyACM0)
AT              → OK
AT+CPIN?        → +CPIN: READY
AT+CREG?        → +CREG: 0,1
AT+COPS?        → operator name
AT+CSQ          → signal (>10 = usable)
AT+CMGF=1       → OK
AT+CMGS="+27821234567"
> Hello
<Ctrl+Z>        → sends SMS
```

### Step 2 — Flash firmware
- Open `firmware/` in PlatformIO (VS Code)
- Write `firmware/src/main.cpp` (does not exist yet — start fresh session)
- Board target: `lilygo-a7670g-s3-standard`
- Key pin defines are already in `firmware/config/board.h`

### Step 3 — Wire up to bridge
```bash
# On commsgateway VM, after board has DHCP reservation
sudo sed -i 's|^ESP32_URL=.*|ESP32_URL=http://192.168.x.x|' \
  /opt/commsgateway/comms-gateway/bridge/.env
sudo systemctl restart commsgateway
```

### Key GPIO pins (from LilyGO utilities.h — LILYGO_A7670X_S3_STAN)

| Signal | GPIO |
|--------|------|
| Modem TX | 4 |
| Modem RX | 5 |
| PWRKEY | 46 |
| GPS RX (NMEA) | 48 |
| GPS enable | 1 |
| Battery ADC | 8 |

### APN by carrier

| Carrier | APN |
|---------|-----|
| Vodacom | `web.vodacom.net` |
| MTN | `internet` |
| Cell C | `internet` |
| Telkom | `lte.telkom.co.za` |

---

## Home Assistant integration (ready to add)

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

Get the API key:
```bash
ssh commsgateway 'sudo grep "^API_KEY=" /opt/commsgateway/comms-gateway/bridge/.env'
```

---

## Useful server commands

```bash
# Service
sudo systemctl status commsgateway
sudo systemctl restart commsgateway
sudo tail -f /opt/commsgateway/comms-gateway/bridge/logs/gateway.log

# WAHA
docker ps
docker logs -f waha
docker restart waha

# Update from git
sudo bash /opt/commsgateway/comms-gateway/bridge/deploy.sh --update
```

---

## Reference

| Resource | Link |
|----------|------|
| Repo | github.com/wvnispen/My-Projects |
| LilyGO board GitHub | github.com/Xinyuan-LilyGO/LilyGO-T-A76XX |
| TinyGSM | github.com/vshymanskyy/TinyGSM |
| WAHA docs | waha.devlike.pro |
| Telegram Bot API | core.telegram.org/bots/api |
| Web UI | http://192.168.8.18/ |
| API docs | http://192.168.8.18/api/docs |

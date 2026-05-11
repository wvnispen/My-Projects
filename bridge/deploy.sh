#!/usr/bin/env bash
# CommsGateway — Deployment Script
# Targets: Ubuntu 24.04 LTS / Ubuntu 26.04 LTS (VM or bare metal)
# Run as root: sudo bash deploy.sh

set -euo pipefail

# ── Colours ────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Config ─────────────────────────────────────────────────────────────────
APP_USER="commsgateway"
APP_DIR="/opt/commsgateway"
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="commsgateway"
WAHA_DIR="/opt/waha"
WAHA_PORT="3000"
APP_PORT="8080"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Preflight ──────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && die "Run as root: sudo bash deploy.sh"

echo -e "\n${BOLD}═══════════════════════════════════════════════${NC}"
echo -e "${BOLD}  CommsGateway — Deployment${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════${NC}\n"

# ── 1. System packages ─────────────────────────────────────────────────────
info "Updating package lists..."
apt-get update -qq

info "Installing system dependencies..."
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    nginx curl git openssl \
    ca-certificates gnupg lsb-release

success "System packages installed"

# ── 2. Docker ──────────────────────────────────────────────────────────────
if command -v docker &>/dev/null; then
    success "Docker already installed ($(docker --version | cut -d' ' -f3 | tr -d ','))"
else
    info "Installing Docker..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable --now docker
    success "Docker installed"
fi

# ── 3. App user ────────────────────────────────────────────────────────────
if id "$APP_USER" &>/dev/null; then
    success "User '$APP_USER' already exists"
else
    info "Creating user '$APP_USER'..."
    useradd -r -s /bin/bash -d "$APP_DIR" -m "$APP_USER"
    usermod -aG docker "$APP_USER"
    success "User '$APP_USER' created"
fi

# ── 4. App directory ───────────────────────────────────────────────────────
info "Setting up $APP_DIR..."
mkdir -p "$APP_DIR"/{routers,channels,middleware,static,logs}

# Copy application files from repo
cp -r "$SCRIPT_DIR"/{main.py,config.py,requirements.txt} "$APP_DIR/"
cp -r "$SCRIPT_DIR"/routers/*.py "$APP_DIR/routers/"
cp -r "$SCRIPT_DIR"/channels/*.py "$APP_DIR/channels/"
cp -r "$SCRIPT_DIR"/middleware/*.py "$APP_DIR/middleware/"
cp -r "$SCRIPT_DIR"/static/* "$APP_DIR/static/"
touch "$APP_DIR"/routers/__init__.py \
      "$APP_DIR"/channels/__init__.py \
      "$APP_DIR"/middleware/__init__.py

chown -R "$APP_USER:$APP_USER" "$APP_DIR"
success "Application files copied"

# ── 5. Python venv ─────────────────────────────────────────────────────────
info "Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
chown -R "$APP_USER:$APP_USER" "$VENV_DIR"
success "Python venv ready"

# ── 6. .env file ───────────────────────────────────────────────────────────
if [[ -f "$APP_DIR/.env" ]]; then
    warn ".env already exists — skipping (edit manually if needed)"
else
    info "Generating .env from template..."
    GENERATED_API_KEY=$(openssl rand -hex 32)
    GENERATED_WAHA_KEY=$(openssl rand -hex 16)
    sed \
        -e "s|CHANGE_ME_API_KEY|$GENERATED_API_KEY|g" \
        -e "s|CHANGE_ME_WAHA_KEY|$GENERATED_WAHA_KEY|g" \
        "$SCRIPT_DIR/.env.example" > "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
    success ".env created with generated keys"
    echo -e "  ${YELLOW}API Key:  ${BOLD}$GENERATED_API_KEY${NC}"
    echo -e "  ${YELLOW}WAHA Key: ${BOLD}$GENERATED_WAHA_KEY${NC}"
    echo -e "  ${YELLOW}→ Save these! Edit $APP_DIR/.env to add remaining config.${NC}\n"
fi

# ── 7. WAHA (WhatsApp bridge) ──────────────────────────────────────────────
WAHA_KEY=$(grep WAHA_API_KEY "$APP_DIR/.env" | cut -d= -f2 | tr -d '"')

info "Deploying WAHA WhatsApp bridge..."
mkdir -p "$WAHA_DIR/sessions"
chown -R "$APP_USER:$APP_USER" "$WAHA_DIR"

if docker ps -a --format '{{.Names}}' | grep -q "^waha$"; then
    warn "WAHA container already exists — skipping (use 'docker restart waha' to restart)"
else
    docker run -d \
        --name waha \
        --restart unless-stopped \
        -p "127.0.0.1:${WAHA_PORT}:3000" \
        -v "${WAHA_DIR}/sessions:/app/.sessions" \
        -e "WHATSAPP_API_KEY=${WAHA_KEY}" \
        -e "WHATSAPP_HOOK_EVENTS=message" \
        devlikeapro/waha:latest
    success "WAHA container started"
fi

# ── 8. systemd service ─────────────────────────────────────────────────────
info "Installing systemd service..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=CommsGateway Bridge API
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${VENV_DIR}/bin/uvicorn main:app --host 127.0.0.1 --port ${APP_PORT} --log-level info
Restart=on-failure
RestartSec=5
StandardOutput=append:${APP_DIR}/logs/gateway.log
StandardError=append:${APP_DIR}/logs/gateway.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
success "systemd service installed and started"

# ── 9. nginx ──────────────────────────────────────────────────────────────
info "Configuring nginx reverse proxy..."
cat > "/etc/nginx/sites-available/commsgateway" <<'EOF'
server {
    listen 80;
    server_name _;

    # Web UI — no auth (internal network only)
    location / {
        proxy_pass         http://127.0.0.1:8080;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
    }

    # API — proxied through (auth is handled by the app)
    location /api/ {
        proxy_pass         http://127.0.0.1:8080;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_read_timeout 30s;
    }
}
EOF

ln -sf /etc/nginx/sites-available/commsgateway /etc/nginx/sites-enabled/commsgateway
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
success "nginx configured"

# ── 10. Firewall ───────────────────────────────────────────────────────────
if command -v ufw &>/dev/null; then
    info "Configuring UFW firewall..."
    ufw allow ssh    >/dev/null
    ufw allow 80/tcp >/dev/null
    ufw --force enable >/dev/null
    success "UFW: ports 22 and 80 open"
fi

# ── Done ───────────────────────────────────────────────────────────────────
VM_IP=$(hostname -I | awk '{print $1}')
echo -e "\n${BOLD}${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN}  Deployment complete!${NC}"
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════${NC}\n"
echo -e "  Web UI:    ${BOLD}http://${VM_IP}/${NC}"
echo -e "  API:       ${BOLD}http://${VM_IP}/api/v1/send${NC}"
echo -e "  Status:    ${BOLD}http://${VM_IP}/api/v1/status${NC}"
echo -e "  WAHA:      ${BOLD}http://127.0.0.1:${WAHA_PORT}/dashboard${NC}  (SSH tunnel to access)\n"
echo -e "${YELLOW}Next steps:${NC}"
echo -e "  1. Edit ${BOLD}${APP_DIR}/.env${NC} — add Telegram token, ESP32 IP, WhatsApp number"
echo -e "  2. Restart service: ${BOLD}systemctl restart ${SERVICE_NAME}${NC}"
echo -e "  3. SSH tunnel for WAHA QR scan:"
echo -e "     ${BOLD}ssh -L 3000:127.0.0.1:3000 user@${VM_IP}${NC}"
echo -e "     Then open: http://localhost:3000/dashboard"
echo -e "  4. Scan QR code with WhatsApp on the dedicated phone"
echo -e "  5. Open the web UI and send a test message\n"
echo -e "  Logs: ${BOLD}tail -f ${APP_DIR}/logs/gateway.log${NC}"
echo -e "  WAHA logs: ${BOLD}docker logs -f waha${NC}\n"

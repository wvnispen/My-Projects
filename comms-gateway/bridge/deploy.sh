#!/usr/bin/env bash
# CommsGateway — Deployment Script
# Targets: Ubuntu 24.04 LTS / Ubuntu 26.04 LTS (VM or bare metal)
#
# First deploy:  sudo bash deploy.sh
# Update only:   sudo bash deploy.sh --update

set -euo pipefail

# ── Colours ────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Config — edit REPO_URL before running ──────────────────────────────────
REPO_URL="https://github.com/wvnispen/My-Projects.git"
REPO_BRANCH="main"
REPO_DIR="/opt/commsgateway"          # full git clone lives here
APP_DIR="$REPO_DIR/comms-gateway/bridge"   # uvicorn runs from here
VENV_DIR="$APP_DIR/venv"
APP_USER="commsgateway"
SERVICE_NAME="commsgateway"
WAHA_DIR="/opt/waha"
WAHA_PORT="3000"
APP_PORT="8080"

# ── Flags ──────────────────────────────────────────────────────────────────
UPDATE_ONLY=false
[[ "${1:-}" == "--update" ]] && UPDATE_ONLY=true

# ── Preflight ──────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && die "Run as root: sudo bash deploy.sh"

echo -e "\n${BOLD}═══════════════════════════════════════════════${NC}"
if $UPDATE_ONLY; then
  echo -e "${BOLD}  CommsGateway — Update${NC}"
else
  echo -e "${BOLD}  CommsGateway — First Deployment${NC}"
fi
echo -e "${BOLD}═══════════════════════════════════════════════${NC}\n"

# ══════════════════════════════════════════════════════════════════════════
# UPDATE PATH — git pull + pip sync + restart
# ══════════════════════════════════════════════════════════════════════════
if $UPDATE_ONLY; then
    [[ ! -d "$REPO_DIR/.git" ]] && die "Repo not found at $REPO_DIR — run deploy.sh without --update first"

    info "Pulling latest from $REPO_BRANCH..."
    git -C "$REPO_DIR" fetch origin
    git -C "$REPO_DIR" reset --hard "origin/$REPO_BRANCH"
    chown -R "$APP_USER:$APP_USER" "$REPO_DIR"
    success "Repo updated ($(git -C "$REPO_DIR" log -1 --format='%h %s'))"

    info "Syncing Python dependencies..."
    "$VENV_DIR/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
    success "Dependencies synced"

    info "Restarting service..."
    systemctl restart "$SERVICE_NAME"
    success "Service restarted"

    echo -e "\n${GREEN}Update complete.${NC}"
    echo -e "  Logs: ${BOLD}journalctl -u $SERVICE_NAME -f${NC}\n"
    exit 0
fi

# ══════════════════════════════════════════════════════════════════════════
# FULL DEPLOYMENT
# ══════════════════════════════════════════════════════════════════════════

# ── 1. System packages ─────────────────────────────────────────────────────
info "Updating package lists..."
apt-get update -qq

info "Installing system dependencies..."
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    nginx curl git openssl \
    ca-certificates gnupg lsb-release

success "System packages installed (git $(git --version | awk '{print $3}'))"

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
    useradd -r -s /bin/bash -d "$REPO_DIR" -m "$APP_USER"
    usermod -aG docker "$APP_USER"
    success "User '$APP_USER' created"
fi

# ── 4. Clone / update repo ─────────────────────────────────────────────────
if [[ -d "$REPO_DIR/.git" ]]; then
    info "Repo already cloned — pulling latest..."
    git -C "$REPO_DIR" fetch origin
    git -C "$REPO_DIR" reset --hard "origin/$REPO_BRANCH"
    success "Repo updated ($(git -C "$REPO_DIR" log -1 --format='%h %s'))"
else
    info "Cloning $REPO_URL → $REPO_DIR..."
    git clone --branch "$REPO_BRANCH" "$REPO_URL" "$REPO_DIR"
    success "Repo cloned"
fi

mkdir -p "$APP_DIR/logs"
chown -R "$APP_USER:$APP_USER" "$REPO_DIR"

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
        "$APP_DIR/.env.example" > "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
    success ".env created with generated keys"
    echo -e "  ${YELLOW}API Key:  ${BOLD}$GENERATED_API_KEY${NC}"
    echo -e "  ${YELLOW}WAHA Key: ${BOLD}$GENERATED_WAHA_KEY${NC}"
    echo -e "  ${YELLOW}→ Save these! Edit $APP_DIR/.env to add remaining config.${NC}\n"
fi

# ── 7. WAHA (WhatsApp bridge) ──────────────────────────────────────────────
WAHA_KEY=$(grep "^WAHA_API_KEY=" "$APP_DIR/.env" | cut -d= -f2 | tr -d '"')

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

# ── 9. nginx ───────────────────────────────────────────────────────────────
info "Configuring nginx reverse proxy..."
cat > "/etc/nginx/sites-available/commsgateway" <<'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass         http://127.0.0.1:8080;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
    }

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
echo -e "  WAHA:      ${BOLD}http://127.0.0.1:${WAHA_PORT}/dashboard${NC}  (SSH tunnel)\n"
echo -e "${YELLOW}Next steps:${NC}"
echo -e "  1. Edit   ${BOLD}${APP_DIR}/.env${NC} — add Telegram token, ESP32 IP, WhatsApp number"
echo -e "  2. Restart ${BOLD}systemctl restart ${SERVICE_NAME}${NC}"
echo -e "  3. Scan WA ${BOLD}ssh -L 3000:127.0.0.1:3000 user@${VM_IP}${NC}"
echo -e "             then open http://localhost:3000/dashboard"
echo -e "  4. Test    ${BOLD}http://${VM_IP}/${NC}\n"
echo -e "${YELLOW}Future updates:${NC}"
echo -e "  ${BOLD}sudo bash $APP_DIR/../bridge/deploy.sh --update${NC}"
echo -e "  or:  git push → ${BOLD}sudo bash /opt/commsgateway/bridge/deploy.sh --update${NC}\n"
echo -e "  Logs: ${BOLD}tail -f ${APP_DIR}/logs/gateway.log${NC}"
echo -e "  WAHA: ${BOLD}docker logs -f waha${NC}\n"

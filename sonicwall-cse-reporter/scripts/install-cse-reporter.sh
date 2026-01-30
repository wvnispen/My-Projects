#!/bin/bash
#
# SonicWall CSE Reporter - Installation Script
# Version 2.3.0
#
# https://github.com/wvnispen/sonicwall-cse-reporter
#

set +e  # Don't exit on error - handle explicitly

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

VERSION="2.3.0"
LOKI_PORT=3100
GRAFANA_PORT=3000

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$PROJECT_DIR/config"
DASHBOARD_DIR="$PROJECT_DIR/dashboards"
SYSTEMD_DIR="$PROJECT_DIR/systemd"

INSTALL_TYPE=""
UPGRADE_MODE=false
CSE_API_KEY=""
GRAFANA_EXISTS=false
LOKI_EXISTS=false
COLLECTOR_EXISTS=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --upgrade) UPGRADE_MODE=true; shift ;;
        --fresh) INSTALL_TYPE="fresh"; shift ;;
        --addon) INSTALL_TYPE="addon"; shift ;;
        --api-key) CSE_API_KEY="$2"; shift 2 ;;
        --help|-h)
            echo "SonicWall CSE Reporter Installer v${VERSION}"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --upgrade       Upgrade existing installation"
            echo "  --fresh         Force fresh installation"
            echo "  --addon         Add to existing Grafana/Flow Reporter"
            echo "  --api-key KEY   Set CSE API key"
            echo "  --help          Show this help"
            echo ""
            echo "Examples:"
            echo "  sudo $0                    # Interactive installation"
            echo "  sudo $0 --api-key ABC123   # Install with API key"
            echo "  sudo $0 --upgrade          # Upgrade existing install"
            exit 0 ;;
        *) shift ;;
    esac
done

print_banner() {
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║                                                               ║"
    echo "║            SonicWall CSE Reporter v${VERSION}                     ║"
    echo "║                                                               ║"
    echo "║  Cloud Secure Edge Reporting for Grafana                      ║"
    echo "║  https://github.com/wvnispen/sonicwall-cse-reporter           ║"
    echo "║                                                               ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
die() { log_error "$1"; exit 1; }

check_root() {
    [[ $EUID -ne 0 ]] && die "This script must be run as root (use sudo)"
}

check_ubuntu() {
    [[ ! -f /etc/os-release ]] && die "Cannot detect OS"
    source /etc/os-release
    [[ "$ID" != "ubuntu" ]] && die "Requires Ubuntu. Detected: $ID"
    log_info "Detected Ubuntu $VERSION_ID"
}

detect_existing_installation() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Detecting Existing Installation${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    
    if systemctl is-active --quiet grafana-server 2>/dev/null; then
        log_info "✓ Grafana running"
        GRAFANA_EXISTS=true
    else
        log_info "✗ Grafana not detected"
        GRAFANA_EXISTS=false
    fi
    
    if systemctl is-active --quiet loki 2>/dev/null; then
        log_info "✓ Loki running"
        LOKI_EXISTS=true
    else
        log_info "✗ Loki not detected"
        LOKI_EXISTS=false
    fi
    
    if systemctl is-active --quiet cse-collector 2>/dev/null || [[ -f /opt/cse-collector/cse-collector.py ]]; then
        log_info "✓ CSE Collector detected"
        COLLECTOR_EXISTS=true
        if [[ -f /opt/cse-collector/cse-collector.py ]]; then
            COLLECTOR_VERSION=$(grep -oP 'Version \K[0-9.]+' /opt/cse-collector/cse-collector.py 2>/dev/null | head -1 || echo "unknown")
            log_info "  Current version: $COLLECTOR_VERSION"
        fi
    else
        log_info "✗ CSE Collector not detected"
        COLLECTOR_EXISTS=false
    fi
    echo ""
}

prompt_installation_type() {
    [[ -n "$INSTALL_TYPE" ]] && return 0
    
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Installation Options${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    
    if [[ "$COLLECTOR_EXISTS" == "true" ]]; then
        echo "Existing CSE Reporter v${COLLECTOR_VERSION:-unknown} detected."
        echo ""
        echo "  1) Upgrade to v${VERSION} (Recommended)"
        echo "  2) Fresh Installation (resets config)"
        echo ""
        while true; do
            read -r -p "Select [1-2] (default: 1): " choice
            case ${choice:-1} in
                1) INSTALL_TYPE="upgrade"; log_info "Selected: Upgrade"; break ;;
                2) 
                    read -r -p "Reset configuration? (y/N): " confirm
                    [[ "$confirm" =~ ^[Yy]$ ]] && { INSTALL_TYPE="fresh"; break; }
                    ;;
                *) echo "Invalid option" ;;
            esac
        done
    elif [[ "$GRAFANA_EXISTS" == "true" ]]; then
        echo "Existing Grafana detected."
        echo ""
        echo "  1) Add-on Installation (Recommended)"
        echo "  2) Fresh Installation"
        echo ""
        while true; do
            read -r -p "Select [1-2] (default: 1): " choice
            case ${choice:-1} in
                1) INSTALL_TYPE="addon"; log_info "Selected: Add-on"; break ;;
                2) INSTALL_TYPE="fresh"; log_info "Selected: Fresh"; break ;;
                *) echo "Invalid option" ;;
            esac
        done
    else
        echo "Fresh installation will include:"
        echo "  • Grafana (Dashboard UI)"
        echo "  • Loki (Log Storage)"
        echo "  • CSE Collector (API-based event collection)"
        echo ""
        read -r -p "Continue? (Y/n): " confirm
        [[ "$confirm" =~ ^[Nn]$ ]] && exit 0
        INSTALL_TYPE="fresh"
    fi
    echo ""
}

prompt_api_key() {
    [[ -n "$CSE_API_KEY" ]] && return 0
    
    # Check existing
    if [[ -f /etc/cse-collector/env ]]; then
        EXISTING_KEY=$(grep "^CSE_API_KEY=" /etc/cse-collector/env 2>/dev/null | cut -d'=' -f2)
        if [[ -n "$EXISTING_KEY" && "$EXISTING_KEY" != "your-api-key-here" ]]; then
            log_info "Using existing API key"
            CSE_API_KEY="$EXISTING_KEY"
            return 0
        fi
    fi
    
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  CSE API Key Configuration${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Get your API key from:"
    echo "  CSE Admin Console → Settings → API Keys"
    echo ""
    read -r -p "Enter API key (or Enter to skip): " CSE_API_KEY
    [[ -z "$CSE_API_KEY" ]] && log_warn "No API key - configure later in /etc/cse-collector/env"
    echo ""
}

install_prerequisites() {
    log_info "Installing prerequisites..."
    apt-get update -qq
    apt-get install -y -qq apt-transport-https software-properties-common wget curl gnupg2 jq unzip python3 python3-pip > /dev/null
    log_info "Prerequisites installed"
}

add_grafana_repo() {
    log_info "Adding Grafana Labs repository..."
    mkdir -p /etc/apt/keyrings/
    wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor > /etc/apt/keyrings/grafana.gpg
    echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" > /etc/apt/sources.list.d/grafana.list
    apt-get update -qq
    log_info "Repository added"
}

install_grafana() {
    [[ "$GRAFANA_EXISTS" == "true" && "$INSTALL_TYPE" != "fresh" ]] && { log_info "Grafana exists, skipping"; return 0; }
    
    log_info "Installing Grafana..."
    apt-get install -y -qq grafana > /dev/null
    systemctl daemon-reload
    systemctl enable grafana-server
    systemctl start grafana-server
    sleep 5
    systemctl is-active --quiet grafana-server || die "Grafana failed to start"
    log_info "Grafana running on port ${GRAFANA_PORT}"
}

install_loki() {
    [[ "$LOKI_EXISTS" == "true" && "$INSTALL_TYPE" == "upgrade" ]] && { log_info "Loki exists, skipping"; return 0; }
    
    log_info "Installing Loki..."
    
    # Create user/group before package install
    getent group loki > /dev/null 2>&1 || groupadd --system loki
    getent passwd loki > /dev/null 2>&1 || useradd --system --no-create-home --shell /bin/false -g loki loki
    
    # Create directories
    mkdir -p /var/lib/loki/{chunks,rules,wal,tsdb-shipper-active,tsdb-shipper-cache,compactor}
    chown -R loki:loki /var/lib/loki
    
    apt-get install -y -qq loki > /dev/null
    
    # Deploy config
    [[ -f /etc/loki/config.yml ]] && cp /etc/loki/config.yml /etc/loki/config.yml.bak
    cp "$CONFIG_DIR/loki/loki-config.yml" /etc/loki/config.yml
    chown -R loki:loki /var/lib/loki
    
    systemctl daemon-reload
    systemctl enable loki
    systemctl restart loki
    sleep 5
    systemctl is-active --quiet loki || { journalctl -u loki -n 10; die "Loki failed to start"; }
    log_info "Loki running on port ${LOKI_PORT}"
}

install_collector() {
    log_info "Installing CSE Collector v${VERSION}..."
    
    systemctl stop cse-collector 2>/dev/null || true
    
    mkdir -p /opt/cse-collector /etc/cse-collector /var/lib/cse-collector /var/log/cse-collector
    
    # Backup existing
    [[ -f /opt/cse-collector/cse-collector.py ]] && \
        cp /opt/cse-collector/cse-collector.py "/opt/cse-collector/cse-collector.py.bak.$(date +%Y%m%d%H%M%S)"
    
    cp "$SCRIPT_DIR/cse-collector.py" /opt/cse-collector/
    chmod +x /opt/cse-collector/cse-collector.py
    
    log_info "Installing Python dependencies..."
    pip3 install --break-system-packages -q requests pyyaml 2>/dev/null || pip3 install -q requests pyyaml
    
    # Config
    [[ ! -f /etc/cse-collector/config.yaml || "$INSTALL_TYPE" == "fresh" ]] && \
        cp "$CONFIG_DIR/cse-collector/config.yaml" /etc/cse-collector/
    
    # API key
    if [[ -n "$CSE_API_KEY" ]]; then
        echo "CSE_API_KEY=$CSE_API_KEY" > /etc/cse-collector/env
        chmod 600 /etc/cse-collector/env
        log_info "API key configured"
    elif [[ ! -f /etc/cse-collector/env ]]; then
        cp "$CONFIG_DIR/cse-collector/env.template" /etc/cse-collector/env
        chmod 600 /etc/cse-collector/env
    fi
    
    cp "$SYSTEMD_DIR/cse-collector.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable cse-collector
    
    # Reset cursor on upgrade
    if [[ "$INSTALL_TYPE" == "upgrade" ]]; then
        echo ""
        log_warn "Reset cursor to re-fetch events with new format?"
        read -r -p "Reset? (Y/n): " confirm
        [[ ! "$confirm" =~ ^[Nn]$ ]] && rm -f /var/lib/cse-collector/cursor.json
    fi
    
    # Start if API key valid
    API_KEY_VAL=$(grep "^CSE_API_KEY=" /etc/cse-collector/env 2>/dev/null | cut -d'=' -f2)
    if [[ -n "$API_KEY_VAL" && "$API_KEY_VAL" != "your-api-key-here" ]]; then
        systemctl start cse-collector
        sleep 3
        if systemctl is-active --quiet cse-collector; then
            log_info "CSE Collector started"
        else
            log_error "Collector failed to start"
            journalctl -u cse-collector -n 10
        fi
    else
        log_warn "Collector installed but not started (configure API key first)"
        log_warn "  Edit /etc/cse-collector/env then: sudo systemctl start cse-collector"
    fi
}

configure_grafana_datasource() {
    log_info "Configuring Loki datasource..."
    
    local GRAFANA_URL="http://localhost:${GRAFANA_PORT}"
    local GRAFANA_CREDS="admin:admin"
    
    for i in {1..30}; do
        curl -s -u "$GRAFANA_CREDS" "$GRAFANA_URL/api/health" 2>/dev/null | grep -q "ok" && break
        sleep 2
    done
    
    if ! curl -s -u "$GRAFANA_CREDS" "$GRAFANA_URL/api/datasources/name/Loki" 2>/dev/null | grep -q '"id"'; then
        curl -s -X POST -H "Content-Type: application/json" -u "$GRAFANA_CREDS" \
            "$GRAFANA_URL/api/datasources" \
            -d '{"name":"Loki","type":"loki","url":"http://localhost:3100","access":"proxy"}' > /dev/null
        log_info "Loki datasource created"
    else
        log_info "Loki datasource exists"
    fi
}

create_dashboard_folder() {
    log_info "Creating dashboard folder..."
    
    local GRAFANA_URL="http://localhost:${GRAFANA_PORT}"
    local GRAFANA_CREDS="admin:admin"
    
    FOLDER_UID=$(curl -s -u "$GRAFANA_CREDS" "$GRAFANA_URL/api/folders" 2>/dev/null | \
        python3 -c "import sys,json; folders=json.load(sys.stdin); print(next((f['uid'] for f in folders if f['title']=='SonicWall CSE'), ''))" 2>/dev/null || echo "")
    
    if [[ -z "$FOLDER_UID" ]]; then
        FOLDER_UID=$(curl -s -X POST -H "Content-Type: application/json" -u "$GRAFANA_CREDS" \
            "$GRAFANA_URL/api/folders" -d '{"title":"SonicWall CSE"}' | \
            python3 -c "import sys,json; print(json.load(sys.stdin).get('uid',''))" 2>/dev/null)
        log_info "Folder created (UID: $FOLDER_UID)"
    else
        log_info "Folder exists (UID: $FOLDER_UID)"
    fi
    
    export CSE_FOLDER_UID="$FOLDER_UID"
}

import_dashboards() {
    log_info "Importing dashboards..."
    
    local GRAFANA_URL="http://localhost:${GRAFANA_PORT}"
    local GRAFANA_CREDS="admin:admin"
    
    LOKI_UID=$(curl -s -u "$GRAFANA_CREDS" "$GRAFANA_URL/api/datasources/name/Loki" 2>/dev/null | \
        python3 -c "import sys,json; print(json.load(sys.stdin).get('uid','loki'))" 2>/dev/null || echo "loki")
    
    for dashboard_file in "$DASHBOARD_DIR"/*.json; do
        [[ -f "$dashboard_file" ]] || continue
        local dashboard_name=$(basename "$dashboard_file" .json)
        
        TEMP_PAYLOAD=$(mktemp)
        python3 << PYEOF
import json
with open('$dashboard_file', 'r') as f:
    dashboard = json.load(f)
dashboard.pop('id', None)
def update_ds(obj):
    if isinstance(obj, dict):
        if obj.get('type') == 'loki' and 'uid' in obj:
            obj['uid'] = '$LOKI_UID'
        for v in obj.values():
            update_ds(v)
    elif isinstance(obj, list):
        for item in obj:
            update_ds(item)
update_ds(dashboard)
with open('$TEMP_PAYLOAD', 'w') as f:
    json.dump({'dashboard': dashboard, 'folderUid': '$CSE_FOLDER_UID', 'overwrite': True}, f)
PYEOF
        
        RESULT=$(curl -s -X POST -H "Content-Type: application/json" -u "$GRAFANA_CREDS" \
            "$GRAFANA_URL/api/dashboards/db" -d @"$TEMP_PAYLOAD")
        rm -f "$TEMP_PAYLOAD"
        
        if echo "$RESULT" | grep -q '"status":"success"'; then
            log_info "  ✓ $dashboard_name"
        else
            log_warn "  ⚠ $dashboard_name"
        fi
    done
}

configure_firewall() {
    command -v ufw &>/dev/null && ufw status | grep -q "active" && \
        ufw allow ${GRAFANA_PORT}/tcp comment "Grafana" 2>/dev/null && \
        log_info "Firewall configured"
}

print_summary() {
    local SERVER_IP=$(hostname -I | awk '{print $1}')
    
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Installation Complete!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  Services:"
    echo "    • Grafana:       http://${SERVER_IP}:${GRAFANA_PORT}"
    echo "    • Loki:          http://localhost:${LOKI_PORT}"
    echo "    • CSE Collector: Polling every 60 seconds"
    echo ""
    echo "  Dashboards:"
    echo "    Grafana → Dashboards → SonicWall CSE"
    echo ""
    echo "  Verify:"
    echo "    sudo journalctl -u cse-collector -f"
    echo "    curl -s 'http://localhost:3100/loki/api/v1/labels' | jq"
    echo ""
    echo -e "${BLUE}  Documentation: https://github.com/wvnispen/sonicwall-cse-reporter${NC}"
    echo ""
}

main() {
    print_banner
    check_root
    check_ubuntu
    detect_existing_installation
    [[ "$UPGRADE_MODE" == "true" ]] && INSTALL_TYPE="upgrade" || prompt_installation_type
    prompt_api_key
    
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Installing (${INSTALL_TYPE})${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    
    install_prerequisites
    add_grafana_repo
    [[ "$INSTALL_TYPE" == "fresh" || "$GRAFANA_EXISTS" != "true" ]] && install_grafana
    install_loki
    install_collector
    configure_grafana_datasource
    create_dashboard_folder
    import_dashboards
    configure_firewall
    print_summary
}

main "$@"

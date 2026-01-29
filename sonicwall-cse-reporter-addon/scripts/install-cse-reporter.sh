#!/bin/bash
#
# SonicWall CSE Reporter - Installation Script
# Version 2.0.0 - API Integration
#
# This script installs the CSE Events API Collector, Loki, and CSE dashboards
# Can be used as an add-on to existing Flow Reporter or as fresh install
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Version
VERSION="2.0.0"

# Default ports
LOKI_PORT=3100
GRAFANA_PORT=3000

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$PROJECT_DIR/config"
DASHBOARD_DIR="$PROJECT_DIR/dashboards"

# Installation type
INSTALL_TYPE=""
UPGRADE_MODE=false
CSE_API_KEY=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --upgrade)
            UPGRADE_MODE=true
            shift
            ;;
        --api-key)
            CSE_API_KEY="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

print_banner() {
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║                                                               ║"
    echo "║         SonicWall CSE Reporter - Installer v${VERSION}           ║"
    echo "║              API Integration Edition                          ║"
    echo "║                                                               ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

check_ubuntu() {
    if [[ ! -f /etc/os-release ]]; then
        log_error "Cannot detect OS. This script requires Ubuntu 24.04 LTS"
        exit 1
    fi
    
    source /etc/os-release
    if [[ "$ID" != "ubuntu" ]]; then
        log_error "This script requires Ubuntu. Detected: $ID"
        exit 1
    fi
    
    if [[ "$VERSION_ID" != "24.04" && "$VERSION_ID" != "22.04" ]]; then
        log_warn "This script is tested on Ubuntu 24.04/22.04. Detected: $VERSION_ID"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    log_info "Detected Ubuntu $VERSION_ID"
}

detect_existing_installation() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Detecting Installation Type${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    
    # Check for existing Grafana
    if systemctl is-active --quiet grafana-server 2>/dev/null; then
        log_info "Detected existing Grafana installation"
        GRAFANA_EXISTS=true
    else
        GRAFANA_EXISTS=false
    fi
    
    # Check for existing Elasticsearch (indicates Flow Reporter)
    if systemctl is-active --quiet elasticsearch 2>/dev/null; then
        log_info "Detected existing Elasticsearch installation (Flow Reporter)"
        FLOW_REPORTER_EXISTS=true
    else
        FLOW_REPORTER_EXISTS=false
    fi
    
    # Check for existing Loki
    if systemctl is-active --quiet loki 2>/dev/null; then
        log_info "Detected existing Loki installation"
        LOKI_EXISTS=true
    else
        LOKI_EXISTS=false
    fi
    
    # Check for existing CSE Collector
    if systemctl is-active --quiet cse-collector 2>/dev/null; then
        log_info "Detected existing CSE Collector installation"
        COLLECTOR_EXISTS=true
    else
        COLLECTOR_EXISTS=false
    fi
    
    echo ""
}

prompt_api_key() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  CSE API Configuration${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    
    if [[ -n "$CSE_API_KEY" ]]; then
        log_info "API key provided via command line"
        return
    fi
    
    # Check if already configured
    if [[ -f /etc/cse-collector/env ]]; then
        existing_key=$(grep "^CSE_API_KEY=" /etc/cse-collector/env 2>/dev/null | cut -d'=' -f2)
        if [[ -n "$existing_key" && "$existing_key" != "your-api-key-secret-here" ]]; then
            log_info "Existing API key found in /etc/cse-collector/env"
            read -p "Keep existing API key? (Y/n): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                CSE_API_KEY="$existing_key"
                return
            fi
        fi
    fi
    
    echo "To collect logs from SonicWall CSE, you need an API key."
    echo ""
    echo "To create an API key:"
    echo "  1. Log into CSE Command Center"
    echo "  2. Navigate to Settings → API Keys"
    echo "  3. Create a new key with 'ReadOnly' scope"
    echo "  4. Copy the API Secret"
    echo ""
    echo "Documentation: https://cse-docs.sonicwall.com/docs/visibility-logging/events/elk-stack/"
    echo ""
    
    while true; do
        read -p "Enter your CSE API Key (or 'skip' to configure later): " CSE_API_KEY
        if [[ "$CSE_API_KEY" == "skip" ]]; then
            log_warn "Skipping API key configuration. You must configure it later in /etc/cse-collector/env"
            CSE_API_KEY=""
            break
        elif [[ -n "$CSE_API_KEY" ]]; then
            # Basic validation - CSE API keys are typically long strings
            if [[ ${#CSE_API_KEY} -lt 20 ]]; then
                log_warn "API key seems too short. Are you sure this is correct?"
                read -p "Continue anyway? (y/N): " -n 1 -r
                echo
                if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                    continue
                fi
            fi
            break
        fi
    done
    
    echo ""
}

prompt_installation_type() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Installation Options${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    
    if [[ "$GRAFANA_EXISTS" == "true" ]]; then
        echo "Existing Grafana detected. Choose installation type:"
        echo ""
        echo "  1) Add-on Installation (Recommended)"
        echo "     - Add Loki and CSE Collector to existing stack"
        echo "     - Create CSE dashboards in existing Grafana"
        echo "     - Preserve existing Flow Reporter configuration"
        echo ""
        echo "  2) Fresh Installation"
        echo "     - Full installation including Grafana"
        echo "     - WARNING: May conflict with existing installation"
        echo ""
        
        while true; do
            read -p "Select option [1-2] (default: 1): " choice
            choice=${choice:-1}
            case $choice in
                1)
                    INSTALL_TYPE="addon"
                    log_info "Selected: Add-on Installation"
                    break
                    ;;
                2)
                    INSTALL_TYPE="fresh"
                    log_warn "Selected: Fresh Installation"
                    read -p "Are you sure? (y/N): " -n 1 -r
                    echo
                    if [[ $REPLY =~ ^[Yy]$ ]]; then
                        break
                    fi
                    ;;
                *)
                    echo "Invalid option. Please select 1 or 2."
                    ;;
            esac
        done
    else
        echo "No existing Grafana detected. This will be a fresh installation."
        echo ""
        echo "The following components will be installed:"
        echo "  - Grafana (Dashboard UI)"
        echo "  - Loki (Log Storage)"
        echo "  - CSE Collector (API-based log collection)"
        echo ""
        read -p "Continue with fresh installation? (Y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Nn]$ ]]; then
            log_info "Installation cancelled"
            exit 0
        fi
        INSTALL_TYPE="fresh"
    fi
    
    echo ""
}

install_prerequisites() {
    log_info "Installing prerequisites..."
    
    apt-get update
    apt-get install -y \
        apt-transport-https \
        software-properties-common \
        wget \
        curl \
        gnupg2 \
        jq \
        unzip \
        python3 \
        python3-pip \
        python3-venv
    
    log_info "Prerequisites installed"
}

add_grafana_repo() {
    log_info "Adding Grafana Labs APT repository..."
    
    # Add Grafana GPG key
    mkdir -p /etc/apt/keyrings/
    wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor > /etc/apt/keyrings/grafana.gpg
    
    # Add repository
    echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" > /etc/apt/sources.list.d/grafana.list
    
    apt-get update
    
    log_info "Grafana Labs repository added"
}

install_grafana() {
    if [[ "$GRAFANA_EXISTS" == "true" && "$INSTALL_TYPE" == "addon" ]]; then
        log_info "Skipping Grafana installation (already exists)"
        return
    fi
    
    log_info "Installing Grafana..."
    
    apt-get install -y grafana
    
    systemctl daemon-reload
    systemctl enable grafana-server
    systemctl start grafana-server
    
    log_info "Waiting for Grafana to start..."
    sleep 5
    
    if systemctl is-active --quiet grafana-server; then
        log_info "Grafana installed and running on port ${GRAFANA_PORT}"
    else
        log_error "Grafana failed to start"
        journalctl -u grafana-server --no-pager -n 20
        exit 1
    fi
}

install_loki() {
    if [[ "$LOKI_EXISTS" == "true" && "$UPGRADE_MODE" == "false" ]]; then
        log_info "Loki already installed, skipping..."
        return
    fi
    
    log_info "Installing Loki..."
    
    apt-get install -y loki
    
    # Backup default config
    if [[ -f /etc/loki/config.yml ]]; then
        cp /etc/loki/config.yml /etc/loki/config.yml.bak
    fi
    
    # Deploy our configuration
    cp "$CONFIG_DIR/loki/loki-config.yml" /etc/loki/config.yml
    
    # Create data directory
    mkdir -p /var/lib/loki
    chown loki:loki /var/lib/loki
    
    systemctl daemon-reload
    systemctl enable loki
    systemctl restart loki
    
    log_info "Waiting for Loki to start..."
    sleep 5
    
    if systemctl is-active --quiet loki; then
        log_info "Loki installed and running on port ${LOKI_PORT}"
    else
        log_error "Loki failed to start"
        journalctl -u loki --no-pager -n 20
        exit 1
    fi
}

install_cse_collector() {
    log_info "Installing CSE Events Collector..."
    
    # Create user
    if ! id -u cse-collector &>/dev/null; then
        useradd -r -s /bin/false cse-collector
    fi
    
    # Create directories
    mkdir -p /opt/cse-collector
    mkdir -p /etc/cse-collector
    mkdir -p /var/lib/cse-collector
    mkdir -p /var/log/cse-collector
    
    # Install Python dependencies
    log_info "Installing Python dependencies..."
    pip3 install --break-system-packages requests pyyaml
    
    # Copy collector script
    cp "$SCRIPT_DIR/cse-collector.py" /opt/cse-collector/
    chmod +x /opt/cse-collector/cse-collector.py
    
    # Copy config
    cp "$CONFIG_DIR/cse-collector/config.yaml" /etc/cse-collector/
    
    # Create environment file with API key
    if [[ -n "$CSE_API_KEY" ]]; then
        echo "CSE_API_KEY=$CSE_API_KEY" > /etc/cse-collector/env
    else
        cp "$CONFIG_DIR/cse-collector/env.template" /etc/cse-collector/env
    fi
    chmod 600 /etc/cse-collector/env
    
    # Set ownership
    chown -R cse-collector:cse-collector /var/lib/cse-collector
    chown -R cse-collector:cse-collector /var/log/cse-collector
    chown root:cse-collector /etc/cse-collector/env
    
    # Install systemd service
    cp "$SCRIPT_DIR/../systemd/cse-collector.service" /etc/systemd/system/
    
    systemctl daemon-reload
    systemctl enable cse-collector
    
    # Only start if API key is configured
    if [[ -n "$CSE_API_KEY" ]]; then
        systemctl start cse-collector
        sleep 3
        if systemctl is-active --quiet cse-collector; then
            log_info "CSE Collector installed and running"
        else
            log_warn "CSE Collector installed but failed to start. Check configuration."
            journalctl -u cse-collector --no-pager -n 10
        fi
    else
        log_warn "CSE Collector installed but not started (API key not configured)"
        log_warn "Configure API key in /etc/cse-collector/env and run: systemctl start cse-collector"
    fi
}

configure_grafana_datasource() {
    log_info "Configuring Loki datasource in Grafana..."
    
    GRAFANA_URL="http://localhost:${GRAFANA_PORT}"
    GRAFANA_CREDS="admin:admin"
    
    # Try to connect to Grafana API
    for i in {1..30}; do
        if curl -s -u "$GRAFANA_CREDS" "$GRAFANA_URL/api/health" | grep -q "ok"; then
            break
        fi
        log_info "Waiting for Grafana API... ($i/30)"
        sleep 2
    done
    
    # Check if Loki datasource already exists
    EXISTING_DS=$(curl -s -u "$GRAFANA_CREDS" "$GRAFANA_URL/api/datasources/name/Loki" 2>/dev/null || echo "")
    
    if echo "$EXISTING_DS" | grep -q '"id"'; then
        log_info "Loki datasource already exists in Grafana"
    else
        curl -s -X POST \
            -H "Content-Type: application/json" \
            -u "$GRAFANA_CREDS" \
            "$GRAFANA_URL/api/datasources" \
            -d '{
                "name": "Loki",
                "type": "loki",
                "url": "http://localhost:3100",
                "access": "proxy",
                "isDefault": false
            }' > /dev/null
        
        log_info "Loki datasource created in Grafana"
    fi
}

create_dashboard_folder() {
    log_info "Creating 'SonicWall CSE' dashboard folder..."
    
    GRAFANA_URL="http://localhost:${GRAFANA_PORT}"
    GRAFANA_CREDS="admin:admin"
    
    EXISTING_FOLDER=$(curl -s -u "$GRAFANA_CREDS" "$GRAFANA_URL/api/folders" | jq -r '.[] | select(.title=="SonicWall CSE") | .uid')
    
    if [[ -n "$EXISTING_FOLDER" ]]; then
        log_info "Dashboard folder 'SonicWall CSE' already exists (UID: $EXISTING_FOLDER)"
        FOLDER_UID="$EXISTING_FOLDER"
    else
        FOLDER_RESPONSE=$(curl -s -X POST \
            -H "Content-Type: application/json" \
            -u "$GRAFANA_CREDS" \
            "$GRAFANA_URL/api/folders" \
            -d '{"title": "SonicWall CSE"}')
        
        FOLDER_UID=$(echo "$FOLDER_RESPONSE" | jq -r '.uid')
        
        if [[ "$FOLDER_UID" != "null" && -n "$FOLDER_UID" ]]; then
            log_info "Dashboard folder 'SonicWall CSE' created (UID: $FOLDER_UID)"
        else
            log_error "Failed to create dashboard folder"
            echo "$FOLDER_RESPONSE"
        fi
    fi
    
    export CSE_FOLDER_UID="$FOLDER_UID"
}

import_dashboards() {
    log_info "Importing CSE dashboards..."
    
    GRAFANA_URL="http://localhost:${GRAFANA_PORT}"
    GRAFANA_CREDS="admin:admin"
    
    for dashboard_file in "$DASHBOARD_DIR"/*.json; do
        if [[ -f "$dashboard_file" ]]; then
            dashboard_name=$(basename "$dashboard_file" .json)
            log_info "Importing dashboard: $dashboard_name"
            
            DASHBOARD_JSON=$(cat "$dashboard_file")
            
            IMPORT_PAYLOAD=$(jq -n \
                --arg folderUid "$CSE_FOLDER_UID" \
                --argjson dashboard "$DASHBOARD_JSON" \
                '{
                    "dashboard": $dashboard,
                    "folderUid": $folderUid,
                    "overwrite": true
                }')
            
            IMPORT_RESULT=$(curl -s -X POST \
                -H "Content-Type: application/json" \
                -u "$GRAFANA_CREDS" \
                "$GRAFANA_URL/api/dashboards/db" \
                -d "$IMPORT_PAYLOAD")
            
            if echo "$IMPORT_RESULT" | grep -q '"status":"success"'; then
                log_info "  ✓ $dashboard_name imported successfully"
            else
                log_warn "  ⚠ $dashboard_name import may have issues"
                echo "$IMPORT_RESULT" | jq -r '.message // .status // .' 2>/dev/null || echo "$IMPORT_RESULT"
            fi
        fi
    done
}

configure_firewall() {
    log_info "Configuring firewall rules..."
    
    if command -v ufw &> /dev/null && ufw status | grep -q "active"; then
        ufw allow ${GRAFANA_PORT}/tcp comment "Grafana"
        log_info "UFW rule added for port ${GRAFANA_PORT}"
    else
        log_info "UFW not active, skipping firewall configuration"
        log_info "Ensure port ${GRAFANA_PORT} (Grafana) is accessible"
    fi
}

print_summary() {
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Installation Complete!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Services installed and running:"
    echo ""
    
    if [[ "$INSTALL_TYPE" == "fresh" ]]; then
        echo "  ✓ Grafana          : http://$(hostname -I | awk '{print $1}'):${GRAFANA_PORT}"
        echo "                       Default login: admin / admin"
    fi
    
    echo "  ✓ Loki             : http://localhost:${LOKI_PORT}"
    
    if [[ -n "$CSE_API_KEY" ]]; then
        echo "  ✓ CSE Collector    : Running (polling CSE API)"
    else
        echo "  ⚠ CSE Collector    : Installed but not started (API key required)"
    fi
    
    echo ""
    echo "Dashboard folder: SonicWall CSE"
    echo ""
    
    if [[ -z "$CSE_API_KEY" ]]; then
        echo -e "${YELLOW}IMPORTANT: Configure your CSE API key${NC}"
        echo ""
        echo "1. Create an API key in CSE Command Center:"
        echo "   Settings → API Keys → Create new key (ReadOnly scope)"
        echo ""
        echo "2. Add the API key to the configuration:"
        echo "   sudo nano /etc/cse-collector/env"
        echo "   Set: CSE_API_KEY=your-api-key-here"
        echo ""
        echo "3. Start the collector:"
        echo "   sudo systemctl start cse-collector"
        echo ""
    fi
    
    echo -e "${YELLOW}Next Steps:${NC}"
    echo ""
    echo "1. Access Grafana dashboards:"
    echo "   http://$(hostname -I | awk '{print $1}'):${GRAFANA_PORT}"
    echo "   Navigate to: Dashboards → SonicWall CSE"
    echo ""
    echo "2. Verify data is flowing:"
    echo "   curl -s 'http://localhost:${LOKI_PORT}/loki/api/v1/labels' | jq"
    echo ""
    echo "3. Check collector status:"
    echo "   sudo systemctl status cse-collector"
    echo "   sudo journalctl -u cse-collector -f"
    echo ""
    echo -e "${BLUE}Documentation: https://github.com/wvnispen/sonicwall-cse-reporter-addon${NC}"
    echo ""
}

# Main execution
main() {
    print_banner
    check_root
    check_ubuntu
    detect_existing_installation
    
    if [[ "$UPGRADE_MODE" == "true" ]]; then
        log_info "Running in upgrade mode..."
        INSTALL_TYPE="addon"
    else
        prompt_installation_type
    fi
    
    prompt_api_key
    
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Starting Installation${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    
    install_prerequisites
    add_grafana_repo
    
    if [[ "$INSTALL_TYPE" == "fresh" ]]; then
        install_grafana
    fi
    
    install_loki
    install_cse_collector
    configure_grafana_datasource
    create_dashboard_folder
    import_dashboards
    configure_firewall
    print_summary
}

main "$@"

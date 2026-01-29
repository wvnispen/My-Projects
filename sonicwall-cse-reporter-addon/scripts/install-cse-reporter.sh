#!/bin/bash
#
# SonicWall CSE Reporter - Installation Script
# Version 1.0.0
#
# This script installs Loki, Grafana Alloy, and CSE dashboards
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
VERSION="1.0.0"

# Default ports
LOKI_PORT=3100
ALLOY_SYSLOG_PORT=6514
ALLOY_UI_PORT=12345
GRAFANA_PORT=3000

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$PROJECT_DIR/config"
DASHBOARD_DIR="$PROJECT_DIR/dashboards"

# Installation type
INSTALL_TYPE=""
UPGRADE_MODE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --upgrade)
            UPGRADE_MODE=true
            shift
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
    echo "║           SonicWall CSE Reporter - Installer                  ║"
    echo "║                     Version ${VERSION}                            ║"
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
    
    # Check for existing Grafana (indicates Flow Reporter or standalone Grafana)
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
    
    # Check for existing Alloy
    if systemctl is-active --quiet alloy 2>/dev/null; then
        log_info "Detected existing Alloy installation"
        ALLOY_EXISTS=true
    else
        ALLOY_EXISTS=false
    fi
    
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
        echo "     - Add Loki and Alloy to existing stack"
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
                    log_warn "Selected: Fresh Installation (existing services may conflict)"
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
        echo "  - Grafana Alloy (Log Collection)"
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
        unzip
    
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
    
    # Enable and start service
    systemctl daemon-reload
    systemctl enable grafana-server
    systemctl start grafana-server
    
    # Wait for Grafana to start
    log_info "Waiting for Grafana to start..."
    sleep 5
    
    # Check if Grafana is running
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
    
    # Enable and start service
    systemctl daemon-reload
    systemctl enable loki
    systemctl restart loki
    
    # Wait for Loki to start
    log_info "Waiting for Loki to start..."
    sleep 5
    
    # Check if Loki is running
    if systemctl is-active --quiet loki; then
        log_info "Loki installed and running on port ${LOKI_PORT}"
    else
        log_error "Loki failed to start"
        journalctl -u loki --no-pager -n 20
        exit 1
    fi
}

install_alloy() {
    if [[ "$ALLOY_EXISTS" == "true" && "$UPGRADE_MODE" == "false" ]]; then
        log_info "Alloy already installed, updating configuration..."
    else
        log_info "Installing Grafana Alloy..."
        apt-get install -y alloy
    fi
    
    # Create config directory
    mkdir -p /etc/alloy
    
    # Backup existing config if present
    if [[ -f /etc/alloy/config.alloy ]]; then
        cp /etc/alloy/config.alloy /etc/alloy/config.alloy.bak
    fi
    
    # Deploy our configuration
    cp "$CONFIG_DIR/alloy/config.alloy" /etc/alloy/config.alloy
    
    # Create log directory
    mkdir -p /var/log/alloy
    
    # Update systemd service to use our config
    mkdir -p /etc/systemd/system/alloy.service.d
    cat > /etc/systemd/system/alloy.service.d/override.conf << 'EOF'
[Service]
ExecStart=
ExecStart=/usr/bin/alloy run /etc/alloy/config.alloy --storage.path=/var/lib/alloy/data
EOF
    
    # Enable and start service
    systemctl daemon-reload
    systemctl enable alloy
    systemctl restart alloy
    
    # Wait for Alloy to start
    log_info "Waiting for Alloy to start..."
    sleep 5
    
    # Check if Alloy is running
    if systemctl is-active --quiet alloy; then
        log_info "Alloy installed and running"
        log_info "  - Syslog receiver on port ${ALLOY_SYSLOG_PORT}"
        log_info "  - Alloy UI on port ${ALLOY_UI_PORT}"
    else
        log_error "Alloy failed to start"
        journalctl -u alloy --no-pager -n 20
        exit 1
    fi
}

configure_grafana_datasource() {
    log_info "Configuring Loki datasource in Grafana..."
    
    # Wait for Grafana API to be ready
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
        # Create Loki datasource
        curl -s -X POST \
            -H "Content-Type: application/json" \
            -u "$GRAFANA_CREDS" \
            "$GRAFANA_URL/api/datasources" \
            -d '{
                "name": "Loki",
                "type": "loki",
                "url": "http://localhost:3100",
                "access": "proxy",
                "isDefault": false,
                "jsonData": {}
            }' > /dev/null
        
        log_info "Loki datasource created in Grafana"
    fi
}

create_dashboard_folder() {
    log_info "Creating 'SonicWall CSE' dashboard folder..."
    
    GRAFANA_URL="http://localhost:${GRAFANA_PORT}"
    GRAFANA_CREDS="admin:admin"
    
    # Check if folder exists
    EXISTING_FOLDER=$(curl -s -u "$GRAFANA_CREDS" "$GRAFANA_URL/api/folders" | jq -r '.[] | select(.title=="SonicWall CSE") | .uid')
    
    if [[ -n "$EXISTING_FOLDER" ]]; then
        log_info "Dashboard folder 'SonicWall CSE' already exists (UID: $EXISTING_FOLDER)"
        FOLDER_UID="$EXISTING_FOLDER"
    else
        # Create folder
        FOLDER_RESPONSE=$(curl -s -X POST \
            -H "Content-Type: application/json" \
            -u "$GRAFANA_CREDS" \
            "$GRAFANA_URL/api/folders" \
            -d '{
                "title": "SonicWall CSE"
            }')
        
        FOLDER_UID=$(echo "$FOLDER_RESPONSE" | jq -r '.uid')
        
        if [[ "$FOLDER_UID" != "null" && -n "$FOLDER_UID" ]]; then
            log_info "Dashboard folder 'SonicWall CSE' created (UID: $FOLDER_UID)"
        else
            log_error "Failed to create dashboard folder"
            echo "$FOLDER_RESPONSE"
        fi
    fi
    
    # Export for dashboard import
    export CSE_FOLDER_UID="$FOLDER_UID"
}

import_dashboards() {
    log_info "Importing CSE dashboards..."
    
    GRAFANA_URL="http://localhost:${GRAFANA_PORT}"
    GRAFANA_CREDS="admin:admin"
    
    # Import each dashboard
    for dashboard_file in "$DASHBOARD_DIR"/*.json; do
        if [[ -f "$dashboard_file" ]]; then
            dashboard_name=$(basename "$dashboard_file" .json)
            log_info "Importing dashboard: $dashboard_name"
            
            # Read dashboard JSON and wrap it for import API
            DASHBOARD_JSON=$(cat "$dashboard_file")
            
            # Create import payload with folder UID
            IMPORT_PAYLOAD=$(jq -n \
                --arg folderUid "$CSE_FOLDER_UID" \
                --argjson dashboard "$DASHBOARD_JSON" \
                '{
                    "dashboard": $dashboard,
                    "folderUid": $folderUid,
                    "overwrite": true
                }')
            
            # Import dashboard
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
    
    # Check if ufw is installed and active
    if command -v ufw &> /dev/null && ufw status | grep -q "active"; then
        ufw allow ${ALLOY_SYSLOG_PORT}/tcp comment "Alloy Syslog (CSE)"
        ufw allow ${GRAFANA_PORT}/tcp comment "Grafana"
        log_info "UFW rules added for ports ${ALLOY_SYSLOG_PORT} and ${GRAFANA_PORT}"
    else
        log_info "UFW not active, skipping firewall configuration"
        log_info "Ensure ports ${ALLOY_SYSLOG_PORT} (Syslog) and ${GRAFANA_PORT} (Grafana) are accessible"
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
    echo "  ✓ Grafana Alloy    : Syslog on port ${ALLOY_SYSLOG_PORT}"
    echo "                       UI on port ${ALLOY_UI_PORT}"
    echo ""
    echo "Dashboard folder: SonicWall CSE"
    echo ""
    echo -e "${YELLOW}Next Steps:${NC}"
    echo ""
    echo "1. Configure SonicWall CSE to send syslog to:"
    echo "   Server: $(hostname -I | awk '{print $1}')"
    echo "   Port:   ${ALLOY_SYSLOG_PORT}"
    echo "   Protocol: TCP (TLS recommended for production)"
    echo ""
    echo "2. Access Grafana dashboards:"
    echo "   http://$(hostname -I | awk '{print $1}'):${GRAFANA_PORT}"
    echo "   Navigate to: Dashboards → SonicWall CSE"
    echo ""
    echo "3. Verify data is flowing:"
    echo "   curl -s 'http://localhost:${LOKI_PORT}/loki/api/v1/labels' | jq"
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
    install_alloy
    configure_grafana_datasource
    create_dashboard_folder
    import_dashboards
    configure_firewall
    print_summary
}

main "$@"

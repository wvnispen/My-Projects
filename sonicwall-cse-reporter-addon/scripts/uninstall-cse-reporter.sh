#!/bin/bash
#
# SonicWall CSE Reporter - Uninstall Script
# Version 2.0.0
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

print_banner() {
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║         SonicWall CSE Reporter - Uninstaller                  ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

confirm_uninstall() {
    echo ""
    echo -e "${YELLOW}WARNING: This will remove the following components:${NC}"
    echo "  - CSE Collector (API collection service)"
    echo "  - Loki (log storage)"
    echo "  - CSE dashboards from Grafana"
    echo ""
    echo -e "${YELLOW}This will NOT remove:${NC}"
    echo "  - Grafana (may be used by Flow Reporter)"
    echo "  - Elasticsearch (used by Flow Reporter)"
    echo ""
    read -p "Are you sure you want to continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Uninstall cancelled"
        exit 0
    fi
}

remove_cse_collector() {
    log_info "Removing CSE Collector..."
    
    if systemctl is-active --quiet cse-collector 2>/dev/null; then
        systemctl stop cse-collector
    fi
    
    if systemctl is-enabled --quiet cse-collector 2>/dev/null; then
        systemctl disable cse-collector
    fi
    
    rm -f /etc/systemd/system/cse-collector.service
    rm -rf /opt/cse-collector
    
    # Ask about config/data removal
    if [[ -d /etc/cse-collector ]]; then
        echo ""
        read -p "Remove CSE Collector configuration (includes API key)? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf /etc/cse-collector
            log_info "Configuration removed"
        else
            log_info "Configuration preserved at /etc/cse-collector"
        fi
    fi
    
    if [[ -d /var/lib/cse-collector ]]; then
        rm -rf /var/lib/cse-collector
    fi
    
    rm -rf /var/log/cse-collector
    
    # Remove user
    if id -u cse-collector &>/dev/null; then
        userdel cse-collector 2>/dev/null || true
    fi
    
    systemctl daemon-reload
    
    log_info "CSE Collector removed"
}

remove_loki() {
    log_info "Removing Loki..."
    
    if systemctl is-active --quiet loki 2>/dev/null; then
        systemctl stop loki
    fi
    
    if systemctl is-enabled --quiet loki 2>/dev/null; then
        systemctl disable loki
    fi
    
    if dpkg -l | grep -q loki; then
        apt-get remove -y loki
        apt-get autoremove -y
    fi
    
    # Ask about data removal
    if [[ -d /var/lib/loki ]]; then
        echo ""
        read -p "Remove Loki data directory? This deletes all log history. (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf /var/lib/loki
            log_info "Loki data removed"
        else
            log_info "Loki data preserved at /var/lib/loki"
        fi
    fi
    
    rm -rf /etc/loki
    
    systemctl daemon-reload
    
    log_info "Loki removed"
}

remove_dashboards() {
    log_info "Removing CSE dashboards from Grafana..."
    
    GRAFANA_URL="http://localhost:3000"
    GRAFANA_CREDS="admin:admin"
    
    if ! curl -s -u "$GRAFANA_CREDS" "$GRAFANA_URL/api/health" | grep -q "ok"; then
        log_warn "Grafana not accessible, skipping dashboard removal"
        return
    fi
    
    # Find and delete CSE folder
    FOLDER_UID=$(curl -s -u "$GRAFANA_CREDS" "$GRAFANA_URL/api/folders" | jq -r '.[] | select(.title=="SonicWall CSE") | .uid')
    
    if [[ -n "$FOLDER_UID" && "$FOLDER_UID" != "null" ]]; then
        curl -s -X DELETE -u "$GRAFANA_CREDS" "$GRAFANA_URL/api/folders/$FOLDER_UID" > /dev/null
        log_info "Removed 'SonicWall CSE' dashboard folder"
    else
        log_info "CSE dashboard folder not found"
    fi
    
    # Remove Loki datasource
    DS_ID=$(curl -s -u "$GRAFANA_CREDS" "$GRAFANA_URL/api/datasources/name/Loki" | jq -r '.id // empty')
    
    if [[ -n "$DS_ID" ]]; then
        curl -s -X DELETE -u "$GRAFANA_CREDS" "$GRAFANA_URL/api/datasources/$DS_ID" > /dev/null
        log_info "Removed Loki datasource"
    fi
}

print_summary() {
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Uninstall Complete${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "The following components have been removed:"
    echo "  ✓ CSE Collector"
    echo "  ✓ Loki"
    echo "  ✓ CSE dashboards"
    echo ""
}

main() {
    print_banner
    check_root
    confirm_uninstall
    
    echo ""
    log_info "Starting uninstall..."
    echo ""
    
    remove_dashboards
    remove_cse_collector
    remove_loki
    
    print_summary
}

main "$@"

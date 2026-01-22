#!/bin/bash
#
# SonicWall Flow Reporter - Uninstall Script
#
# Removes all components installed by install-native.sh
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║      SonicWall Flow Reporter - Uninstall                      ║${NC}"
echo -e "${YELLOW}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}ERROR: This script must be run as root (use sudo)${NC}"
   exit 1
fi

echo -e "${YELLOW}WARNING: This will remove:${NC}"
echo "  - SonicWall Flow Reporter services"
echo "  - Elasticsearch (and all data)"
echo "  - Grafana (and dashboards)"
echo "  - Application files in /opt/sonicwall-flow-reporter"
echo "  - Data in /var/lib/sonicwall-flow-reporter"
echo ""
read -p "Are you sure you want to continue? (yes/N) " -r
echo

if [[ ! $REPLY == "yes" ]]; then
    echo "Uninstall cancelled."
    exit 0
fi

echo -e "\n${GREEN}Stopping services...${NC}"
systemctl stop swfr-collector.service 2>/dev/null || true
systemctl stop swfr-identity.service 2>/dev/null || true
systemctl stop swfr-aggregator.timer 2>/dev/null || true
systemctl stop grafana-server 2>/dev/null || true
systemctl stop elasticsearch 2>/dev/null || true

echo -e "\n${GREEN}Disabling services...${NC}"
systemctl disable swfr-collector.service 2>/dev/null || true
systemctl disable swfr-identity.service 2>/dev/null || true
systemctl disable swfr-aggregator.timer 2>/dev/null || true

echo -e "\n${GREEN}Removing systemd service files...${NC}"
rm -f /etc/systemd/system/swfr-collector.service
rm -f /etc/systemd/system/swfr-identity.service
rm -f /etc/systemd/system/swfr-aggregator.service
rm -f /etc/systemd/system/swfr-aggregator.timer
systemctl daemon-reload

echo -e "\n${GREEN}Removing Elasticsearch...${NC}"
apt-get remove -y elasticsearch 2>/dev/null || true
rm -f /etc/apt/sources.list.d/elastic-8.x.list
rm -f /usr/share/keyrings/elasticsearch-keyring.gpg

echo -e "\n${GREEN}Removing Grafana...${NC}"
apt-get remove -y grafana 2>/dev/null || true
rm -f /etc/apt/sources.list.d/grafana.list
rm -f /usr/share/keyrings/grafana-keyring.gpg

echo -e "\n${GREEN}Removing application directories...${NC}"
rm -rf /opt/sonicwall-flow-reporter
rm -rf /var/lib/sonicwall-flow-reporter
rm -rf /var/log/sonicwall-flow-reporter
rm -rf /etc/sonicwall-flow-reporter

echo -e "\n${GREEN}Removing service user...${NC}"
userdel swfr 2>/dev/null || true

echo -e "\n${GREEN}Cleaning up apt...${NC}"
apt-get autoremove -y

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              Uninstall Complete                               ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Note: Firewall rules were not removed. To remove them manually:"
echo "  sudo ufw delete allow 2055/udp"
echo "  sudo ufw delete allow 3000/tcp"
echo "  sudo ufw delete allow 8080/tcp"
echo ""

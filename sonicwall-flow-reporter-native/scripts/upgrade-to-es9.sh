#!/bin/bash
#
# SonicWall Flow Reporter - Upgrade to Elasticsearch 9.x
# 
# This script upgrades an existing ES 8.x installation to ES 9.x
# and updates the Python libraries to match.
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║    SonicWall Flow Reporter - Upgrade to Elasticsearch 9.x     ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}ERROR: This script must be run as root (use sudo)${NC}"
   exit 1
fi

# Check current ES version
echo -e "${GREEN}Checking current Elasticsearch version...${NC}"
ES_VERSION=$(curl -s http://localhost:9200 | grep -o '"number" : "[^"]*"' | cut -d'"' -f4 || echo "unknown")
echo "  Current version: $ES_VERSION"

if [[ $ES_VERSION == 9.* ]]; then
    echo -e "${YELLOW}Elasticsearch is already version 9.x${NC}"
    echo "Updating Python libraries only..."
else
    echo ""
    echo -e "${YELLOW}This will upgrade Elasticsearch from $ES_VERSION to 9.x${NC}"
    echo -e "${YELLOW}Your data will be preserved, but please backup first!${NC}"
    echo ""
    read -p "Continue with upgrade? (yes/N) " -r
    if [[ ! $REPLY == "yes" ]]; then
        echo "Upgrade cancelled."
        exit 0
    fi
    
    # Stop services
    echo -e "\n${GREEN}Stopping services...${NC}"
    systemctl stop swfr-collector 2>/dev/null || true
    systemctl stop swfr-identity 2>/dev/null || true
    systemctl stop elasticsearch
    
    # Update repository to 9.x
    echo -e "\n${GREEN}Updating Elasticsearch repository to 9.x...${NC}"
    rm -f /etc/apt/sources.list.d/elastic-8.x.list 2>/dev/null || true
    echo "deb [signed-by=/usr/share/keyrings/elasticsearch-keyring.gpg] https://artifacts.elastic.co/packages/9.x/apt stable main" | tee /etc/apt/sources.list.d/elastic-9.x.list
    
    # Upgrade Elasticsearch
    echo -e "\n${GREEN}Upgrading Elasticsearch...${NC}"
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y elasticsearch
    
    # Start Elasticsearch
    echo -e "\n${GREEN}Starting Elasticsearch...${NC}"
    systemctl start elasticsearch
    
    # Wait for ES to be ready
    echo -n "  Waiting for Elasticsearch..."
    for i in {1..60}; do
        if curl -s http://127.0.0.1:9200/_cluster/health > /dev/null 2>&1; then
            echo -e " ${GREEN}ready${NC}"
            break
        fi
        echo -n "."
        sleep 2
    done
fi

# Update Python libraries
echo -e "\n${GREEN}Updating Python elasticsearch library to 9.x...${NC}"

# Identity UI
if [ -d "/opt/sonicwall-flow-reporter/identity-ui/venv" ]; then
    echo "  Updating identity-ui..."
    /opt/sonicwall-flow-reporter/identity-ui/venv/bin/pip uninstall -y elasticsearch 2>/dev/null || true
    /opt/sonicwall-flow-reporter/identity-ui/venv/bin/pip install 'elasticsearch>=9.0.0,<10.0.0'
fi

# Collector
if [ -d "/opt/sonicwall-flow-reporter/collector/venv" ]; then
    echo "  Updating collector..."
    /opt/sonicwall-flow-reporter/collector/venv/bin/pip uninstall -y elasticsearch 2>/dev/null || true
    /opt/sonicwall-flow-reporter/collector/venv/bin/pip install 'elasticsearch>=9.0.0,<10.0.0'
fi

# Restart services
echo -e "\n${GREEN}Restarting services...${NC}"
systemctl start swfr-collector 2>/dev/null || true
systemctl start swfr-identity 2>/dev/null || true

# Verify
sleep 3
echo ""
echo -e "${GREEN}Verification:${NC}"
NEW_VERSION=$(curl -s http://localhost:9200 | grep -o '"number" : "[^"]*"' | cut -d'"' -f4 || echo "unknown")
echo "  Elasticsearch version: $NEW_VERSION"
echo "  swfr-collector: $(systemctl is-active swfr-collector 2>/dev/null || echo 'not installed')"
echo "  swfr-identity: $(systemctl is-active swfr-identity 2>/dev/null || echo 'not installed')"

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    Upgrade Complete!                          ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Test the Identity UI at: http://$(hostname -I | awk '{print $1}'):8080"

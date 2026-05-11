#!/bin/bash
#
# SonicWall Flow Reporter - Host Setup Script
# Supported: Debian 12/13, Ubuntu 22.04/24.04
#
# This script:
# 1. Updates the system
# 2. Installs Docker and Docker Compose
# 3. Configures firewall rules
# 4. Creates directory structure
# 5. Configures system limits for Elasticsearch
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

INSTALL_DIR="/opt/sonicwall-flow-reporter"

print_banner() {
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║                                                               ║"
    echo "║           SonicWall Flow Reporter - Setup Script              ║"
    echo "║                                                               ║"
    echo "║   IPFIX/NetFlow Collection • Grafana Dashboards • Identity    ║"
    echo "║                                                               ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_banner

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}ERROR: This script must be run as root (use sudo)${NC}"
   exit 1
fi

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    VERSION=$VERSION_ID
    CODENAME=$VERSION_CODENAME
else
    echo -e "${RED}ERROR: Cannot detect OS. Supported: Debian 12/13, Ubuntu 22.04/24.04${NC}"
    exit 1
fi

echo -e "${GREEN}Detected OS:${NC} $PRETTY_NAME"
echo ""

# ============================================================================
# Step 1: System Update
# ============================================================================
echo -e "${GREEN}[1/6] Updating system packages...${NC}"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

# ============================================================================
# Step 2: Install Prerequisites
# ============================================================================
echo -e "\n${GREEN}[2/6] Installing prerequisites...${NC}"
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    ufw \
    htop \
    jq \
    unzip

# ============================================================================
# Step 3: Install Docker
# ============================================================================
echo -e "\n${GREEN}[3/6] Installing Docker...${NC}"

# Check if Docker is already installed
if command -v docker &> /dev/null; then
    echo -e "${YELLOW}Docker already installed, verifying...${NC}"
    docker --version
    
    # Ensure docker compose plugin is available
    if ! docker compose version &> /dev/null; then
        echo -e "${YELLOW}Installing Docker Compose plugin...${NC}"
        apt-get install -y docker-compose-plugin
    fi
else
    # Remove old Docker versions if present
    apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

    # Add Docker's official GPG key
    install -m 0755 -d /etc/apt/keyrings
    
    # Determine the correct Docker repo
    DOCKER_OS=$OS
    DOCKER_CODENAME=$CODENAME
    
    # Handle Debian 13 (trixie) - use bookworm repo
    if [ "$OS" = "debian" ] && [ "$CODENAME" = "trixie" ]; then
        DOCKER_CODENAME="bookworm"
        echo -e "${YELLOW}Note: Using Docker bookworm repo for Debian 13 (trixie)${NC}"
    fi
    
    # Handle Ubuntu 24.04 (noble)
    if [ "$OS" = "ubuntu" ] && [ "$CODENAME" = "noble" ]; then
        DOCKER_CODENAME="noble"
    fi
    
    curl -fsSL https://download.docker.com/linux/$DOCKER_OS/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$DOCKER_OS \
      $DOCKER_CODENAME stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

    # Install Docker
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin

    # Start and enable Docker
    systemctl start docker
    systemctl enable docker
fi

# Verify Docker installation
echo -e "${GREEN}Docker version:${NC}"
docker --version
docker compose version

# ============================================================================
# Step 4: Configure Firewall
# ============================================================================
echo -e "\n${GREEN}[4/6] Configuring firewall...${NC}"

# Enable UFW
ufw --force enable

# Allow SSH
ufw allow 22/tcp comment 'SSH'

# Allow IPFIX
ufw allow 2055/udp comment 'IPFIX from SonicWall'

# Allow Grafana
ufw allow 3000/tcp comment 'Grafana Web UI'

# Allow Identity UI
ufw allow 8080/tcp comment 'Identity Management UI'

echo -e "${GREEN}Firewall rules:${NC}"
ufw status numbered

# ============================================================================
# Step 5: Create Directory Structure
# ============================================================================
echo -e "\n${GREEN}[5/6] Creating directory structure...${NC}"

mkdir -p $INSTALL_DIR/{data/elasticsearch,data/grafana,data/identity-db,logs}

# Set permissions for Elasticsearch (runs as uid 1000)
chown -R 1000:1000 $INSTALL_DIR/data/elasticsearch

# Set permissions for Grafana (runs as uid 472)
chown -R 472:472 $INSTALL_DIR/data/grafana

echo -e "${GREEN}Created:${NC} $INSTALL_DIR"
ls -la $INSTALL_DIR/

# ============================================================================
# Step 6: Configure System Limits for Elasticsearch
# ============================================================================
echo -e "\n${GREEN}[6/6] Configuring system limits for Elasticsearch...${NC}"

# Set vm.max_map_count (required for Elasticsearch)
if ! grep -q "vm.max_map_count=262144" /etc/sysctl.conf; then
    echo "vm.max_map_count=262144" >> /etc/sysctl.conf
fi
sysctl -w vm.max_map_count=262144

echo -e "${GREEN}vm.max_map_count set to 262144${NC}"

# ============================================================================
# Summary
# ============================================================================
SERVER_IP=$(hostname -I | awk '{print $1}')

echo ""
echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                     Setup Complete! ✓                         ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Server IP:${NC} $SERVER_IP"
echo -e "${GREEN}Install Directory:${NC} $INSTALL_DIR"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo "  1. Copy project files to $INSTALL_DIR:"
echo -e "     ${CYAN}sudo cp -r . $INSTALL_DIR/${NC}"
echo ""
echo "  2. Configure the application:"
echo -e "     ${CYAN}cd $INSTALL_DIR${NC}"
echo -e "     ${CYAN}sudo cp .env.example .env${NC}"
echo -e "     ${CYAN}sudo nano .env${NC}  # Set your passwords!"
echo ""
echo "  3. Start the services:"
echo -e "     ${CYAN}sudo docker compose up -d${NC}"
echo ""
echo "  4. Configure SonicWall IPFIX to send to:"
echo -e "     ${CYAN}$SERVER_IP:2055${NC}"
echo ""
echo -e "${GREEN}Access Points (after starting services):${NC}"
echo -e "  Grafana:      ${CYAN}http://$SERVER_IP:3000${NC}"
echo -e "  Identity UI:  ${CYAN}http://$SERVER_IP:8080${NC}"
echo ""

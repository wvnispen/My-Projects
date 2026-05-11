#!/bin/bash
#
# SonicWall Flow Reporter - Native Ubuntu 24.04 Installation
# 
# This script installs all components directly on the host OS:
# - Elasticsearch 9.x
# - Grafana OSS
# - Python IPFIX Collector (systemd service)
# - Python Identity UI (systemd service)
#
# Tested on: Ubuntu 24.04 LTS
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
INSTALL_DIR="/opt/sonicwall-flow-reporter"
DATA_DIR="/var/lib/sonicwall-flow-reporter"
LOG_DIR="/var/log/sonicwall-flow-reporter"
CONFIG_FILE="/etc/sonicwall-flow-reporter/config.env"
SERVICE_USER="swfr"

print_banner() {
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║                                                               ║"
    echo "║      SonicWall Flow Reporter - Native Linux Installation      ║"
    echo "║                                                               ║"
    echo "║          Ubuntu 24.04 LTS • No Docker Required                ║"
    echo "║                                                               ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo -e "${RED}ERROR: This script must be run as root (use sudo)${NC}"
        exit 1
    fi
}

check_ubuntu() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        if [ "$ID" != "ubuntu" ]; then
            echo -e "${YELLOW}WARNING: This script is designed for Ubuntu. Detected: $ID${NC}"
            read -p "Continue anyway? (y/N) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 1
            fi
        fi
    fi
    echo -e "${GREEN}OS Check:${NC} $PRETTY_NAME"
}

# ============================================================================
# STEP 1: System Preparation
# ============================================================================
install_prerequisites() {
    echo -e "\n${GREEN}[1/8] Installing prerequisites...${NC}"
    
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        apt-transport-https \
        ca-certificates \
        curl \
        gnupg \
        lsb-release \
        software-properties-common \
        ufw \
        htop \
        jq \
        unzip \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        build-essential \
        default-jdk
    
    echo -e "${GREEN}Prerequisites installed${NC}"
}

# ============================================================================
# STEP 2: Create Service User and Directories
# ============================================================================
create_user_and_dirs() {
    echo -e "\n${GREEN}[2/8] Creating service user and directories...${NC}"
    
    # Create service user (no login shell)
    if ! id "$SERVICE_USER" &>/dev/null; then
        useradd --system --no-create-home --shell /usr/sbin/nologin $SERVICE_USER
        echo -e "  Created user: ${CYAN}$SERVICE_USER${NC}"
    else
        echo -e "  User already exists: ${CYAN}$SERVICE_USER${NC}"
    fi
    
    # Create directories
    mkdir -p $INSTALL_DIR/{collector,identity-ui}
    mkdir -p $DATA_DIR/{elasticsearch,identity-db}
    mkdir -p $LOG_DIR
    mkdir -p /etc/sonicwall-flow-reporter
    
    echo -e "${GREEN}Directories created${NC}"
}

# ============================================================================
# STEP 3: Install Elasticsearch
# ============================================================================
install_elasticsearch() {
    echo -e "\n${GREEN}[3/8] Installing Elasticsearch 9.x...${NC}"
    
    # Check if already installed
    if systemctl is-active --quiet elasticsearch; then
        echo -e "${YELLOW}Elasticsearch already running, skipping installation${NC}"
        return
    fi
    
    # Import Elasticsearch GPG key
    curl -fsSL https://artifacts.elastic.co/GPG-KEY-elasticsearch | gpg --dearmor -o /usr/share/keyrings/elasticsearch-keyring.gpg
    
    # Add repository
    echo "deb [signed-by=/usr/share/keyrings/elasticsearch-keyring.gpg] https://artifacts.elastic.co/packages/9.x/apt stable main" | tee /etc/apt/sources.list.d/elastic-9.x.list
    
    # Install
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y elasticsearch
    
    # Configure Elasticsearch
    cat > /etc/elasticsearch/elasticsearch.yml << 'EOF'
# SonicWall Flow Reporter - Elasticsearch Configuration
cluster.name: sonicwall-flow-reporter
node.name: node-1
path.data: /var/lib/elasticsearch
path.logs: /var/log/elasticsearch
network.host: 127.0.0.1
http.port: 9200

# Disable security for local-only access (simpler setup)
xpack.security.enabled: false
xpack.security.enrollment.enabled: false
xpack.security.http.ssl.enabled: false
xpack.security.transport.ssl.enabled: false

# Memory settings
indices.memory.index_buffer_size: 20%

# Discovery for single node
discovery.type: single-node
EOF

    # Configure JVM heap (use 50% of RAM, max 4GB for small deployments)
    TOTAL_MEM=$(free -g | awk '/^Mem:/{print $2}')
    HEAP_SIZE=$((TOTAL_MEM / 2))
    if [ $HEAP_SIZE -lt 1 ]; then HEAP_SIZE=1; fi
    if [ $HEAP_SIZE -gt 4 ]; then HEAP_SIZE=4; fi
    
    cat > /etc/elasticsearch/jvm.options.d/heap.options << EOF
-Xms${HEAP_SIZE}g
-Xmx${HEAP_SIZE}g
EOF
    
    echo -e "  Elasticsearch heap: ${CYAN}${HEAP_SIZE}GB${NC}"
    
    # Set vm.max_map_count
    if ! grep -q "vm.max_map_count=262144" /etc/sysctl.conf; then
        echo "vm.max_map_count=262144" >> /etc/sysctl.conf
    fi
    sysctl -w vm.max_map_count=262144
    
    # Enable and start
    systemctl daemon-reload
    systemctl enable elasticsearch
    systemctl start elasticsearch
    
    # Wait for Elasticsearch to be ready
    echo -n "  Waiting for Elasticsearch to start..."
    for i in {1..60}; do
        if curl -s http://127.0.0.1:9200/_cluster/health > /dev/null 2>&1; then
            echo -e " ${GREEN}ready${NC}"
            break
        fi
        echo -n "."
        sleep 2
    done
    
    echo -e "${GREEN}Elasticsearch installed and running${NC}"
}

# ============================================================================
# STEP 4: Setup Elasticsearch Indices
# ============================================================================
setup_elasticsearch_indices() {
    echo -e "\n${GREEN}[4/8] Setting up Elasticsearch indices...${NC}"
    
    ES_URL="http://127.0.0.1:9200"
    
    # Wait for ES to be fully ready
    until curl -s "$ES_URL/_cluster/health" | grep -q '"status":"green"\|"status":"yellow"'; do
        echo "  Waiting for Elasticsearch cluster..."
        sleep 5
    done
    
    # Create ILM policy
    echo "  Creating ILM policy..."
    curl -s -X PUT "$ES_URL/_ilm/policy/flows-policy" -H 'Content-Type: application/json' -d '{
        "policy": {
            "phases": {
                "hot": {
                    "min_age": "0ms",
                    "actions": {
                        "rollover": {
                            "max_age": "1d",
                            "max_primary_shard_size": "10gb"
                        }
                    }
                },
                "warm": {
                    "min_age": "7d",
                    "actions": {
                        "shrink": { "number_of_shards": 1 },
                        "forcemerge": { "max_num_segments": 1 }
                    }
                },
                "delete": {
                    "min_age": "30d",
                    "actions": { "delete": {} }
                }
            }
        }
    }' > /dev/null
    
    # Create index template for flows
    echo "  Creating index template..."
    curl -s -X PUT "$ES_URL/_index_template/flows-template" -H 'Content-Type: application/json' -d '{
        "index_patterns": ["flows-*"],
        "template": {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "index.lifecycle.name": "flows-policy",
                "index.lifecycle.rollover_alias": "flows"
            },
            "mappings": {
                "properties": {
                    "@timestamp": { "type": "date" },
                    "src_ip": { "type": "ip" },
                    "dst_ip": { "type": "ip" },
                    "src_port": { "type": "integer" },
                    "dst_port": { "type": "integer" },
                    "protocol": { "type": "keyword" },
                    "bytes_in": { "type": "long" },
                    "bytes_out": { "type": "long" },
                    "packets_in": { "type": "long" },
                    "packets_out": { "type": "long" },
                    "user_id": { "type": "keyword" },
                    "user_name": { "type": "keyword" },
                    "src_user": { "type": "keyword" },
                    "dst_user": { "type": "keyword" },
                    "application": { "type": "keyword" },
                    "action": { "type": "keyword" },
                    "interface_in": { "type": "keyword" },
                    "interface_out": { "type": "keyword" },
                    "flow_duration": { "type": "long" },
                    "firewall_ip": { "type": "ip" },
                    "src_mac": { "type": "keyword" },
                    "dst_mac": { "type": "keyword" }
                }
            }
        }
    }' > /dev/null
    
    # Create identity mappings index
    echo "  Creating identity index..."
    curl -s -X PUT "$ES_URL/identity-mappings" -H 'Content-Type: application/json' -d '{
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0
        },
        "mappings": {
            "properties": {
                "ip_address": { "type": "ip" },
                "user_id": { "type": "keyword" },
                "user_name": { "type": "keyword" },
                "mac_address": { "type": "keyword" },
                "hostname": { "type": "keyword" },
                "department": { "type": "keyword" },
                "location": { "type": "keyword" },
                "source": { "type": "keyword" },
                "created_at": { "type": "date" },
                "updated_at": { "type": "date" },
                "expires_at": { "type": "date" }
            }
        }
    }' > /dev/null
    
    # Create initial flows index
    echo "  Creating initial flows index..."
    curl -s -X PUT "$ES_URL/flows-000001" -H 'Content-Type: application/json' -d '{
        "aliases": {
            "flows": { "is_write_index": true },
            "flows-raw": {}
        }
    }' > /dev/null
    
    echo -e "${GREEN}Elasticsearch indices configured${NC}"
}

# ============================================================================
# STEP 5: Install Grafana
# ============================================================================
install_grafana() {
    echo -e "\n${GREEN}[5/8] Installing Grafana...${NC}"
    
    # Check if already installed
    if systemctl is-active --quiet grafana-server; then
        echo -e "${YELLOW}Grafana already running, skipping installation${NC}"
        return
    fi
    
    # Import Grafana GPG key
    curl -fsSL https://apt.grafana.com/gpg.key | gpg --dearmor -o /usr/share/keyrings/grafana-keyring.gpg
    
    # Add repository
    echo "deb [signed-by=/usr/share/keyrings/grafana-keyring.gpg] https://apt.grafana.com stable main" | tee /etc/apt/sources.list.d/grafana.list
    
    # Install
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y grafana
    
    # Configure Grafana
    cat >> /etc/grafana/grafana.ini << 'EOF'

# SonicWall Flow Reporter Configuration
[server]
http_port = 3000

[security]
admin_user = admin

[users]
allow_sign_up = false

[auth.anonymous]
enabled = false
EOF

    # Enable and start
    systemctl daemon-reload
    systemctl enable grafana-server
    systemctl start grafana-server
    
    # Wait for Grafana to be ready
    echo -n "  Waiting for Grafana to start..."
    for i in {1..30}; do
        if curl -s http://127.0.0.1:3000/api/health > /dev/null 2>&1; then
            echo -e " ${GREEN}ready${NC}"
            break
        fi
        echo -n "."
        sleep 1
    done
    
    echo -e "${GREEN}Grafana installed and running${NC}"
}

# ============================================================================
# STEP 6: Configure Grafana Datasource and Dashboard
# ============================================================================
configure_grafana() {
    echo -e "\n${GREEN}[6/8] Configuring Grafana datasource and dashboards...${NC}"
    
    GRAFANA_URL="http://127.0.0.1:3000"
    GRAFANA_CREDS="admin:admin"
    
    # Setup provisioning directories
    echo "  Setting up Grafana provisioning..."
    mkdir -p /etc/grafana/provisioning/datasources
    mkdir -p /etc/grafana/provisioning/dashboards
    mkdir -p /var/lib/grafana/dashboards
    
    # Copy datasource provisioning
    cat > /etc/grafana/provisioning/datasources/sonicwall.yml << 'EOF'
apiVersion: 1

datasources:
  - name: Elasticsearch-Flows
    type: elasticsearch
    access: proxy
    url: http://127.0.0.1:9200
    database: "flows-*"
    jsonData:
      timeField: "@timestamp"
      esVersion: "9.0.0"
      maxConcurrentShardRequests: 5
      logMessageField: ""
      logLevelField: ""
    isDefault: true
EOF
    
    # Copy dashboard provisioning
    cat > /etc/grafana/provisioning/dashboards/sonicwall.yml << 'EOF'
apiVersion: 1

providers:
  - name: 'SonicWall Flow Reporter'
    orgId: 1
    folder: 'SonicWall'
    folderUid: 'sonicwall'
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
EOF
    
    # Copy all dashboard files
    echo "  Installing dashboards..."
    if [ -d "$INSTALL_DIR/grafana/dashboards" ]; then
        cp -f "$INSTALL_DIR/grafana/dashboards/"*.json /var/lib/grafana/dashboards/
        chown -R grafana:grafana /var/lib/grafana/dashboards/
    fi
    
    # Set permissions
    chown -R root:grafana /etc/grafana/provisioning/
    chmod -R 640 /etc/grafana/provisioning/datasources/*
    chmod -R 640 /etc/grafana/provisioning/dashboards/*
    
    # Restart Grafana to load provisioning
    systemctl restart grafana-server
    sleep 3
    
    echo -e "${GREEN}Grafana configured with provisioning${NC}"
}

# ============================================================================
# STEP 7: Install Python Applications
# ============================================================================
install_python_apps() {
    echo -e "\n${GREEN}[7/8] Installing Python applications...${NC}"
    
    # Get the source directory (where this script is located)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    
    # Copy collector files
    echo "  Installing IPFIX Collector..."
    cp -r "$SCRIPT_DIR/collector/"* "$INSTALL_DIR/collector/"
    
    # Copy identity-ui files
    echo "  Installing Identity UI..."
    cp -r "$SCRIPT_DIR/identity-ui/"* "$INSTALL_DIR/identity-ui/"
    
    # Remove Docker files
    rm -f "$INSTALL_DIR/collector/Dockerfile" 2>/dev/null
    rm -f "$INSTALL_DIR/identity-ui/Dockerfile" 2>/dev/null
    
    # Create Python virtual environments
    echo "  Creating virtual environments..."
    
    # Collector venv
    python3 -m venv "$INSTALL_DIR/collector/venv"
    "$INSTALL_DIR/collector/venv/bin/pip" install --upgrade pip
    "$INSTALL_DIR/collector/venv/bin/pip" install \
        'elasticsearch>=9.0.0,<10.0.0' \
        python-dateutil \
        requests
    
    # Identity UI venv
    python3 -m venv "$INSTALL_DIR/identity-ui/venv"
    "$INSTALL_DIR/identity-ui/venv/bin/pip" install --upgrade pip
    "$INSTALL_DIR/identity-ui/venv/bin/pip" install \
        'fastapi>=0.100.0' \
        'uvicorn[standard]>=0.23.0' \
        'elasticsearch>=9.0.0,<10.0.0' \
        requests \
        python-multipart \
        python-dateutil \
        jinja2 \
        'passlib[bcrypt]' \
        aiofiles \
        httpx
    
    # Copy Grafana files
    echo "  Installing Grafana dashboards..."
    mkdir -p "$INSTALL_DIR/grafana"
    cp -r "$SCRIPT_DIR/grafana/"* "$INSTALL_DIR/grafana/"
    
    # Set ownership
    chown -R $SERVICE_USER:$SERVICE_USER $INSTALL_DIR
    chown -R $SERVICE_USER:$SERVICE_USER $DATA_DIR
    chown -R $SERVICE_USER:$SERVICE_USER $LOG_DIR
    
    echo -e "${GREEN}Python applications installed${NC}"
}

# ============================================================================
# STEP 8: Create Systemd Services
# ============================================================================
create_systemd_services() {
    echo -e "\n${GREEN}[8/8] Creating systemd services...${NC}"
    
    # Create config file
    cat > $CONFIG_FILE << 'EOF'
# SonicWall Flow Reporter Configuration
# Edit these values for your environment

# Elasticsearch
ELASTICSEARCH_HOST=127.0.0.1
ELASTICSEARCH_PORT=9200

# IPFIX Collector
IPFIX_LISTEN_IP=0.0.0.0
IPFIX_LISTEN_PORT=2055

# Identity UI
IDENTITY_UI_HOST=0.0.0.0
IDENTITY_UI_PORT=8080
IDENTITY_ADMIN_PASSWORD=admin
SECRET_KEY=change-this-to-a-random-string-32chars

# Optional: SonicWall SSO
SONICWALL_SSO_ENABLED=false
SONICWALL_HOST=
SONICWALL_API_USER=
SONICWALL_API_PASSWORD=
EOF
    
    chmod 600 $CONFIG_FILE
    chown root:$SERVICE_USER $CONFIG_FILE
    
    # IPFIX Collector Service
    cat > /etc/systemd/system/swfr-collector.service << EOF
[Unit]
Description=SonicWall Flow Reporter - IPFIX Collector
After=network.target elasticsearch.service
Wants=elasticsearch.service

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR/collector
EnvironmentFile=$CONFIG_FILE
ExecStart=$INSTALL_DIR/collector/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=append:$LOG_DIR/collector.log
StandardError=append:$LOG_DIR/collector.log

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DATA_DIR $LOG_DIR
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

    # Identity UI Service
    cat > /etc/systemd/system/swfr-identity.service << EOF
[Unit]
Description=SonicWall Flow Reporter - Identity Management UI
After=network.target elasticsearch.service
Wants=elasticsearch.service

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR/identity-ui
EnvironmentFile=$CONFIG_FILE
Environment="PYTHONUNBUFFERED=1"
ExecStart=$INSTALL_DIR/identity-ui/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=10
StandardOutput=append:$LOG_DIR/identity-ui.log
StandardError=append:$LOG_DIR/identity-ui.log

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DATA_DIR $LOG_DIR $INSTALL_DIR
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

    # Aggregator Service (runs hourly via timer)
    cat > /etc/systemd/system/swfr-aggregator.service << EOF
[Unit]
Description=SonicWall Flow Reporter - Data Aggregator
After=network.target elasticsearch.service

[Service]
Type=oneshot
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR/collector
EnvironmentFile=$CONFIG_FILE
ExecStart=$INSTALL_DIR/collector/venv/bin/python aggregator.py
StandardOutput=append:$LOG_DIR/aggregator.log
StandardError=append:$LOG_DIR/aggregator.log
EOF

    cat > /etc/systemd/system/swfr-aggregator.timer << EOF
[Unit]
Description=Run SonicWall Flow Reporter Aggregator Hourly

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
EOF

    # Reload systemd and enable services
    systemctl daemon-reload
    systemctl enable swfr-collector.service
    systemctl enable swfr-identity.service
    systemctl enable swfr-aggregator.timer
    
    echo -e "${GREEN}Systemd services created${NC}"
}

# ============================================================================
# STEP 9: Configure Firewall
# ============================================================================
configure_firewall() {
    echo -e "\n${GREEN}Configuring firewall...${NC}"
    
    ufw --force enable
    ufw allow 22/tcp comment 'SSH'
    ufw allow 2055/udp comment 'IPFIX from SonicWall'
    ufw allow 3000/tcp comment 'Grafana Web UI'
    ufw allow 8080/tcp comment 'Identity Management UI'
    
    echo -e "${GREEN}Firewall configured${NC}"
}

# ============================================================================
# STEP 10: Start Services
# ============================================================================
start_services() {
    echo -e "\n${GREEN}Starting services...${NC}"
    
    systemctl start swfr-collector.service
    systemctl start swfr-identity.service
    systemctl start swfr-aggregator.timer
    
    sleep 3
    
    # Check status
    echo ""
    echo -e "${CYAN}Service Status:${NC}"
    echo -e "  Elasticsearch: $(systemctl is-active elasticsearch)"
    echo -e "  Grafana:       $(systemctl is-active grafana-server)"
    echo -e "  Collector:     $(systemctl is-active swfr-collector)"
    echo -e "  Identity UI:   $(systemctl is-active swfr-identity)"
}

# ============================================================================
# Summary
# ============================================================================
print_summary() {
    SERVER_IP=$(hostname -I | awk '{print $1}')
    
    echo ""
    echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║              Installation Complete! ✓                         ║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${GREEN}Server IP:${NC} $SERVER_IP"
    echo ""
    echo -e "${YELLOW}Access Points:${NC}"
    echo -e "  Grafana:      ${CYAN}http://$SERVER_IP:3000${NC}  (admin/admin)"
    echo -e "  Identity UI:  ${CYAN}http://$SERVER_IP:8080${NC}  (admin/admin)"
    echo ""
    echo -e "${YELLOW}Configure SonicWall IPFIX:${NC}"
    echo -e "  Collector IP: ${CYAN}$SERVER_IP${NC}"
    echo -e "  Port:         ${CYAN}2055${NC} (UDP)"
    echo ""
    echo -e "${YELLOW}Configuration File:${NC}"
    echo -e "  ${CYAN}$CONFIG_FILE${NC}"
    echo ""
    echo -e "${YELLOW}Service Management:${NC}"
    echo -e "  ${CYAN}sudo systemctl status swfr-collector${NC}"
    echo -e "  ${CYAN}sudo systemctl status swfr-identity${NC}"
    echo -e "  ${CYAN}sudo journalctl -u swfr-collector -f${NC}"
    echo ""
    echo -e "${YELLOW}Log Files:${NC}"
    echo -e "  ${CYAN}$LOG_DIR/collector.log${NC}"
    echo -e "  ${CYAN}$LOG_DIR/identity-ui.log${NC}"
    echo ""
    echo -e "${RED}IMPORTANT:${NC} Change the default passwords!"
    echo -e "  1. Edit ${CYAN}$CONFIG_FILE${NC}"
    echo -e "  2. Change Grafana admin password in web UI"
    echo ""
}

# ============================================================================
# Main
# ============================================================================
main() {
    print_banner
    check_root
    check_ubuntu
    
    install_prerequisites
    create_user_and_dirs
    install_elasticsearch
    setup_elasticsearch_indices
    install_grafana
    install_python_apps
    create_systemd_services
    configure_firewall
    configure_grafana
    start_services
    print_summary
}

main "$@"

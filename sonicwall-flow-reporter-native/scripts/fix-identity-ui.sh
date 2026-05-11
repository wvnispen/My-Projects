#!/bin/bash
#
# SonicWall Flow Reporter - Fix Identity UI Service
# Run this on an existing installation to fix the identity-ui service
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="/opt/sonicwall-flow-reporter"
LOG_DIR="/var/log/sonicwall-flow-reporter"
DATA_DIR="/var/lib/sonicwall-flow-reporter"
CONFIG_FILE="/etc/sonicwall-flow-reporter/config.env"
SERVICE_USER="swfr"

echo -e "${GREEN}Fixing SonicWall Flow Reporter Identity UI...${NC}"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}ERROR: This script must be run as root (use sudo)${NC}"
   exit 1
fi

# Stop the service
echo "Stopping identity-ui service..."
systemctl stop swfr-identity 2>/dev/null || true

# Update the app.py to fix environment variable names
echo "Patching app.py..."
if [ -f "$INSTALL_DIR/identity-ui/app.py" ]; then
    # Fix ADMIN_PASSWORD to also check IDENTITY_ADMIN_PASSWORD
    sed -i "s/ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD'/ADMIN_PASSWORD = os.environ.get('IDENTITY_ADMIN_PASSWORD', os.environ.get('ADMIN_PASSWORD'/g" "$INSTALL_DIR/identity-ui/app.py"
    
    # Fix static files mounting
    sed -i 's|app.mount("/static", StaticFiles(directory="static")|# Static files disabled - directory empty|g' "$INSTALL_DIR/identity-ui/app.py"
fi

# Ensure templates directory path is absolute
echo "Fixing template paths..."
cat > "$INSTALL_DIR/identity-ui/app_wrapper.py" << 'WRAPPER'
#!/usr/bin/env python3
"""Wrapper to ensure correct working directory"""
import os
import sys

# Change to the identity-ui directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
WRAPPER

# Update systemd service
echo "Updating systemd service..."
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
StandardOutput=journal
StandardError=journal

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DATA_DIR $LOG_DIR $INSTALL_DIR
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# Fix permissions
echo "Fixing permissions..."
chown -R $SERVICE_USER:$SERVICE_USER $INSTALL_DIR
chmod 755 $INSTALL_DIR/identity-ui

# Ensure all required packages are installed
echo "Checking Python packages..."
$INSTALL_DIR/identity-ui/venv/bin/pip install --quiet \
    fastapi>=0.100.0 \
    uvicorn[standard]>=0.23.0 \
    elasticsearch>=8.0.0 \
    python-multipart \
    python-dateutil \
    jinja2 \
    passlib[bcrypt] \
    aiofiles \
    httpx 2>/dev/null || true

# Reload systemd
systemctl daemon-reload

# Start the service
echo "Starting identity-ui service..."
systemctl start swfr-identity

# Wait a moment
sleep 3

# Check status
echo ""
echo -e "${GREEN}Service status:${NC}"
systemctl status swfr-identity --no-pager -l

echo ""
echo -e "${GREEN}Testing connection...${NC}"
sleep 2
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ | grep -q "401\|200"; then
    echo -e "${GREEN}✓ Identity UI is responding on port 8080${NC}"
else
    echo -e "${YELLOW}Identity UI may still be starting. Check logs:${NC}"
    echo "  sudo journalctl -u swfr-identity -f"
fi

echo ""
echo -e "${GREEN}Done!${NC}"
echo ""
echo "Access the Identity UI at: http://$(hostname -I | awk '{print $1}'):8080"
echo "Default credentials: admin / admin"
echo ""
echo "View logs with: sudo journalctl -u swfr-identity -f"

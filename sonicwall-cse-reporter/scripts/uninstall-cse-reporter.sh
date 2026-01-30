#!/bin/bash
set -e
echo "SonicWall CSE Reporter - Uninstaller"
[[ $EUID -ne 0 ]] && { echo "Run as root"; exit 1; }
read -p "Remove CSE Reporter components? (y/N): " -n1 -r; echo
[[ ! $REPLY =~ ^[Yy]$ ]] && exit 0

systemctl stop cse-collector 2>/dev/null || true
systemctl disable cse-collector 2>/dev/null || true
rm -f /etc/systemd/system/cse-collector.service
systemctl daemon-reload

read -p "Remove collector data? (y/N): " -n1 -r; echo
[[ $REPLY =~ ^[Yy]$ ]] && rm -rf /opt/cse-collector /etc/cse-collector /var/lib/cse-collector /var/log/cse-collector

systemctl stop loki 2>/dev/null || true
apt-get remove -y loki 2>/dev/null || true
read -p "Remove Loki data? (y/N): " -n1 -r; echo
[[ $REPLY =~ ^[Yy]$ ]] && rm -rf /var/lib/loki /etc/loki

# Remove dashboards from Grafana
curl -s -u admin:admin "http://localhost:3000/api/folders" 2>/dev/null | python3 -c "
import sys,json
try:
    folders=json.load(sys.stdin)
    uid=next((f['uid'] for f in folders if f['title']=='SonicWall CSE'), None)
    if uid: print(uid)
except: pass
" | while read uid; do
    curl -s -X DELETE -u admin:admin "http://localhost:3000/api/folders/$uid" >/dev/null
done

echo "Uninstall complete"

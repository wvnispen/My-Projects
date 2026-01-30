# Troubleshooting Guide

## Quick Health Check

```bash
# Check all services
sudo systemctl status cse-collector loki grafana-server

# View collector logs
sudo journalctl -u cse-collector -n 50

# Check Loki is receiving data
curl -s "http://localhost:3100/loki/api/v1/labels" | jq
```

## Common Issues

### No Data in Dashboards

1. **Check collector status:**
   ```bash
   sudo systemctl status cse-collector
   ```

2. **Check for successful sends:**
   ```bash
   sudo journalctl -u cse-collector | grep "Successfully sent"
   ```

3. **Verify API key:**
   ```bash
   cat /etc/cse-collector/env
   ```
   Should show: `CSE_API_KEY=your-actual-key`

4. **Check Loki has labels:**
   ```bash
   curl -s "http://localhost:3100/loki/api/v1/labels" | jq
   ```
   Should show labels like: `event_type`, `category`, `status`

### "entry too far behind" Error

Loki is rejecting events because timestamps are too old. Reset everything:

```bash
# Stop services
sudo systemctl stop cse-collector loki

# Clear Loki data
sudo rm -rf /var/lib/loki/chunks/*
sudo rm -rf /var/lib/loki/wal/*
sudo rm -rf /var/lib/loki/tsdb-shipper-active/*
sudo rm -rf /var/lib/loki/tsdb-shipper-cache/*

# Clear collector cursor
sudo rm -f /var/lib/cse-collector/cursor.json

# Start fresh
sudo systemctl start loki
sleep 5
sudo systemctl start cse-collector
```

### 401 Unauthorized Error

Your CSE API key is invalid or expired.

1. Check current key:
   ```bash
   cat /etc/cse-collector/env
   ```

2. Get new key from CSE Admin Console → Settings → API Keys

3. Update the key:
   ```bash
   sudo nano /etc/cse-collector/env
   # Change: CSE_API_KEY=your-new-key
   ```

4. Restart collector:
   ```bash
   sudo systemctl restart cse-collector
   ```

### Loki Won't Start

1. **Check logs:**
   ```bash
   sudo journalctl -u loki -n 50
   ```

2. **Check disk space:**
   ```bash
   df -h /var/lib/loki
   ```

3. **Fix permissions:**
   ```bash
   sudo chown -R loki:loki /var/lib/loki
   ```

4. **Validate config:**
   ```bash
   /usr/bin/loki -config.file=/etc/loki/config.yml -verify-config
   ```

### Collector Not Starting

1. **Check Python dependencies:**
   ```bash
   python3 -c "import requests, yaml; print('OK')"
   ```

2. **Install if missing:**
   ```bash
   pip3 install --break-system-packages requests pyyaml
   ```

3. **Test collector manually:**
   ```bash
   sudo CSE_API_KEY=your-key /opt/cse-collector/cse-collector.py
   ```

### Dashboard Shows "No Data"

1. **Check time range** - Make sure dashboard time range includes when events were collected

2. **Hard refresh browser** - Ctrl+Shift+R

3. **Check datasource:**
   - Go to Grafana → Connections → Data sources → Loki
   - Click "Save & test"

4. **Query Loki directly:**
   ```bash
   curl -s -G "http://localhost:3100/loki/api/v1/query" \
     --data-urlencode 'query={job="sonicwall-cse"}' | jq '.data.result | length'
   ```
   Should return a number > 0

## Configuration Files

| File | Purpose |
|------|---------|
| `/etc/cse-collector/config.yaml` | Collector settings |
| `/etc/cse-collector/env` | API key |
| `/etc/loki/config.yml` | Loki configuration |
| `/var/lib/cse-collector/cursor.json` | Event cursor state |

## Log Locations

| Component | Log Command |
|-----------|-------------|
| CSE Collector | `sudo journalctl -u cse-collector -f` |
| Loki | `sudo journalctl -u loki -f` |
| Grafana | `sudo journalctl -u grafana-server -f` |

## Getting Help

If issues persist:

1. Collect diagnostic info:
   ```bash
   mkdir -p /tmp/cse-diag
   sudo systemctl status cse-collector loki grafana-server > /tmp/cse-diag/status.txt
   sudo journalctl -u cse-collector -n 200 > /tmp/cse-diag/collector.log
   sudo journalctl -u loki -n 200 > /tmp/cse-diag/loki.log
   cat /etc/cse-collector/config.yaml > /tmp/cse-diag/config.yaml
   cat /etc/loki/config.yml > /tmp/cse-diag/loki-config.yml
   curl -s "http://localhost:3100/loki/api/v1/labels" > /tmp/cse-diag/labels.json
   tar -czf /tmp/cse-diagnostics.tar.gz -C /tmp cse-diag
   ```

2. Open an issue at: https://github.com/wvnispen/sonicwall-cse-reporter/issues

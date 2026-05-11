# SonicWall Flow Reporter - Native Linux Installation

**Version 1.4.1**

Real-time network flow monitoring and reporting for SonicWall firewalls using IPFIX/NetFlow.

## Changes in v1.4.1

- **Fixed**: Threat dashboard now properly separates Inbound Attacks vs Outbound Threats
- **Fixed**: Dashboard field names now use `.keyword` suffix for Elasticsearch aggregations
- **Fixed**: Threat direction field no longer concatenates incorrectly
- **Improved**: Threat Sources panel now correctly shows which feed detected each threat
- **Improved**: Dashboard labels clearly indicate attacker IPs vs internal IPs

## NEW in v1.4.0 - Value-Added Features

### 🌍 GeoIP Location Mapping
- World map showing traffic destinations by country
- City-level geolocation for destination IPs
- ASN/Organization identification (ISP, cloud provider, etc.)
- Requires free MaxMind GeoLite2 database

### 🛡️ Threat Intelligence Integration
- Automatic IP reputation checking against multiple threat feeds
- Emerging Threats, Feodo Tracker, Spamhaus DROP
- Custom local blocklist support
- Real-time alerting on malicious traffic

### 📊 Application Classification
- Traffic categorization by application type
- Port-based service identification (HTTP, HTTPS, SSH, RDP, etc.)
- Productivity classification (Productive, Unproductive, Neutral)
- URL-based categorization (Streaming, Social Media, Business)

### ⚠️ Risk Scoring
- Automatic risk score (0-100) for each flow
- Based on: port risk, data volume, app category, threat intel
- High-risk flow alerting

### 🔍 DNS Reverse Lookup
- Hostname resolution for destination IPs
- Cached for performance
- Makes dashboards more readable

### 📈 New Dashboards
- **GeoIP & World Map** - Geographic traffic visualization
- **Threat Intelligence** - Security monitoring and alerts
- **Applications & Productivity** - Traffic classification

### 🔔 Alerting (Grafana)
- Pre-configured alert rules for common scenarios
- Threat detection alerts
- High bandwidth user alerts
- Risky port usage alerts
- Unusual country access alerts

Real-time IPFIX/NetFlow reporting for SonicWall firewalls running natively on Ubuntu 24.04 LTS (no Docker required).

## Features

- **IPFIX Collection** - Receives and parses NetFlow/IPFIX data from SonicWall firewalls
- **User Identity Mapping** - Map IPs to users via web UI, CSV import, DHCP leases, or SonicWall SSO
- **Real-time Dashboards** - Grafana dashboards for bandwidth, top talkers, application usage
- **365-Day Retention** - Tiered storage with automatic data lifecycle management
- **Native Installation** - Runs directly on Ubuntu 24.04 with systemd services

## Architecture

```
┌─────────────────┐      IPFIX/UDP:2055      ┌────────────────────────┐
│    SonicWall    │ ────────────────────────▶│    IPFIX Collector     │
│    Firewall     │                          │  (Python + systemd)    │
└─────────────────┘                          └───────────┬────────────┘
                                                         │
                                                         ▼
┌────────────────────────────────────────────────────────────────────────┐
│  Native Services on Ubuntu 24.04                                       │
│                                                                        │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐ │
│  │  Elasticsearch   │  │     Grafana      │  │   Identity Web UI    │ │
│  │   (apt/deb)      │  │    (apt/deb)     │  │  (Python + uvicorn)  │ │
│  └──────────────────┘  └──────────────────┘  └──────────────────────┘ │
│                                                                        │
│  ┌──────────────────┐                                                  │
│  │    Aggregator    │  Hourly rollups via systemd timer               │
│  └──────────────────┘                                                  │
└────────────────────────────────────────────────────────────────────────┘
```

## System Requirements

### Minimum
- Ubuntu 24.04 LTS (or Ubuntu 22.04)
- 4 vCPUs
- 8 GB RAM
- 100 GB SSD storage

### Recommended (production)
- 4-8 vCPUs
- 16 GB RAM  
- 500 GB SSD storage

## Quick Start (10 Minutes)

### Step 1: Download and Extract

```bash
# Download the package
unzip sonicwall-flow-reporter-native.zip
cd sonicwall-flow-reporter-native
```

### Step 2: Run the Installer

```bash
sudo bash scripts/install-native.sh
```

This script will:
1. Install prerequisites (Python, Java, build tools)
2. Install Elasticsearch 9.x from official repos
3. Install Grafana OSS from official repos
4. Create Python virtual environments for collector and identity UI
5. Set up systemd services
6. Configure firewall rules
7. Initialize Elasticsearch indices

### Step 3: Configure SonicWall IPFIX Export

On your SonicWall firewall:

1. Navigate to **Manage → Logs & Reporting → Log Settings → NetFlow/IPFIX**
2. Enable **NetFlow/IPFIX Reporting**
3. Set **Collector IP** to your server's IP address
4. Set **Port** to `2055`
5. Set **Version** to `IPFIX` (or NetFlow v9)
6. Select templates to export
7. Click **Accept** to save

### Step 4: Access the Interfaces

| Service | URL | Default Login |
|---------|-----|---------------|
| **Grafana** | http://YOUR_IP:3000 | admin / admin |
| **Identity UI** | http://YOUR_IP:8080 | admin / admin |

---

## Service Management

### View Service Status

```bash
# All custom services
sudo systemctl status swfr-collector
sudo systemctl status swfr-identity

# Elasticsearch and Grafana
sudo systemctl status elasticsearch
sudo systemctl status grafana-server
```

### Start/Stop/Restart Services

```bash
# IPFIX Collector
sudo systemctl start swfr-collector
sudo systemctl stop swfr-collector
sudo systemctl restart swfr-collector

# Identity UI
sudo systemctl start swfr-identity
sudo systemctl stop swfr-identity
sudo systemctl restart swfr-identity

# Restart all
sudo systemctl restart elasticsearch grafana-server swfr-collector swfr-identity
```

### View Logs

```bash
# IPFIX Collector logs
sudo journalctl -u swfr-collector -f
cat /var/log/sonicwall-flow-reporter/collector.log

# Identity UI logs
sudo journalctl -u swfr-identity -f
cat /var/log/sonicwall-flow-reporter/identity-ui.log

# Elasticsearch logs
sudo journalctl -u elasticsearch -f

# Grafana logs
sudo journalctl -u grafana-server -f
```

---

## Configuration

### Main Configuration File

Edit `/etc/sonicwall-flow-reporter/config.env`:

```bash
sudo nano /etc/sonicwall-flow-reporter/config.env
```

```bash
# Elasticsearch
ELASTICSEARCH_HOST=127.0.0.1
ELASTICSEARCH_PORT=9200

# IPFIX Collector
IPFIX_LISTEN_IP=0.0.0.0
IPFIX_LISTEN_PORT=2055

# Identity UI
IDENTITY_UI_HOST=0.0.0.0
IDENTITY_UI_PORT=8080
IDENTITY_ADMIN_PASSWORD=your-secure-password
SECRET_KEY=change-this-to-a-random-32-character-string

# Optional: SonicWall SSO
SONICWALL_SSO_ENABLED=false
SONICWALL_HOST=192.168.1.1
SONICWALL_API_USER=admin
SONICWALL_API_PASSWORD=your-firewall-password
```

After editing, restart services:
```bash
sudo systemctl restart swfr-collector swfr-identity
```

### Elasticsearch Configuration

Edit `/etc/elasticsearch/elasticsearch.yml`:

```bash
sudo nano /etc/elasticsearch/elasticsearch.yml
```

Key settings:
```yaml
cluster.name: sonicwall-flow-reporter
node.name: node-1
network.host: 127.0.0.1
http.port: 9200
discovery.type: single-node
xpack.security.enabled: false
```

### Elasticsearch JVM Heap

Edit `/etc/elasticsearch/jvm.options.d/heap.options`:

```bash
-Xms4g
-Xmx4g
```

Set to 50% of available RAM, max 31GB.

### Grafana Configuration

Edit `/etc/grafana/grafana.ini`:

```bash
sudo nano /etc/grafana/grafana.ini
```

Change admin password:
```ini
[security]
admin_password = your-secure-password
```

---

## Directory Structure

```
/opt/sonicwall-flow-reporter/
├── collector/              # IPFIX collector Python app
│   ├── venv/              # Python virtual environment
│   ├── main.py            # Entry point
│   ├── ipfix_collector.py # Collector logic
│   └── ...
├── identity-ui/           # Identity management web app
│   ├── venv/              # Python virtual environment
│   ├── app.py             # FastAPI application
│   └── templates/         # HTML templates
└── grafana/               # Dashboard JSON files

/var/lib/sonicwall-flow-reporter/
├── elasticsearch/         # ES data (if configured)
└── identity-db/           # Identity database

/var/log/sonicwall-flow-reporter/
├── collector.log          # IPFIX collector logs
├── identity-ui.log        # Web UI logs
└── aggregator.log         # Aggregator logs

/etc/sonicwall-flow-reporter/
└── config.env             # Main configuration
```

---

## Identity Management

Access the Identity UI at http://YOUR_IP:8080

### Import Methods

1. **Manual Entry** - Add individual IP-to-user mappings
2. **CSV Import** - Bulk import from spreadsheet
3. **DHCP Import** - Import from various DHCP servers:
   - SonicWall DHCP Server
   - ISC DHCP (dhcpd.conf)
   - dnsmasq
   - Windows DHCP Server
   - MikroTik RouterOS
   - OPNsense/pfSense
4. **SonicWall SSO** - Auto-sync from firewall API

---

## Maintenance

### Check Disk Usage

```bash
# Elasticsearch disk usage
curl -s http://localhost:9200/_cat/indices?v | sort -k9 -h

# Overall disk
df -h /var/lib/elasticsearch
```

### Backup

```bash
# Stop services for consistent backup
sudo systemctl stop swfr-collector swfr-identity

# Backup Elasticsearch (snapshot recommended for production)
sudo tar -czf backup-$(date +%Y%m%d).tar.gz \
    /var/lib/elasticsearch \
    /etc/sonicwall-flow-reporter \
    /opt/sonicwall-flow-reporter

# Restart
sudo systemctl start swfr-collector swfr-identity
```

### Update Application

```bash
# Stop services
sudo systemctl stop swfr-collector swfr-identity

# Backup current version
sudo cp -r /opt/sonicwall-flow-reporter /opt/sonicwall-flow-reporter.bak

# Extract new version
cd /tmp
unzip sonicwall-flow-reporter-native-NEW.zip
sudo cp -r sonicwall-flow-reporter-native/collector/* /opt/sonicwall-flow-reporter/collector/
sudo cp -r sonicwall-flow-reporter-native/identity-ui/* /opt/sonicwall-flow-reporter/identity-ui/

# Set permissions
sudo chown -R swfr:swfr /opt/sonicwall-flow-reporter

# Restart
sudo systemctl start swfr-collector swfr-identity
```

---

## Troubleshooting

### No Data in Grafana

1. **Check collector is receiving data:**
   ```bash
   sudo journalctl -u swfr-collector | tail -20
   ```
   Look for: `Stats: packets=X, flows=X`

2. **Verify UDP traffic:**
   ```bash
   sudo tcpdump -i any port 2055 -c 10 -n
   ```

3. **Check Elasticsearch:**
   ```bash
   curl http://localhost:9200/flows/_count
   ```

4. **Verify firewall:**
   ```bash
   sudo ufw status
   ```

### Elasticsearch Won't Start

```bash
# Check logs
sudo journalctl -u elasticsearch

# Verify memory settings
sudo sysctl vm.max_map_count

# Fix if needed
sudo sysctl -w vm.max_map_count=262144
```

### Identity UI Not Accessible

```bash
# Check service
sudo systemctl status swfr-identity

# Check logs
cat /var/log/sonicwall-flow-reporter/identity-ui.log

# Verify port
ss -tlnp | grep 8080
```

---

## Uninstall

To completely remove the installation:

```bash
sudo bash scripts/uninstall.sh
```

This removes:
- All SonicWall Flow Reporter services
- Elasticsearch and data
- Grafana
- Application files
- Service user

---

## Ports Reference

| Port | Protocol | Service | Description |
|------|----------|---------|-------------|
| 2055 | UDP | IPFIX Collector | Flow data from SonicWall |
| 3000 | TCP | Grafana | Web dashboards |
| 8080 | TCP | Identity UI | User mapping management |
| 9200 | TCP | Elasticsearch | Data storage (localhost only) |

---

## Security Notes

1. **Elasticsearch** runs with security disabled and binds to localhost only
2. **Grafana** - Change the default admin password immediately
3. **Identity UI** - Change the default password in config.env
4. **Firewall** - Only ports 22, 2055, 3000, 8080 are exposed

For production deployments, consider:
- Enabling Elasticsearch security
- Setting up HTTPS for Grafana and Identity UI
- Using a reverse proxy (nginx) with SSL certificates
- Restricting IPFIX sources by IP

---

## Setting Up GeoIP (Optional but Recommended)

GeoIP enrichment adds country, city, and organization data to your traffic analysis.

### Step 1: Get a Free MaxMind License Key

1. Go to https://www.maxmind.com/en/geolite2/signup
2. Create a free account
3. Go to Account > Manage License Keys
4. Generate a new license key

### Step 2: Download the Databases

```bash
# Run the download script with your license key
sudo bash /opt/sonicwall-flow-reporter/scripts/download-geoip.sh YOUR_LICENSE_KEY
```

This downloads:
- GeoLite2-City.mmdb - Country, city, coordinates
- GeoLite2-ASN.mmdb - ISP/Organization info

### Step 3: Restart the Collector

```bash
sudo systemctl restart swfr-collector
```

### Step 4: Verify GeoIP is Working

Check the collector logs:
```bash
sudo journalctl -u swfr-collector | grep -i geoip
```

You should see: `GeoIP enrichment enabled`

---

## Setting Up Threat Intelligence

Threat intelligence is enabled by default and uses free public feeds:
- Emerging Threats Compromised IPs
- Emerging Threats Block List
- Feodo Tracker (Banking Trojans)
- Spamhaus DROP

### Custom Blocklist

To add your own blocklist:

1. Create a file with one IP or CIDR per line:
```bash
sudo nano /opt/sonicwall-flow-reporter/blocklist.txt
```

Example content:
```
# My custom blocklist
192.0.2.1
198.51.100.0/24
203.0.113.50
```

2. Configure the collector:
```bash
sudo nano /etc/sonicwall-flow-reporter/config.env
```

Add:
```bash
THREAT_INTEL_BLOCKLIST=/opt/sonicwall-flow-reporter/blocklist.txt
```

3. Restart:
```bash
sudo systemctl restart swfr-collector
```

---

## Environment Variables

The collector supports these environment variables in `/etc/sonicwall-flow-reporter/config.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_GEOIP` | `true` | Enable GeoIP enrichment |
| `GEOIP_DB_DIR` | `/opt/sonicwall-flow-reporter/geoip` | GeoIP database directory |
| `ENABLE_DNS` | `true` | Enable DNS reverse lookup |
| `DNS_TIMEOUT` | `1.0` | DNS lookup timeout (seconds) |
| `ENABLE_APP_CLASSIFIER` | `true` | Enable application classification |
| `ENABLE_THREAT_INTEL` | `true` | Enable threat intelligence |
| `THREAT_INTEL_BLOCKLIST` | (none) | Path to custom blocklist file |
| `ABUSEIPDB_API_KEY` | (none) | AbuseIPDB API key (optional) |

---

## License

MIT License - Free for commercial and personal use.

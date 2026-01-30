# SonicWall CSE Reporter

**Version 2.3.0**

Real-time reporting and analytics for SonicWall Cloud Secure Edge (CSE) using Grafana and Loki.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Version](https://img.shields.io/badge/version-2.3.0-green.svg)
![Ubuntu](https://img.shields.io/badge/ubuntu-24.04-orange.svg)

## Overview

SonicWall CSE Reporter provides comprehensive daily, weekly, and monthly reporting for your Cloud Secure Edge deployment. It collects events directly from the CSE Events API and stores them in Loki for visualization in Grafana dashboards.

### Features

- **Direct API Integration** - Polls CSE Events API (no syslog configuration required)
- **Pre-built Dashboards** - Daily, Weekly, Monthly reports plus Authentication and Security views
- **Real-time Monitoring** - Events appear in dashboards within seconds
- **Native Ubuntu** - Runs directly on Ubuntu 24.04 (no Docker required)
- **Add-on Compatible** - Works alongside existing SonicWall Flow Reporter

## Architecture

```
┌─────────────────────────┐                    ┌──────────────────────────┐
│   SonicWall Cloud       │    HTTPS/REST      │     CSE Collector        │
│   Secure Edge (CSE)     │ ◄─────────────────►│   (Python Service)       │
│   Events API            │                    │   Polls every 60s        │
└─────────────────────────┘                    └───────────┬──────────────┘
                                                           │
                                                           ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  Ubuntu 24.04 Server                                                       │
│                                                                            │
│  ┌──────────────────────┐  ┌──────────────────────┐                        │
│  │        Loki          │  │       Grafana        │                        │
│  │   (Log Storage)      │  │    (Dashboards)      │                        │
│  │   Port 3100          │  │    Port 3000         │                        │
│  └──────────────────────┘  └──────────────────────┘                        │
│                                                                            │
│  Dashboard Folder: "SonicWall CSE"                                         │
└────────────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Download and Extract

```bash
wget https://github.com/wvnispen/sonicwall-cse-reporter/releases/download/v2.3.0/sonicwall-cse-reporter.zip
unzip sonicwall-cse-reporter.zip
cd sonicwall-cse-reporter
```

### 2. Get Your CSE API Key

1. Log into your SonicWall CSE Admin Console
2. Navigate to **Settings → API Keys**
3. Create a new API key or copy an existing one

### 3. Run the Installer

```bash
sudo bash scripts/install-cse-reporter.sh
```

The installer will:
- Detect existing Grafana/Flow Reporter installations
- Install Loki and configure it for CSE events
- Install and configure the CSE Collector service
- Create the "SonicWall CSE" dashboard folder
- Import all pre-built dashboards

### 4. Access Dashboards

Open Grafana at `http://<server-ip>:3000`

Navigate to **Dashboards → SonicWall CSE** to find:
- CSE Daily Overview
- CSE Weekly Summary  
- CSE Monthly Report
- CSE Authentication Analytics
- CSE Security Events

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Ubuntu 24.04 LTS | Ubuntu 24.04 LTS |
| CPU | 2 vCPUs | 4 vCPUs |
| RAM | 4 GB | 8 GB |
| Storage | 50 GB SSD | 100 GB SSD |

## Configuration

### Collector Configuration

Edit `/etc/cse-collector/config.yaml`:

```yaml
cse_api_url: "https://net.banyanops.com/api/v1/events"
loki_url: "http://localhost:3100/loki/api/v1/push"
poll_interval_seconds: 60
batch_size: 1000
lookback_minutes: 1440  # 24 hours on first run
```

### API Key

Edit `/etc/cse-collector/env`:

```bash
CSE_API_KEY=your-api-key-here
```

### Loki Retention

Edit `/etc/loki/config.yml` to adjust retention:

```yaml
limits_config:
  retention_period: 2160h  # 90 days (default)
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| grafana-server | 3000 | Web UI and dashboards |
| loki | 3100 | Log storage and querying |
| cse-collector | - | CSE Events API polling |

## Commands

### Check Status
```bash
sudo systemctl status cse-collector loki grafana-server
```

### View Collector Logs
```bash
sudo journalctl -u cse-collector -f
```

### Verify Loki Data
```bash
curl -s "http://localhost:3100/loki/api/v1/labels" | jq
```

### Restart Services
```bash
sudo systemctl restart cse-collector
sudo systemctl restart loki
```

### Reset Event Collection
```bash
sudo systemctl stop cse-collector
sudo rm -f /var/lib/cse-collector/cursor.json
sudo systemctl start cse-collector
```

## Upgrading

```bash
# Download new version
wget https://github.com/wvnispen/sonicwall-cse-reporter/releases/download/vX.X.X/sonicwall-cse-reporter.zip
unzip sonicwall-cse-reporter.zip
cd sonicwall-cse-reporter

# Run upgrade
sudo bash scripts/install-cse-reporter.sh --upgrade
```

## Uninstalling

```bash
sudo bash scripts/uninstall-cse-reporter.sh
```

## Troubleshooting

### No Data in Dashboards

1. Check collector is running:
   ```bash
   sudo systemctl status cse-collector
   ```

2. Check for errors:
   ```bash
   sudo journalctl -u cse-collector -n 50
   ```

3. Verify API key is correct in `/etc/cse-collector/env`

4. Check Loki is receiving data:
   ```bash
   curl -s "http://localhost:3100/loki/api/v1/labels" | jq
   ```

### Collector Shows Errors

- **"entry too far behind"**: Clear Loki data and restart:
  ```bash
  sudo systemctl stop cse-collector loki
  sudo rm -rf /var/lib/loki/chunks/* /var/lib/loki/wal/*
  sudo systemctl start loki
  sleep 5
  sudo rm -f /var/lib/cse-collector/cursor.json
  sudo systemctl start cse-collector
  ```

- **"401 Unauthorized"**: Check API key in `/etc/cse-collector/env`

### Loki Won't Start

Check logs:
```bash
sudo journalctl -u loki -n 50
```

Common issues:
- Disk full: Check `df -h /var/lib/loki`
- Permission issues: Run `sudo chown -R loki:loki /var/lib/loki`

## Available Labels

The following labels are available for filtering in Grafana:

| Label | Description | Example Values |
|-------|-------------|----------------|
| `event_type` | Type of CSE event | Identity, Access, TrustScoring |
| `category` | Event category | authentication, access, posture |
| `status` | Event result | success, denied, unknown |
| `severity` | Log severity | INFO, WARN, ERROR |
| `device_platform` | Device OS | iOS, Android, Windows, macOS |
| `device_ownership` | Device type | Employee Owned, Corporate |

High-cardinality data (user email, IP address, etc.) is available in the log line for text searching.

## Directory Structure

```
/opt/cse-collector/           # Collector script
/etc/cse-collector/           # Configuration
  ├── config.yaml             # Collector settings
  └── env                     # API key (CSE_API_KEY)
/var/lib/cse-collector/       # Cursor state
/var/log/cse-collector/       # Logs
/etc/loki/config.yml          # Loki configuration
/var/lib/loki/                # Loki data storage
```

## License

MIT License - See [LICENSE](LICENSE) file

## Related Projects

- [SonicWall Flow Reporter Native](https://github.com/wvnispen/sonicwall-flow-reporter-native) - NetFlow reporting for SonicWall firewalls

## Changelog

### v2.3.0 (2026-01-30)
- Direct CSE Events API integration (replaces syslog)
- Low-cardinality labels for efficient Loki storage
- Automatic timestamp sorting within streams
- Improved Loki configuration for historical data
- Better error handling and logging

### v2.0.0
- Initial API-based release
- Five pre-built dashboards
- Native Ubuntu deployment

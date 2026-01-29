# SonicWall CSE Reporter

**Version 2.0.0** - API Integration Edition

Real-time reporting and analytics for SonicWall Cloud Secure Edge (CSE) using Grafana, Loki, and the CSE Events API.

## Overview

SonicWall CSE Reporter provides comprehensive daily, weekly, and monthly reporting for your Cloud Secure Edge deployment. It collects events directly from the CSE Events API and presents them in intuitive Grafana dashboards.

## What's New in v2.0.0

- **API Integration**: Replaced syslog-based collection with direct CSE Events API polling
- **Richer Event Data**: Access to full event metadata including trust scores, device info, policies
- **Easier Setup**: No network/firewall configuration needed - outbound HTTPS only
- **Better Reliability**: Pull-based collection with cursor tracking for exactly-once delivery

## Architecture

```
┌─────────────────────────┐                          ┌──────────────────────────┐
│   SonicWall Cloud       │       HTTPS API          │     CSE Collector        │
│   Secure Edge (CSE)     │ ◀─────────────────────── │   (Python Service)       │
│                         │  net.banyanops.com/api   │   Polls every 60s        │
└─────────────────────────┘                          └───────────┬──────────────┘
                                                                 │
                                                                 ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│  Native Services on Ubuntu 24.04                                               │
│                                                                                │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐  │
│  │        Loki          │  │       Grafana        │  │    Elasticsearch     │  │
│  │   (Log Storage)      │  │    (Dashboards)      │  │  (Flow Reporter DB)  │  │
│  │                      │  │                      │  │    [if existing]     │  │
│  └──────────────────────┘  └──────────────────────┘  └──────────────────────┘  │
│                                                                                │
│  Dashboard Folder: "SonicWall CSE"                                             │
└────────────────────────────────────────────────────────────────────────────────┘
```

## Features

- **Authentication Monitoring** - Track successful/failed logins (Grant/Deny), MFA, SSO events
- **Access Analytics** - Monitor authorized/unauthorized connections to services
- **Policy & Compliance** - Real-time tracking of policy events and ITP blocks
- **Trust Scoring** - Device posture and trust level changes
- **Device Analytics** - OS breakdown, device registrations, compliance
- **Daily/Weekly/Monthly Reports** - Pre-built dashboards for different reporting intervals

## CSE Event Types Captured

| Event Type | Description |
|------------|-------------|
| **Registration** | Device register/unregister events |
| **Identity** | Authentication attempts (Grant/Deny) |
| **Access** | Connection authorization (Authorized/Unauthorized) |
| **TrustScoring** | Device trust level changes |
| **Threat** | URL filtering blocks |
| **Compliance** | ITP policy violations |
| **AdminLogin** | Admin console login attempts |
| **Audit** | Kubernetes command audit logs |

## Prerequisites

### Option A: Add to Existing SonicWall Flow Reporter
- SonicWall Flow Reporter Native v1.4.0 or newer installed
- This provides the existing Grafana instance

### Option B: Fresh Installation
- Ubuntu 24.04 LTS
- 4 vCPUs, 8 GB RAM minimum
- 100 GB storage (SSD recommended)
- Outbound HTTPS access to `net.banyanops.com`

## Quick Start

### Step 1: Create CSE API Key

In your SonicWall CSE Command Center:

1. Navigate to **Settings → API Keys**
2. Click **Add API Key**
3. Configure:
   - **Name**: `CSE-Reporter`
   - **Scope**: `ReadOnly`
4. **Copy and save the API Secret** - you'll need this during installation

![API Key Creation](docs/images/api-key.png)

### Step 2: Download and Extract

```bash
wget https://github.com/wvnispen/sonicwall-cse-reporter-addon/releases/download/v2.0.0/sonicwall-cse-reporter-v2.0.0.zip
unzip sonicwall-cse-reporter-v2.0.0.zip
cd sonicwall-cse-reporter-addon
```

### Step 3: Run the Installer

```bash
sudo bash scripts/install-cse-reporter.sh
```

The installer will:
1. Detect if this is an existing Flow Reporter installation or fresh deployment
2. Prompt for your CSE API key
3. Install Grafana (if fresh install)
4. Install Loki from official Grafana Labs APT repository
5. Install and configure the CSE Collector service
6. Create "SonicWall CSE" dashboard folder in Grafana
7. Import pre-built dashboards

You can also provide the API key via command line:
```bash
sudo bash scripts/install-cse-reporter.sh --api-key "your-api-key-here"
```

### Step 4: Access Dashboards

Open Grafana at `http://<server-ip>:3000`

Navigate to **Dashboards → SonicWall CSE** folder to find:
- CSE Daily Overview
- CSE Weekly Summary
- CSE Monthly Report
- CSE Authentication Analytics
- CSE Security Events

## Configuration

### CSE Collector Configuration

Configuration file: `/etc/cse-collector/config.yaml`

```yaml
# CSE API Configuration
cse_api_url: "https://net.banyanops.com/api/v1/events"

# Loki Configuration
loki_url: "http://localhost:3100/loki/api/v1/push"

# Collection Settings
poll_interval_seconds: 60
batch_size: 1000

# Logging
log_level: "INFO"
```

### API Key Configuration

The API key is stored securely in `/etc/cse-collector/env`:

```bash
# Edit the file
sudo nano /etc/cse-collector/env

# Set your API key
CSE_API_KEY=your-api-key-here

# Restart the collector
sudo systemctl restart cse-collector
```

### European Command Center

If using the European CSE Command Center, update the API URL:

```yaml
cse_api_url: "https://eucc.console.banyanops.com/api/v1/events"
```

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Ubuntu 24.04 LTS | Ubuntu 24.04 LTS |
| CPU | 4 vCPUs | 8 vCPUs |
| RAM | 8 GB | 16 GB |
| Storage | 100 GB SSD | 500 GB SSD |
| Network | Outbound HTTPS | Outbound HTTPS |

## Services Installed

| Service | Port | Description |
|---------|------|-------------|
| grafana-server | 3000 | Web UI and dashboards |
| loki | 3100 | Log storage and querying |
| cse-collector | - | API polling service (no inbound port) |

## Directory Structure

```
/opt/cse-collector/              # Collector application
/etc/cse-collector/              # Configuration
  ├── config.yaml                # Main config
  └── env                        # API key (secured)
/var/lib/cse-collector/          # Cursor/state storage
/var/log/cse-collector/          # Collector logs
/etc/loki/                       # Loki configuration
/var/lib/loki/                   # Loki data storage
```

## Troubleshooting

### Check service status
```bash
sudo systemctl status cse-collector
sudo systemctl status loki
sudo systemctl status grafana-server
```

### View collector logs
```bash
sudo journalctl -u cse-collector -f
```

### Test API connectivity
```bash
# Test with your API key
curl -H "Authorization: Bearer YOUR_API_KEY" \
  "https://net.banyanops.com/api/v1/events?limit=1"
```

### Verify Loki is receiving data
```bash
curl -s "http://localhost:3100/loki/api/v1/labels" | jq
```

### Common Issues

**No data in dashboards:**
1. Check collector is running: `systemctl status cse-collector`
2. Check API key is valid: Test curl command above
3. Check collector logs for errors

**API rate limiting:**
- Default poll interval is 60 seconds to avoid rate limits
- Do not decrease below 30 seconds

**Events missing:**
- Collector uses cursor tracking - check `/var/lib/cse-collector/cursor.json`
- On first run, only fetches last 5 minutes by default

## Upgrading

```bash
cd sonicwall-cse-reporter-addon
git pull
sudo bash scripts/install-cse-reporter.sh --upgrade
```

## Uninstalling

```bash
sudo bash scripts/uninstall-cse-reporter.sh
```

## API Reference

The CSE Events API documentation is available at:
- [ELK Stack Integration Guide](https://cse-docs.sonicwall.com/docs/visibility-logging/events/elk-stack/)
- [Event Properties & Definitions](https://cse-docs.sonicwall.com/docs/visibility-logging/events/event-props/)

## Support

- GitHub Issues: https://github.com/wvnispen/sonicwall-cse-reporter-addon/issues
- SonicWall Flow Reporter: https://github.com/wvnispen/sonicwall-flow-reporter-native

## License

MIT License - See [LICENSE](LICENSE) file

## Changelog

### v2.0.0 (2026-01-29)
- **Breaking Change**: Switched from syslog to CSE Events API
- Added Python-based CSE Collector service
- Richer event metadata with trust scores, device info
- Updated dashboards for API-based labels
- Simplified deployment (no inbound ports required)

### v1.0.0 (2026-01-29)
- Initial release with syslog-based collection

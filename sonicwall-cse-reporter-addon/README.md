# SonicWall CSE Reporter

**Version 1.0.0**

Real-time reporting and analytics for SonicWall Cloud Secure Edge (CSE) using Grafana, Loki, and Alloy.

## Overview

SonicWall CSE Reporter provides comprehensive daily, weekly, and monthly reporting for your Cloud Secure Edge deployment. It captures authentication events, access logs, policy violations, and device posture data via syslog and presents them in intuitive Grafana dashboards.

## Architecture

```
┌─────────────────────────┐      Syslog (TCP/TLS)      ┌──────────────────────────┐
│   SonicWall Cloud       │ ──────────────────────────▶│     Grafana Alloy        │
│   Secure Edge (CSE)     │         Port 6514          │   (Syslog Receiver)      │
└─────────────────────────┘                            └───────────┬──────────────┘
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

- **Authentication Monitoring** - Track successful/failed logins, MFA usage, SSO events
- **Application Access Analytics** - Monitor which applications users access and when
- **Policy Violation Tracking** - Real-time alerts on policy violations and blocked access
- **Device Posture Reporting** - Compliance status of connecting devices
- **User Session Analytics** - Session duration, concurrent sessions, geographic access
- **Daily/Weekly/Monthly Reports** - Pre-built dashboards for different reporting intervals

## Prerequisites

### Option A: Add to Existing SonicWall Flow Reporter
- SonicWall Flow Reporter Native v1.4.0 or newer installed
- This provides the existing Grafana instance

### Option B: Fresh Installation
- Ubuntu 24.04 LTS
- 4 vCPUs, 8 GB RAM minimum
- 100 GB storage (SSD recommended)

## Quick Start

### Step 1: Download and Extract

```bash
wget https://github.com/wvnispen/sonicwall-cse-reporter-addon/releases/download/v1.0.0/sonicwall-cse-reporter-v1.0.0.zip
unzip sonicwall-cse-reporter-v1.0.0.zip
cd sonicwall-cse-reporter-addon
```

### Step 2: Run the Installer

```bash
sudo bash scripts/install-cse-reporter.sh
```

The installer will:
1. Detect if this is an existing Flow Reporter installation or fresh deployment
2. Install Grafana (if fresh install)
3. Install Loki from official Grafana Labs APT repository
4. Install Grafana Alloy from official Grafana Labs APT repository
5. Configure Alloy syslog receiver for CSE logs
6. Create "SonicWall CSE" dashboard folder in Grafana
7. Import pre-built dashboards
8. Configure systemd services

### Step 3: Configure SonicWall CSE Syslog Export

In your SonicWall CSE Admin Console:

1. Navigate to **Settings → Log Settings** (or **Logs & Reports → Syslog**)
2. Enable **Syslog Export**
3. Set **Server Address** to your reporter server's IP
4. Set **Port** to `6514`
5. Set **Protocol** to `TCP` (TLS recommended for production)
6. Select log types to export:
   - Authentication Events
   - Access Logs
   - Policy Violations
   - Device Posture Events

### Step 4: Access Dashboards

Open Grafana at `http://<server-ip>:3000`

Navigate to **Dashboards → SonicWall CSE** folder to find:
- CSE Daily Overview
- CSE Weekly Summary
- CSE Monthly Report
- CSE Authentication Analytics
- CSE Application Access
- CSE Security Events

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Ubuntu 24.04 LTS | Ubuntu 24.04 LTS |
| CPU | 4 vCPUs | 8 vCPUs |
| RAM | 8 GB | 16 GB |
| Storage | 100 GB SSD | 500 GB SSD |
| Network | 1 Gbps | 1 Gbps |

## Log Retention

Default retention periods (configurable):
- Loki: 90 days
- Dashboard data: Real-time to 365 days (based on Loki retention)

## Services Installed

| Service | Port | Description |
|---------|------|-------------|
| grafana-server | 3000 | Web UI and dashboards |
| loki | 3100 | Log storage and querying |
| alloy | 6514 | Syslog receiver (TCP) |
| alloy | 12345 | Alloy UI (optional) |

## Directory Structure

```
/etc/alloy/                    # Alloy configuration
/etc/loki/                     # Loki configuration
/var/lib/loki/                 # Loki data storage
/var/log/alloy/                # Alloy logs
```

## Troubleshooting

### Check service status
```bash
sudo systemctl status alloy
sudo systemctl status loki
sudo systemctl status grafana-server
```

### View Alloy logs
```bash
sudo journalctl -u alloy -f
```

### Test syslog reception
```bash
echo "<14>1 $(date -u +%Y-%m-%dT%H:%M:%SZ) test-host cse - - - Test message" | nc localhost 6514
```

### Verify Loki is receiving data
```bash
curl -s "http://localhost:3100/loki/api/v1/labels" | jq
```

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

## Support

- GitHub Issues: https://github.com/wvnispen/sonicwall-cse-reporter-addon/issues
- SonicWall Flow Reporter: https://github.com/wvnispen/sonicwall-flow-reporter-native

## License

MIT License - See [LICENSE](LICENSE) file

## Changelog

### v1.0.0 (2026-01-29)
- Initial release
- Loki log storage integration
- Grafana Alloy syslog collection
- Daily, Weekly, Monthly dashboard templates
- Authentication and access analytics
- Native Ubuntu 24.04 deployment

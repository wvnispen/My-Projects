# SonicWall Flow Reporter

Real-time IPFIX/NetFlow reporting for SonicWall firewalls with user identity mapping, DHCP integration, and Grafana dashboards.

## Features

- **IPFIX Collection** - Receives and parses NetFlow/IPFIX data from SonicWall firewalls
- **User Identity Mapping** - Map IPs to users via web UI, CSV import, DHCP leases, or SonicWall SSO
- **Real-time Dashboards** - Grafana dashboards for bandwidth, top talkers, application usage
- **365-Day Retention** - Tiered storage with automatic data lifecycle management
- **Easy Deployment** - Single VM with Docker Compose

## Architecture

```
┌─────────────────┐      IPFIX/UDP:2055      ┌────────────────────────┐
│    SonicWall    │ ────────────────────────▶│    IPFIX Collector     │
│    Firewall     │                          │    (Python)            │
└─────────────────┘                          └───────────┬────────────┘
                                                         │
                                                         ▼
┌────────────────────────────────────────────────────────────────────────┐
│  Docker Compose Stack                                                  │
│                                                                        │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐ │
│  │  Elasticsearch   │  │     Grafana      │  │   Identity Web UI    │ │
│  │  (data storage)  │  │   (dashboards)   │  │   (user mappings)    │ │
│  └──────────────────┘  └──────────────────┘  └──────────────────────┘ │
│                                                                        │
│  ┌──────────────────┐                                                  │
│  │    Aggregator    │  Hourly/Daily rollups for long-term reporting   │
│  └──────────────────┘                                                  │
└────────────────────────────────────────────────────────────────────────┘
```

## Quick Start (5 Minutes)

### Prerequisites

- Debian 13 (Trixie), Debian 12 (Bookworm), or Ubuntu 24.04 LTS
- Minimum 4 vCPUs, 8 GB RAM, 100 GB storage
- Network access to your SonicWall firewall
- Static IP address recommended

### Step 1: Prepare the Server

```bash
# Download and extract the package
unzip sonicwall-flow-reporter.zip
cd sonicwall-flow-reporter

# Run the setup script (installs Docker, configures firewall)
sudo bash scripts/setup-host.sh
```

### Step 2: Configure the Application

```bash
# Copy to installation directory
sudo cp -r . /opt/sonicwall-flow-reporter
cd /opt/sonicwall-flow-reporter

# Create configuration file
sudo cp .env.example .env
sudo nano .env
```

**Required settings in `.env`:**

```bash
# Set secure passwords (CHANGE THESE!)
ELASTIC_PASSWORD=your-secure-elasticsearch-password
GF_SECURITY_ADMIN_PASSWORD=your-grafana-admin-password
IDENTITY_ADMIN_PASSWORD=your-identity-ui-password
SECRET_KEY=generate-a-random-32-character-string
```

### Step 3: Start the Services

```bash
cd /opt/sonicwall-flow-reporter
sudo docker compose up -d
```

Wait 1-2 minutes for all services to initialize, then verify:

```bash
sudo docker compose ps
```

All services should show "running" status.

### Step 4: Configure SonicWall IPFIX Export

On your SonicWall firewall:

1. Navigate to **Manage → Logs & Reporting → Log Settings → NetFlow/IPFIX**
2. Enable **NetFlow/IPFIX Reporting**
3. Set **Collector IP** to your server's IP address
4. Set **Port** to `2055`
5. Set **Version** to `IPFIX` (or NetFlow v9)
6. Select templates to export (recommend: all available)
7. Click **Accept** to save

### Step 5: Access the Interfaces

| Service | URL | Default Login |
|---------|-----|---------------|
| **Grafana** | http://YOUR_IP:3000 | admin / (your GF_SECURITY_ADMIN_PASSWORD) |
| **Identity UI** | http://YOUR_IP:8080 | admin / (your IDENTITY_ADMIN_PASSWORD) |

### Step 6: Verify Data Flow

1. Open Grafana at http://YOUR_IP:3000
2. Go to **Dashboards** → **SonicWall Flow Reporter** → **Overview**
3. You should see traffic data within a few minutes

---

## Detailed Configuration

### Environment Variables (.env)

| Variable | Description | Default |
|----------|-------------|---------|
| `ELASTIC_PASSWORD` | Elasticsearch password | (required) |
| `ES_JAVA_OPTS` | Elasticsearch JVM memory | `-Xms2g -Xmx2g` |
| `GF_SECURITY_ADMIN_PASSWORD` | Grafana admin password | (required) |
| `IDENTITY_ADMIN_PASSWORD` | Identity UI admin password | (required) |
| `SECRET_KEY` | Identity UI session secret | (required) |
| `IPFIX_LISTEN_PORT` | UDP port for IPFIX data | `2055` |
| `IPFIX_ALLOWED_SOURCES` | Restrict to specific firewall IPs | (empty = all) |
| `TZ` | Timezone | `Africa/Johannesburg` |

### SonicWall SSO Integration (Optional)

To automatically sync user-to-IP mappings from SonicWall:

```bash
# Add to .env file:
SONICWALL_SSO_ENABLED=true
SONICWALL_HOST=192.168.1.1
SONICWALL_API_PORT=443
SONICWALL_API_USER=admin
SONICWALL_API_PASSWORD=your-firewall-password
```

Then restart: `sudo docker compose up -d`

### Data Retention

Default retention policy:

| Data Type | Retention | Index Pattern |
|-----------|-----------|---------------|
| Raw flows | 30 days | `flows-raw-*` |
| Hourly aggregates | 90 days | `flows-hourly-*` |
| Daily summaries | 365 days | `flows-daily-*` |

To modify, edit `elasticsearch/ilm-policy.json` and restart.

---

## Identity Management

The Identity UI (http://YOUR_IP:8080) allows you to map IP addresses to user names for enriched reporting.

### Methods to Add Mappings

1. **Manual Entry** - Add individual IP-to-user mappings
2. **CSV Import** - Bulk import from spreadsheet
3. **DHCP Import** - Import static DHCP leases from:
   - SonicWall DHCP Server
   - ISC DHCP (dhcpd.conf)
   - dnsmasq
   - Windows DHCP Server
   - MikroTik RouterOS
   - OPNsense/pfSense
4. **SonicWall SSO** - Auto-sync from firewall (requires API access)

### DHCP Import Example

Export static leases from your DHCP server as CSV:

```csv
192.168.1.100,00:1A:2B:3C:4D:5E,Workstation-01
192.168.1.101,00:1A:2B:3C:4D:5F,Laptop-Sales
192.168.1.102,00:1A:2B:3C:4D:60,Printer-Floor2
```

Then import via **Identity UI → Import DHCP**.

---

## Grafana Dashboards

### Overview Dashboard

- Total flows, bytes, unique IPs
- Bandwidth over time graph
- Top source IPs, destination IPs, ports
- Traffic summary tables
- Raw flow log viewer

### Customizing Dashboards

1. Edit panels directly in Grafana (changes persist)
2. Create new dashboards using the Elasticsearch datasource
3. Use Lucene queries to filter data:
   - `src_ip:192.168.1.*` - Filter by source IP
   - `user_name:*` - Only flows with identified users
   - `dst_port:443` - HTTPS traffic only

### Fixing "No Data" in Stat Panels

If stat panels show "No data", edit each panel:

1. Click panel → Edit
2. In Query section, set **Group By** → **Date Histogram** → `@timestamp`
3. Click **Apply**

---

## Maintenance

### View Logs

```bash
cd /opt/sonicwall-flow-reporter

# All services
sudo docker compose logs -f

# Specific service
sudo docker compose logs -f collector
sudo docker compose logs -f identity-ui
sudo docker compose logs -f elasticsearch
```

### Backup

```bash
# Stop services (optional, for consistent backup)
sudo docker compose stop

# Backup data directory
sudo tar -czf backup-$(date +%Y%m%d).tar.gz /opt/sonicwall-flow-reporter/data

# Restart services
sudo docker compose start
```

### Update

```bash
cd /opt/sonicwall-flow-reporter

# Pull latest images
sudo docker compose pull

# Restart with new images
sudo docker compose up -d
```

### Check Disk Usage

```bash
# Elasticsearch indices
curl -s -u elastic:YOUR_PASSWORD http://localhost:9200/_cat/indices?v | sort -k9 -h

# Disk usage
df -h /opt/sonicwall-flow-reporter/data
```

### Force Index Rollover (if disk full)

```bash
curl -X POST "localhost:9200/flows-raw/_rollover" \
  -u elastic:YOUR_PASSWORD \
  -H 'Content-Type: application/json'
```

---

## Troubleshooting

### No data in Grafana

1. **Check IPFIX collector is receiving data:**
   ```bash
   sudo docker compose logs collector | tail -20
   ```
   Look for: `Stats: packets=X, flows=X, templates=X`

2. **Verify SonicWall is sending data:**
   ```bash
   sudo tcpdump -i any port 2055 -c 10 -n
   ```

3. **Check Elasticsearch has data:**
   ```bash
   curl -s -u elastic:YOUR_PASSWORD http://localhost:9200/flows-raw/_count
   ```

4. **Verify firewall rules:**
   ```bash
   sudo ufw status
   ```
   Port 2055/udp should be allowed.

### Elasticsearch won't start

1. **Check memory settings:**
   ```bash
   sudo sysctl vm.max_map_count
   ```
   Should be 262144. If not: `sudo sysctl -w vm.max_map_count=262144`

2. **Check permissions:**
   ```bash
   sudo chown -R 1000:1000 /opt/sonicwall-flow-reporter/data/elasticsearch
   ```

### Identity UI not accessible

1. **Check container is running:**
   ```bash
   sudo docker compose ps identity-ui
   ```

2. **Check logs:**
   ```bash
   sudo docker compose logs identity-ui
   ```

3. **Verify port is open:**
   ```bash
   sudo ufw allow 8080/tcp
   ```

---

## Ports Reference

| Port | Protocol | Service | Description |
|------|----------|---------|-------------|
| 2055 | UDP | IPFIX Collector | Receives flow data from SonicWall |
| 3000 | TCP | Grafana | Web dashboards |
| 8080 | TCP | Identity UI | User mapping management |
| 9200 | TCP | Elasticsearch | Data storage (internal) |

---

## System Requirements

### Minimum (1-2 firewalls, 30-day detailed retention)

- 4 vCPUs
- 8 GB RAM
- 100 GB SSD storage

### Recommended (production, 365-day retention)

- 4-8 vCPUs
- 16 GB RAM
- 500 GB SSD storage

### Storage Estimation

- ~1-5 GB per day per firewall (depends on traffic volume)
- 365 days × 2 GB/day = ~730 GB (before compression)
- With aggregation: ~200-300 GB typical

---

## License

MIT License - Free for commercial and personal use.

---

## Support

For issues, feature requests, or questions:
- Review logs: `sudo docker compose logs -f`
- Check Elasticsearch health: `curl -u elastic:PASS http://localhost:9200/_cluster/health?pretty`

---

## Version History

- **v1.0.0** (2024-12-20)
  - Initial release
  - IPFIX collector with SonicWall template support
  - Elasticsearch storage with ILM retention policies
  - Grafana dashboards
  - Identity UI with CSV import
  - DHCP static lease import
  - SonicWall SSO integration

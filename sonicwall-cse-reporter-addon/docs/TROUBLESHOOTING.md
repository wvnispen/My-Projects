# Troubleshooting Guide

This guide helps diagnose and resolve common issues with the SonicWall CSE Reporter.

## Service Status Checks

### Quick Health Check

```bash
# Check all services
echo "=== Service Status ==="
systemctl status alloy --no-pager -l
systemctl status loki --no-pager -l
systemctl status grafana-server --no-pager -l

# Check ports
echo "=== Listening Ports ==="
ss -tlnp | grep -E '(3000|3100|6514)'
```

### Individual Service Checks

**Grafana Alloy:**
```bash
systemctl status alloy
journalctl -u alloy -n 100 --no-pager
```

**Loki:**
```bash
systemctl status loki
journalctl -u loki -n 100 --no-pager
curl -s http://localhost:3100/ready
```

**Grafana:**
```bash
systemctl status grafana-server
curl -s http://localhost:3000/api/health
```

## Common Issues

### Issue: No Data in Dashboards

**Symptoms:**
- Dashboards show "No data"
- Empty graphs and tables

**Diagnosis:**

1. **Check if Alloy is receiving data:**
   ```bash
   # Watch Alloy logs for incoming messages
   journalctl -u alloy -f | grep -i "syslog\|received\|message"
   ```

2. **Check if Loki has data:**
   ```bash
   # List available labels
   curl -s "http://localhost:3100/loki/api/v1/labels" | jq
   
   # Query recent logs
   curl -s "http://localhost:3100/loki/api/v1/query_range" \
     --data-urlencode 'query={job="sonicwall-cse"}' \
     --data-urlencode 'limit=10' | jq
   ```

3. **Test syslog reception manually:**
   ```bash
   # Send a test message
   echo '<14>1 2026-01-29T10:00:00Z test-host sonicwall-cse - - - user=testuser action=success event_type=authentication' | nc localhost 6514
   
   # Check if it arrived in Loki (wait a few seconds)
   curl -s "http://localhost:3100/loki/api/v1/query" \
     --data-urlencode 'query={job="sonicwall-cse"} |= "testuser"' | jq
   ```

**Solutions:**

- Verify CSE syslog configuration points to correct IP/port
- Check firewall allows port 6514
- Verify Alloy config syntax: `alloy fmt /etc/alloy/config.alloy`

### Issue: Alloy Won't Start

**Symptoms:**
- `systemctl status alloy` shows failed
- Error messages in journal

**Diagnosis:**
```bash
# Check for config errors
alloy fmt /etc/alloy/config.alloy

# Check detailed error
journalctl -u alloy -n 50 --no-pager
```

**Common Causes:**

1. **Syntax error in config:**
   ```bash
   # Validate config
   alloy run --config.file=/etc/alloy/config.alloy --dry-run
   ```

2. **Port already in use:**
   ```bash
   ss -tlnp | grep 6514
   # Kill conflicting process or change port
   ```

3. **Permission issues:**
   ```bash
   ls -la /etc/alloy/
   ls -la /var/lib/alloy/
   ```

### Issue: Loki Won't Start

**Symptoms:**
- `systemctl status loki` shows failed

**Diagnosis:**
```bash
journalctl -u loki -n 100 --no-pager
```

**Common Causes:**

1. **Disk full:**
   ```bash
   df -h /var/lib/loki
   # Clean up if needed
   ```

2. **Permission issues:**
   ```bash
   ls -la /var/lib/loki
   chown -R loki:loki /var/lib/loki
   ```

3. **Config error:**
   ```bash
   # Validate YAML
   python3 -c "import yaml; yaml.safe_load(open('/etc/loki/config.yml'))"
   ```

### Issue: Grafana Can't Connect to Loki

**Symptoms:**
- Datasource test fails
- "Bad Gateway" or connection errors

**Diagnosis:**

1. **Test Loki directly:**
   ```bash
   curl -s http://localhost:3100/ready
   curl -s http://localhost:3100/loki/api/v1/labels
   ```

2. **Check Grafana datasource config:**
   - URL should be `http://localhost:3100`
   - Access should be "Server (default)"

**Solutions:**

- Ensure Loki is running: `systemctl restart loki`
- Check Grafana datasource URL matches Loki port
- Verify no firewall blocking localhost connections

### Issue: Missing Labels/Fields

**Symptoms:**
- Some fields not extracted (user, application, etc.)
- Labels show as empty

**Diagnosis:**

1. **Check raw log format:**
   ```bash
   # See what Alloy receives
   journalctl -u alloy -f
   ```

2. **Verify CSE log format matches parser regex**

**Solutions:**

- Adjust Alloy regex patterns in `/etc/alloy/config.alloy`
- Ensure CSE is sending expected field formats
- Add custom stage.regex rules for your log format

### Issue: High Memory/CPU Usage

**Symptoms:**
- Server slow or unresponsive
- Services consuming excessive resources

**Diagnosis:**
```bash
# Check resource usage
htop
# or
ps aux | grep -E '(alloy|loki|grafana)'

# Check Loki cardinality
curl -s "http://localhost:3100/loki/api/v1/labels" | jq '. | length'
```

**Solutions:**

1. **Reduce Loki retention:**
   Edit `/etc/loki/config.yml`:
   ```yaml
   limits_config:
     retention_period: 720h  # 30 days instead of 90
   ```

2. **Limit high-cardinality labels:**
   Avoid labels with many unique values (like full log messages)

3. **Increase server resources** if consistently maxed out

## Log File Locations

| Component | Log Location |
|-----------|--------------|
| Alloy | `journalctl -u alloy` |
| Loki | `journalctl -u loki` |
| Grafana | `journalctl -u grafana-server` or `/var/log/grafana/grafana.log` |

## Configuration Files

| Component | Config Path |
|-----------|-------------|
| Alloy | `/etc/alloy/config.alloy` |
| Loki | `/etc/loki/config.yml` |
| Grafana | `/etc/grafana/grafana.ini` |

## Useful Commands

```bash
# Restart all services
sudo systemctl restart alloy loki grafana-server

# Check all logs
sudo journalctl -u alloy -u loki -u grafana-server -f

# Test Loki query
curl -G -s "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={job="sonicwall-cse"}' | jq '.data.result[0].values[:5]'

# Check Alloy targets/pipeline
curl -s http://localhost:12345/metrics | grep alloy

# Export dashboards for backup
curl -s -u admin:admin "http://localhost:3000/api/dashboards/uid/cse-daily-overview" | jq '.dashboard' > backup-daily.json
```

## Getting Help

If issues persist:

1. Collect diagnostic information:
   ```bash
   # Create diagnostic bundle
   mkdir -p /tmp/cse-diag
   systemctl status alloy loki grafana-server > /tmp/cse-diag/services.txt
   journalctl -u alloy -n 500 > /tmp/cse-diag/alloy.log
   journalctl -u loki -n 500 > /tmp/cse-diag/loki.log
   cp /etc/alloy/config.alloy /tmp/cse-diag/
   cp /etc/loki/config.yml /tmp/cse-diag/
   tar -czf /tmp/cse-diagnostics.tar.gz -C /tmp cse-diag
   ```

2. Open an issue at: https://github.com/wvnispen/sonicwall-cse-reporter-addon/issues

Include:
- Ubuntu version
- Service status output
- Relevant log excerpts
- Steps to reproduce

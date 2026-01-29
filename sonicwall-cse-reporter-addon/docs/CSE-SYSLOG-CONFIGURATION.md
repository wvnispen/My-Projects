# Configuring SonicWall CSE Syslog Export

This guide covers how to configure your SonicWall Cloud Secure Edge environment to send logs to the CSE Reporter.

## Prerequisites

- SonicWall CSE Reporter installed and running
- Administrative access to SonicWall CSE Admin Console
- Network connectivity between CSE and reporter server

## Configuration Steps

### Step 1: Access CSE Admin Console

1. Log in to your SonicWall CSE Admin Console
2. Navigate to **Settings** or **Administration**

### Step 2: Configure Syslog Settings

Navigate to the logging/syslog configuration section:

**Settings → Logs & Reports → Syslog** (or similar path depending on CSE version)

Configure the following:

| Setting | Value |
|---------|-------|
| **Enable Syslog** | Yes / Enabled |
| **Server Address** | Your reporter server IP (e.g., `192.168.1.100`) |
| **Port** | `6514` |
| **Protocol** | `TCP` (recommended) or `UDP` |
| **Format** | RFC 5424 (preferred) or RFC 3164 |

### Step 3: Select Log Types

Enable export for the following log categories:

- ✅ **Authentication Events** - Login success/failure, MFA events
- ✅ **Access Logs** - Application access attempts
- ✅ **Policy Events** - Policy matches and violations
- ✅ **Device Posture** - Compliance check results
- ✅ **Session Events** - Session start/end, duration

### Step 4: TLS Configuration (Recommended for Production)

For encrypted syslog transmission:

1. Generate or obtain TLS certificates for your reporter server
2. Update Alloy configuration to enable TLS:

```alloy
loki.source.syslog "cse_syslog" {
  listener {
    address  = "0.0.0.0:6514"
    protocol = "tcp"
    
    tls {
      cert_file = "/etc/alloy/certs/server.crt"
      key_file  = "/etc/alloy/certs/server.key"
    }
  }
  
  forward_to = [loki.process.cse_parser.receiver]
}
```

3. Configure CSE to use TLS and trust the certificate

### Step 5: Test the Configuration

1. **Generate Test Events**
   - Perform a test login to CSE
   - Access an application through CSE
   - Trigger a policy event (if possible in test environment)

2. **Verify Reception**
   
   Check Alloy is receiving logs:
   ```bash
   sudo journalctl -u alloy -f
   ```

3. **Verify Loki Storage**
   
   Query Loki for CSE labels:
   ```bash
   curl -s "http://localhost:3100/loki/api/v1/labels" | jq
   ```

4. **Check Grafana Dashboards**
   
   Navigate to Grafana → Dashboards → SonicWall CSE → CSE Daily Overview

## Troubleshooting

### No Data Appearing

1. **Check network connectivity**
   ```bash
   # From CSE network, test connection to reporter
   nc -zv <reporter-ip> 6514
   ```

2. **Verify Alloy is listening**
   ```bash
   sudo ss -tlnp | grep 6514
   ```

3. **Check Alloy logs**
   ```bash
   sudo journalctl -u alloy -n 50
   ```

4. **Verify firewall rules**
   ```bash
   sudo ufw status
   ```

### Logs Not Parsing Correctly

1. **Check raw syslog format**
   
   Temporarily enable debug logging in Alloy to see raw messages.

2. **Verify CSE syslog format**
   
   Ensure CSE is sending RFC 5424 format (preferred).

3. **Test with manual syslog**
   ```bash
   echo "<14>1 $(date -u +%Y-%m-%dT%H:%M:%SZ) cse-test sonicwall-cse - - - user=testuser action=success event_type=authentication" | nc localhost 6514
   ```

### High Latency or Missing Events

1. **Check Loki ingestion rate**
   ```bash
   curl -s "http://localhost:3100/metrics" | grep loki_ingester
   ```

2. **Review Alloy batch settings** in `/etc/alloy/config.alloy`

3. **Check disk space** for Loki storage
   ```bash
   df -h /var/lib/loki
   ```

## Log Format Reference

CSE sends structured syslog messages. The Alloy parser extracts these fields:

| Field | Description | Example |
|-------|-------------|---------|
| `event_type` | Type of event | `authentication`, `access`, `policy`, `posture` |
| `user` | Username | `john.doe@company.com` |
| `src_ip` | Source IP address | `192.168.1.50` |
| `application` | Accessed application | `salesforce`, `office365` |
| `action` | Result of action | `success`, `denied`, `blocked` |
| `posture_status` | Device compliance | `compliant`, `non-compliant` |

## Support

- GitHub Issues: https://github.com/wvnispen/sonicwall-cse-reporter-addon/issues
- SonicWall CSE Documentation: https://www.sonicwall.com/support/knowledge-base/

#!/usr/bin/env python3
"""
SonicWall Configuration Auditor - Web Application
==================================================
A Flask-based web interface for the SonicWall Configuration Auditor.
Users upload .exp files via browser, server processes and returns reports.

Deployment Options:
1. Local: python app.py
2. Production: gunicorn -w 4 -b 0.0.0.0:8080 app:app
3. Docker: See Dockerfile
4. Cloud: AWS Elastic Beanstalk, Google App Engine, Azure App Service, etc.

Author: SonicWall Pre-Sales Engineering
Version: 1.0.0
"""

import os
import uuid
import json
import base64
import re
import tempfile
import shutil
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List
from urllib.parse import unquote
from functools import wraps

from flask import Flask, render_template_string, request, jsonify, send_file, session
from werkzeug.utils import secure_filename

# ============================================================================
# Configuration
# ============================================================================

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()

ALLOWED_EXTENSIONS = {'exp'}

# ============================================================================
# Auditor Core (embedded to keep everything in one file)
# ============================================================================

class Severity(Enum):
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    INFO = 5

    def __str__(self):
        return self.name

    @property
    def html_color(self):
        colors = {
            Severity.CRITICAL: '#dc3545',
            Severity.HIGH: '#fd7e14',
            Severity.MEDIUM: '#ffc107',
            Severity.LOW: '#17a2b8',
            Severity.INFO: '#28a745',
        }
        return colors.get(self, '#6c757d')


@dataclass
class Finding:
    category: str
    title: str
    severity: Severity
    description: str
    current_value: str
    recommended_value: str
    reference: str
    remediation: str = ""

    def to_dict(self) -> dict:
        return {
            'category': self.category,
            'title': self.title,
            'severity': str(self.severity),
            'severity_color': self.severity.html_color,
            'severity_value': self.severity.value,
            'description': self.description,
            'current_value': self.current_value,
            'recommended_value': self.recommended_value,
            'reference': self.reference,
            'remediation': self.remediation
        }


@dataclass
class AuditResult:
    firewall_info: Dict[str, str] = field(default_factory=dict)
    findings: List[Finding] = field(default_factory=list)
    audit_time: str = field(default_factory=lambda: datetime.now().isoformat())
    summary: Dict[str, int] = field(default_factory=dict)

    def add_finding(self, finding: Finding):
        self.findings.append(finding)
        severity_name = str(finding.severity)
        self.summary[severity_name] = self.summary.get(severity_name, 0) + 1

    def to_dict(self) -> dict:
        return {
            'firewall_info': self.firewall_info,
            'audit_time': self.audit_time,
            'summary': self.summary,
            'total_findings': sum(self.summary.values()),
            'findings': [f.to_dict() for f in self.findings]
        }


class SonicWallConfigParser:
    def __init__(self):
        self.config: Dict[str, str] = {}
        self.raw_content: str = ""

    def load_from_file(self, filepath: str) -> bool:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                encoded_content = f.read().strip()
            try:
                decoded = base64.b64decode(encoded_content).decode('utf-8', errors='ignore')
            except Exception:
                decoded = encoded_content
            self.raw_content = unquote(decoded)
            for pair in self.raw_content.split('&'):
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    self.config[key] = value
            return True
        except Exception as e:
            print(f"Error loading config file: {e}")
            return False

    def load_from_content(self, content: str) -> bool:
        try:
            try:
                decoded = base64.b64decode(content).decode('utf-8', errors='ignore')
            except Exception:
                decoded = content
            self.raw_content = unquote(decoded)
            for pair in self.raw_content.split('&'):
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    self.config[key] = value
            return True
        except Exception as e:
            print(f"Error loading config: {e}")
            return False

    def get(self, key: str, default: str = "") -> str:
        return self.config.get(key, default)

    def get_all_matching(self, pattern: str) -> Dict[str, str]:
        regex = re.compile(pattern, re.IGNORECASE)
        return {k: v for k, v in self.config.items() if regex.search(k)}

    def get_indexed_items(self, prefix: str) -> List[Dict[str, str]]:
        items = []
        i = 0
        while True:
            key = f"{prefix}_{i}"
            matching = {k: v for k, v in self.config.items() if k.startswith(key)}
            if not matching:
                break
            items.append(matching)
            i += 1
        return items


class SonicWallAuditor:
    def __init__(self, parser: SonicWallConfigParser):
        self.parser = parser
        self.result = AuditResult()

    def run_audit(self) -> AuditResult:
        self._extract_firewall_info()
        self._audit_admin_access()
        self._audit_management_interfaces()
        self._audit_authentication()
        self._audit_zones_and_interfaces()
        self._audit_access_rules()
        self._audit_nat_policies()
        self._audit_security_services()
        self._audit_vpn_configuration()
        self._audit_dos_protection()
        self._audit_logging()
        self._audit_system_settings()
        self._audit_ssl_tls_settings()
        return self.result

    def _extract_firewall_info(self):
        self.result.firewall_info = {
            'model': self.parser.get('shortProdName', 'Unknown'),
            'firmware': self.parser.get('buildNum', 'Unknown'),
            'serial': self.parser.get('serialNumber', 'N/A'),
            'ha_enabled': 'Yes' if self.parser.get('hasHAPort', '0') == '1' else 'No',
            'factory_default': self.parser.get('factoryDefault', 'Unknown'),
        }

    def _audit_admin_access(self):
        category = "Administrative Access"
        timeout = self.parser.get('adminLoginTimeout', '5')
        try:
            timeout_val = int(timeout)
            if timeout_val > 15:
                self.result.add_finding(Finding(
                    category=category, title="Admin Login Timeout Too Long", severity=Severity.MEDIUM,
                    description="Admin session timeout is set too high, increasing risk of session hijacking.",
                    current_value=f"{timeout_val} minutes", recommended_value="5-15 minutes",
                    reference="SonicWall Best Practices Guide",
                    remediation="Device > Settings > Administration > Set timeout to 15 minutes or less."
                ))
        except ValueError:
            pass

        otp_required = self.parser.get('adminOtpReq', '0')
        login_otp = self.parser.get('adminLoginOtpRequire', '0')
        if otp_required == '0' and login_otp == '0':
            self.result.add_finding(Finding(
                category=category, title="Multi-Factor Authentication Not Enforced", severity=Severity.HIGH,
                description="One-Time Password (TOTP) is not required for administrator login.",
                current_value="MFA Disabled", recommended_value="Enable TOTP for all administrators",
                reference="CIS Controls - Multi-Factor Authentication",
                remediation="Device > Settings > Administration > Enable 'Require OTP for login'."
            ))

        preempt_action = self.parser.get('adminPreemptAction', '0')
        if preempt_action == '0':
            self.result.add_finding(Finding(
                category=category, title="Admin Session Preemption Not Configured", severity=Severity.INFO,
                description="Administrator session preemption behavior is not configured.",
                current_value="Default (no preemption)", recommended_value="Configure based on requirements",
                reference="SonicWall Administration Guide",
                remediation="Consider configuring admin session preemption policy."
            ))

        login_banner = self.parser.get('cli_loginBanner', '')
        if not login_banner:
            self.result.add_finding(Finding(
                category=category, title="Login Banner Not Configured", severity=Severity.LOW,
                description="A login warning banner is not configured.",
                current_value="No banner configured", recommended_value="Configure authorized use warning",
                reference="NIST 800-53 AC-8",
                remediation="Device > Settings > Administration > Configure login banner."
            ))

    def _audit_management_interfaces(self):
        category = "Management Interfaces"
        api_enabled = self.parser.get('sonicOsApi_enable', 'off')
        if api_enabled == 'on':
            basic_auth = self.parser.get('sonicOsApi_basicAuth', 'on')
            if basic_auth == 'on':
                self.result.add_finding(Finding(
                    category=category, title="API Basic Authentication Enabled", severity=Severity.MEDIUM,
                    description="Basic authentication for API is enabled.",
                    current_value="Basic Auth Enabled", recommended_value="Use Digest or Token authentication",
                    reference="OWASP API Security",
                    remediation="Disable basic auth and enable digest or token authentication."
                ))

        interfaces = self.parser.get_indexed_items('iface')
        for i, iface in enumerate(interfaces):
            iface_name = iface.get(f'iface_name_{i}', f'Interface {i}')
            iface_comment = iface.get(f'iface_comment_{i}', '')
            http_mgmt = iface.get(f'iface_http_mgmt_{i}', '0')
            if http_mgmt == '1':
                self.result.add_finding(Finding(
                    category=category, title=f"HTTP Management on {iface_name}", severity=Severity.HIGH,
                    description=f"HTTP (unencrypted) management is enabled on {iface_name}.",
                    current_value="HTTP Enabled", recommended_value="Disable HTTP, use HTTPS only",
                    reference="CIS Controls - Encrypt Data in Transit",
                    remediation=f"Network > Interfaces > {iface_name} > Disable HTTP Management."
                ))
            if 'WAN' in iface_comment.upper() or iface_name.upper() in ['X1', 'WAN']:
                https_mgmt = iface.get(f'iface_https_mgmt_{i}', '0')
                ssh_mgmt = iface.get(f'iface_ssh_mgmt_{i}', '0')
                if https_mgmt == '1':
                    self.result.add_finding(Finding(
                        category=category, title=f"HTTPS Management on WAN ({iface_name})", severity=Severity.HIGH,
                        description=f"HTTPS management exposed on WAN interface {iface_name}.",
                        current_value="HTTPS on WAN", recommended_value="Disable or restrict by source IP",
                        reference="SonicWall Security Best Practices",
                        remediation="Disable management on WAN or implement source IP restrictions."
                    ))
                if ssh_mgmt == '1':
                    self.result.add_finding(Finding(
                        category=category, title=f"SSH Management on WAN ({iface_name})", severity=Severity.HIGH,
                        description=f"SSH management exposed on WAN interface {iface_name}.",
                        current_value="SSH on WAN", recommended_value="Disable SSH on WAN",
                        reference="CIS Controls - Limit Network Access",
                        remediation="Disable SSH on WAN interfaces."
                    ))

    def _audit_authentication(self):
        category = "Authentication"
        enc_method = self.parser.get('prefsParamEncryptMethod', '0')
        if enc_method not in ['5', '6']:
            self.result.add_finding(Finding(
                category=category, title="Weak Password Encryption", severity=Severity.MEDIUM,
                description="Password encryption may not use strongest algorithm.",
                current_value=f"Method {enc_method}", recommended_value="Use Method 5 or 6",
                reference="NIST Cryptographic Standards",
                remediation="Upgrade firmware for stronger encryption."
            ))

    def _audit_zones_and_interfaces(self):
        category = "Zones & Interfaces"
        zones = self.parser.get_indexed_items('zoneObj')
        for i, zone in enumerate(zones):
            zone_name = zone.get(f'zoneObjId_{i}', f'Zone {i}')
            zone_type = zone.get(f'zoneObjZoneType_{i}', '0')
            guest_enabled = zone.get(f'zoneObjEnableGuestServices_{i}', '0')
            if guest_enabled == '1':
                bypass_av = zone.get(f'zoneObjBypassAv_{i}', '0')
                if bypass_av == '1':
                    self.result.add_finding(Finding(
                        category=category, title=f"AV Bypass for Guests on {zone_name}", severity=Severity.HIGH,
                        description=f"Guest traffic bypasses AV scanning on {zone_name}.",
                        current_value="AV Bypass Enabled", recommended_value="Disable AV bypass",
                        reference="Network Security Best Practices",
                        remediation=f"Disable AV bypass for guest services on {zone_name}."
                    ))

    def _audit_access_rules(self):
        category = "Access Rules"
        policies = self.parser.get_indexed_items('policy')
        any_any_rules = []
        for i, policy in enumerate(policies):
            policy_name = policy.get(f'policyName_{i}', f'Rule {i}')
            src_net = policy.get(f'policySrcNet_{i}', '')
            dst_net = policy.get(f'policyDstNet_{i}', '')
            dst_svc = policy.get(f'policyDstSvc_{i}', '')
            action = policy.get(f'policyAction_{i}', '0')
            bypass_dpi = policy.get(f'policyBypassDpi_{i}', '0')
            is_allow = action == '2'
            is_any = (not src_net or src_net.lower() == 'any') and \
                     (not dst_net or dst_net.lower() == 'any') and \
                     (not dst_svc or dst_svc.lower() == 'any')
            if is_allow and is_any:
                any_any_rules.append(policy_name)
            if bypass_dpi == '1' and is_allow:
                self.result.add_finding(Finding(
                    category=category, title=f"DPI Bypass: {policy_name}", severity=Severity.MEDIUM,
                    description=f"DPI bypassed on rule '{policy_name}'.",
                    current_value="DPI Bypass Enabled", recommended_value="Disable unless required",
                    reference="SonicWall Security Best Practices",
                    remediation=f"Review and disable DPI bypass on '{policy_name}'."
                ))
        if any_any_rules:
            self.result.add_finding(Finding(
                category=category, title="Overly Permissive Rules", severity=Severity.HIGH,
                description=f"Found {len(any_any_rules)} any-any-any rule(s).",
                current_value=f"Rules: {', '.join(any_any_rules[:3])}{'...' if len(any_any_rules) > 3 else ''}",
                recommended_value="Restrict to specific sources/destinations",
                reference="CIS Controls - Network Segmentation",
                remediation="Review and restrict overly permissive access rules."
            ))

    def _audit_nat_policies(self):
        category = "NAT Policies"
        nat_policies = self.parser.get_all_matching(r'^natPol')
        if nat_policies:
            self.result.add_finding(Finding(
                category=category, title="NAT Policies Review", severity=Severity.INFO,
                description="NAT policies configured. Review for exposure.",
                current_value=f"{len(nat_policies)} NAT settings",
                recommended_value="Review inbound NAT policies",
                reference="Network Security Best Practices",
                remediation="Audit NAT policies to minimize attack surface."
            ))

    def _audit_security_services(self):
        category = "Security Services"
        ssl_spy_enabled = self.parser.get('sslSpyEnabled', 'off')
        ssl_spy_server = self.parser.get('sslSpyServerEnabled', 'off')
        if ssl_spy_enabled == 'off':
            self.result.add_finding(Finding(
                category=category, title="DPI-SSL Client Disabled", severity=Severity.HIGH,
                description="DPI-SSL Client inspection disabled. Encrypted traffic not inspected.",
                current_value="DPI-SSL Client: Disabled",
                recommended_value="Enable DPI-SSL",
                reference="SonicWall DPI-SSL Guide",
                remediation="Firewall Settings > DPI-SSL > Enable Client inspection."
            ))
        if ssl_spy_server == 'off':
            self.result.add_finding(Finding(
                category=category, title="DPI-SSL Server Disabled", severity=Severity.MEDIUM,
                description="DPI-SSL Server inspection disabled.",
                current_value="DPI-SSL Server: Disabled",
                recommended_value="Enable for inbound inspection",
                reference="SonicWall DPI-SSL Guide",
                remediation="Enable DPI-SSL Server if hosting services."
            ))

    def _audit_vpn_configuration(self):
        category = "VPN Configuration"
        vpn_policies = self.parser.get_indexed_items('ipsec')
        for i, vpn in enumerate(vpn_policies):
            vpn_name = vpn.get(f'ipsecName_{i}', f'VPN {i}')
            ph1_crypt = vpn.get(f'ipsecPh1CryptAlg_{i}', '0')
            ph1_dh = vpn.get(f'ipsecP1DHGrp_{i}', '0')
            if ph1_crypt in ['1', '2']:
                self.result.add_finding(Finding(
                    category=category, title=f"Weak Encryption: {vpn_name}", severity=Severity.HIGH,
                    description=f"VPN '{vpn_name}' uses weak encryption (DES/3DES).",
                    current_value=f"{'DES' if ph1_crypt == '1' else '3DES'}",
                    recommended_value="Use AES-256",
                    reference="NIST Cryptographic Standards",
                    remediation=f"Update '{vpn_name}' to AES-256."
                ))
            if ph1_dh in ['0', '1']:
                self.result.add_finding(Finding(
                    category=category, title=f"Weak DH Group: {vpn_name}", severity=Severity.HIGH,
                    description=f"VPN '{vpn_name}' uses weak DH group.",
                    current_value=f"DH Group {ph1_dh}",
                    recommended_value="Use DH Group 14+",
                    reference="NIST SP 800-57",
                    remediation=f"Update '{vpn_name}' to DH Group 14+."
                ))

    def _audit_dos_protection(self):
        category = "DoS Protection"
        dos_profiles = self.parser.get_indexed_items('dosAct')
        for i, dos in enumerate(dos_profiles):
            profile_name = dos.get(f'dosActObjName_{i}', f'DoS Profile {i}')
            syn_flood = dos.get(f'dosSynFld_{i}', '0')
            if syn_flood == '0':
                self.result.add_finding(Finding(
                    category=category, title=f"SYN Flood Disabled: {profile_name}", severity=Severity.HIGH,
                    description=f"SYN Flood protection disabled in '{profile_name}'.",
                    current_value="SYN Flood: Disabled",
                    recommended_value="Enable protection",
                    reference="DoS Mitigation Best Practices",
                    remediation=f"Enable SYN Flood in '{profile_name}'."
                ))

    def _audit_logging(self):
        category = "Logging & Monitoring"
        syslog_server = self.parser.get('syslogServerName', '')
        if not syslog_server or syslog_server.strip() == '' or syslog_server == '0.0.0.0':
            self.result.add_finding(Finding(
                category=category, title="Syslog Not Configured", severity=Severity.HIGH,
                description="No syslog server configured.",
                current_value="Syslog: Not configured",
                recommended_value="Configure syslog to SIEM",
                reference="NIST 800-53 AU-4",
                remediation="Device > Log > Syslog > Configure server."
            ))
        else:
            self.result.add_finding(Finding(
                category=category, title="Syslog Configured", severity=Severity.INFO,
                description="Syslog server is configured.",
                current_value=f"Syslog: {syslog_server}",
                recommended_value="Verify logs received",
                reference="NIST 800-53 AU-4",
                remediation="Verify syslog server is receiving logs."
            ))

        analyzer_mode = self.parser.get('syslogAnalyzerMode', 'off')
        viewpoint_mode = self.parser.get('syslogViewPointMode', 'off')
        if analyzer_mode == 'off' and viewpoint_mode == 'off':
            self.result.add_finding(Finding(
                category=category, title="Analytics Not Configured", severity=Severity.MEDIUM,
                description="NSM/Analytics integration not configured.",
                current_value="Analytics: Disabled",
                recommended_value="Configure NSM or Analytics",
                reference="SonicWall NSM Guide",
                remediation="Enable NSM or Analytics integration."
            ))

        ntp_enabled = self.parser.get('ntp_useNtp', 'off')
        if ntp_enabled.lower() != 'on':
            self.result.add_finding(Finding(
                category=category, title="NTP Disabled", severity=Severity.MEDIUM,
                description="NTP not enabled. Time accuracy critical for logs.",
                current_value="NTP: Disabled",
                recommended_value="Enable NTP",
                reference="NIST 800-53 AU-8",
                remediation="Device > Settings > Time > Enable NTP."
            ))

    def _audit_system_settings(self):
        category = "System Settings"
        factory_default = self.parser.get('factoryDefault', 'off')
        if factory_default == 'on':
            self.result.add_finding(Finding(
                category=category, title="Factory Default Detected", severity=Severity.CRITICAL,
                description="Firewall running factory default configuration.",
                current_value="Factory Default: Yes",
                recommended_value="Configure according to policy",
                reference="Deployment Best Practices",
                remediation="Complete firewall configuration."
            ))

        geo_enabled = self.parser.get('geoEnforcement', '0')
        if geo_enabled != '1':
            self.result.add_finding(Finding(
                category=category, title="Geo-IP Disabled", severity=Severity.MEDIUM,
                description="Geo-IP enforcement disabled.",
                current_value="Geo-IP: Disabled",
                recommended_value="Enable Geo-IP filtering",
                reference="Threat Intelligence Best Practices",
                remediation="Security Services > Geo-IP > Enable."
            ))

        botnet_enabled = self.parser.get('botnetBlock', '0')
        if botnet_enabled != '1':
            self.result.add_finding(Finding(
                category=category, title="Botnet Filtering Disabled", severity=Severity.HIGH,
                description="Botnet filtering disabled.",
                current_value="Botnet: Disabled",
                recommended_value="Enable Botnet filtering",
                reference="Threat Intelligence Best Practices",
                remediation="Security Services > Botnet Filter > Enable."
            ))

    def _audit_ssl_tls_settings(self):
        category = "SSL/TLS Security"
        cipher_config = self.parser.get('cipherControlTLS', '')
        if cipher_config:
            weak_cipher_ids = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 47, 48, 49, 50, 51, 52, 53]
            try:
                ciphers = json.loads(cipher_config)
                enabled_weak = [c.get('c') for c in ciphers if c.get('b', 0) == 0 and c.get('c', 0) in weak_cipher_ids]
                if enabled_weak:
                    self.result.add_finding(Finding(
                        category=category, title="Weak TLS Ciphers", severity=Severity.HIGH,
                        description=f"Found {len(enabled_weak)} weak cipher suites.",
                        current_value=f"Weak ciphers: {len(enabled_weak)}",
                        recommended_value="Disable NULL, EXPORT, RC4, DES",
                        reference="NIST TLS Guidelines",
                        remediation="Review and disable weak ciphers."
                    ))
            except json.JSONDecodeError:
                pass


# ============================================================================
# Helper Functions
# ============================================================================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def cleanup_old_files():
    """Clean up files older than 1 hour"""
    import time
    now = time.time()
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.isfile(filepath) and now - os.path.getmtime(filepath) > 3600:
            os.remove(filepath)


# ============================================================================
# HTML Templates
# ============================================================================

INDEX_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SonicWall Configuration Auditor</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #ff6b35;
            --primary-dark: #e55a2b;
            --bg: #0f0f1a;
            --surface: #1a1a2e;
            --text: #e8e8e8;
            --text-muted: #8892a0;
            --success: #00d68f;
            --warning: #ffaa00;
            --danger: #ff3d71;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Outfit', sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            line-height: 1.6;
        }
        .container { max-width: 900px; margin: 0 auto; padding: 40px 20px; }
        .header {
            text-align: center;
            margin-bottom: 40px;
        }
        .logo {
            display: inline-flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 16px;
        }
        .logo-icon {
            width: 50px;
            height: 50px;
            background: linear-gradient(135deg, var(--primary), #f7931e);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
        }
        .logo-text { font-size: 1.8rem; font-weight: 700; }
        .subtitle { color: var(--text-muted); }
        .upload-area {
            background: var(--surface);
            border: 2px dashed rgba(255, 107, 53, 0.3);
            border-radius: 16px;
            padding: 60px 40px;
            text-align: center;
            transition: all 0.3s;
            cursor: pointer;
        }
        .upload-area:hover, .upload-area.dragover {
            border-color: var(--primary);
            background: rgba(255, 107, 53, 0.05);
        }
        .upload-icon { font-size: 3rem; margin-bottom: 16px; }
        .upload-text { font-size: 1.2rem; margin-bottom: 8px; }
        .upload-hint { color: var(--text-muted); font-size: 0.9rem; }
        .file-input { display: none; }
        .btn {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 14px 32px;
            border-radius: 8px;
            font-weight: 600;
            text-decoration: none;
            border: none;
            cursor: pointer;
            font-size: 1rem;
            font-family: inherit;
            transition: all 0.3s;
        }
        .btn-primary {
            background: linear-gradient(135deg, var(--primary), #f7931e);
            color: white;
        }
        .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 4px 20px rgba(255, 107, 53, 0.4); }
        .btn-primary:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
        .selected-file {
            margin-top: 20px;
            padding: 16px;
            background: rgba(255, 107, 53, 0.1);
            border-radius: 8px;
            display: none;
        }
        .selected-file.show { display: flex; align-items: center; justify-content: space-between; }
        .file-name { font-family: 'JetBrains Mono', monospace; }
        .file-remove { background: none; border: none; color: var(--danger); cursor: pointer; font-size: 1.2rem; }
        .actions { margin-top: 30px; text-align: center; }
        .progress-container { margin-top: 30px; display: none; }
        .progress-container.show { display: block; }
        .progress-bar {
            height: 6px;
            background: var(--surface);
            border-radius: 3px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(135deg, var(--primary), #f7931e);
            width: 0%;
            transition: width 0.3s;
        }
        .progress-text { text-align: center; margin-top: 12px; color: var(--text-muted); }
        .error-message {
            margin-top: 20px;
            padding: 16px;
            background: rgba(255, 61, 113, 0.1);
            border: 1px solid var(--danger);
            border-radius: 8px;
            color: var(--danger);
            display: none;
        }
        .error-message.show { display: block; }
        .features {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin-top: 60px;
        }
        .feature {
            background: var(--surface);
            padding: 24px;
            border-radius: 12px;
            text-align: center;
        }
        .feature-icon { font-size: 2rem; margin-bottom: 12px; }
        .feature-title { font-weight: 600; margin-bottom: 8px; }
        .feature-desc { color: var(--text-muted); font-size: 0.9rem; }
        @media (max-width: 640px) {
            .features { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">
                <div class="logo-icon">&#128737;</div>
                <span class="logo-text">SonicWall Auditor</span>
            </div>
            <p class="subtitle">Upload your .exp configuration file for instant security assessment</p>
        </div>

        <div class="upload-area" id="uploadArea">
            <div class="upload-icon">&#128194;</div>
            <div class="upload-text">Drop your .exp file here</div>
            <div class="upload-hint">or click to browse</div>
            <input type="file" class="file-input" id="fileInput" accept=".exp">
        </div>

        <div class="selected-file" id="selectedFile">
            <span class="file-name" id="fileName"></span>
            <button class="file-remove" id="removeFile">&times;</button>
        </div>

        <div class="error-message" id="errorMessage"></div>

        <div class="progress-container" id="progressContainer">
            <div class="progress-bar">
                <div class="progress-fill" id="progressFill"></div>
            </div>
            <div class="progress-text" id="progressText">Uploading...</div>
        </div>

        <div class="actions">
            <button class="btn btn-primary" id="auditBtn" disabled>
                &#128270; Run Security Audit
            </button>
        </div>

        <div class="features">
            <div class="feature">
                <div class="feature-icon">&#128274;</div>
                <div class="feature-title">Secure</div>
                <div class="feature-desc">Files processed server-side, never stored permanently</div>
            </div>
            <div class="feature">
                <div class="feature-icon">&#9889;</div>
                <div class="feature-title">Instant</div>
                <div class="feature-desc">Get results in seconds with 50+ security checks</div>
            </div>
            <div class="feature">
                <div class="feature-icon">&#128196;</div>
                <div class="feature-title">Reports</div>
                <div class="feature-desc">Download professional HTML and PDF reports</div>
            </div>
        </div>
    </div>

    <script>
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        const selectedFile = document.getElementById('selectedFile');
        const fileName = document.getElementById('fileName');
        const removeFile = document.getElementById('removeFile');
        const auditBtn = document.getElementById('auditBtn');
        const progressContainer = document.getElementById('progressContainer');
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        const errorMessage = document.getElementById('errorMessage');

        let currentFile = null;

        uploadArea.addEventListener('click', () => fileInput.click());
        uploadArea.addEventListener('dragover', (e) => { e.preventDefault(); uploadArea.classList.add('dragover'); });
        uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
        });
        fileInput.addEventListener('change', () => { if (fileInput.files.length) handleFile(fileInput.files[0]); });
        removeFile.addEventListener('click', clearFile);
        auditBtn.addEventListener('click', runAudit);

        function handleFile(file) {
            if (!file.name.endsWith('.exp')) {
                showError('Please select a .exp configuration file');
                return;
            }
            currentFile = file;
            fileName.textContent = file.name;
            selectedFile.classList.add('show');
            auditBtn.disabled = false;
            errorMessage.classList.remove('show');
        }

        function clearFile() {
            currentFile = null;
            fileInput.value = '';
            selectedFile.classList.remove('show');
            auditBtn.disabled = true;
        }

        function showError(msg) {
            errorMessage.textContent = msg;
            errorMessage.classList.add('show');
        }

        async function runAudit() {
            if (!currentFile) return;

            auditBtn.disabled = true;
            progressContainer.classList.add('show');
            errorMessage.classList.remove('show');

            const formData = new FormData();
            formData.append('file', currentFile);

            try {
                progressFill.style.width = '30%';
                progressText.textContent = 'Uploading configuration...';

                const response = await fetch('/audit', {
                    method: 'POST',
                    body: formData
                });

                progressFill.style.width = '70%';
                progressText.textContent = 'Running security audit...';

                const data = await response.json();

                if (data.error) {
                    showError(data.error);
                    progressContainer.classList.remove('show');
                    auditBtn.disabled = false;
                    return;
                }

                progressFill.style.width = '100%';
                progressText.textContent = 'Redirecting to results...';

                setTimeout(() => {
                    window.location.href = '/results/' + data.audit_id;
                }, 500);

            } catch (err) {
                showError('Error processing file. Please try again.');
                progressContainer.classList.remove('show');
                auditBtn.disabled = false;
            }
        }
    </script>
</body>
</html>
'''

RESULTS_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Audit Results - SonicWall Configuration Auditor</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #ff6b35;
            --bg: #0f0f1a;
            --surface: #1a1a2e;
            --text: #e8e8e8;
            --text-muted: #8892a0;
            --critical: #dc3545;
            --high: #fd7e14;
            --medium: #ffc107;
            --low: #17a2b8;
            --info: #28a745;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Outfit', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }
        .container { max-width: 1100px; margin: 0 auto; padding: 40px 20px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 40px; flex-wrap: wrap; gap: 20px; }
        .logo { display: flex; align-items: center; gap: 12px; text-decoration: none; color: var(--text); }
        .logo-icon { width: 40px; height: 40px; background: linear-gradient(135deg, var(--primary), #f7931e); border-radius: 10px; display: flex; align-items: center; justify-content: center; }
        .logo-text { font-size: 1.4rem; font-weight: 700; }
        .actions { display: flex; gap: 12px; }
        .btn { display: inline-flex; align-items: center; gap: 8px; padding: 10px 20px; border-radius: 6px; font-weight: 500; text-decoration: none; border: none; cursor: pointer; font-size: 0.9rem; font-family: inherit; transition: all 0.3s; }
        .btn-primary { background: linear-gradient(135deg, var(--primary), #f7931e); color: white; }
        .btn-outline { background: transparent; color: var(--primary); border: 1px solid var(--primary); }
        .btn:hover { transform: translateY(-1px); }
        .firewall-info { background: var(--surface); border-radius: 12px; padding: 24px; margin-bottom: 30px; display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 20px; }
        .info-item label { display: block; color: var(--text-muted); font-size: 0.85rem; margin-bottom: 4px; }
        .info-item span { font-weight: 600; font-size: 1.1rem; }
        .summary { display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; margin-bottom: 40px; }
        .summary-card { background: var(--surface); border-radius: 10px; padding: 20px; text-align: center; border-left: 4px solid; }
        .summary-card.critical { border-color: var(--critical); }
        .summary-card.high { border-color: var(--high); }
        .summary-card.medium { border-color: var(--medium); }
        .summary-card.low { border-color: var(--low); }
        .summary-card.info { border-color: var(--info); }
        .summary-count { font-size: 2rem; font-weight: 700; }
        .summary-label { color: var(--text-muted); font-size: 0.9rem; }
        .findings-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .findings-title { font-size: 1.5rem; font-weight: 600; }
        .filter-tabs { display: flex; gap: 8px; flex-wrap: wrap; }
        .filter-tab { padding: 6px 14px; border-radius: 20px; background: var(--surface); border: none; color: var(--text-muted); cursor: pointer; font-family: inherit; font-size: 0.85rem; transition: all 0.2s; }
        .filter-tab:hover, .filter-tab.active { background: var(--primary); color: white; }
        .finding { background: var(--surface); border-radius: 10px; padding: 20px; margin-bottom: 16px; border-left: 4px solid; }
        .finding.CRITICAL { border-color: var(--critical); }
        .finding.HIGH { border-color: var(--high); }
        .finding.MEDIUM { border-color: var(--medium); }
        .finding.LOW { border-color: var(--low); }
        .finding.INFO { border-color: var(--info); }
        .finding-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; gap: 12px; }
        .finding-title { font-weight: 600; font-size: 1.1rem; }
        .finding-badge { padding: 4px 10px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; color: white; }
        .finding-badge.CRITICAL { background: var(--critical); }
        .finding-badge.HIGH { background: var(--high); }
        .finding-badge.MEDIUM { background: var(--medium); color: #333; }
        .finding-badge.LOW { background: var(--low); }
        .finding-badge.INFO { background: var(--info); }
        .finding-category { color: var(--text-muted); font-size: 0.85rem; margin-bottom: 8px; }
        .finding-description { margin-bottom: 16px; }
        .finding-details { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; font-size: 0.9rem; }
        .finding-detail { background: rgba(255,255,255,0.03); padding: 12px; border-radius: 6px; }
        .finding-detail label { display: block; color: var(--text-muted); font-size: 0.8rem; margin-bottom: 4px; }
        .finding-remediation { margin-top: 16px; padding: 12px; background: rgba(0, 214, 143, 0.1); border-radius: 6px; border-left: 3px solid var(--info); }
        .finding-remediation label { color: var(--info); font-weight: 600; font-size: 0.85rem; }
        .no-findings { text-align: center; padding: 60px; color: var(--text-muted); }
        @media (max-width: 768px) {
            .summary { grid-template-columns: repeat(3, 1fr); }
            .header { flex-direction: column; align-items: flex-start; }
        }
        @media (max-width: 480px) {
            .summary { grid-template-columns: repeat(2, 1fr); }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <a href="/" class="logo">
                <div class="logo-icon">&#128737;</div>
                <span class="logo-text">SonicWall Auditor</span>
            </a>
            <div class="actions">
                <a href="/download/html/{{ audit_id }}" class="btn btn-primary">&#128196; Download HTML</a>
                <a href="/download/json/{{ audit_id }}" class="btn btn-outline">&#128194; Download JSON</a>
                <a href="/" class="btn btn-outline">&#128257; New Audit</a>
            </div>
        </div>

        <div class="firewall-info">
            {% for key, value in result.firewall_info.items() %}
            <div class="info-item">
                <label>{{ key.replace('_', ' ').title() }}</label>
                <span>{{ value }}</span>
            </div>
            {% endfor %}
            <div class="info-item">
                <label>Audit Time</label>
                <span>{{ result.audit_time[:19].replace('T', ' ') }}</span>
            </div>
        </div>

        <div class="summary">
            <div class="summary-card critical">
                <div class="summary-count">{{ result.summary.get('CRITICAL', 0) }}</div>
                <div class="summary-label">Critical</div>
            </div>
            <div class="summary-card high">
                <div class="summary-count">{{ result.summary.get('HIGH', 0) }}</div>
                <div class="summary-label">High</div>
            </div>
            <div class="summary-card medium">
                <div class="summary-count">{{ result.summary.get('MEDIUM', 0) }}</div>
                <div class="summary-label">Medium</div>
            </div>
            <div class="summary-card low">
                <div class="summary-count">{{ result.summary.get('LOW', 0) }}</div>
                <div class="summary-label">Low</div>
            </div>
            <div class="summary-card info">
                <div class="summary-count">{{ result.summary.get('INFO', 0) }}</div>
                <div class="summary-label">Info</div>
            </div>
        </div>

        <div class="findings-header">
            <h2 class="findings-title">Findings ({{ result.total_findings }})</h2>
            <div class="filter-tabs">
                <button class="filter-tab active" data-filter="all">All</button>
                <button class="filter-tab" data-filter="CRITICAL">Critical</button>
                <button class="filter-tab" data-filter="HIGH">High</button>
                <button class="filter-tab" data-filter="MEDIUM">Medium</button>
                <button class="filter-tab" data-filter="LOW">Low</button>
                <button class="filter-tab" data-filter="INFO">Info</button>
            </div>
        </div>

        <div id="findings">
            {% for finding in result.findings|sort(attribute='severity_value') %}
            <div class="finding {{ finding.severity }}" data-severity="{{ finding.severity }}">
                <div class="finding-header">
                    <div>
                        <div class="finding-category">{{ finding.category }}</div>
                        <div class="finding-title">{{ finding.title }}</div>
                    </div>
                    <span class="finding-badge {{ finding.severity }}">{{ finding.severity }}</span>
                </div>
                <div class="finding-description">{{ finding.description }}</div>
                <div class="finding-details">
                    <div class="finding-detail">
                        <label>Current Value</label>
                        <span>{{ finding.current_value }}</span>
                    </div>
                    <div class="finding-detail">
                        <label>Recommended</label>
                        <span>{{ finding.recommended_value }}</span>
                    </div>
                    <div class="finding-detail">
                        <label>Reference</label>
                        <span>{{ finding.reference }}</span>
                    </div>
                </div>
                {% if finding.remediation %}
                <div class="finding-remediation">
                    <label>Remediation</label>
                    <p>{{ finding.remediation }}</p>
                </div>
                {% endif %}
            </div>
            {% endfor %}
        </div>

        {% if not result.findings %}
        <div class="no-findings">
            <p>No findings detected. Configuration appears secure!</p>
        </div>
        {% endif %}
    </div>

    <script>
        document.querySelectorAll('.filter-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const filter = tab.dataset.filter;
                document.querySelectorAll('.finding').forEach(f => {
                    f.style.display = (filter === 'all' || f.dataset.severity === filter) ? 'block' : 'none';
                });
            });
        });
    </script>
</body>
</html>
'''


# ============================================================================
# Routes
# ============================================================================

@app.route('/')
def index():
    return render_template_string(INDEX_HTML)


@app.route('/audit', methods=['POST'])
def audit():
    cleanup_old_files()
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Please upload a .exp file'}), 400
    
    try:
        # Generate unique ID for this audit
        audit_id = str(uuid.uuid4())[:8]
        
        # Save uploaded file temporarily
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{audit_id}_{filename}")
        file.save(filepath)
        
        # Run audit
        parser = SonicWallConfigParser()
        if not parser.load_from_file(filepath):
            os.remove(filepath)
            return jsonify({'error': 'Failed to parse configuration file'}), 400
        
        auditor = SonicWallAuditor(parser)
        result = auditor.run_audit()
        
        # Store result in session (or use Redis/database for production)
        result_dict = result.to_dict()
        result_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{audit_id}_result.json")
        with open(result_path, 'w') as f:
            json.dump(result_dict, f)
        
        # Clean up uploaded file
        os.remove(filepath)
        
        return jsonify({'audit_id': audit_id, 'success': True})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/results/<audit_id>')
def results(audit_id):
    result_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{audit_id}_result.json")
    
    if not os.path.exists(result_path):
        return "Audit results not found or expired", 404
    
    with open(result_path, 'r') as f:
        result = json.load(f)
    
    return render_template_string(RESULTS_HTML, result=result, audit_id=audit_id)


@app.route('/download/html/<audit_id>')
def download_html(audit_id):
    result_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{audit_id}_result.json")
    
    if not os.path.exists(result_path):
        return "Audit results not found", 404
    
    with open(result_path, 'r') as f:
        result = json.load(f)
    
    # Generate HTML report
    html = generate_html_report(result)
    
    # Save to temp file
    html_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{audit_id}_report.html")
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return send_file(html_path, as_attachment=True, download_name=f"sonicwall_audit_{audit_id}.html")


@app.route('/download/json/<audit_id>')
def download_json(audit_id):
    result_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{audit_id}_result.json")
    
    if not os.path.exists(result_path):
        return "Audit results not found", 404
    
    return send_file(result_path, as_attachment=True, download_name=f"sonicwall_audit_{audit_id}.json")


def generate_html_report(result):
    """Generate standalone HTML report"""
    findings_html = ""
    categories = {}
    for f in result['findings']:
        if f['category'] not in categories:
            categories[f['category']] = []
        categories[f['category']].append(f)
    
    for category, findings in categories.items():
        findings_html += f'<div class="category"><h2>{category}</h2>'
        for f in sorted(findings, key=lambda x: x['severity_value']):
            findings_html += f'''
            <div class="finding {f['severity'].lower()}">
                <div class="finding-header">
                    <span class="finding-title">{f['title']}</span>
                    <span class="finding-severity {f['severity'].lower()}">{f['severity']}</span>
                </div>
                <div class="finding-detail"><strong>Description:</strong> {f['description']}</div>
                <div class="finding-detail"><strong>Current:</strong> {f['current_value']}</div>
                <div class="finding-detail"><strong>Recommended:</strong> {f['recommended_value']}</div>
                <div class="finding-detail"><strong>Reference:</strong> {f['reference']}</div>
                {f'<div class="finding-remediation"><strong>Remediation:</strong> {f["remediation"]}</div>' if f['remediation'] else ''}
            </div>'''
        findings_html += '</div>'
    
    return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>SonicWall Audit Report</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:20px;background:#f5f5f5}}
.header{{background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:30px;border-radius:10px;margin-bottom:20px}}
.info-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:15px;margin-bottom:20px}}
.info-card{{background:white;padding:15px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1)}}
.info-card h3{{color:#667eea;font-size:0.8rem;margin:0 0 5px}}
.summary{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:30px}}
.summary-card{{padding:15px;border-radius:8px;text-align:center;color:white}}
.summary-card.critical{{background:#dc3545}}.summary-card.high{{background:#fd7e14}}
.summary-card.medium{{background:#ffc107;color:#333}}.summary-card.low{{background:#17a2b8}}.summary-card.info{{background:#28a745}}
.category h2{{color:#667eea;border-bottom:2px solid #667eea;padding-bottom:8px;margin:20px 0 15px}}
.finding{{background:white;border-left:4px solid;padding:15px;margin-bottom:12px;border-radius:0 8px 8px 0}}
.finding.critical{{border-color:#dc3545}}.finding.high{{border-color:#fd7e14}}.finding.medium{{border-color:#ffc107}}.finding.low{{border-color:#17a2b8}}.finding.info{{border-color:#28a745}}
.finding-header{{display:flex;justify-content:space-between;margin-bottom:10px}}
.finding-title{{font-weight:600}}.finding-severity{{padding:2px 8px;border-radius:4px;font-size:0.75rem;color:white}}
.finding-severity.critical{{background:#dc3545}}.finding-severity.high{{background:#fd7e14}}.finding-severity.medium{{background:#ffc107;color:#333}}.finding-severity.low{{background:#17a2b8}}.finding-severity.info{{background:#28a745}}
.finding-detail{{margin:8px 0;font-size:0.9rem}}.finding-detail strong{{color:#555}}
.finding-remediation{{background:#e8f5e9;padding:10px;border-radius:4px;margin-top:10px}}
</style></head><body>
<div class="header"><h1>SonicWall Configuration Audit Report</h1><p>Generated: {result['audit_time'][:19]}</p></div>
<div class="info-grid">{''.join(f'<div class="info-card"><h3>{k.replace("_"," ").title()}</h3><p>{v}</p></div>' for k,v in result['firewall_info'].items())}</div>
<div class="summary">
<div class="summary-card critical"><div style="font-size:1.5rem;font-weight:bold">{result['summary'].get('CRITICAL',0)}</div><div>Critical</div></div>
<div class="summary-card high"><div style="font-size:1.5rem;font-weight:bold">{result['summary'].get('HIGH',0)}</div><div>High</div></div>
<div class="summary-card medium"><div style="font-size:1.5rem;font-weight:bold">{result['summary'].get('MEDIUM',0)}</div><div>Medium</div></div>
<div class="summary-card low"><div style="font-size:1.5rem;font-weight:bold">{result['summary'].get('LOW',0)}</div><div>Low</div></div>
<div class="summary-card info"><div style="font-size:1.5rem;font-weight:bold">{result['summary'].get('INFO',0)}</div><div>Info</div></div>
</div>
{findings_html}
</body></html>'''


# ============================================================================
# Main
# ============================================================================

if __name__ == '__main__':
    print("=" * 50)
    print("SonicWall Configuration Auditor - Web Interface")
    print("=" * 50)
    print(f"Upload folder: {app.config['UPLOAD_FOLDER']}")
    print("Starting server at http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)

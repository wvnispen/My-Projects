#!/usr/bin/env python3
"""
SonicWall Configuration Auditor
================================
A comprehensive tool to audit SonicWall firewall configurations against
industry best practices and security hardening guidelines.

Supports:
- SonicOS 7.x (Gen 7)
- SonicOS 8.x (Gen 8)

Input Methods:
1. Load from exported .exp configuration file
2. Fetch via REST API from live firewall

Output Formats:
- Terminal (colored)
- HTML Report
- PDF Report
- JSON (for automation)

Based on:
- SonicWall Best Practices Guide
- CIS Benchmark recommendations
- NIST Cybersecurity Framework
- Common security hardening standards

Author: SonicWall Pre-Sales Engineering
Version: 1.1.0
"""

import argparse
import base64
import json
import os
import re
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote
import getpass

# Optional imports for GUI
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext
    TK_AVAILABLE = True
except ImportError:
    TK_AVAILABLE = False

# Optional imports for REST API and reporting
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


class Severity(Enum):
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    INFO = 5

    def __str__(self):
        return self.name

    @property
    def color(self):
        colors_map = {
            Severity.CRITICAL: '\033[91m',
            Severity.HIGH: '\033[93m',
            Severity.MEDIUM: '\033[94m',
            Severity.LOW: '\033[96m',
            Severity.INFO: '\033[92m',
        }
        return colors_map.get(self, '\033[0m')

    @property
    def html_color(self):
        colors_map = {
            Severity.CRITICAL: '#dc3545',
            Severity.HIGH: '#fd7e14',
            Severity.MEDIUM: '#ffc107',
            Severity.LOW: '#17a2b8',
            Severity.INFO: '#28a745',
        }
        return colors_map.get(self, '#6c757d')


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

    def load_from_api(self, host: str, username: str, password: str,
                      port: int = 443, verify_ssl: bool = False) -> bool:
        if not REQUESTS_AVAILABLE:
            print("Error: 'requests' library required for API access.")
            return False
        try:
            if not verify_ssl:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            base_url = f"https://{host}:{port}/api/sonicos"
            session = requests.Session()
            session.verify = verify_ssl
            auth_url = f"{base_url}/auth"
            auth_response = session.post(auth_url, auth=(username, password),
                                         headers={'Accept': 'application/json'})
            if auth_response.status_code != 200:
                print(f"Authentication failed: {auth_response.status_code}")
                return False
            config_endpoints = [
                '/administration/settings', '/zones', '/interfaces/ipv4',
                '/access-rules/ipv4', '/nat-policies/ipv4', '/vpn/policies/ipv4',
                '/security-services/gateway-anti-virus', '/security-services/intrusion-prevention',
                '/security-services/anti-spyware', '/security-services/content-filter',
                '/firewall/dos', '/log/settings', '/high-availability/settings', '/users/local',
            ]
            for endpoint in config_endpoints:
                try:
                    response = session.get(f"{base_url}{endpoint}", headers={'Accept': 'application/json'})
                    if response.status_code == 200:
                        self._flatten_json(response.json(), endpoint.replace('/', '_'))
                except Exception:
                    pass
            session.delete(auth_url)
            return len(self.config) > 0
        except Exception as e:
            print(f"API connection error: {e}")
            return False

    def _flatten_json(self, data: Any, prefix: str = ""):
        if isinstance(data, dict):
            for key, value in data.items():
                self._flatten_json(value, f"{prefix}_{key}" if prefix else key)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                self._flatten_json(item, f"{prefix}_{i}")
        else:
            self.config[prefix] = str(data)

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
                    reference="SonicWall Best Practices Guide - Administrative Access",
                    remediation="Navigate to Device > Settings > Administration and set 'Administrator inactivity timeout' to 15 minutes or less."
                ))
        except ValueError:
            pass

        cli_timeout = self.parser.get('cli_idleTimeout', '300')
        try:
            cli_timeout_val = int(cli_timeout)
            if cli_timeout_val > 600:
                self.result.add_finding(Finding(
                    category=category, title="CLI Idle Timeout Too Long", severity=Severity.LOW,
                    description="CLI session timeout is set too high.",
                    current_value=f"{cli_timeout_val} seconds", recommended_value="300-600 seconds",
                    reference="SonicWall Best Practices Guide",
                    remediation="Configure CLI idle timeout via CLI: 'administration idle-logout 300'"
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
                reference="CIS Controls - Use Multi-Factor Authentication",
                remediation="Navigate to Device > Settings > Administration and enable 'Require OTP for login'."
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
                current_value="No banner configured", recommended_value="Configure authorized use warning banner",
                reference="NIST 800-53 AC-8 - System Use Notification",
                remediation="Configure login banner via Device > Settings > Administration."
            ))

    def _audit_management_interfaces(self):
        category = "Management Interfaces"
        api_enabled = self.parser.get('sonicOsApi_enable', 'off')
        if api_enabled == 'on':
            basic_auth = self.parser.get('sonicOsApi_basicAuth', 'on')
            token_auth = self.parser.get('sonicOsApi_tokenAuth', 'off')
            if basic_auth == 'on':
                self.result.add_finding(Finding(
                    category=category, title="API Basic Authentication Enabled", severity=Severity.MEDIUM,
                    description="Basic authentication for API is enabled.",
                    current_value="Basic Auth Enabled", recommended_value="Use Digest or Token authentication",
                    reference="OWASP API Security - Authentication",
                    remediation="Disable basic auth and enable digest or token authentication."
                ))
            if token_auth == 'off':
                self.result.add_finding(Finding(
                    category=category, title="API Token Authentication Disabled", severity=Severity.LOW,
                    description="Token-based authentication for API is disabled.",
                    current_value="Token Auth Disabled", recommended_value="Enable token authentication",
                    reference="SonicWall API Best Practices",
                    remediation="Enable API token authentication for automated access."
                ))

        interfaces = self.parser.get_indexed_items('iface')
        for i, iface in enumerate(interfaces):
            iface_name = iface.get(f'iface_name_{i}', f'Interface {i}')
            iface_comment = iface.get(f'iface_comment_{i}', '')
            http_mgmt = iface.get(f'iface_http_mgmt_{i}', '0')
            if http_mgmt == '1':
                self.result.add_finding(Finding(
                    category=category, title=f"HTTP Management Enabled on {iface_name}", severity=Severity.HIGH,
                    description=f"HTTP (unencrypted) management is enabled on interface {iface_name}.",
                    current_value="HTTP Management Enabled", recommended_value="Disable HTTP, use HTTPS only",
                    reference="CIS Controls - Encrypt Sensitive Data in Transit",
                    remediation=f"Disable HTTP Management on {iface_name}."
                ))
            if 'WAN' in iface_comment.upper() or iface_name.upper() in ['X1', 'WAN']:
                https_mgmt = iface.get(f'iface_https_mgmt_{i}', '0')
                ssh_mgmt = iface.get(f'iface_ssh_mgmt_{i}', '0')
                snmp_mgmt = iface.get(f'iface_snmp_mgmt_{i}', '0')
                if https_mgmt == '1':
                    self.result.add_finding(Finding(
                        category=category, title=f"HTTPS Management on WAN ({iface_name})", severity=Severity.HIGH,
                        description=f"HTTPS management is enabled on WAN interface {iface_name}.",
                        current_value="HTTPS Enabled on WAN", recommended_value="Disable or restrict by source IP",
                        reference="SonicWall Security Best Practices",
                        remediation="Disable management on WAN or implement strict source IP restrictions."
                    ))
                if ssh_mgmt == '1':
                    self.result.add_finding(Finding(
                        category=category, title=f"SSH Management on WAN ({iface_name})", severity=Severity.HIGH,
                        description=f"SSH management is enabled on WAN interface {iface_name}.",
                        current_value="SSH Enabled on WAN", recommended_value="Disable SSH on WAN",
                        reference="CIS Controls - Limit Network Access",
                        remediation="Disable SSH on WAN interfaces."
                    ))
                if snmp_mgmt == '1':
                    self.result.add_finding(Finding(
                        category=category, title=f"SNMP on WAN ({iface_name})", severity=Severity.MEDIUM,
                        description=f"SNMP is enabled on WAN interface {iface_name}.",
                        current_value="SNMP Enabled on WAN", recommended_value="Disable SNMP on WAN",
                        reference="NIST Guidelines - Secure Network Management",
                        remediation="Disable SNMP on WAN interfaces."
                    ))

    def _audit_authentication(self):
        category = "Authentication"
        enc_method = self.parser.get('prefsParamEncryptMethod', '0')
        if enc_method not in ['5', '6']:
            self.result.add_finding(Finding(
                category=category, title="Weak Password Encryption Method", severity=Severity.MEDIUM,
                description="Password encryption method may not be using the strongest algorithm.",
                current_value=f"Method {enc_method}", recommended_value="Use Method 5 or 6",
                reference="NIST Guidelines - Cryptographic Standards",
                remediation="Upgrade firmware if stronger encryption is not available."
            ))

    def _audit_zones_and_interfaces(self):
        category = "Zones & Interfaces"
        zones = self.parser.get_indexed_items('zoneObj')
        for i, zone in enumerate(zones):
            zone_name = zone.get(f'zoneObjId_{i}', f'Zone {i}')
            zone_type = zone.get(f'zoneObjZoneType_{i}', '0')
            gav_profile = zone.get(f'zoneObjGavProfile_{i}', '0')
            dpi_ssl_client = zone.get(f'zoneObjDPISSLCProfile_{i}', '0')
            if zone_type == '1':
                if gav_profile == '0':
                    self.result.add_finding(Finding(
                        category=category, title=f"Gateway AV Not Applied to {zone_name}", severity=Severity.MEDIUM,
                        description=f"Gateway Anti-Virus profile is not applied to zone {zone_name}.",
                        current_value="GAV Profile: None", recommended_value="Apply appropriate GAV profile",
                        reference="SonicWall Security Services Best Practices",
                        remediation=f"Apply a GAV profile to zone {zone_name}."
                    ))
                if dpi_ssl_client == '0':
                    self.result.add_finding(Finding(
                        category=category, title=f"DPI-SSL Client Not Enabled on {zone_name}", severity=Severity.MEDIUM,
                        description=f"DPI-SSL Client inspection is not enabled on zone {zone_name}.",
                        current_value="DPI-SSL Client: Disabled", recommended_value="Enable DPI-SSL Client",
                        reference="SonicWall DPI-SSL Best Practices",
                        remediation=f"Enable DPI-SSL Client inspection on zone {zone_name}."
                    ))
            guest_enabled = zone.get(f'zoneObjEnableGuestServices_{i}', '0')
            if guest_enabled == '1':
                inter_guest = zone.get(f'zoneObjInterGuestComm_{i}', '0')
                bypass_av = zone.get(f'zoneObjBypassAv_{i}', '0')
                if inter_guest == '1':
                    self.result.add_finding(Finding(
                        category=category, title=f"Inter-Guest Communication on {zone_name}", severity=Severity.MEDIUM,
                        description=f"Guest users can communicate with each other on zone {zone_name}.",
                        current_value="Inter-Guest: Enabled", recommended_value="Disable for isolation",
                        reference="Guest Network Security Best Practices",
                        remediation=f"Disable inter-guest communication on zone {zone_name}."
                    ))
                if bypass_av == '1':
                    self.result.add_finding(Finding(
                        category=category, title=f"AV Bypass for Guests on {zone_name}", severity=Severity.HIGH,
                        description=f"Guest traffic bypasses anti-virus scanning on zone {zone_name}.",
                        current_value="Guest AV Bypass: Enabled", recommended_value="Disable AV bypass",
                        reference="Network Security Best Practices",
                        remediation=f"Disable AV bypass for guest services on zone {zone_name}."
                    ))

    def _audit_access_rules(self):
        category = "Access Rules"
        policies = self.parser.get_indexed_items('policy')
        any_any_rules = []
        unlogged_rules = []
        disabled_rules = []
        for i, policy in enumerate(policies):
            policy_name = policy.get(f'policyName_{i}', f'Rule {i}')
            src_net = policy.get(f'policySrcNet_{i}', '')
            dst_net = policy.get(f'policyDstNet_{i}', '')
            dst_svc = policy.get(f'policyDstSvc_{i}', '')
            action = policy.get(f'policyAction_{i}', '0')
            enabled = policy.get(f'policyEnabled_{i}', '1')
            logging = policy.get(f'policyLog_{i}', '0')
            bypass_dpi = policy.get(f'policyBypassDpi_{i}', '0')
            is_allow = action == '2'
            is_any_src = not src_net or src_net.lower() == 'any'
            is_any_dst = not dst_net or dst_net.lower() == 'any'
            is_any_svc = not dst_svc or dst_svc.lower() == 'any'
            if is_allow and is_any_src and is_any_dst and is_any_svc:
                any_any_rules.append(policy_name)
            if enabled == '1' and logging == '0':
                unlogged_rules.append(policy_name)
            if enabled == '0':
                disabled_rules.append(policy_name)
            if bypass_dpi == '1' and is_allow:
                self.result.add_finding(Finding(
                    category=category, title=f"DPI Bypass on Rule: {policy_name}", severity=Severity.MEDIUM,
                    description=f"Deep Packet Inspection is bypassed on rule '{policy_name}'.",
                    current_value="DPI Bypass: Enabled", recommended_value="Disable DPI bypass unless required",
                    reference="SonicWall Security Best Practices",
                    remediation=f"Review and disable DPI bypass on rule '{policy_name}'."
                ))
        if any_any_rules:
            self.result.add_finding(Finding(
                category=category, title="Overly Permissive Access Rules Found", severity=Severity.HIGH,
                description=f"Found {len(any_any_rules)} rule(s) with 'any' source, destination, and service.",
                current_value=f"Rules: {', '.join(any_any_rules[:5])}{'...' if len(any_any_rules) > 5 else ''}",
                recommended_value="Restrict rules to specific sources/destinations/services",
                reference="CIS Controls - Implement Network Segmentation",
                remediation="Review and restrict overly permissive access rules."
            ))
        if len(unlogged_rules) > 5:
            self.result.add_finding(Finding(
                category=category, title="Multiple Access Rules Without Logging", severity=Severity.MEDIUM,
                description=f"Found {len(unlogged_rules)} active rule(s) without logging enabled.",
                current_value=f"{len(unlogged_rules)} rules without logging",
                recommended_value="Enable logging on all access rules",
                reference="NIST 800-53 AU-2 - Audit Events",
                remediation="Enable logging on access rules for security monitoring."
            ))
        if len(disabled_rules) > 10:
            self.result.add_finding(Finding(
                category=category, title="Multiple Disabled Access Rules", severity=Severity.INFO,
                description=f"Found {len(disabled_rules)} disabled rule(s). Consider removing unused rules.",
                current_value=f"{len(disabled_rules)} disabled rules", recommended_value="Remove unused rules",
                reference="Configuration Management Best Practices",
                remediation="Review and remove disabled rules that are no longer needed."
            ))

    def _audit_nat_policies(self):
        category = "NAT Policies"
        nat_policies = self.parser.get_all_matching(r'^natPol')
        if nat_policies:
            self.result.add_finding(Finding(
                category=category, title="NAT Policies Review Recommended", severity=Severity.INFO,
                description="NAT policies are configured. Review to ensure only necessary services are exposed.",
                current_value=f"{len(nat_policies)} NAT-related settings found",
                recommended_value="Review all inbound NAT policies",
                reference="Network Security Best Practices",
                remediation="Audit NAT policies to minimize attack surface."
            ))

    def _audit_security_services(self):
        category = "Security Services"
        gav_settings = self.parser.get_all_matching(r'^gav')
        if not gav_settings:
            self.result.add_finding(Finding(
                category=category, title="Gateway Anti-Virus Not Detected", severity=Severity.HIGH,
                description="Gateway Anti-Virus configuration not found.",
                current_value="GAV: Not configured or not licensed",
                recommended_value="Enable and configure Gateway Anti-Virus",
                reference="SonicWall Security Services Guide",
                remediation="Ensure GAV license is active and service is enabled."
            ))
        aspy_settings = self.parser.get_all_matching(r'^aspy')
        if not aspy_settings:
            self.result.add_finding(Finding(
                category=category, title="Anti-Spyware Not Detected", severity=Severity.HIGH,
                description="Anti-Spyware configuration not found.",
                current_value="Anti-Spyware: Not configured or not licensed",
                recommended_value="Enable and configure Anti-Spyware",
                reference="SonicWall Security Services Guide",
                remediation="Ensure Anti-Spyware license is active and service is enabled."
            ))
        ssl_spy_enabled = self.parser.get('sslSpyEnabled', 'off')
        ssl_spy_server = self.parser.get('sslSpyServerEnabled', 'off')
        if ssl_spy_enabled == 'off':
            self.result.add_finding(Finding(
                category=category, title="DPI-SSL Client Inspection Disabled", severity=Severity.HIGH,
                description="DPI-SSL Client inspection is disabled. Encrypted traffic will not be inspected.",
                current_value="DPI-SSL Client: Disabled",
                recommended_value="Enable DPI-SSL for encrypted traffic inspection",
                reference="SonicWall DPI-SSL Deployment Guide",
                remediation="Enable DPI-SSL Client inspection under Firewall Settings > DPI-SSL."
            ))
        if ssl_spy_server == 'off':
            self.result.add_finding(Finding(
                category=category, title="DPI-SSL Server Inspection Disabled", severity=Severity.MEDIUM,
                description="DPI-SSL Server inspection is disabled.",
                current_value="DPI-SSL Server: Disabled",
                recommended_value="Enable DPI-SSL Server for inbound inspection",
                reference="SonicWall DPI-SSL Deployment Guide",
                remediation="Enable DPI-SSL Server inspection if hosting internal services."
            ))
        cfs_https = self.parser.get('cfsProfileEnableHttpsFlting_0', 'off')
        if cfs_https == 'off':
            self.result.add_finding(Finding(
                category=category, title="CFS HTTPS Filtering Disabled", severity=Severity.MEDIUM,
                description="Content Filtering Service HTTPS inspection is disabled.",
                current_value="CFS HTTPS Filtering: Disabled",
                recommended_value="Enable HTTPS filtering",
                reference="SonicWall Content Filtering Guide",
                remediation="Enable HTTPS filtering in CFS profile settings."
            ))

    def _audit_vpn_configuration(self):
        category = "VPN Configuration"
        vpn_policies = self.parser.get_indexed_items('ipsec')
        for i, vpn in enumerate(vpn_policies):
            vpn_name = vpn.get(f'ipsecName_{i}', f'VPN {i}')
            ph1_crypt = vpn.get(f'ipsecPh1CryptAlg_{i}', '0')
            ph2_crypt = vpn.get(f'ipsecPh2CryptAlg_{i}', '0')
            ph1_dh = vpn.get(f'ipsecP1DHGrp_{i}', '0')
            if ph1_crypt in ['1', '2']:
                self.result.add_finding(Finding(
                    category=category, title=f"Weak Phase 1 Encryption: {vpn_name}", severity=Severity.HIGH,
                    description=f"VPN '{vpn_name}' uses weak Phase 1 encryption (DES/3DES).",
                    current_value=f"Encryption: {'DES' if ph1_crypt == '1' else '3DES'}",
                    recommended_value="Use AES-256",
                    reference="NIST Cryptographic Standards",
                    remediation=f"Update VPN '{vpn_name}' to use AES-256 encryption."
                ))
            if ph2_crypt in ['1', '2']:
                self.result.add_finding(Finding(
                    category=category, title=f"Weak Phase 2 Encryption: {vpn_name}", severity=Severity.HIGH,
                    description=f"VPN '{vpn_name}' uses weak Phase 2 encryption (DES/3DES).",
                    current_value=f"Encryption: {'DES' if ph2_crypt == '1' else '3DES'}",
                    recommended_value="Use AES-256",
                    reference="NIST Cryptographic Standards",
                    remediation=f"Update VPN '{vpn_name}' to use AES-256 encryption."
                ))
            if ph1_dh in ['0', '1']:
                self.result.add_finding(Finding(
                    category=category, title=f"Weak DH Group: {vpn_name}", severity=Severity.HIGH,
                    description=f"VPN '{vpn_name}' uses weak Diffie-Hellman group.",
                    current_value=f"DH Group: {ph1_dh}",
                    recommended_value="Use DH Group 14 (2048-bit) or higher",
                    reference="NIST SP 800-57",
                    remediation=f"Update VPN '{vpn_name}' to use DH Group 14 or higher."
                ))

    def _audit_dos_protection(self):
        category = "DoS Protection"
        dos_profiles = self.parser.get_indexed_items('dosAct')
        for i, dos in enumerate(dos_profiles):
            profile_name = dos.get(f'dosActObjName_{i}', f'DoS Profile {i}')
            syn_flood = dos.get(f'dosSynFld_{i}', '0')
            udp_flood = dos.get(f'dosUdpFldEnable_{i}', '0')
            icmp_flood = dos.get(f'dosIcmpFldEnable_{i}', '0')
            if syn_flood == '0':
                self.result.add_finding(Finding(
                    category=category, title=f"SYN Flood Protection Disabled: {profile_name}", severity=Severity.HIGH,
                    description=f"SYN Flood protection is disabled in profile '{profile_name}'.",
                    current_value="SYN Flood Protection: Disabled",
                    recommended_value="Enable SYN Flood protection",
                    reference="DoS Mitigation Best Practices",
                    remediation=f"Enable SYN Flood protection in profile '{profile_name}'."
                ))
            if udp_flood == '0':
                self.result.add_finding(Finding(
                    category=category, title=f"UDP Flood Protection Disabled: {profile_name}", severity=Severity.MEDIUM,
                    description=f"UDP Flood protection is disabled in profile '{profile_name}'.",
                    current_value="UDP Flood Protection: Disabled",
                    recommended_value="Enable UDP Flood protection",
                    reference="DoS Mitigation Best Practices",
                    remediation=f"Enable UDP Flood protection in profile '{profile_name}'."
                ))
            if icmp_flood == '0':
                self.result.add_finding(Finding(
                    category=category, title=f"ICMP Flood Protection Disabled: {profile_name}", severity=Severity.MEDIUM,
                    description=f"ICMP Flood protection is disabled in profile '{profile_name}'.",
                    current_value="ICMP Flood Protection: Disabled",
                    recommended_value="Enable ICMP Flood protection",
                    reference="DoS Mitigation Best Practices",
                    remediation=f"Enable ICMP Flood protection in profile '{profile_name}'."
                ))
            spank = dos.get(f'dosSpankProtect_{i}', '0')
            smurf = dos.get(f'dosSmurfProtect_{i}', '0')
            land = dos.get(f'dosLandAttackProtect_{i}', '0')
            if spank == '0' or smurf == '0' or land == '0':
                self.result.add_finding(Finding(
                    category=category, title=f"Classic DoS Protection Disabled: {profile_name}", severity=Severity.MEDIUM,
                    description=f"Some classic DoS protections are disabled in '{profile_name}'.",
                    current_value=f"Spank: {spank}, Smurf: {smurf}, Land: {land}",
                    recommended_value="Enable all DoS attack protections",
                    reference="Network Security Best Practices",
                    remediation=f"Enable all DoS protections in profile '{profile_name}'."
                ))

    def _audit_logging(self):
        category = "Logging & Monitoring"
        syslog_server = self.parser.get('syslogServerName', '')
        # Check if syslog is not configured (empty, 0.0.0.0, or just whitespace)
        if not syslog_server or syslog_server.strip() == '' or syslog_server == '0.0.0.0':
            self.result.add_finding(Finding(
                category=category, title="Syslog Server Not Configured", severity=Severity.HIGH,
                description="No syslog server is configured.",
                current_value="Syslog: Not configured",
                recommended_value="Configure syslog to send to SIEM/log collector",
                reference="NIST 800-53 AU-4 - Audit Storage Capacity",
                remediation="Configure syslog server under Device > Log > Syslog."
            ))
        else:
            # Syslog is configured - this is good, add as INFO
            self.result.add_finding(Finding(
                category=category, title="Syslog Server Configured", severity=Severity.INFO,
                description=f"Syslog server is configured to send logs to external server.",
                current_value=f"Syslog: {syslog_server}",
                recommended_value="Verify logs are being received",
                reference="NIST 800-53 AU-4 - Audit Storage Capacity",
                remediation="Verify syslog server is receiving logs and retention is adequate."
            ))
        analyzer_mode = self.parser.get('syslogAnalyzerMode', 'off')
        viewpoint_mode = self.parser.get('syslogViewPointMode', 'off')
        if analyzer_mode == 'off' and viewpoint_mode == 'off':
            self.result.add_finding(Finding(
                category=category, title="Analytics Integration Not Configured", severity=Severity.MEDIUM,
                description="SonicWall Analytics/NSM integration is not configured.",
                current_value="Analytics: Not configured",
                recommended_value="Configure NSM or Analytics integration",
                reference="SonicWall Network Security Manager Guide",
                remediation="Consider enabling NSM or Analytics for centralized management."
            ))
        ntp_enabled = self.parser.get('ntp_useNtp', 'off')
        if ntp_enabled.lower() != 'on':
            self.result.add_finding(Finding(
                category=category, title="NTP Not Enabled", severity=Severity.MEDIUM,
                description="NTP is not enabled. Accurate time is critical for log correlation.",
                current_value="NTP: Disabled",
                recommended_value="Enable NTP synchronization",
                reference="NIST 800-53 AU-8 - Time Stamps",
                remediation="Enable NTP under Device > Settings > Time."
            ))

    def _audit_system_settings(self):
        category = "System Settings"
        factory_default = self.parser.get('factoryDefault', 'off')
        if factory_default == 'on':
            self.result.add_finding(Finding(
                category=category, title="Factory Default Configuration Detected", severity=Severity.CRITICAL,
                description="The firewall appears to be running factory default configuration.",
                current_value="Factory Default: Yes",
                recommended_value="Configure firewall according to security requirements",
                reference="Initial Deployment Best Practices",
                remediation="Complete firewall configuration according to your security policy."
            ))
        geo_enabled = self.parser.get('geoEnforcement', '0')
        # '1' means enabled, '0' means disabled
        if geo_enabled != '1':
            self.result.add_finding(Finding(
                category=category, title="Geo-IP Enforcement Disabled", severity=Severity.MEDIUM,
                description="Geo-IP enforcement is disabled globally.",
                current_value="Geo-IP: Disabled",
                recommended_value="Enable Geo-IP filtering",
                reference="Threat Intelligence Best Practices",
                remediation="Enable Geo-IP enforcement under Security Services > Geo-IP."
            ))
        botnet_enabled = self.parser.get('botnetBlock', '0')
        # '1' means enabled, '0' means disabled
        if botnet_enabled != '1':
            self.result.add_finding(Finding(
                category=category, title="Botnet Filtering Disabled", severity=Severity.HIGH,
                description="Botnet filtering is disabled.",
                current_value="Botnet Filtering: Disabled",
                recommended_value="Enable Botnet filtering",
                reference="Threat Intelligence Best Practices",
                remediation="Enable Botnet filtering under Security Services > Botnet Filter."
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
                        category=category, title="Weak TLS Ciphers Enabled", severity=Severity.HIGH,
                        description=f"Found {len(enabled_weak)} weak or obsolete cipher suites enabled.",
                        current_value=f"Weak ciphers enabled: {len(enabled_weak)}",
                        recommended_value="Disable weak ciphers (NULL, EXPORT, RC4, DES)",
                        reference="NIST TLS Implementation Guidelines",
                        remediation="Review and disable weak cipher suites in TLS settings."
                    ))
            except json.JSONDecodeError:
                pass


class ReportGenerator:
    def __init__(self, result: AuditResult):
        self.result = result

    def generate_terminal_report(self, use_colors: bool = True) -> str:
        reset = '\033[0m' if use_colors else ''
        bold = '\033[1m' if use_colors else ''
        lines = []
        lines.append(f"\n{bold}{'=' * 70}{reset}")
        lines.append(f"{bold}SonicWall Configuration Audit Report{reset}")
        lines.append(f"{'=' * 70}")
        lines.append(f"\n{bold}Firewall Information:{reset}")
        for key, value in self.result.firewall_info.items():
            lines.append(f"  {key}: {value}")
        lines.append(f"\n{bold}Audit Time:{reset} {self.result.audit_time}")
        lines.append(f"\n{bold}Summary:{reset}")
        total = sum(self.result.summary.values())
        lines.append(f"  Total Findings: {total}")
        for severity in Severity:
            count = self.result.summary.get(str(severity), 0)
            if count > 0:
                color = severity.color if use_colors else ''
                lines.append(f"  {color}{severity.name}: {count}{reset}")
        lines.append(f"\n{bold}{'=' * 70}{reset}")
        lines.append(f"{bold}Detailed Findings{reset}")
        lines.append(f"{'=' * 70}")
        categories = {}
        for finding in self.result.findings:
            if finding.category not in categories:
                categories[finding.category] = []
            categories[finding.category].append(finding)
        for category, findings in categories.items():
            lines.append(f"\n{bold}[{category}]{reset}")
            lines.append("-" * 50)
            for finding in sorted(findings, key=lambda x: x.severity.value):
                color = finding.severity.color if use_colors else ''
                lines.append(f"\n  {color}[{finding.severity.name}]{reset} {bold}{finding.title}{reset}")
                lines.append(f"    Description: {finding.description}")
                lines.append(f"    Current: {finding.current_value}")
                lines.append(f"    Recommended: {finding.recommended_value}")
                lines.append(f"    Reference: {finding.reference}")
                if finding.remediation:
                    lines.append(f"    Remediation: {finding.remediation}")
        lines.append(f"\n{'=' * 70}")
        lines.append("End of Report")
        lines.append(f"{'=' * 70}\n")
        return '\n'.join(lines)

    def print_terminal_report(self):
        print(self.generate_terminal_report(use_colors=True))

    def generate_html_report(self, output_path: str):
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SonicWall Configuration Audit Report</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px; border-radius: 10px; margin-bottom: 30px; }}
        .header h1 {{ font-size: 2.5rem; margin-bottom: 10px; }}
        .header p {{ opacity: 0.9; }}
        .info-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .info-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .info-card h3 {{ color: #667eea; margin-bottom: 5px; font-size: 0.9rem; text-transform: uppercase; }}
        .info-card p {{ font-size: 1.2rem; font-weight: 600; }}
        .summary {{ background: white; padding: 30px; border-radius: 8px; margin-bottom: 30px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .summary h2 {{ margin-bottom: 20px; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; }}
        .severity-card {{ padding: 20px; border-radius: 8px; text-align: center; color: white; }}
        .severity-card.critical {{ background: #dc3545; }}
        .severity-card.high {{ background: #fd7e14; }}
        .severity-card.medium {{ background: #ffc107; color: #333; }}
        .severity-card.low {{ background: #17a2b8; }}
        .severity-card.info {{ background: #28a745; }}
        .severity-card .count {{ font-size: 2rem; font-weight: 700; }}
        .severity-card .label {{ font-size: 0.9rem; text-transform: uppercase; }}
        .findings {{ background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .category {{ margin-bottom: 30px; }}
        .category h2 {{ color: #667eea; border-bottom: 2px solid #667eea; padding-bottom: 10px; margin-bottom: 20px; }}
        .finding {{ border-left: 4px solid; padding: 20px; margin-bottom: 15px; background: #fafafa; border-radius: 0 8px 8px 0; }}
        .finding.critical {{ border-color: #dc3545; }}
        .finding.high {{ border-color: #fd7e14; }}
        .finding.medium {{ border-color: #ffc107; }}
        .finding.low {{ border-color: #17a2b8; }}
        .finding.info {{ border-color: #28a745; }}
        .finding-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
        .finding-title {{ font-weight: 600; font-size: 1.1rem; }}
        .finding-severity {{ padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; color: white; }}
        .finding-severity.critical {{ background: #dc3545; }}
        .finding-severity.high {{ background: #fd7e14; }}
        .finding-severity.medium {{ background: #ffc107; color: #333; }}
        .finding-severity.low {{ background: #17a2b8; }}
        .finding-severity.info {{ background: #28a745; }}
        .finding-detail {{ margin: 10px 0; }}
        .finding-detail strong {{ color: #555; }}
        .finding-remediation {{ background: #e8f5e9; padding: 15px; border-radius: 5px; margin-top: 10px; }}
        .finding-remediation strong {{ color: #2e7d32; }}
        .footer {{ text-align: center; padding: 20px; color: #666; font-size: 0.9rem; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>SonicWall Configuration Audit Report</h1>
            <p>Generated: {self.result.audit_time}</p>
        </div>
        <div class="info-grid">
            {''.join(f'<div class="info-card"><h3>{k.replace("_", " ").title()}</h3><p>{v}</p></div>' for k, v in self.result.firewall_info.items())}
        </div>
        <div class="summary">
            <h2>Executive Summary</h2>
            <div class="summary-grid">
                {''.join(f'<div class="severity-card {sev.name.lower()}"><div class="count">{self.result.summary.get(str(sev), 0)}</div><div class="label">{sev.name}</div></div>' for sev in Severity)}
            </div>
        </div>
        <div class="findings">
            <h2>Detailed Findings</h2>
"""
        categories = {}
        for finding in self.result.findings:
            if finding.category not in categories:
                categories[finding.category] = []
            categories[finding.category].append(finding)
        for category, findings in categories.items():
            html += f'<div class="category"><h2>{category}</h2>'
            for finding in sorted(findings, key=lambda x: x.severity.value):
                sev_class = finding.severity.name.lower()
                html += f'''<div class="finding {sev_class}">
                    <div class="finding-header">
                        <span class="finding-title">{finding.title}</span>
                        <span class="finding-severity {sev_class}">{finding.severity.name}</span>
                    </div>
                    <div class="finding-detail"><strong>Description:</strong> {finding.description}</div>
                    <div class="finding-detail"><strong>Current Value:</strong> {finding.current_value}</div>
                    <div class="finding-detail"><strong>Recommended:</strong> {finding.recommended_value}</div>
                    <div class="finding-detail"><strong>Reference:</strong> {finding.reference}</div>
                    {f'<div class="finding-remediation"><strong>Remediation:</strong> {finding.remediation}</div>' if finding.remediation else ''}
                </div>'''
            html += '</div>'
        html += """
        </div>
        <div class="footer">
            <p>SonicWall Configuration Auditor | Based on industry best practices and security guidelines</p>
        </div>
    </div>
</body>
</html>
"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"HTML report saved to: {output_path}")

    def generate_pdf_report(self, output_path: str):
        if not REPORTLAB_AVAILABLE:
            print("Error: 'reportlab' library required for PDF generation.")
            return
        doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24, spaceAfter=30, alignment=TA_CENTER, textColor=colors.HexColor('#667eea'))
        heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=16, spaceBefore=20, spaceAfter=10, textColor=colors.HexColor('#667eea'))
        normal_style = ParagraphStyle('CustomNormal', parent=styles['Normal'], fontSize=10, spaceAfter=6)
        story = []
        story.append(Paragraph("SonicWall Configuration Audit Report", title_style))
        story.append(Paragraph(f"Generated: {self.result.audit_time}", styles['Normal']))
        story.append(Spacer(1, 30))
        story.append(Paragraph("Firewall Information", heading_style))
        info_data = [[k.replace('_', ' ').title(), v] for k, v in self.result.firewall_info.items()]
        info_table = Table(info_data, colWidths=[150, 300])
        info_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')), ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('GRID', (0, 0), (-1, -1), 0.5, colors.grey), ('PADDING', (0, 0), (-1, -1), 8)]))
        story.append(info_table)
        story.append(Spacer(1, 20))
        story.append(Paragraph("Executive Summary", heading_style))
        summary_data = [['Severity', 'Count']]
        for sev in Severity:
            summary_data.append([sev.name, str(self.result.summary.get(str(sev), 0))])
        summary_table = Table(summary_data, colWidths=[150, 100])
        summary_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('GRID', (0, 0), (-1, -1), 0.5, colors.grey), ('PADDING', (0, 0), (-1, -1), 8), ('ALIGN', (1, 0), (1, -1), 'CENTER')]))
        story.append(summary_table)
        story.append(PageBreak())
        story.append(Paragraph("Detailed Findings", heading_style))
        categories = {}
        for finding in self.result.findings:
            if finding.category not in categories:
                categories[finding.category] = []
            categories[finding.category].append(finding)
        for category, findings in categories.items():
            story.append(Paragraph(category, heading_style))
            for finding in sorted(findings, key=lambda x: x.severity.value):
                story.append(Paragraph(f"<font color='{finding.severity.html_color}'>[{finding.severity.name}]</font> <b>{finding.title}</b>", normal_style))
                story.append(Paragraph(f"<b>Description:</b> {finding.description}", normal_style))
                story.append(Paragraph(f"<b>Current Value:</b> {finding.current_value}", normal_style))
                story.append(Paragraph(f"<b>Recommended:</b> {finding.recommended_value}", normal_style))
                story.append(Paragraph(f"<b>Reference:</b> {finding.reference}", normal_style))
                if finding.remediation:
                    story.append(Paragraph(f"<b>Remediation:</b> {finding.remediation}", normal_style))
                story.append(Spacer(1, 15))
        doc.build(story)
        print(f"PDF report saved to: {output_path}")

    def generate_json_report(self, output_path: str):
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.result.to_dict(), f, indent=2)
        print(f"JSON report saved to: {output_path}")


class AuditorGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SonicWall Configuration Auditor v1.1")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)
        self.config_file_path = tk.StringVar()
        self.api_host = tk.StringVar()
        self.api_port = tk.StringVar(value="443")
        self.api_username = tk.StringVar(value="admin")
        self.api_password = tk.StringVar()
        self.verify_ssl = tk.BooleanVar(value=False)
        self.output_html = tk.BooleanVar(value=True)
        self.output_pdf = tk.BooleanVar(value=True)
        self.output_json = tk.BooleanVar(value=False)
        self.output_dir = tk.StringVar(value=os.path.expanduser("~"))
        self.parser = None
        self.result = None
        self._setup_ui()

    def _setup_ui(self):
        style = ttk.Style()
        style.configure('Title.TLabel', font=('Helvetica', 16, 'bold'))
        style.configure('Section.TLabelframe.Label', font=('Helvetica', 10, 'bold'))
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        title_label = ttk.Label(main_frame, text="SonicWall Configuration Auditor", style='Title.TLabel')
        title_label.pack(pady=(0, 15))
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        file_frame = ttk.Frame(notebook, padding="10")
        notebook.add(file_frame, text="Load from File")
        self._setup_file_tab(file_frame)
        api_frame = ttk.Frame(notebook, padding="10")
        notebook.add(api_frame, text="Load from API")
        self._setup_api_tab(api_frame)
        output_frame = ttk.LabelFrame(main_frame, text="Output Options", padding="10", style='Section.TLabelframe')
        output_frame.pack(fill=tk.X, pady=(10, 0))
        self._setup_output_options(output_frame)
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(button_frame, text="Run Audit", command=self._run_audit, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear", command=self._clear_output, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Exit", command=self.root.quit, width=15).pack(side=tk.RIGHT, padx=5)
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=(10, 0))
        output_label = ttk.Label(main_frame, text="Audit Results:")
        output_label.pack(anchor=tk.W, pady=(10, 5))
        self.output_text = scrolledtext.ScrolledText(main_frame, height=15, width=80, font=('Consolas', 9))
        self.output_text.pack(fill=tk.BOTH, expand=True)
        self.output_text.tag_configure('critical', foreground='#dc3545', font=('Consolas', 9, 'bold'))
        self.output_text.tag_configure('high', foreground='#fd7e14', font=('Consolas', 9, 'bold'))
        self.output_text.tag_configure('medium', foreground='#0d6efd', font=('Consolas', 9, 'bold'))
        self.output_text.tag_configure('low', foreground='#0dcaf0', font=('Consolas', 9, 'bold'))
        self.output_text.tag_configure('info', foreground='#198754', font=('Consolas', 9, 'bold'))
        self.output_text.tag_configure('bold', font=('Consolas', 9, 'bold'))
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(5, 0))

    def _setup_file_tab(self, parent):
        file_frame = ttk.Frame(parent)
        file_frame.pack(fill=tk.X, pady=10)
        ttk.Label(file_frame, text="Configuration File (.exp):").pack(anchor=tk.W)
        entry_frame = ttk.Frame(file_frame)
        entry_frame.pack(fill=tk.X, pady=5)
        ttk.Entry(entry_frame, textvariable=self.config_file_path, width=70).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(entry_frame, text="Browse...", command=self._browse_file).pack(side=tk.LEFT, padx=(5, 0))
        instructions = """
Instructions:
1. Export your SonicWall configuration from the firewall web interface
   (Device > Settings > Firmware & Backups > Export Settings)
2. Save the .exp file to your computer
3. Use the Browse button to select the exported configuration file
4. Configure output options below and click 'Run Audit'
        """
        ttk.Label(parent, text=instructions, justify=tk.LEFT, foreground='gray').pack(anchor=tk.W, pady=10)

    def _setup_api_tab(self, parent):
        api_grid = ttk.Frame(parent)
        api_grid.pack(fill=tk.X, pady=10)
        ttk.Label(api_grid, text="Firewall IP/Hostname:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(api_grid, textvariable=self.api_host, width=40).grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)
        ttk.Label(api_grid, text="Port:").grid(row=0, column=2, sticky=tk.W, pady=5, padx=(10, 0))
        ttk.Entry(api_grid, textvariable=self.api_port, width=10).grid(row=0, column=3, sticky=tk.W, pady=5, padx=5)
        ttk.Label(api_grid, text="Username:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(api_grid, textvariable=self.api_username, width=30).grid(row=1, column=1, sticky=tk.W, pady=5, padx=5)
        ttk.Label(api_grid, text="Password:").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(api_grid, textvariable=self.api_password, show="*", width=30).grid(row=2, column=1, sticky=tk.W, pady=5, padx=5)
        ttk.Checkbutton(api_grid, text="Verify SSL Certificate", variable=self.verify_ssl).grid(row=3, column=1, sticky=tk.W, pady=5)
        if not REQUESTS_AVAILABLE:
            notice = ttk.Label(parent, text="Note: 'requests' library required for API access.\nInstall with: pip install requests", foreground='red')
            notice.pack(anchor=tk.W, pady=10)
        instructions = """
Instructions:
1. Ensure the SonicOS API is enabled on your firewall
   (Device > Settings > Administration > SonicOS API)
2. Enter the firewall IP address or hostname
3. Enter admin credentials with API access
4. The tool will connect via HTTPS to fetch configuration
5. Click 'Run Audit' to start the assessment
        """
        ttk.Label(parent, text=instructions, justify=tk.LEFT, foreground='gray').pack(anchor=tk.W, pady=10)

    def _setup_output_options(self, parent):
        format_frame = ttk.Frame(parent)
        format_frame.pack(fill=tk.X)
        ttk.Label(format_frame, text="Report Formats:").pack(side=tk.LEFT)
        ttk.Checkbutton(format_frame, text="HTML", variable=self.output_html).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(format_frame, text="PDF", variable=self.output_pdf).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(format_frame, text="JSON", variable=self.output_json).pack(side=tk.LEFT, padx=10)
        dir_frame = ttk.Frame(parent)
        dir_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(dir_frame, text="Output Directory:").pack(side=tk.LEFT)
        ttk.Entry(dir_frame, textvariable=self.output_dir, width=50).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(dir_frame, text="Browse...", command=self._browse_output_dir).pack(side=tk.LEFT)

    def _browse_file(self):
        filename = filedialog.askopenfilename(title="Select SonicWall Configuration File", filetypes=[("SonicWall Export", "*.exp"), ("All Files", "*.*")])
        if filename:
            self.config_file_path.set(filename)

    def _browse_output_dir(self):
        directory = filedialog.askdirectory(title="Select Output Directory")
        if directory:
            self.output_dir.set(directory)

    def _clear_output(self):
        self.output_text.delete(1.0, tk.END)
        self.status_var.set("Ready")

    def _log(self, message: str, tag: str = None):
        self.output_text.insert(tk.END, message + "\n", tag)
        self.output_text.see(tk.END)
        self.root.update_idletasks()

    def _run_audit(self):
        config_file = self.config_file_path.get().strip()
        api_host = self.api_host.get().strip()
        if not config_file and not api_host:
            messagebox.showerror("Error", "Please specify a configuration file or API connection details.")
            return
        self.progress.start()
        self.status_var.set("Running audit...")
        self._clear_output()
        thread = threading.Thread(target=self._audit_thread, args=(config_file, api_host))
        thread.daemon = True
        thread.start()

    def _audit_thread(self, config_file: str, api_host: str):
        try:
            self.parser = SonicWallConfigParser()
            if config_file:
                self._log(f"Loading configuration from: {config_file}")
                if not self.parser.load_from_file(config_file):
                    self._log("ERROR: Failed to load configuration file", "critical")
                    self._finish_audit()
                    return
            else:
                if not REQUESTS_AVAILABLE:
                    self._log("ERROR: 'requests' library required for API access", "critical")
                    self._finish_audit()
                    return
                self._log(f"Connecting to firewall: {api_host}")
                password = self.api_password.get()
                port = int(self.api_port.get())
                verify_ssl = self.verify_ssl.get()
                if not self.parser.load_from_api(api_host, self.api_username.get(), password, port, verify_ssl):
                    self._log("ERROR: Failed to connect to firewall API", "critical")
                    self._finish_audit()
                    return
            self._log(f"Loaded {len(self.parser.config)} configuration parameters")
            self._log("Running security audit...\n")
            auditor = SonicWallAuditor(self.parser)
            self.result = auditor.run_audit()
            self._display_results()
            self._generate_reports()
            self._log("\nAudit complete!")
            self.status_var.set("Audit complete")
        except Exception as e:
            self._log(f"ERROR: {str(e)}", "critical")
            import traceback
            self._log(traceback.format_exc())
        finally:
            self._finish_audit()

    def _display_results(self):
        result = self.result
        self._log("=" * 70, "bold")
        self._log("SonicWall Configuration Audit Report", "bold")
        self._log("=" * 70, "bold")
        self._log("\nFirewall Information:", "bold")
        for key, value in result.firewall_info.items():
            self._log(f"  {key}: {value}")
        self._log(f"\nAudit Time: {result.audit_time}")
        self._log("\nSummary:", "bold")
        total = sum(result.summary.values())
        self._log(f"  Total Findings: {total}")
        for severity in Severity:
            count = result.summary.get(str(severity), 0)
            if count > 0:
                self._log(f"  {severity.name}: {count}", severity.name.lower())
        self._log("\n" + "=" * 70, "bold")
        self._log("Detailed Findings", "bold")
        self._log("=" * 70, "bold")
        categories = {}
        for finding in result.findings:
            if finding.category not in categories:
                categories[finding.category] = []
            categories[finding.category].append(finding)
        for category, findings in categories.items():
            self._log(f"\n[{category}]", "bold")
            self._log("-" * 50)
            for finding in sorted(findings, key=lambda x: x.severity.value):
                self._log(f"\n  [{finding.severity.name}] {finding.title}", finding.severity.name.lower())
                self._log(f"    Description: {finding.description}")
                self._log(f"    Current: {finding.current_value}")
                self._log(f"    Recommended: {finding.recommended_value}")
                self._log(f"    Reference: {finding.reference}")
                if finding.remediation:
                    self._log(f"    Remediation: {finding.remediation}")
        self._log("\n" + "=" * 70, "bold")
        self._log("End of Report", "bold")
        self._log("=" * 70, "bold")

    def _generate_reports(self):
        if not self.result:
            return
        reporter = ReportGenerator(self.result)
        output_dir = self.output_dir.get()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"sonicwall_audit_{timestamp}"
        if self.output_html.get():
            html_path = os.path.join(output_dir, f"{base_name}.html")
            reporter.generate_html_report(html_path)
            self._log(f"\nHTML report saved: {html_path}")
        if self.output_pdf.get():
            if REPORTLAB_AVAILABLE:
                pdf_path = os.path.join(output_dir, f"{base_name}.pdf")
                reporter.generate_pdf_report(pdf_path)
                self._log(f"PDF report saved: {pdf_path}")
            else:
                self._log("WARNING: PDF generation skipped (reportlab not installed)", "medium")
        if self.output_json.get():
            json_path = os.path.join(output_dir, f"{base_name}.json")
            reporter.generate_json_report(json_path)
            self._log(f"JSON report saved: {json_path}")

    def _finish_audit(self):
        self.progress.stop()
        self.root.update_idletasks()

    def run(self):
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser(description='SonicWall Configuration Auditor', formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Launch GUI (default)
  %(prog)s

  # Audit from config file (CLI mode)
  %(prog)s -f sonicwall_config.exp

  # Audit from API with HTML report
  %(prog)s -a 192.168.1.1 -u admin --html report.html

  # Generate all report formats
  %(prog)s -f config.exp --html report.html --pdf report.pdf --json report.json
        """)
    parser.add_argument('--gui', action='store_true', help='Launch GUI (default if no other args)')
    input_group = parser.add_argument_group('Input Options')
    input_group.add_argument('-f', '--file', help='Path to SonicWall .exp config file')
    input_group.add_argument('-a', '--api', help='Firewall IP/hostname for API access')
    input_group.add_argument('-u', '--username', help='API username (default: admin)', default='admin')
    input_group.add_argument('-p', '--password', help='API password (will prompt if not provided)')
    input_group.add_argument('--port', type=int, default=443, help='API port (default: 443)')
    input_group.add_argument('--verify-ssl', action='store_true', help='Verify SSL certificate')
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument('--html', help='Generate HTML report to specified path')
    output_group.add_argument('--pdf', help='Generate PDF report to specified path')
    output_group.add_argument('--json', help='Generate JSON report to specified path')
    output_group.add_argument('-q', '--quiet', action='store_true', help='Suppress terminal output')
    args = parser.parse_args()
    if not args.file and not args.api:
        if TK_AVAILABLE:
            gui = AuditorGUI()
            gui.run()
            return
        else:
            parser.error("GUI not available. Use --file or --api options.")
    config_parser = SonicWallConfigParser()
    if args.file:
        print(f"Loading configuration from: {args.file}")
        if not config_parser.load_from_file(args.file):
            sys.exit(1)
    else:
        if not REQUESTS_AVAILABLE:
            print("Error: 'requests' library required for API access")
            sys.exit(1)
        password = args.password or getpass.getpass(f"Password for {args.username}@{args.api}: ")
        print(f"Connecting to firewall at: {args.api}")
        if not config_parser.load_from_api(args.api, args.username, password, args.port, args.verify_ssl):
            sys.exit(1)
    print(f"Loaded {len(config_parser.config)} configuration parameters")
    print("Running security audit...")
    auditor = SonicWallAuditor(config_parser)
    result = auditor.run_audit()
    reporter = ReportGenerator(result)
    if not args.quiet:
        reporter.print_terminal_report()
    if args.html:
        reporter.generate_html_report(args.html)
    if args.pdf:
        reporter.generate_pdf_report(args.pdf)
    if args.json:
        reporter.generate_json_report(args.json)
    if result.summary.get('CRITICAL', 0) > 0:
        sys.exit(2)
    elif result.summary.get('HIGH', 0) > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()

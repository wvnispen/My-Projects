#!/usr/bin/env python3
"""
Application Classification Module

Maps SonicWall application IDs and categories to human-readable names
and productivity classifications.
"""

import logging
from typing import Dict, Optional, Any

logger = logging.getLogger('swfr.apps')


# SonicWall Application Categories
# These are the standard SonicWall app category IDs
APP_CATEGORIES = {
    0: {'name': 'Unknown', 'group': 'Unknown'},
    1: {'name': 'Business', 'group': 'Productivity'},
    2: {'name': 'Communication', 'group': 'Productivity'},
    3: {'name': 'Collaboration', 'group': 'Productivity'},
    4: {'name': 'Storage & Backup', 'group': 'Productivity'},
    5: {'name': 'Media', 'group': 'Entertainment'},
    6: {'name': 'General Internet', 'group': 'General'},
    7: {'name': 'Social Networking', 'group': 'Entertainment'},
    8: {'name': 'Gaming', 'group': 'Entertainment'},
    9: {'name': 'Proxy', 'group': 'Security Risk'},
    10: {'name': 'Remote Access', 'group': 'Productivity'},
    11: {'name': 'VoIP', 'group': 'Communication'},
    12: {'name': 'Email', 'group': 'Productivity'},
    13: {'name': 'File Sharing', 'group': 'General'},
    14: {'name': 'Streaming Media', 'group': 'Entertainment'},
    15: {'name': 'Web', 'group': 'General'},
    16: {'name': 'Security', 'group': 'Security'},
    17: {'name': 'Network Infrastructure', 'group': 'Infrastructure'},
    18: {'name': 'Database', 'group': 'Productivity'},
    19: {'name': 'Development', 'group': 'Productivity'},
    20: {'name': 'Management', 'group': 'Infrastructure'},
}

# Productivity classification for groups
PRODUCTIVITY_MAP = {
    'Productivity': 'productive',
    'Communication': 'productive',
    'Infrastructure': 'neutral',
    'Security': 'neutral',
    'General': 'neutral',
    'Entertainment': 'unproductive',
    'Security Risk': 'risky',
    'Unknown': 'unknown',
}

# Common well-known ports and their services
WELL_KNOWN_PORTS = {
    20: {'service': 'FTP Data', 'category': 'File Transfer'},
    21: {'service': 'FTP', 'category': 'File Transfer'},
    22: {'service': 'SSH', 'category': 'Remote Access'},
    23: {'service': 'Telnet', 'category': 'Remote Access', 'risk': 'high'},
    25: {'service': 'SMTP', 'category': 'Email'},
    53: {'service': 'DNS', 'category': 'Infrastructure'},
    67: {'service': 'DHCP', 'category': 'Infrastructure'},
    68: {'service': 'DHCP', 'category': 'Infrastructure'},
    80: {'service': 'HTTP', 'category': 'Web'},
    110: {'service': 'POP3', 'category': 'Email'},
    123: {'service': 'NTP', 'category': 'Infrastructure'},
    143: {'service': 'IMAP', 'category': 'Email'},
    161: {'service': 'SNMP', 'category': 'Management'},
    162: {'service': 'SNMP Trap', 'category': 'Management'},
    389: {'service': 'LDAP', 'category': 'Directory'},
    443: {'service': 'HTTPS', 'category': 'Web'},
    445: {'service': 'SMB', 'category': 'File Sharing'},
    465: {'service': 'SMTPS', 'category': 'Email'},
    514: {'service': 'Syslog', 'category': 'Management'},
    587: {'service': 'SMTP Submission', 'category': 'Email'},
    636: {'service': 'LDAPS', 'category': 'Directory'},
    853: {'service': 'DNS over TLS', 'category': 'Infrastructure'},
    993: {'service': 'IMAPS', 'category': 'Email'},
    995: {'service': 'POP3S', 'category': 'Email'},
    1194: {'service': 'OpenVPN', 'category': 'VPN'},
    1433: {'service': 'MSSQL', 'category': 'Database'},
    1521: {'service': 'Oracle', 'category': 'Database'},
    3306: {'service': 'MySQL', 'category': 'Database'},
    3389: {'service': 'RDP', 'category': 'Remote Access', 'risk': 'medium'},
    5432: {'service': 'PostgreSQL', 'category': 'Database'},
    5900: {'service': 'VNC', 'category': 'Remote Access'},
    5985: {'service': 'WinRM HTTP', 'category': 'Management'},
    5986: {'service': 'WinRM HTTPS', 'category': 'Management'},
    6379: {'service': 'Redis', 'category': 'Database'},
    8080: {'service': 'HTTP Proxy', 'category': 'Web'},
    8443: {'service': 'HTTPS Alt', 'category': 'Web'},
    9200: {'service': 'Elasticsearch', 'category': 'Database'},
    27017: {'service': 'MongoDB', 'category': 'Database'},
}

# Known streaming/social media domains for classification
STREAMING_DOMAINS = [
    'netflix.com', 'youtube.com', 'youtu.be', 'twitch.tv', 'hulu.com',
    'disneyplus.com', 'hbomax.com', 'peacocktv.com', 'paramount.com',
    'amazonvideo.com', 'primevideo.com', 'spotify.com', 'soundcloud.com',
    'pandora.com', 'deezer.com', 'tidal.com', 'apple.com/music',
    'vimeo.com', 'dailymotion.com', 'crunchyroll.com', 'funimation.com',
]

SOCIAL_MEDIA_DOMAINS = [
    'facebook.com', 'fb.com', 'instagram.com', 'twitter.com', 'x.com',
    'tiktok.com', 'snapchat.com', 'linkedin.com', 'pinterest.com',
    'reddit.com', 'tumblr.com', 'whatsapp.com', 'telegram.org',
    'discord.com', 'discordapp.com', 'slack.com',
]

PRODUCTIVITY_DOMAINS = [
    'microsoft.com', 'office.com', 'office365.com', 'sharepoint.com',
    'onedrive.com', 'outlook.com', 'teams.microsoft.com',
    'google.com', 'googleapis.com', 'gmail.com', 'docs.google.com',
    'drive.google.com', 'meet.google.com', 'workspace.google.com',
    'zoom.us', 'zoom.com', 'webex.com', 'gotomeeting.com',
    'salesforce.com', 'servicenow.com', 'workday.com', 'jira.com',
    'atlassian.com', 'confluence.com', 'github.com', 'gitlab.com',
    'bitbucket.org', 'dropbox.com', 'box.com',
]


class ApplicationClassifier:
    """Classifies applications and URLs for productivity analysis"""
    
    def __init__(self):
        self.categories = APP_CATEGORIES
        self.ports = WELL_KNOWN_PORTS
        logger.info("Application classifier initialized")
    
    def get_category_info(self, category_id: int) -> Dict[str, str]:
        """Get category name and group for a category ID"""
        return self.categories.get(category_id, self.categories[0])
    
    def get_port_info(self, port: int) -> Optional[Dict[str, str]]:
        """Get service info for a well-known port"""
        return self.ports.get(port)
    
    def classify_url(self, url: str) -> Dict[str, str]:
        """Classify a URL/hostname for productivity"""
        if not url:
            return {'classification': 'unknown', 'category': 'Unknown'}
        
        url_lower = url.lower()
        
        # Check streaming domains
        for domain in STREAMING_DOMAINS:
            if domain in url_lower:
                return {'classification': 'unproductive', 'category': 'Streaming'}
        
        # Check social media domains
        for domain in SOCIAL_MEDIA_DOMAINS:
            if domain in url_lower:
                return {'classification': 'unproductive', 'category': 'Social Media'}
        
        # Check productivity domains
        for domain in PRODUCTIVITY_DOMAINS:
            if domain in url_lower:
                return {'classification': 'productive', 'category': 'Business'}
        
        return {'classification': 'neutral', 'category': 'General'}
    
    def enrich_flow(self, flow: Dict[str, Any]) -> Dict[str, Any]:
        """Add application classification to a flow record"""
        
        # Classify by app category ID
        app_cat_id = flow.get('app_category_id')
        if app_cat_id is not None:
            cat_info = self.get_category_info(app_cat_id)
            flow['app_category_name'] = cat_info['name']
            flow['app_group'] = cat_info['group']
            flow['app_productivity'] = PRODUCTIVITY_MAP.get(cat_info['group'], 'unknown')
        
        # Classify by destination port
        dst_port = flow.get('dst_port')
        if dst_port:
            port_info = self.get_port_info(dst_port)
            if port_info:
                flow['service_name'] = port_info['service']
                flow['service_category'] = port_info['category']
                if 'risk' in port_info:
                    flow['service_risk'] = port_info['risk']
        
        # Classify by URL if available
        url_host = flow.get('url_host')
        if url_host:
            url_class = self.classify_url(url_host)
            flow['url_classification'] = url_class['classification']
            flow['url_category'] = url_class['category']
        
        return flow


# Risk scoring based on various factors
def calculate_risk_score(flow: Dict[str, Any]) -> int:
    """
    Calculate a risk score (0-100) for a flow based on various factors.
    Higher score = higher risk.
    """
    score = 0
    
    # Risky ports
    dst_port = flow.get('dst_port', 0)
    risky_ports = {23: 30, 3389: 20, 5900: 20, 445: 15, 135: 15, 139: 15}
    if dst_port in risky_ports:
        score += risky_ports[dst_port]
    
    # Unusual ports (very high or non-standard)
    if dst_port > 10000 and dst_port not in [27017, 32400]:
        score += 10
    
    # App category risk
    app_cat_id = flow.get('app_category_id')
    if app_cat_id == 9:  # Proxy
        score += 25
    elif app_cat_id == 13:  # File Sharing
        score += 15
    
    # Large data transfer
    bytes_total = flow.get('bytes_total', 0)
    if bytes_total > 100_000_000:  # > 100MB
        score += 15
    elif bytes_total > 10_000_000:  # > 10MB
        score += 5
    
    # Service risk
    if flow.get('service_risk') == 'high':
        score += 20
    elif flow.get('service_risk') == 'medium':
        score += 10
    
    return min(score, 100)  # Cap at 100

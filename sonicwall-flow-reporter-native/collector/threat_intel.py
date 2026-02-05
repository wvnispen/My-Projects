#!/usr/bin/env python3
"""
Threat Intelligence Module

Integrates with threat intelligence feeds to flag traffic to/from known malicious IPs.
Supports multiple threat feed sources and local blocklists.
"""

import os
import logging
import threading
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Set, Optional, Any, List

logger = logging.getLogger('swfr.threat_intel')


class ThreatIntelCache:
    """Thread-safe cache for threat intelligence data"""
    
    def __init__(self):
        self.malicious_ips: Set[str] = set()
        self.malicious_networks: List[tuple] = []  # List of (network_int, mask_int)
        self.threat_data: Dict[str, Dict] = {}  # IP -> threat info
        self.lock = threading.RLock()
        self.last_update: Optional[datetime] = None
    
    def add_ip(self, ip: str, threat_info: Dict = None):
        with self.lock:
            self.malicious_ips.add(ip)
            if threat_info:
                self.threat_data[ip] = threat_info
    
    def add_network(self, network: str):
        """Add a CIDR network to the blocklist"""
        try:
            import ipaddress
            net = ipaddress.ip_network(network, strict=False)
            network_int = int(net.network_address)
            mask_int = int(net.netmask)
            with self.lock:
                self.malicious_networks.append((network_int, mask_int, network))
        except Exception as e:
            logger.debug(f"Error adding network {network}: {e}")
    
    def is_malicious(self, ip: str) -> Optional[Dict]:
        """Check if an IP is in the threat list"""
        with self.lock:
            # Direct IP match
            if ip in self.malicious_ips:
                return self.threat_data.get(ip, {'source': 'blocklist', 'threat_type': 'malicious'})
            
            # Network match
            try:
                import ipaddress
                ip_int = int(ipaddress.ip_address(ip))
                for network_int, mask_int, network_str in self.malicious_networks:
                    if (ip_int & mask_int) == network_int:
                        return {'source': 'blocklist', 'threat_type': 'malicious_network', 'network': network_str}
            except:
                pass
            
            return None
    
    def clear(self):
        with self.lock:
            self.malicious_ips.clear()
            self.malicious_networks.clear()
            self.threat_data.clear()
    
    def stats(self) -> Dict:
        with self.lock:
            return {
                'malicious_ips': len(self.malicious_ips),
                'malicious_networks': len(self.malicious_networks),
                'last_update': self.last_update.isoformat() if self.last_update else None
            }


class ThreatIntelligence:
    """
    Threat intelligence integration for flagging malicious traffic.
    
    Supports:
    - Local blocklist files
    - Emerging Threats (free)
    - AbuseIPDB (requires API key)
    - Custom threat feeds
    """
    
    DEFAULT_FEEDS = {
        'emerging_threats_compromised': {
            'url': 'https://rules.emergingthreats.net/blockrules/compromised-ips.txt',
            'format': 'plain',
            'enabled': True,
        },
        'emerging_threats_block': {
            'url': 'https://rules.emergingthreats.net/fwrules/emerging-Block-IPs.txt',
            'format': 'plain',
            'enabled': True,
        },
        'feodotracker': {
            'url': 'https://feodotracker.abuse.ch/downloads/ipblocklist.txt',
            'format': 'plain',
            'enabled': True,
        },
        'spamhaus_drop': {
            'url': 'https://www.spamhaus.org/drop/drop.txt',
            'format': 'cidr_comment',
            'enabled': True,
        },
    }
    
    def __init__(self, 
                 enabled: bool = True,
                 local_blocklist_path: str = None,
                 abuseipdb_key: str = None,
                 update_interval_hours: int = 24):
        
        self.enabled = enabled
        self.cache = ThreatIntelCache()
        self.local_blocklist_path = Path(local_blocklist_path) if local_blocklist_path else None
        self.abuseipdb_key = abuseipdb_key
        self.update_interval = timedelta(hours=update_interval_hours)
        self.feeds = self.DEFAULT_FEEDS.copy()
        
        if not self.enabled:
            logger.info("Threat intelligence disabled")
            return
        
        # Initial load
        self._update_feeds()
        
        # Start background update thread
        self.update_thread = threading.Thread(target=self._periodic_update, daemon=True)
        self.update_thread.start()
        
        logger.info(f"Threat intelligence initialized - {self.cache.stats()}")
    
    def _update_feeds(self):
        """Update all threat feeds"""
        if not self.enabled:
            return
        
        self.cache.clear()
        
        # Load local blocklist
        if self.local_blocklist_path and self.local_blocklist_path.exists():
            self._load_local_blocklist()
        
        # Load remote feeds
        for feed_name, feed_config in self.feeds.items():
            if feed_config.get('enabled', False):
                try:
                    self._load_feed(feed_name, feed_config)
                except Exception as e:
                    logger.warning(f"Error loading feed {feed_name}: {e}")
        
        self.cache.last_update = datetime.now(timezone.utc)
        logger.info(f"Threat feeds updated: {self.cache.stats()}")
    
    def _load_local_blocklist(self):
        """Load IPs from local blocklist file"""
        try:
            with open(self.local_blocklist_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '/' in line:
                            self.cache.add_network(line)
                        else:
                            self.cache.add_ip(line, {'source': 'local_blocklist'})
            logger.info(f"Loaded local blocklist: {self.local_blocklist_path}")
        except Exception as e:
            logger.error(f"Error loading local blocklist: {e}")
    
    def _load_feed(self, feed_name: str, config: Dict):
        """Load a threat feed"""
        try:
            response = requests.get(config['url'], timeout=30)
            response.raise_for_status()
            
            format_type = config.get('format', 'plain')
            count = 0
            
            for line in response.text.split('\n'):
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                ip = None
                
                if format_type == 'plain':
                    # Simple IP per line
                    ip = line.split()[0] if line.split() else None
                    
                elif format_type == 'cidr_comment':
                    # CIDR ; comment format
                    parts = line.split(';')
                    if parts:
                        cidr = parts[0].strip()
                        if '/' in cidr:
                            self.cache.add_network(cidr)
                            count += 1
                            continue
                        else:
                            ip = cidr
                
                elif format_type == 'csv':
                    # CSV format
                    parts = line.split(',')
                    if parts:
                        ip = parts[0].strip()
                
                # Add IP if valid
                if ip:
                    # Basic IP validation
                    if self._is_valid_ip(ip):
                        self.cache.add_ip(ip, {'source': feed_name})
                        count += 1
                    elif '/' in ip:
                        self.cache.add_network(ip)
                        count += 1
            
            logger.info(f"Loaded {count} entries from {feed_name}")
            
        except Exception as e:
            logger.warning(f"Error loading feed {feed_name}: {e}")
    
    def _is_valid_ip(self, ip: str) -> bool:
        """Basic IP validation"""
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        try:
            return all(0 <= int(p) <= 255 for p in parts)
        except ValueError:
            return False
    
    def _periodic_update(self):
        """Periodically update threat feeds"""
        import time
        while True:
            time.sleep(self.update_interval.total_seconds())
            try:
                self._update_feeds()
            except Exception as e:
                logger.error(f"Error in periodic threat feed update: {e}")
    
    def check_ip(self, ip: str) -> Optional[Dict[str, Any]]:
        """Check if an IP is in threat intelligence"""
        if not self.enabled or not ip:
            return None
        
        return self.cache.is_malicious(ip)
    
    def enrich_flow(self, flow: Dict[str, Any]) -> Dict[str, Any]:
        """Add threat intelligence data to a flow record"""
        if not self.enabled:
            return flow
        
        # Check destination IP
        dst_ip = flow.get('dst_ip')
        if dst_ip:
            threat_info = self.check_ip(dst_ip)
            if threat_info:
                flow['dst_threat'] = threat_info
                flow['threat_detected'] = True
                flow['threat_direction'] = 'outbound'
        
        # Check source IP (for inbound threats)
        src_ip = flow.get('src_ip')
        if src_ip and not src_ip.startswith(('10.', '192.168.', '172.')):
            threat_info = self.check_ip(src_ip)
            if threat_info:
                flow['src_threat'] = threat_info
                flow['threat_detected'] = True
                # Set direction - 'both' if already outbound, otherwise 'inbound'
                if flow.get('threat_direction') == 'outbound':
                    flow['threat_direction'] = 'both'
                else:
                    flow['threat_direction'] = 'inbound'
        
        return flow
    
    def add_to_blocklist(self, ip: str, threat_info: Dict = None):
        """Manually add an IP to the blocklist"""
        info = threat_info or {'source': 'manual', 'threat_type': 'blocked'}
        self.cache.add_ip(ip, info)
    
    def get_stats(self) -> Dict:
        """Get threat intelligence statistics"""
        return self.cache.stats()

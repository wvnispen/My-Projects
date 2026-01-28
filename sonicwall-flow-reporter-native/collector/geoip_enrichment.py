#!/usr/bin/env python3
"""
GeoIP Enrichment Module

Adds geographic location data to flow records based on IP addresses.
Uses MaxMind GeoLite2 databases for lookups.
"""

import os
import logging
import threading
import tarfile
import shutil
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any
from pathlib import Path

logger = logging.getLogger('swfr.geoip')

# Try to import geoip2, but don't fail if not available
try:
    import geoip2.database
    import geoip2.errors
    GEOIP_AVAILABLE = True
except ImportError:
    GEOIP_AVAILABLE = False
    logger.warning("geoip2 module not installed. GeoIP enrichment disabled.")


class GeoIPCache:
    """Thread-safe LRU cache for GeoIP lookups"""
    
    def __init__(self, max_size: int = 50000, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl = timedelta(seconds=ttl_seconds)
        self.cache: Dict[str, tuple] = {}
        self.lock = threading.Lock()
    
    def get(self, ip: str) -> Optional[Dict]:
        with self.lock:
            if ip in self.cache:
                data, expiry = self.cache[ip]
                if datetime.now(timezone.utc) < expiry:
                    return data
                else:
                    del self.cache[ip]
            return None
    
    def set(self, ip: str, data: Optional[Dict]):
        with self.lock:
            if len(self.cache) >= self.max_size:
                # Remove 10% oldest entries
                to_remove = sorted(self.cache.items(), key=lambda x: x[1][1])[:self.max_size // 10]
                for key, _ in to_remove:
                    del self.cache[key]
            
            expiry = datetime.now(timezone.utc) + self.ttl
            self.cache[ip] = (data, expiry)


class GeoIPEnricher:
    """Enriches flow data with geographic location information"""
    
    # Default database paths
    DEFAULT_DB_DIR = "/opt/sonicwall-flow-reporter/geoip"
    CITY_DB = "GeoLite2-City.mmdb"
    ASN_DB = "GeoLite2-ASN.mmdb"
    
    # Private/reserved IP ranges that should not be looked up
    PRIVATE_PREFIXES = (
        '10.', '172.16.', '172.17.', '172.18.', '172.19.',
        '172.20.', '172.21.', '172.22.', '172.23.', '172.24.',
        '172.25.', '172.26.', '172.27.', '172.28.', '172.29.',
        '172.30.', '172.31.', '192.168.', '127.', '0.', '169.254.',
        '224.', '239.', '255.', '::'  # Also skip IPv6 link-local
    )
    
    def __init__(self, db_dir: str = None):
        self.db_dir = Path(db_dir or self.DEFAULT_DB_DIR)
        self.city_reader = None
        self.asn_reader = None
        self.cache = GeoIPCache()
        self.enabled = False
        
        if not GEOIP_AVAILABLE:
            logger.warning("GeoIP enrichment disabled - geoip2 module not installed")
            return
        
        self._load_databases()
    
    def _load_databases(self):
        """Load GeoIP databases"""
        try:
            city_path = self.db_dir / self.CITY_DB
            asn_path = self.db_dir / self.ASN_DB
            
            if city_path.exists():
                self.city_reader = geoip2.database.Reader(str(city_path))
                logger.info(f"Loaded GeoIP City database: {city_path}")
                self.enabled = True
            else:
                logger.warning(f"GeoIP City database not found: {city_path}")
            
            if asn_path.exists():
                self.asn_reader = geoip2.database.Reader(str(asn_path))
                logger.info(f"Loaded GeoIP ASN database: {asn_path}")
            else:
                logger.info(f"GeoIP ASN database not found (optional): {asn_path}")
                
        except Exception as e:
            logger.error(f"Error loading GeoIP databases: {e}")
            self.enabled = False
    
    def is_private_ip(self, ip: str) -> bool:
        """Check if IP is private/reserved"""
        if not ip:
            return True
        return any(ip.startswith(prefix) for prefix in self.PRIVATE_PREFIXES)
    
    def lookup(self, ip: str) -> Optional[Dict[str, Any]]:
        """Look up geographic information for an IP address"""
        if not self.enabled or not ip or self.is_private_ip(ip):
            return None
        
        # Check cache
        cached = self.cache.get(ip)
        if cached is not None:
            return cached if cached else None
        
        result = {}
        
        try:
            # City/Country lookup
            if self.city_reader:
                try:
                    city_response = self.city_reader.city(ip)
                    
                    result['geo'] = {
                        'country_code': city_response.country.iso_code,
                        'country_name': city_response.country.name,
                        'city': city_response.city.name,
                        'region': city_response.subdivisions.most_specific.name if city_response.subdivisions else None,
                        'postal_code': city_response.postal.code,
                        'timezone': city_response.location.time_zone,
                    }
                    
                    # Add coordinates for map visualization
                    if city_response.location.latitude and city_response.location.longitude:
                        result['geo']['location'] = {
                            'lat': city_response.location.latitude,
                            'lon': city_response.location.longitude
                        }
                    
                except geoip2.errors.AddressNotFoundError:
                    pass
            
            # ASN lookup
            if self.asn_reader:
                try:
                    asn_response = self.asn_reader.asn(ip)
                    result['asn'] = {
                        'number': asn_response.autonomous_system_number,
                        'organization': asn_response.autonomous_system_organization
                    }
                except geoip2.errors.AddressNotFoundError:
                    pass
                    
        except Exception as e:
            logger.debug(f"GeoIP lookup error for {ip}: {e}")
        
        # Cache result
        self.cache.set(ip, result if result else None)
        
        return result if result else None
    
    def enrich_flow(self, flow: Dict[str, Any]) -> Dict[str, Any]:
        """Add GeoIP data to a flow record"""
        if not self.enabled:
            return flow
        
        # Look up destination IP (most interesting for outbound traffic)
        dst_ip = flow.get('dst_ip')
        if dst_ip:
            geo_data = self.lookup(dst_ip)
            if geo_data:
                if 'geo' in geo_data:
                    flow['dst_geo'] = geo_data['geo']
                if 'asn' in geo_data:
                    flow['dst_asn'] = geo_data['asn']
        
        # Optionally look up source IP for inbound traffic analysis
        src_ip = flow.get('src_ip')
        if src_ip and not self.is_private_ip(src_ip):
            geo_data = self.lookup(src_ip)
            if geo_data:
                if 'geo' in geo_data:
                    flow['src_geo'] = geo_data['geo']
                if 'asn' in geo_data:
                    flow['src_asn'] = geo_data['asn']
        
        return flow
    
    def close(self):
        """Close database readers"""
        if self.city_reader:
            self.city_reader.close()
        if self.asn_reader:
            self.asn_reader.close()


def download_geoip_databases(license_key: str, db_dir: str = None):
    """
    Download GeoLite2 databases from MaxMind.
    Requires a free MaxMind license key.
    
    Get a free license key at: https://www.maxmind.com/en/geolite2/signup
    """
    import requests
    
    db_dir = Path(db_dir or GeoIPEnricher.DEFAULT_DB_DIR)
    db_dir.mkdir(parents=True, exist_ok=True)
    
    databases = [
        ('GeoLite2-City', 'GeoLite2-City.mmdb'),
        ('GeoLite2-ASN', 'GeoLite2-ASN.mmdb'),
    ]
    
    for edition_id, filename in databases:
        url = f"https://download.maxmind.com/app/geoip_download?edition_id={edition_id}&license_key={license_key}&suffix=tar.gz"
        
        try:
            logger.info(f"Downloading {edition_id}...")
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            tar_path = db_dir / f"{edition_id}.tar.gz"
            with open(tar_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Extract the .mmdb file
            with tarfile.open(tar_path, 'r:gz') as tar:
                for member in tar.getmembers():
                    if member.name.endswith('.mmdb'):
                        member.name = filename
                        tar.extract(member, db_dir)
                        break
            
            # Clean up tar file
            tar_path.unlink()
            
            logger.info(f"Successfully downloaded {filename}")
            
        except Exception as e:
            logger.error(f"Error downloading {edition_id}: {e}")
            raise

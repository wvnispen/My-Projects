#!/usr/bin/env python3
"""
Identity Enrichment Module

Looks up IP addresses against the identity database to add user information
to flow records. Supports:
- Direct IP matches
- Subnet/CIDR matches
- Caching for performance
"""

import logging
import threading
import ipaddress
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any, List
from elasticsearch import Elasticsearch

logger = logging.getLogger('swfr.enrichment')


class IdentityCache:
    """Thread-safe LRU cache for identity lookups"""
    
    def __init__(self, max_size: int = 10000, ttl_seconds: int = 300):
        self.max_size = max_size
        self.ttl = timedelta(seconds=ttl_seconds)
        self.cache: Dict[str, tuple] = {}  # ip -> (identity, expiry)
        self.lock = threading.Lock()
    
    def get(self, ip: str) -> Optional[Dict]:
        """Get identity from cache if not expired"""
        with self.lock:
            if ip in self.cache:
                identity, expiry = self.cache[ip]
                if datetime.now(timezone.utc) < expiry:
                    return identity
                else:
                    del self.cache[ip]
            return None
    
    def set(self, ip: str, identity: Optional[Dict]):
        """Store identity in cache"""
        with self.lock:
            # Evict oldest entries if at capacity
            if len(self.cache) >= self.max_size:
                # Remove 10% oldest entries
                to_remove = sorted(self.cache.items(), key=lambda x: x[1][1])[:self.max_size // 10]
                for key, _ in to_remove:
                    del self.cache[key]
            
            expiry = datetime.now(timezone.utc) + self.ttl
            self.cache[ip] = (identity, expiry)
    
    def clear(self):
        """Clear the cache"""
        with self.lock:
            self.cache.clear()


class IdentityEnricher:
    """Enriches flow data with user identity information"""
    
    def __init__(self, es_client: Elasticsearch):
        self.es_client = es_client
        self.cache = IdentityCache()
        
        # Pre-load subnet mappings for faster lookup
        self.subnet_mappings: List[tuple] = []  # [(network, identity), ...]
        self.subnet_lock = threading.Lock()
        
        # Load initial mappings
        self._load_subnet_mappings()
        
        # Start periodic refresh thread
        self.refresh_thread = threading.Thread(target=self._periodic_refresh, daemon=True)
        self.refresh_thread.start()
    
    def _load_subnet_mappings(self):
        """Load all subnet mappings from Elasticsearch"""
        try:
            result = self.es_client.search(
                index="identity-mappings",
                body={
                    "size": 10000,
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"active": True}},
                                {"exists": {"field": "subnet"}}
                            ]
                        }
                    }
                }
            )
            
            new_mappings = []
            for hit in result['hits']['hits']:
                source = hit['_source']
                try:
                    # Parse subnet range
                    subnet = source.get('subnet', {})
                    if subnet and 'gte' in subnet and 'lte' in subnet:
                        # IP range format
                        start = ipaddress.ip_address(subnet['gte'])
                        end = ipaddress.ip_address(subnet['lte'])
                        # Convert to network (approximation)
                        network = ipaddress.ip_network(f"{start}/24", strict=False)
                    else:
                        continue
                    
                    identity = {
                        'user_id': source.get('user_id'),
                        'user_name': source.get('user_name'),
                        'department': source.get('department'),
                        'location': source.get('location'),
                        'description': source.get('description')
                    }
                    new_mappings.append((network, identity))
                    
                except Exception as e:
                    logger.debug(f"Error parsing subnet mapping: {e}")
            
            with self.subnet_lock:
                self.subnet_mappings = new_mappings
            
            logger.info(f"Loaded {len(new_mappings)} subnet mappings")
            
        except Exception as e:
            logger.error(f"Error loading subnet mappings: {e}")
    
    def _periodic_refresh(self):
        """Periodically refresh subnet mappings and clear cache"""
        import time
        while True:
            time.sleep(300)  # Refresh every 5 minutes
            self._load_subnet_mappings()
            self.cache.clear()
    
    def lookup(self, ip: str) -> Optional[Dict[str, Any]]:
        """Look up identity for an IP address"""
        # Check cache first
        cached = self.cache.get(ip)
        if cached is not None:
            return cached if cached else None
        
        identity = None
        
        # Try direct IP lookup
        identity = self._lookup_direct(ip)
        
        # Try subnet lookup if no direct match
        if not identity:
            identity = self._lookup_subnet(ip)
        
        # Cache result (even if None to prevent repeated lookups)
        self.cache.set(ip, identity)
        
        return identity
    
    def _lookup_direct(self, ip: str) -> Optional[Dict]:
        """Look up by exact IP address"""
        try:
            result = self.es_client.search(
                index="identity-mappings",
                body={
                    "size": 1,
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"ip_address": ip}},
                                {"term": {"active": True}}
                            ]
                        }
                    },
                    "sort": [{"updated_at": "desc"}]
                }
            )
            
            if result['hits']['hits']:
                source = result['hits']['hits'][0]['_source']
                return {
                    'user_id': source.get('user_id'),
                    'user_name': source.get('user_name'),
                    'department': source.get('department'),
                    'location': source.get('location')
                }
            
        except Exception as e:
            logger.debug(f"Error in direct IP lookup: {e}")
        
        return None
    
    def _lookup_subnet(self, ip: str) -> Optional[Dict]:
        """Look up by subnet match"""
        try:
            ip_obj = ipaddress.ip_address(ip)
            
            with self.subnet_lock:
                for network, identity in self.subnet_mappings:
                    if ip_obj in network:
                        return identity
            
        except Exception as e:
            logger.debug(f"Error in subnet lookup: {e}")
        
        return None
    
    def add_mapping(self, ip_address: Optional[str] = None, subnet: Optional[str] = None,
                    user_id: str = None, user_name: str = None, department: str = None,
                    location: str = None, description: str = None, source: str = 'manual') -> bool:
        """Add or update an identity mapping"""
        now = datetime.now(timezone.utc).isoformat()
        
        doc = {
            'user_id': user_id,
            'user_name': user_name,
            'department': department,
            'location': location,
            'description': description,
            'source': source,
            'active': True,
            'created_at': now,
            'updated_at': now
        }
        
        if ip_address:
            doc['ip_address'] = ip_address
        
        if subnet:
            # Parse CIDR notation
            try:
                network = ipaddress.ip_network(subnet, strict=False)
                doc['subnet'] = {
                    'gte': str(network.network_address),
                    'lte': str(network.broadcast_address)
                }
            except ValueError as e:
                logger.error(f"Invalid subnet format: {subnet}")
                return False
        
        try:
            # Use upsert to update existing or create new
            doc_id = f"{ip_address or subnet}_{user_id}"
            self.es_client.index(
                index="identity-mappings",
                id=doc_id,
                document=doc
            )
            
            # Clear cache for this IP
            if ip_address:
                self.cache.set(ip_address, None)
            
            # Trigger subnet refresh if subnet mapping
            if subnet:
                self._load_subnet_mappings()
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding identity mapping: {e}")
            return False
    
    def remove_mapping(self, ip_address: Optional[str] = None, user_id: Optional[str] = None) -> bool:
        """Remove an identity mapping (soft delete by setting active=False)"""
        try:
            query = {"bool": {"must": []}}
            
            if ip_address:
                query["bool"]["must"].append({"term": {"ip_address": ip_address}})
            if user_id:
                query["bool"]["must"].append({"term": {"user_id": user_id}})
            
            if not query["bool"]["must"]:
                return False
            
            self.es_client.update_by_query(
                index="identity-mappings",
                body={
                    "query": query,
                    "script": {
                        "source": "ctx._source.active = false; ctx._source.updated_at = params.now",
                        "params": {"now": datetime.now(timezone.utc).isoformat()}
                    }
                }
            )
            
            # Clear cache
            if ip_address:
                self.cache.set(ip_address, None)
            
            return True
            
        except Exception as e:
            logger.error(f"Error removing identity mapping: {e}")
            return False

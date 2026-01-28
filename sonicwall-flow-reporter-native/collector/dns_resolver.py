#!/usr/bin/env python3
"""
DNS Reverse Lookup Module

Resolves IP addresses to hostnames for better readability in dashboards.
Uses caching to minimize DNS queries.
"""

import socket
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor, TimeoutError

logger = logging.getLogger('swfr.dns')


class DNSCache:
    """Thread-safe LRU cache for DNS lookups"""
    
    def __init__(self, max_size: int = 100000, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl = timedelta(seconds=ttl_seconds)
        self.cache: Dict[str, tuple] = {}
        self.lock = threading.Lock()
        self.hits = 0
        self.misses = 0
    
    def get(self, ip: str) -> Optional[str]:
        with self.lock:
            if ip in self.cache:
                hostname, expiry = self.cache[ip]
                if datetime.now(timezone.utc) < expiry:
                    self.hits += 1
                    return hostname
                else:
                    del self.cache[ip]
            self.misses += 1
            return None
    
    def set(self, ip: str, hostname: Optional[str]):
        with self.lock:
            if len(self.cache) >= self.max_size:
                # Remove 10% oldest entries
                to_remove = sorted(self.cache.items(), key=lambda x: x[1][1])[:self.max_size // 10]
                for key, _ in to_remove:
                    del self.cache[key]
            
            expiry = datetime.now(timezone.utc) + self.ttl
            self.cache[ip] = (hostname, expiry)
    
    def stats(self) -> Dict[str, int]:
        with self.lock:
            total = self.hits + self.misses
            return {
                'size': len(self.cache),
                'hits': self.hits,
                'misses': self.misses,
                'hit_rate': (self.hits / total * 100) if total > 0 else 0
            }


class DNSResolver:
    """Asynchronous DNS reverse lookup with caching"""
    
    # Private IP prefixes to skip
    PRIVATE_PREFIXES = (
        '10.', '172.16.', '172.17.', '172.18.', '172.19.',
        '172.20.', '172.21.', '172.22.', '172.23.', '172.24.',
        '172.25.', '172.26.', '172.27.', '172.28.', '172.29.',
        '172.30.', '172.31.', '192.168.', '127.', '0.', '169.254.'
    )
    
    def __init__(self, timeout: float = 1.0, max_workers: int = 10, enabled: bool = True):
        self.timeout = timeout
        self.enabled = enabled
        self.cache = DNSCache()
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='dns')
        
        # Track pending lookups to avoid duplicates
        self.pending: Dict[str, threading.Event] = {}
        self.pending_lock = threading.Lock()
        
        logger.info(f"DNS resolver initialized (enabled={enabled}, timeout={timeout}s)")
    
    def is_private_ip(self, ip: str) -> bool:
        """Check if IP is private/reserved"""
        if not ip:
            return True
        return any(ip.startswith(prefix) for prefix in self.PRIVATE_PREFIXES)
    
    def _do_lookup(self, ip: str) -> Optional[str]:
        """Perform actual DNS lookup"""
        try:
            hostname, _, _ = socket.gethostbyaddr(ip)
            return hostname
        except (socket.herror, socket.gaierror, socket.timeout):
            return None
        except Exception as e:
            logger.debug(f"DNS lookup error for {ip}: {e}")
            return None
    
    def lookup(self, ip: str) -> Optional[str]:
        """
        Look up hostname for an IP address.
        Returns cached result immediately or None if not cached.
        Triggers async lookup if not in cache.
        """
        if not self.enabled or not ip or self.is_private_ip(ip):
            return None
        
        # Check cache first
        cached = self.cache.get(ip)
        if cached is not None:
            return cached if cached else None
        
        # Check if lookup is already pending
        with self.pending_lock:
            if ip in self.pending:
                return None  # Lookup in progress
            self.pending[ip] = threading.Event()
        
        # Submit async lookup
        def lookup_and_cache():
            try:
                hostname = self._do_lookup(ip)
                self.cache.set(ip, hostname)
            finally:
                with self.pending_lock:
                    if ip in self.pending:
                        self.pending[ip].set()
                        del self.pending[ip]
        
        self.executor.submit(lookup_and_cache)
        return None
    
    def lookup_sync(self, ip: str) -> Optional[str]:
        """
        Synchronous lookup with timeout.
        Use sparingly as it blocks.
        """
        if not self.enabled or not ip or self.is_private_ip(ip):
            return None
        
        # Check cache
        cached = self.cache.get(ip)
        if cached is not None:
            return cached if cached else None
        
        # Do lookup with timeout
        try:
            future = self.executor.submit(self._do_lookup, ip)
            hostname = future.result(timeout=self.timeout)
            self.cache.set(ip, hostname)
            return hostname
        except TimeoutError:
            self.cache.set(ip, None)  # Cache negative result
            return None
        except Exception as e:
            logger.debug(f"Sync DNS lookup error for {ip}: {e}")
            return None
    
    def enrich_flow(self, flow: Dict[str, Any]) -> Dict[str, Any]:
        """Add DNS hostname to a flow record (non-blocking)"""
        if not self.enabled:
            return flow
        
        # Look up destination hostname
        dst_ip = flow.get('dst_ip')
        if dst_ip:
            hostname = self.lookup(dst_ip)
            if hostname:
                flow['dst_hostname'] = hostname
        
        # Look up source hostname for non-private IPs
        src_ip = flow.get('src_ip')
        if src_ip and not self.is_private_ip(src_ip):
            hostname = self.lookup(src_ip)
            if hostname:
                flow['src_hostname'] = hostname
        
        return flow
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return self.cache.stats()
    
    def shutdown(self):
        """Shutdown the executor"""
        self.executor.shutdown(wait=False)

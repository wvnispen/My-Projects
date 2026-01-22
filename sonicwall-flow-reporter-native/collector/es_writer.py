#!/usr/bin/env python3
"""
Elasticsearch Writer for IPFIX flows

Handles buffered bulk writes to Elasticsearch with automatic flushing.
"""

import os
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

logger = logging.getLogger('swfr.es_writer')


class ElasticsearchWriter:
    """Buffered writer for Elasticsearch"""
    
    def __init__(self, buffer_size: int = 1000, flush_interval: float = 5.0):
        self.es_host = os.environ.get('ELASTICSEARCH_HOST', 'localhost')
        self.es_port = int(os.environ.get('ELASTICSEARCH_PORT', '9200'))
        self.es_password = os.environ.get('ELASTIC_PASSWORD', '')
        
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        
        self.buffer: List[Dict[str, Any]] = []
        self.buffer_lock = threading.Lock()
        
        # Connect to Elasticsearch
        self.es_client = self._connect()
        
        # Start periodic flush thread
        self.running = True
        self.flush_thread = threading.Thread(target=self._periodic_flush, daemon=True)
        self.flush_thread.start()
        
        logger.info(f"Connected to Elasticsearch at {self.es_host}:{self.es_port}")
    
    def _connect(self) -> Elasticsearch:
        """Create Elasticsearch connection"""
        es_url = f"http://{self.es_host}:{self.es_port}"
        
        # Only use auth if password is provided
        if self.es_password:
            return Elasticsearch(
                hosts=[es_url],
                basic_auth=("elastic", self.es_password),
                retry_on_timeout=True,
                max_retries=3
            )
        else:
            return Elasticsearch(
                hosts=[es_url],
                retry_on_timeout=True,
                max_retries=3
            )
    
    def write_flows(self, flows: List[Dict[str, Any]]):
        """Add flows to buffer for bulk writing"""
        with self.buffer_lock:
            self.buffer.extend(flows)
            
            if len(self.buffer) >= self.buffer_size:
                self._flush_buffer()
    
    def _flush_buffer(self):
        """Flush buffer to Elasticsearch (must hold buffer_lock)"""
        if not self.buffer:
            return
        
        flows_to_write = self.buffer
        self.buffer = []
        
        try:
            actions = []
            for flow in flows_to_write:
                # Determine index based on timestamp
                timestamp = flow.get('@timestamp', datetime.now(timezone.utc).isoformat())
                
                action = {
                    '_index': 'flows-raw',  # Uses write alias
                    '_source': flow
                }
                actions.append(action)
            
            success, failed = bulk(self.es_client, actions, raise_on_error=False, 
                                   raise_on_exception=False)
            
            if failed:
                logger.error(f"Failed to index {len(failed)} flows")
            else:
                logger.debug(f"Indexed {success} flows")
                
        except Exception as e:
            logger.error(f"Error flushing to Elasticsearch: {e}")
            # Re-add to buffer on failure (with limit to prevent memory issues)
            with self.buffer_lock:
                if len(self.buffer) < self.buffer_size * 10:
                    self.buffer = flows_to_write + self.buffer
    
    def _periodic_flush(self):
        """Periodically flush buffer"""
        import time
        while self.running:
            time.sleep(self.flush_interval)
            with self.buffer_lock:
                if self.buffer:
                    self._flush_buffer()
    
    def flush(self):
        """Force flush all buffered data"""
        with self.buffer_lock:
            self._flush_buffer()
    
    def close(self):
        """Close writer and flush remaining data"""
        self.running = False
        self.flush()
        self.es_client.close()


class AggregationWriter:
    """Writer for aggregated flow data (hourly/daily rollups)"""
    
    def __init__(self, es_client: Elasticsearch):
        self.es_client = es_client
    
    def write_hourly_aggregate(self, aggregate: Dict[str, Any]):
        """Write hourly aggregate record"""
        try:
            self.es_client.index(
                index='flows-hourly',
                document=aggregate
            )
        except Exception as e:
            logger.error(f"Error writing hourly aggregate: {e}")
    
    def write_daily_aggregate(self, aggregate: Dict[str, Any]):
        """Write daily aggregate record"""
        try:
            self.es_client.index(
                index='flows-daily',
                document=aggregate
            )
        except Exception as e:
            logger.error(f"Error writing daily aggregate: {e}")
    
    def aggregate_hourly(self, hour: datetime) -> List[Dict]:
        """Aggregate raw flows into hourly summaries"""
        hour_start = hour.replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start.replace(minute=59, second=59)
        
        query = {
            "size": 0,
            "query": {
                "range": {
                    "@timestamp": {
                        "gte": hour_start.isoformat(),
                        "lt": hour_end.isoformat()
                    }
                }
            },
            "aggs": {
                "by_user": {
                    "composite": {
                        "size": 10000,
                        "sources": [
                            {"firewall_ip": {"terms": {"field": "firewall_ip"}}},
                            {"user_name": {"terms": {"field": "user_name", "missing_bucket": True}}},
                            {"application_name": {"terms": {"field": "application_name", "missing_bucket": True}}}
                        ]
                    },
                    "aggs": {
                        "bytes_in": {"sum": {"field": "bytes_in"}},
                        "bytes_out": {"sum": {"field": "bytes_out"}},
                        "bytes_total": {"sum": {"field": "bytes_total"}},
                        "packets_total": {"sum": {"field": "packets_total"}},
                        "unique_destinations": {"cardinality": {"field": "dst_ip"}}
                    }
                }
            }
        }
        
        try:
            result = self.es_client.search(index="flows-raw-*", body=query)
            aggregates = []
            
            for bucket in result.get('aggregations', {}).get('by_user', {}).get('buckets', []):
                aggregate = {
                    '@timestamp': hour_start.isoformat(),
                    'hour': hour_start.isoformat(),
                    'firewall_ip': bucket['key']['firewall_ip'],
                    'user_name': bucket['key']['user_name'],
                    'application_name': bucket['key']['application_name'],
                    'bytes_in': int(bucket['bytes_in']['value']),
                    'bytes_out': int(bucket['bytes_out']['value']),
                    'bytes_total': int(bucket['bytes_total']['value']),
                    'packets_total': int(bucket['packets_total']['value']),
                    'flow_count': bucket['doc_count'],
                    'unique_destinations': bucket['unique_destinations']['value']
                }
                aggregates.append(aggregate)
            
            return aggregates
            
        except Exception as e:
            logger.error(f"Error aggregating hourly data: {e}")
            return []
    
    def aggregate_daily(self, day: datetime) -> List[Dict]:
        """Aggregate hourly data into daily summaries"""
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start.replace(hour=23, minute=59, second=59)
        
        query = {
            "size": 0,
            "query": {
                "range": {
                    "@timestamp": {
                        "gte": day_start.isoformat(),
                        "lt": day_end.isoformat()
                    }
                }
            },
            "aggs": {
                "by_user": {
                    "composite": {
                        "size": 10000,
                        "sources": [
                            {"firewall_ip": {"terms": {"field": "firewall_ip"}}},
                            {"user_name": {"terms": {"field": "user_name", "missing_bucket": True}}}
                        ]
                    },
                    "aggs": {
                        "bytes_in": {"sum": {"field": "bytes_in"}},
                        "bytes_out": {"sum": {"field": "bytes_out"}},
                        "bytes_total": {"sum": {"field": "bytes_total"}},
                        "packets_total": {"sum": {"field": "packets_total"}},
                        "unique_destinations": {"sum": {"field": "unique_destinations"}},
                        "unique_applications": {"cardinality": {"field": "application_name"}}
                    }
                }
            }
        }
        
        try:
            result = self.es_client.search(index="flows-hourly-*", body=query)
            aggregates = []
            
            for bucket in result.get('aggregations', {}).get('by_user', {}).get('buckets', []):
                aggregate = {
                    '@timestamp': day_start.isoformat(),
                    'day': day_start.isoformat(),
                    'firewall_ip': bucket['key']['firewall_ip'],
                    'user_name': bucket['key']['user_name'],
                    'bytes_in': int(bucket['bytes_in']['value']),
                    'bytes_out': int(bucket['bytes_out']['value']),
                    'bytes_total': int(bucket['bytes_total']['value']),
                    'packets_total': int(bucket['packets_total']['value']),
                    'flow_count': bucket['doc_count'],
                    'unique_destinations': int(bucket['unique_destinations']['value']),
                    'unique_applications': bucket['unique_applications']['value']
                }
                aggregates.append(aggregate)
            
            return aggregates
            
        except Exception as e:
            logger.error(f"Error aggregating daily data: {e}")
            return []

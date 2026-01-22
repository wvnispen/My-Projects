#!/usr/bin/env python3
"""
SonicWall IPFIX Collector

Listens for IPFIX/NetFlow v9 packets from SonicWall firewalls,
parses them, enriches with identity data, and stores in Elasticsearch.

Supports:
- NetFlow v9
- IPFIX (NetFlow v10)
- SonicWall enterprise fields
"""

import os
import sys
import socket
import struct
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

from sonicwall_templates import (
    get_field_definition, get_protocol_name, decode_tcp_flags
)
from es_writer import ElasticsearchWriter
from enrichment import IdentityEnricher

logger = logging.getLogger('swfr.collector')


# ============================================================================
# NetFlow/IPFIX Header Structures
# ============================================================================

# NetFlow v9 header: version(2) + count(2) + sysuptime(4) + unix_secs(4) + seq(4) + source_id(4)
NETFLOW_V9_HEADER_SIZE = 20

# IPFIX header: version(2) + length(2) + export_time(4) + seq(4) + domain_id(4)
IPFIX_HEADER_SIZE = 16

# FlowSet header: flowset_id(2) + length(2)
FLOWSET_HEADER_SIZE = 4


class TemplateCache:
    """Cache for IPFIX/NetFlow templates received from firewalls"""
    
    def __init__(self):
        # Key: (source_ip, domain_id, template_id) -> List of (field_id, length, enterprise_id)
        self.templates: Dict[Tuple[str, int, int], List[Tuple[int, int, Optional[int]]]] = {}
        self.lock = threading.Lock()
    
    def add_template(self, source_ip: str, domain_id: int, template_id: int, 
                     fields: List[Tuple[int, int, Optional[int]]]):
        """Store a template definition"""
        with self.lock:
            key = (source_ip, domain_id, template_id)
            self.templates[key] = fields
            logger.info(f"Cached template {template_id} from {source_ip} with {len(fields)} fields")
    
    def get_template(self, source_ip: str, domain_id: int, template_id: int) -> Optional[List]:
        """Retrieve a template definition"""
        with self.lock:
            return self.templates.get((source_ip, domain_id, template_id))
    
    def clear_source(self, source_ip: str):
        """Clear all templates from a specific source"""
        with self.lock:
            keys_to_remove = [k for k in self.templates if k[0] == source_ip]
            for key in keys_to_remove:
                del self.templates[key]


class IPFIXCollector:
    """Main IPFIX collector service"""
    
    def __init__(self):
        self.listen_ip = os.environ.get('IPFIX_LISTEN_IP', '0.0.0.0')
        self.listen_port = int(os.environ.get('IPFIX_LISTEN_PORT', '2055'))
        self.allowed_sources = self._parse_allowed_sources()
        
        self.template_cache = TemplateCache()
        self.es_writer = ElasticsearchWriter()
        self.enricher = IdentityEnricher(self.es_writer.es_client)
        
        self.stats = defaultdict(int)
        self.running = False
    
    def _parse_allowed_sources(self) -> Optional[set]:
        """Parse allowed source IPs from environment"""
        sources = os.environ.get('IPFIX_ALLOWED_SOURCES', '').strip()
        if not sources:
            return None  # Allow all
        return set(s.strip() for s in sources.split(',') if s.strip())
    
    def run(self):
        """Start the collector"""
        self.running = True
        
        # Start stats reporter thread
        stats_thread = threading.Thread(target=self._report_stats, daemon=True)
        stats_thread.start()
        
        # Create UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Increase receive buffer for high-volume environments
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        
        sock.bind((self.listen_ip, self.listen_port))
        logger.info(f"IPFIX Collector listening on {self.listen_ip}:{self.listen_port}")
        
        if self.allowed_sources:
            logger.info(f"Accepting flows from: {', '.join(self.allowed_sources)}")
        else:
            logger.info("Accepting flows from any source")
        
        while self.running:
            try:
                data, addr = sock.recvfrom(65535)
                source_ip = addr[0]
                
                # Check allowed sources
                if self.allowed_sources and source_ip not in self.allowed_sources:
                    self.stats['rejected_source'] += 1
                    continue
                
                self.stats['packets_received'] += 1
                self._process_packet(data, source_ip)
                
            except Exception as e:
                logger.error(f"Error processing packet: {e}", exc_info=True)
                self.stats['errors'] += 1
    
    def _process_packet(self, data: bytes, source_ip: str):
        """Process an IPFIX or NetFlow v9 packet"""
        if len(data) < 4:
            return
        
        version = struct.unpack('!H', data[0:2])[0]
        
        if version == 9:
            self._process_netflow_v9(data, source_ip)
        elif version == 10:
            self._process_ipfix(data, source_ip)
        else:
            logger.warning(f"Unknown NetFlow version {version} from {source_ip}")
            self.stats['unknown_version'] += 1
    
    def _process_netflow_v9(self, data: bytes, source_ip: str):
        """Process NetFlow v9 packet"""
        if len(data) < NETFLOW_V9_HEADER_SIZE:
            return
        
        # Parse header
        version, count, sys_uptime, unix_secs, seq, source_id = struct.unpack(
            '!HHIIII', data[0:NETFLOW_V9_HEADER_SIZE]
        )
        
        export_time = datetime.fromtimestamp(unix_secs, tz=timezone.utc)
        offset = NETFLOW_V9_HEADER_SIZE
        
        # Process FlowSets
        while offset < len(data) - FLOWSET_HEADER_SIZE:
            flowset_id, flowset_length = struct.unpack('!HH', data[offset:offset+4])
            
            if flowset_length < 4:
                break
            
            flowset_data = data[offset+4:offset+flowset_length]
            
            if flowset_id == 0:
                # Template FlowSet
                self._parse_template_flowset(flowset_data, source_ip, source_id, is_ipfix=False)
            elif flowset_id == 1:
                # Options Template FlowSet (skip for now)
                pass
            elif flowset_id >= 256:
                # Data FlowSet
                self._parse_data_flowset(flowset_data, source_ip, source_id, flowset_id, export_time)
            
            offset += flowset_length
            
            # Align to 4-byte boundary
            if offset % 4 != 0:
                offset += 4 - (offset % 4)
    
    def _process_ipfix(self, data: bytes, source_ip: str):
        """Process IPFIX (NetFlow v10) packet"""
        if len(data) < IPFIX_HEADER_SIZE:
            return
        
        version, length, export_time_unix, seq, domain_id = struct.unpack(
            '!HHIII', data[0:IPFIX_HEADER_SIZE]
        )
        
        export_time = datetime.fromtimestamp(export_time_unix, tz=timezone.utc)
        offset = IPFIX_HEADER_SIZE
        
        # Process Sets
        while offset < len(data) - FLOWSET_HEADER_SIZE:
            set_id, set_length = struct.unpack('!HH', data[offset:offset+4])
            
            if set_length < 4:
                break
            
            set_data = data[offset+4:offset+set_length]
            
            if set_id == 2:
                # Template Set
                self._parse_template_flowset(set_data, source_ip, domain_id, is_ipfix=True)
            elif set_id == 3:
                # Options Template Set (skip for now)
                pass
            elif set_id >= 256:
                # Data Set
                self._parse_data_flowset(set_data, source_ip, domain_id, set_id, export_time)
            
            offset += set_length
    
    def _parse_template_flowset(self, data: bytes, source_ip: str, domain_id: int, is_ipfix: bool):
        """Parse template definitions"""
        offset = 0
        
        while offset < len(data) - 4:
            template_id, field_count = struct.unpack('!HH', data[offset:offset+4])
            offset += 4
            
            if template_id < 256:
                break
            
            fields = []
            for _ in range(field_count):
                if offset + 4 > len(data):
                    break
                
                field_id, field_length = struct.unpack('!HH', data[offset:offset+4])
                offset += 4
                
                enterprise_id = None
                
                # Check enterprise bit (high bit of field_id)
                if field_id & 0x8000:
                    field_id &= 0x7FFF  # Clear enterprise bit
                    if offset + 4 <= len(data):
                        enterprise_id = struct.unpack('!I', data[offset:offset+4])[0]
                        offset += 4
                
                fields.append((field_id, field_length, enterprise_id))
            
            self.template_cache.add_template(source_ip, domain_id, template_id, fields)
            self.stats['templates_received'] += 1
    
    def _parse_data_flowset(self, data: bytes, source_ip: str, domain_id: int, 
                            template_id: int, export_time: datetime):
        """Parse data records using cached template"""
        template = self.template_cache.get_template(source_ip, domain_id, template_id)
        
        if not template:
            self.stats['missing_template'] += 1
            logger.debug(f"No template {template_id} from {source_ip}")
            return
        
        # Calculate record length from template
        record_length = sum(f[1] for f in template if f[1] > 0)
        
        # Handle variable-length fields (not fully implemented)
        if record_length == 0:
            logger.warning(f"Variable-length template {template_id} not fully supported")
            return
        
        offset = 0
        flows = []
        
        while offset + record_length <= len(data):
            flow = self._parse_flow_record(data[offset:offset+record_length], template, 
                                           source_ip, export_time)
            if flow:
                flows.append(flow)
            offset += record_length
        
        if flows:
            self.es_writer.write_flows(flows)
            self.stats['flows_processed'] += len(flows)
    
    def _parse_flow_record(self, data: bytes, template: List[Tuple[int, int, Optional[int]]], 
                           source_ip: str, export_time: datetime) -> Optional[Dict[str, Any]]:
        """Parse a single flow record"""
        flow = {
            '@timestamp': export_time.isoformat(),
            'firewall_ip': source_ip,
        }
        
        offset = 0
        for field_id, field_length, enterprise_id in template:
            if offset + field_length > len(data):
                break
            
            field_data = data[offset:offset+field_length]
            offset += field_length
            
            # Look up field definition (always returns a definition, even for unknown fields)
            field_def = get_field_definition(field_id, enterprise_id)
            
            if field_def:
                try:
                    value = field_def.decode(field_data)
                    if value is not None:
                        flow[field_def.name] = value
                except Exception as e:
                    logger.debug(f"Error decoding field {field_id}: {e}")
        
        # Post-processing
        self._enrich_flow(flow)
        
        return flow
    
    def _enrich_flow(self, flow: Dict[str, Any]):
        """Enrich flow with derived fields and identity data"""
        # Add protocol name
        if 'protocol' in flow:
            if isinstance(flow['protocol'], int):
                flow['protocol_name'] = get_protocol_name(flow['protocol'])
            elif isinstance(flow['protocol'], str) and flow['protocol'].isdigit():
                flow['protocol_name'] = get_protocol_name(int(flow['protocol']))
        
        # Decode TCP flags to readable format
        if 'tcp_flags' in flow and isinstance(flow['tcp_flags'], int):
            flow['tcp_flags_str'] = decode_tcp_flags(flow['tcp_flags'])
        
        # Calculate bytes_in from various possible fields
        bytes_in = 0
        for field in ['bytes_in', 'init_bytes_total', 'initiator_octets']:
            if field in flow and flow[field]:
                bytes_in = flow[field]
                break
        flow['bytes_in'] = bytes_in
        
        # Calculate bytes_out from various possible fields
        bytes_out = 0
        for field in ['bytes_out', 'resp_bytes_total', 'responder_octets']:
            if field in flow and flow[field]:
                bytes_out = flow[field]
                break
        flow['bytes_out'] = bytes_out
        
        # Calculate total bytes
        flow['bytes_total'] = bytes_in + bytes_out
        
        # Calculate packets_in from various possible fields
        packets_in = 0
        for field in ['packets_in', 'init_packets_total']:
            if field in flow and flow[field]:
                packets_in = flow[field]
                break
        flow['packets_in'] = packets_in
        
        # Calculate packets_out from various possible fields
        packets_out = 0
        for field in ['packets_out', 'resp_packets_total']:
            if field in flow and flow[field]:
                packets_out = flow[field]
                break
        flow['packets_out'] = packets_out
        
        # Calculate total packets
        flow['packets_total'] = packets_in + packets_out
        
        # Calculate flow duration from various timestamp fields
        if 'flow_start_ms' in flow and 'flow_end_ms' in flow:
            try:
                duration = int(flow['flow_end_ms']) - int(flow['flow_start_ms'])
                flow['flow_duration_ms'] = max(0, duration)
            except (ValueError, TypeError):
                pass
        elif 'flow_start_sec' in flow and 'flow_end_sec' in flow:
            try:
                duration = (int(flow['flow_end_sec']) - int(flow['flow_start_sec'])) * 1000
                flow['flow_duration_ms'] = max(0, duration)
            except (ValueError, TypeError):
                pass
        elif 'flow_start' in flow and 'flow_end' in flow:
            try:
                duration = (int(flow['flow_end']) - int(flow['flow_start'])) * 1000
                flow['flow_duration_ms'] = max(0, duration)
            except (ValueError, TypeError):
                pass
        elif 'first_switched' in flow and 'last_switched' in flow:
            try:
                duration = int(flow['last_switched']) - int(flow['first_switched'])
                flow['flow_duration_ms'] = max(0, duration)
            except (ValueError, TypeError):
                pass
        elif 'flow_duration' in flow:
            flow['flow_duration_ms'] = flow['flow_duration']
        
        # Convert IP integer fields to dotted notation if present
        if 'src_ip_int' in flow and 'src_ip' not in flow:
            try:
                ip_int = int(flow['src_ip_int'])
                flow['src_ip'] = f"{(ip_int >> 24) & 0xFF}.{(ip_int >> 16) & 0xFF}.{(ip_int >> 8) & 0xFF}.{ip_int & 0xFF}"
            except (ValueError, TypeError):
                pass
        
        if 'dst_ip_int' in flow and 'dst_ip' not in flow:
            try:
                ip_int = int(flow['dst_ip_int'])
                flow['dst_ip'] = f"{(ip_int >> 24) & 0xFF}.{(ip_int >> 16) & 0xFF}.{(ip_int >> 8) & 0xFF}.{ip_int & 0xFF}"
            except (ValueError, TypeError):
                pass
        
        # Enrich with identity data from source IP
        if 'src_ip' in flow:
            identity = self.enricher.lookup(flow['src_ip'])
            if identity:
                flow['src_user_id'] = identity.get('user_id')
                flow['src_user_name'] = identity.get('user_name')
                flow['src_department'] = identity.get('department')
                flow['src_location'] = identity.get('location')
                # Also set generic user fields for backward compatibility
                if not flow.get('user_id'):
                    flow['user_id'] = identity.get('user_id')
                if not flow.get('user_name'):
                    flow['user_name'] = identity.get('user_name')
        
        # Enrich with identity data from destination IP
        if 'dst_ip' in flow:
            identity = self.enricher.lookup(flow['dst_ip'])
            if identity:
                flow['dst_user_id'] = identity.get('user_id')
                flow['dst_user_name'] = identity.get('user_name')
                flow['dst_department'] = identity.get('department')
                flow['dst_location'] = identity.get('location')
    
    def _report_stats(self):
        """Periodically log collection statistics"""
        import time
        while self.running:
            time.sleep(60)
            logger.info(
                f"Stats: packets={self.stats['packets_received']}, "
                f"flows={self.stats['flows_processed']}, "
                f"templates={self.stats['templates_received']}, "
                f"errors={self.stats['errors']}"
            )
    
    def stop(self):
        """Stop the collector"""
        self.running = False
        self.es_writer.flush()

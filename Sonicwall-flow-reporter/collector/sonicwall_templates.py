"""
SonicWall IPFIX Template Definitions

SonicWall uses NetFlow v9 / IPFIX with enterprise-specific fields.
This module defines the field mappings for SonicWall IPFIX exports.

Reference: SonicWall NetFlow/IPFIX documentation
Enterprise ID: 8741 (SonicWall)
"""

from enum import IntEnum
from dataclasses import dataclass
from typing import Dict, Optional, Callable
import struct
import socket

# ============================================================================
# Standard IPFIX Information Elements (IANA)
# ============================================================================

class IPFIXFieldType(IntEnum):
    """Standard IPFIX field types from IANA registry"""
    # Flow identifiers
    OCTET_DELTA_COUNT = 1
    PACKET_DELTA_COUNT = 2
    PROTOCOL_IDENTIFIER = 4
    IP_CLASS_OF_SERVICE = 5
    TCP_CONTROL_BITS = 6
    SOURCE_TRANSPORT_PORT = 7
    SOURCE_IPV4_ADDRESS = 8
    SOURCE_IPV4_PREFIX_LENGTH = 9
    INPUT_SNMP = 10
    DESTINATION_TRANSPORT_PORT = 11
    DESTINATION_IPV4_ADDRESS = 12
    DESTINATION_IPV4_PREFIX_LENGTH = 13
    OUTPUT_SNMP = 14
    IPV4_NEXT_HOP_ADDRESS = 15
    SOURCE_AS = 16
    DESTINATION_AS = 17
    
    # Timestamps
    FLOW_START_SYS_UP_TIME = 22
    FLOW_END_SYS_UP_TIME = 23
    FLOW_START_MILLISECONDS = 152
    FLOW_END_MILLISECONDS = 153
    FLOW_START_SECONDS = 150
    FLOW_END_SECONDS = 151
    
    # Bytes/Packets
    IN_BYTES = 1
    IN_PKTS = 2
    OUT_BYTES = 23  # postOctetDeltaCount
    OUT_PKTS = 24   # postPacketDeltaCount
    
    # Interface
    INGRESS_INTERFACE = 10
    EGRESS_INTERFACE = 14
    
    # IPv6
    SOURCE_IPV6_ADDRESS = 27
    DESTINATION_IPV6_ADDRESS = 28
    
    # NAT
    POST_NAT_SOURCE_IPV4_ADDRESS = 225
    POST_NAT_DESTINATION_IPV4_ADDRESS = 226
    POST_NAPT_SOURCE_TRANSPORT_PORT = 227
    POST_NAPT_DESTINATION_TRANSPORT_PORT = 228
    
    # Flow direction
    FLOW_DIRECTION = 61


# ============================================================================
# SonicWall Enterprise Fields (Enterprise ID: 8741)
# ============================================================================

class SonicWallFieldType(IntEnum):
    """SonicWall enterprise-specific IPFIX fields"""
    # Application identification
    SW_APPLICATION_ID = 1
    SW_APPLICATION_NAME = 2
    SW_APPLICATION_CATEGORY = 3
    
    # User identification
    SW_USER_NAME = 10
    SW_USER_DOMAIN = 11
    SW_USER_GROUP = 12
    
    # Security
    SW_RULE_ID = 20
    SW_RULE_NAME = 21
    SW_ZONE_SOURCE = 22
    SW_ZONE_DESTINATION = 23
    
    # Connection details
    SW_CONNECTION_ID = 30
    SW_SESSION_ID = 31
    
    # Threat information
    SW_THREAT_NAME = 40
    SW_THREAT_CATEGORY = 41
    SW_THREAT_SEVERITY = 42
    
    # URL/Content
    SW_URL_HOST = 50
    SW_URL_PATH = 51
    SW_CONTENT_TYPE = 52
    
    # Interface names
    SW_INTERFACE_IN_NAME = 60
    SW_INTERFACE_OUT_NAME = 61


# ============================================================================
# Protocol Mappings
# ============================================================================

PROTOCOL_NAMES = {
    1: 'ICMP',
    6: 'TCP',
    17: 'UDP',
    47: 'GRE',
    50: 'ESP',
    51: 'AH',
    58: 'ICMPv6',
    89: 'OSPF',
    132: 'SCTP',
}

# ============================================================================
# Field Decoders
# ============================================================================

def decode_ipv4(data: bytes) -> str:
    """Decode 4 bytes to IPv4 address string"""
    return socket.inet_ntoa(data)

def decode_ipv6(data: bytes) -> str:
    """Decode 16 bytes to IPv6 address string"""
    return socket.inet_ntop(socket.AF_INET6, data)

def decode_uint8(data: bytes) -> int:
    return struct.unpack('!B', data)[0]

def decode_uint16(data: bytes) -> int:
    return struct.unpack('!H', data)[0]

def decode_uint32(data: bytes) -> int:
    return struct.unpack('!I', data)[0]

def decode_uint64(data: bytes) -> int:
    return struct.unpack('!Q', data)[0]

def decode_string(data: bytes) -> str:
    """Decode null-terminated or fixed-length string"""
    return data.rstrip(b'\x00').decode('utf-8', errors='replace')

def decode_mac(data: bytes) -> str:
    """Decode 6 bytes to MAC address string"""
    return ':'.join(f'{b:02x}' for b in data)


@dataclass
class FieldDefinition:
    """Definition for an IPFIX field"""
    name: str
    length: int  # 0 = variable length
    decoder: Callable[[bytes], any]
    enterprise_id: Optional[int] = None


# ============================================================================
# Complete Field Registry
# ============================================================================

FIELD_REGISTRY: Dict[tuple, FieldDefinition] = {
    # Standard IANA fields (enterprise_id = None or 0)
    (8, None): FieldDefinition('src_ip', 4, decode_ipv4),
    (12, None): FieldDefinition('dst_ip', 4, decode_ipv4),
    (27, None): FieldDefinition('src_ip', 16, decode_ipv6),
    (28, None): FieldDefinition('dst_ip', 16, decode_ipv6),
    (7, None): FieldDefinition('src_port', 2, decode_uint16),
    (11, None): FieldDefinition('dst_port', 2, decode_uint16),
    (4, None): FieldDefinition('protocol', 1, decode_uint8),
    (1, None): FieldDefinition('bytes_in', 4, decode_uint32),
    (2, None): FieldDefinition('packets_in', 4, decode_uint32),
    (23, None): FieldDefinition('bytes_out', 4, decode_uint32),
    (24, None): FieldDefinition('packets_out', 4, decode_uint32),
    (10, None): FieldDefinition('interface_in', 4, decode_uint32),
    (14, None): FieldDefinition('interface_out', 4, decode_uint32),
    (6, None): FieldDefinition('tcp_flags', 1, decode_uint8),
    (61, None): FieldDefinition('direction', 1, decode_uint8),
    (152, None): FieldDefinition('flow_start', 8, decode_uint64),
    (153, None): FieldDefinition('flow_end', 8, decode_uint64),
    (150, None): FieldDefinition('flow_start', 4, decode_uint32),
    (151, None): FieldDefinition('flow_end', 4, decode_uint32),
    (225, None): FieldDefinition('nat_src_ip', 4, decode_ipv4),
    (226, None): FieldDefinition('nat_dst_ip', 4, decode_ipv4),
    (227, None): FieldDefinition('nat_src_port', 2, decode_uint16),
    (228, None): FieldDefinition('nat_dst_port', 2, decode_uint16),
    
    # SonicWall enterprise fields (enterprise_id = 8741)
    (1, 8741): FieldDefinition('application_id', 4, decode_uint32),
    (2, 8741): FieldDefinition('application_name', 0, decode_string),
    (3, 8741): FieldDefinition('application_category', 0, decode_string),
    (10, 8741): FieldDefinition('user_name', 0, decode_string),
    (11, 8741): FieldDefinition('user_domain', 0, decode_string),
    (12, 8741): FieldDefinition('user_group', 0, decode_string),
    (20, 8741): FieldDefinition('rule_id', 4, decode_uint32),
    (21, 8741): FieldDefinition('rule_name', 0, decode_string),
    (22, 8741): FieldDefinition('zone_src', 0, decode_string),
    (23, 8741): FieldDefinition('zone_dst', 0, decode_string),
    (60, 8741): FieldDefinition('interface_in_name', 0, decode_string),
    (61, 8741): FieldDefinition('interface_out_name', 0, decode_string),
}


def get_field_definition(field_id: int, enterprise_id: Optional[int] = None) -> Optional[FieldDefinition]:
    """Look up field definition by ID and enterprise ID"""
    # Try enterprise-specific first
    if enterprise_id:
        key = (field_id, enterprise_id)
        if key in FIELD_REGISTRY:
            return FIELD_REGISTRY[key]
    
    # Fall back to standard fields
    key = (field_id, None)
    return FIELD_REGISTRY.get(key)


def get_protocol_name(protocol: int) -> str:
    """Get human-readable protocol name"""
    return PROTOCOL_NAMES.get(protocol, f'PROTO_{protocol}')

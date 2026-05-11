"""
IPFIX/NetFlow Field Definitions - CORRECTED based on packet capture analysis

Comprehensive support for:
- Standard IPFIX Information Elements (IANA registry)
- NetFlow v9 fields
- SonicWall enterprise fields (Enterprise ID: 8741) - CORRECTED MAPPINGS

CRITICAL FINDINGS FROM PACKET ANALYSIS (January 2026):
=======================================================
1. Field 5 = INTERNAL SOURCE IP (pre-NAT) - The REAL client IP!
2. Field 6 = Destination IP
3. Field 7 = NAT'd source IP (WAN IP)
4. Field 10 = User Object ID (uint32), NOT a string
5. Field 11 = Source port (uint16), NOT user_domain
6. Field 12 = Destination port (uint16), NOT user_group
7. Field 18 = Application short code (4-char ASCII like "isl3")
8. Fields 1-4 = Zone IDs and MAC addresses

Reference:
- IANA IPFIX Registry: https://www.iana.org/assignments/ipfix/ipfix.xhtml
- SonicWall packet capture analysis
"""

from dataclasses import dataclass
from typing import Dict, Optional, Callable, Any
import struct
import socket
import logging

logger = logging.getLogger('swfr.templates')


# ============================================================================
# Field Decoders
# ============================================================================

def decode_ipv4(data: bytes) -> str:
    """Decode 4 bytes to IPv4 address string"""
    if len(data) != 4:
        return None
    return socket.inet_ntoa(data)

def decode_ipv6(data: bytes) -> str:
    """Decode 16 bytes to IPv6 address string"""
    if len(data) != 16:
        return None
    return socket.inet_ntop(socket.AF_INET6, data)

def decode_ip_auto(data: bytes) -> str:
    """Auto-detect IPv4 or IPv6 based on length"""
    if len(data) == 4:
        return decode_ipv4(data)
    elif len(data) == 16:
        return decode_ipv6(data)
    return data.hex()

def decode_uint8(data: bytes) -> int:
    if len(data) < 1:
        return 0
    return data[0]

def decode_uint16(data: bytes) -> int:
    if len(data) < 2:
        return int.from_bytes(data, 'big')
    return struct.unpack('!H', data[:2])[0]

def decode_uint32(data: bytes) -> int:
    if len(data) < 4:
        return int.from_bytes(data, 'big')
    return struct.unpack('!I', data[:4])[0]

def decode_uint64(data: bytes) -> int:
    if len(data) < 8:
        return int.from_bytes(data, 'big')
    return struct.unpack('!Q', data[:8])[0]

def decode_int8(data: bytes) -> int:
    if len(data) < 1:
        return 0
    return struct.unpack('!b', data[:1])[0]

def decode_int16(data: bytes) -> int:
    if len(data) < 2:
        return int.from_bytes(data, 'big', signed=True)
    return struct.unpack('!h', data[:2])[0]

def decode_int32(data: bytes) -> int:
    if len(data) < 4:
        return int.from_bytes(data, 'big', signed=True)
    return struct.unpack('!i', data[:4])[0]

def decode_int64(data: bytes) -> int:
    if len(data) < 8:
        return int.from_bytes(data, 'big', signed=True)
    return struct.unpack('!q', data[:8])[0]

def decode_float32(data: bytes) -> float:
    if len(data) < 4:
        return 0.0
    return struct.unpack('!f', data[:4])[0]

def decode_float64(data: bytes) -> float:
    if len(data) < 8:
        return 0.0
    return struct.unpack('!d', data[:8])[0]

def decode_mac(data: bytes) -> str:
    """Decode 6 bytes to MAC address string"""
    if len(data) != 6:
        return data.hex()
    return ':'.join(f'{b:02x}' for b in data)

def decode_string(data: bytes) -> str:
    """Decode bytes to UTF-8 string, stripping nulls"""
    try:
        return data.rstrip(b'\x00').decode('utf-8', errors='replace').strip()
    except:
        return data.hex()

def decode_ascii(data: bytes) -> str:
    """Decode bytes as ASCII, keeping only printable chars"""
    try:
        stripped = data.rstrip(b'\x00')
        # Check if all printable ASCII
        if stripped and all(32 <= b < 127 for b in stripped):
            return stripped.decode('ascii')
        # If not printable, return hex
        return data.hex() if data else ''
    except:
        return data.hex()

def decode_string_or_id(data: bytes) -> str:
    """Decode as string if printable ASCII, otherwise as numeric ID"""
    try:
        stripped = data.rstrip(b'\x00')
        # Check if all printable ASCII
        if stripped and all(32 <= b < 127 for b in stripped):
            return stripped.decode('ascii')
    except:
        pass
    # Return as numeric ID
    if len(data) <= 8:
        return str(int.from_bytes(data, 'big'))
    return data.hex()

def decode_boolean(data: bytes) -> bool:
    """Decode as boolean"""
    return bool(data[0]) if data else False

def decode_hex(data: bytes) -> str:
    """Return raw hex string"""
    return data.hex()

def decode_timestamp(data: bytes) -> int:
    """Decode timestamp (seconds since epoch)"""
    if len(data) >= 8:
        return struct.unpack('!Q', data[:8])[0]
    elif len(data) >= 4:
        return struct.unpack('!I', data[:4])[0]
    return int.from_bytes(data, 'big')


# ============================================================================
# Field Definition
# ============================================================================

@dataclass
class FieldDefinition:
    """Definition for an IPFIX field"""
    name: str
    decoder: Callable[[bytes], Any]
    description: str = ""


# ============================================================================
# IANA Standard IPFIX Information Elements
# ============================================================================

IANA_FIELDS: Dict[int, FieldDefinition] = {
    # Basic flow identification
    1: FieldDefinition('octetDeltaCount', decode_uint64, 'Octet delta count'),
    2: FieldDefinition('packetDeltaCount', decode_uint64, 'Packet delta count'),
    3: FieldDefinition('deltaFlowCount', decode_uint64, 'Delta flow count'),
    4: FieldDefinition('protocolIdentifier', decode_uint8, 'Protocol identifier'),
    5: FieldDefinition('ipClassOfService', decode_uint8, 'IP class of service'),
    6: FieldDefinition('tcpControlBits', decode_uint16, 'TCP control bits'),
    7: FieldDefinition('sourceTransportPort', decode_uint16, 'Source port'),
    8: FieldDefinition('sourceIPv4Address', decode_ipv4, 'Source IPv4 address'),
    9: FieldDefinition('sourceIPv4PrefixLength', decode_uint8, 'Source IPv4 prefix length'),
    10: FieldDefinition('ingressInterface', decode_uint32, 'Ingress interface'),
    11: FieldDefinition('destinationTransportPort', decode_uint16, 'Destination port'),
    12: FieldDefinition('destinationIPv4Address', decode_ipv4, 'Destination IPv4 address'),
    13: FieldDefinition('destinationIPv4PrefixLength', decode_uint8, 'Destination IPv4 prefix length'),
    14: FieldDefinition('egressInterface', decode_uint32, 'Egress interface'),
    15: FieldDefinition('ipNextHopIPv4Address', decode_ipv4, 'Next hop IPv4'),
    16: FieldDefinition('bgpSourceAsNumber', decode_uint32, 'BGP source AS'),
    17: FieldDefinition('bgpDestinationAsNumber', decode_uint32, 'BGP destination AS'),
    18: FieldDefinition('bgpNextHopIPv4Address', decode_ipv4, 'BGP next hop IPv4'),
    21: FieldDefinition('flowEndSysUpTime', decode_uint32, 'Flow end sys uptime'),
    22: FieldDefinition('flowStartSysUpTime', decode_uint32, 'Flow start sys uptime'),
    27: FieldDefinition('sourceIPv6Address', decode_ipv6, 'Source IPv6 address'),
    28: FieldDefinition('destinationIPv6Address', decode_ipv6, 'Destination IPv6 address'),
    56: FieldDefinition('sourceMacAddress', decode_mac, 'Source MAC address'),
    58: FieldDefinition('vlanId', decode_uint16, 'VLAN ID'),
    60: FieldDefinition('ipVersion', decode_uint8, 'IP version'),
    61: FieldDefinition('flowDirection', decode_uint8, 'Flow direction'),
    80: FieldDefinition('destinationMacAddress', decode_mac, 'Destination MAC'),
    82: FieldDefinition('interfaceName', decode_string, 'Interface name'),
    83: FieldDefinition('interfaceDescription', decode_string, 'Interface description'),
    
    # Timestamps
    150: FieldDefinition('flowStartSeconds', decode_timestamp, 'Flow start seconds'),
    151: FieldDefinition('flowEndSeconds', decode_timestamp, 'Flow end seconds'),
    152: FieldDefinition('flowStartMilliseconds', decode_uint64, 'Flow start milliseconds'),
    153: FieldDefinition('flowEndMilliseconds', decode_uint64, 'Flow end milliseconds'),
    161: FieldDefinition('flowDurationMilliseconds', decode_uint32, 'Flow duration milliseconds'),
    
    # Counters
    85: FieldDefinition('octetTotalCount', decode_uint64, 'Octet total count'),
    86: FieldDefinition('packetTotalCount', decode_uint64, 'Packet total count'),
    
    # Flags
    136: FieldDefinition('flowEndReason', decode_uint8, 'Flow end reason'),
    
    # NAT
    225: FieldDefinition('postNATSourceIPv4Address', decode_ipv4, 'Post NAT source IPv4'),
    226: FieldDefinition('postNATDestinationIPv4Address', decode_ipv4, 'Post NAT destination IPv4'),
    227: FieldDefinition('postNAPTSourceTransportPort', decode_uint16, 'Post NAPT source port'),
    228: FieldDefinition('postNAPTDestinationTransportPort', decode_uint16, 'Post NAPT destination port'),
}


# ============================================================================
# SonicWall Enterprise Fields - CORRECTED MAPPINGS
# ============================================================================

SONICWALL_ENTERPRISE_ID = 8741

SONICWALL_FIELDS: Dict[int, FieldDefinition] = {
    # Zone and Interface identifiers (4 bytes ASCII)
    1: FieldDefinition('zone_id_src', decode_ascii, 'Source zone ID (ASCII code like "isl3")'),
    2: FieldDefinition('interface_id', decode_uint32, 'Interface ID'),
    
    # MAC addresses (6 bytes each)
    3: FieldDefinition('src_mac', decode_mac, 'Source MAC address'),
    4: FieldDefinition('dst_mac', decode_mac, 'Destination MAC address'),
    
    # THE CRITICAL FIELD - Original internal source IP (pre-NAT)
    5: FieldDefinition('internal_src_ip', decode_ipv4, 'Original internal source IP (pre-NAT client IP)'),
    
    # Destination and NAT'd source
    6: FieldDefinition('dst_ip', decode_ipv4, 'Destination IPv4 address'),
    7: FieldDefinition('nat_src_ip', decode_ipv4, 'NAT source IP (WAN IP after NAT)'),
    
    # Flow ID parts (not ports in this context)
    8: FieldDefinition('flow_id_high', decode_uint32, 'Flow ID high bits'),
    9: FieldDefinition('flow_id_low', decode_uint32, 'Flow ID low bits'),
    
    # User Object ID - NOT a string username!
    10: FieldDefinition('user_object_id', decode_uint32, 'User object ID (reference to firewall user database)'),
    
    # Ports (CORRECTED - these ARE the ports!)
    11: FieldDefinition('src_port', decode_uint16, 'Source port'),
    12: FieldDefinition('dst_port', decode_uint16, 'Destination port'),
    
    # Packet and byte counters
    13: FieldDefinition('init_packets', decode_uint32, 'Initiator packet count'),
    14: FieldDefinition('init_bytes', decode_uint32, 'Initiator byte count'),
    15: FieldDefinition('resp_packets', decode_uint32, 'Responder packet count'),
    16: FieldDefinition('resp_bytes', decode_uint32, 'Responder byte count'),
    
    # Destination zone
    17: FieldDefinition('zone_id_dst', decode_ascii, 'Destination zone ID'),
    
    # Application fields (CORRECTED)
    18: FieldDefinition('app_name', decode_ascii, 'Application short code (4-char like "isl3", "http")'),
    19: FieldDefinition('app_id', decode_uint16, 'Application ID'),
    20: FieldDefinition('app_category_id', decode_uint8, 'Application category ID'),
    
    # Additional application info
    21: FieldDefinition('app_super_category', decode_uint8, 'Application super category'),
    22: FieldDefinition('app_risk', decode_uint32, 'Application risk level'),
    
    # Timestamps
    23: FieldDefinition('flow_timestamp', decode_uint64, 'Flow timestamp'),
    
    # Counters
    25: FieldDefinition('counter_1', decode_uint32, 'Counter 1'),
    26: FieldDefinition('counter_2', decode_uint32, 'Counter 2'),
    27: FieldDefinition('counter_3', decode_uint32, 'Counter 3'),
    
    # Statistics (fields 111-116)
    111: FieldDefinition('stat_bytes_in', decode_uint32, 'Bytes in statistic'),
    112: FieldDefinition('stat_bytes_out', decode_uint32, 'Bytes out statistic'),
    113: FieldDefinition('stat_packets_in', decode_uint32, 'Packets in statistic'),
    114: FieldDefinition('stat_packets_out', decode_uint32, 'Packets out statistic'),
    115: FieldDefinition('stat_5', decode_uint32, 'Statistic 5'),
    116: FieldDefinition('stat_6', decode_uint32, 'Statistic 6'),
    
    # Extended fields
    167: FieldDefinition('extended_bytes_1', decode_uint64, 'Extended bytes counter 1'),
    168: FieldDefinition('extended_bytes_2', decode_uint64, 'Extended bytes counter 2'),
    169: FieldDefinition('session_count', decode_uint32, 'Session count'),
    170: FieldDefinition('total_bytes', decode_uint32, 'Total bytes transferred'),
    171: FieldDefinition('dropped_packets', decode_uint32, 'Dropped packets'),
    172: FieldDefinition('dropped_bytes', decode_uint32, 'Dropped bytes'),
    173: FieldDefinition('app_sub_category', decode_uint8, 'Application sub-category'),
    
    # Rule/Policy info
    191: FieldDefinition('rule_info', decode_uint32, 'Rule/policy information'),
    
    # URL/HTTP fields (Template 262)
    59: FieldDefinition('url_host', decode_string, 'URL hostname/path'),
    60: FieldDefinition('url_length', decode_uint32, 'URL length'),
    123: FieldDefinition('url_session_id_high', decode_uint32, 'URL session ID high'),
    124: FieldDefinition('url_session_zone', decode_ascii, 'URL session zone'),
    
    # Additional templates (195-250 for Template 281 - session data)
    195: FieldDefinition('session_start_time', decode_uint64, 'Session start time'),
    196: FieldDefinition('session_end_time', decode_uint64, 'Session end time'),
    197: FieldDefinition('session_protocol', decode_uint16, 'Session protocol'),
    198: FieldDefinition('session_ip_version', decode_uint8, 'Session IP version'),
    199: FieldDefinition('session_direction', decode_uint8, 'Session direction'),
    200: FieldDefinition('session_src_ip', decode_ip_auto, 'Session source IP'),
    201: FieldDefinition('session_dst_ip', decode_ip_auto, 'Session destination IP'),
    202: FieldDefinition('session_nat_src_ip', decode_ip_auto, 'Session NAT source IP'),
    203: FieldDefinition('session_nat_dst_ip', decode_ip_auto, 'Session NAT destination IP'),
    204: FieldDefinition('session_src_port', decode_uint16, 'Session source port'),
    205: FieldDefinition('session_dst_port', decode_uint16, 'Session destination port'),
    206: FieldDefinition('session_nat_src_port', decode_uint16, 'Session NAT source port'),
    207: FieldDefinition('session_nat_dst_port', decode_uint16, 'Session NAT destination port'),
    208: FieldDefinition('session_src_mac', decode_mac, 'Session source MAC'),
    209: FieldDefinition('session_dst_mac', decode_mac, 'Session destination MAC'),
}


# Application category mapping (SonicWall)
APP_CATEGORY_MAP = {
    0: 'Unknown',
    1: 'Business',
    2: 'Communication',
    3: 'Email',
    4: 'File Transfer',
    5: 'Games',
    6: 'General Internet',
    7: 'Malicious',
    8: 'Media',
    9: 'Network Management',
    10: 'P2P',
    11: 'Productivity',
    12: 'Proxy',
    13: 'Remote Access',
    14: 'Security',
    15: 'Social Networking',
    16: 'Storage/Backup',
    17: 'Streaming',
    18: 'Update',
    19: 'VoIP',
    20: 'Web',
}


# Known application codes
APP_CODE_MAP = {
    'isl3': 'SSL/TLS',
    'http': 'HTTP',
    'dns ': 'DNS',
    'smtp': 'SMTP',
    'imap': 'IMAP',
    'ssh ': 'SSH',
    'rdp ': 'RDP',
    'ntp ': 'NTP',
    'quic': 'QUIC',
    'h2  ': 'HTTP/2',
}


# ============================================================================
# Template Management
# ============================================================================

class TemplateStore:
    """Store and manage IPFIX templates"""
    
    def __init__(self):
        self.templates: Dict[tuple, list] = {}  # (domain_id, template_id) -> fields
        
    def add_template(self, domain_id: int, template_id: int, fields: list):
        """Add or update a template"""
        key = (domain_id, template_id)
        self.templates[key] = fields
        logger.debug(f"Stored template {template_id} for domain {domain_id} with {len(fields)} fields")
        
    def get_template(self, domain_id: int, template_id: int) -> Optional[list]:
        """Get a template by domain and template ID"""
        return self.templates.get((domain_id, template_id))
        
    def has_template(self, domain_id: int, template_id: int) -> bool:
        """Check if template exists"""
        return (domain_id, template_id) in self.templates


def get_field_definition(field_id: int, enterprise_id: Optional[int] = None) -> FieldDefinition:
    """Get field definition by ID and enterprise ID"""
    if enterprise_id == SONICWALL_ENTERPRISE_ID:
        if field_id in SONICWALL_FIELDS:
            return SONICWALL_FIELDS[field_id]
        # Return generic definition for unknown SonicWall fields
        return FieldDefinition(f'sw_field_{field_id}', decode_hex, f'Unknown SonicWall field {field_id}')
    
    if enterprise_id is not None:
        # Unknown enterprise
        return FieldDefinition(f'enterprise_{enterprise_id}_field_{field_id}', decode_hex, 
                              f'Enterprise {enterprise_id} field {field_id}')
    
    # Standard IANA field
    if field_id in IANA_FIELDS:
        return IANA_FIELDS[field_id]
        
    return FieldDefinition(f'field_{field_id}', decode_hex, f'Unknown field {field_id}')


def decode_field(field_id: int, data: bytes, enterprise_id: Optional[int] = None) -> tuple:
    """Decode a field and return (name, value)"""
    field_def = get_field_definition(field_id, enterprise_id)
    try:
        value = field_def.decoder(data)
        return (field_def.name, value)
    except Exception as e:
        logger.warning(f"Error decoding field {field_id}: {e}")
        return (field_def.name, data.hex())


# ============================================================================
# Protocol Name Mapping
# ============================================================================

PROTOCOL_NAMES = {
    1: 'ICMP',
    2: 'IGMP',
    6: 'TCP',
    17: 'UDP',
    41: 'IPv6',
    47: 'GRE',
    50: 'ESP',
    51: 'AH',
    58: 'ICMPv6',
    89: 'OSPF',
    132: 'SCTP',
}


def get_protocol_name(protocol_num: int) -> str:
    """Get protocol name from number"""
    return PROTOCOL_NAMES.get(protocol_num, f'PROTO_{protocol_num}')


# ============================================================================
# TCP Flag Mapping
# ============================================================================

TCP_FLAGS = {
    0x01: 'FIN',
    0x02: 'SYN',
    0x04: 'RST',
    0x08: 'PSH',
    0x10: 'ACK',
    0x20: 'URG',
    0x40: 'ECE',
    0x80: 'CWR',
}


def decode_tcp_flags(flags: int) -> str:
    """Convert TCP flags to string representation"""
    if flags == 0:
        return 'NONE'
    parts = []
    for bit, name in TCP_FLAGS.items():
        if flags & bit:
            parts.append(name)
    return ','.join(parts) if parts else 'NONE'

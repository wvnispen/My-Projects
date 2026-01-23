"""
IPFIX/NetFlow Field Definitions

Comprehensive support for:
- Standard IPFIX Information Elements (IANA registry)
- NetFlow v9 fields
- SonicWall enterprise fields (Enterprise ID: 8741)
- Cisco enterprise fields (Enterprise ID: 9)
- Generic handling of unknown vendor extensions

Reference:
- IANA IPFIX Registry: https://www.iana.org/assignments/ipfix/ipfix.xhtml
- SonicWall NetFlow/IPFIX documentation
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

def decode_string(data: bytes) -> str:
    """Decode null-terminated or fixed-length string"""
    return data.rstrip(b'\x00').decode('utf-8', errors='replace').strip()

def decode_mac(data: bytes) -> str:
    """Decode 6 bytes to MAC address string"""
    if len(data) != 6:
        return data.hex()
    return ':'.join(f'{b:02x}' for b in data)

def decode_hex(data: bytes) -> str:
    """Decode raw bytes to hex string"""
    return data.hex()

def decode_boolean(data: bytes) -> bool:
    """Decode single byte to boolean"""
    return data[0] != 0 if data else False

def decode_float32(data: bytes) -> float:
    """Decode 4 bytes to float"""
    if len(data) < 4:
        return 0.0
    return struct.unpack('!f', data[:4])[0]

def decode_float64(data: bytes) -> float:
    """Decode 8 bytes to double"""
    if len(data) < 8:
        return 0.0
    return struct.unpack('!d', data[:8])[0]

def decode_datetime_seconds(data: bytes) -> int:
    """Decode seconds since epoch"""
    return decode_uint32(data)

def decode_datetime_milliseconds(data: bytes) -> int:
    """Decode milliseconds since epoch"""
    return decode_uint64(data)

def decode_bytes_auto(data: bytes) -> Any:
    """Auto-decode based on length"""
    if len(data) == 1:
        return decode_uint8(data)
    elif len(data) == 2:
        return decode_uint16(data)
    elif len(data) == 4:
        return decode_uint32(data)
    elif len(data) == 8:
        return decode_uint64(data)
    return data.hex()


# ============================================================================
# Protocol Mappings
# ============================================================================

PROTOCOL_NAMES = {
    0: 'HOPOPT',
    1: 'ICMP',
    2: 'IGMP',
    4: 'IPv4',
    6: 'TCP',
    8: 'EGP',
    17: 'UDP',
    27: 'RDP',
    41: 'IPv6',
    43: 'IPv6-Route',
    44: 'IPv6-Frag',
    46: 'RSVP',
    47: 'GRE',
    50: 'ESP',
    51: 'AH',
    58: 'ICMPv6',
    59: 'IPv6-NoNxt',
    60: 'IPv6-Opts',
    88: 'EIGRP',
    89: 'OSPF',
    103: 'PIM',
    112: 'VRRP',
    115: 'L2TP',
    132: 'SCTP',
    136: 'UDPLite',
}

# TCP Flags
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


@dataclass
class FieldDefinition:
    """Definition for an IPFIX field"""
    name: str                           # Output field name
    decoder: Callable[[bytes], Any]     # Decoder function
    description: str = ""               # Human-readable description
    
    def decode(self, data: bytes) -> Any:
        """Decode field data with error handling"""
        try:
            return self.decoder(data)
        except Exception as e:
            logger.debug(f"Error decoding {self.name}: {e}")
            return data.hex() if data else None


# ============================================================================
# Standard IPFIX Information Elements (IANA)
# Key: field_id, Value: FieldDefinition
# ============================================================================

STANDARD_FIELDS: Dict[int, FieldDefinition] = {
    # Octet counts
    1: FieldDefinition('bytes_in', decode_bytes_auto, 'Incoming byte count'),
    2: FieldDefinition('packets_in', decode_bytes_auto, 'Incoming packet count'),
    
    # Protocol and ToS
    4: FieldDefinition('protocol', decode_uint8, 'IP protocol number'),
    5: FieldDefinition('ip_tos', decode_uint8, 'IP type of service / DSCP'),
    6: FieldDefinition('tcp_flags', decode_uint8, 'TCP control flags'),
    
    # Ports
    7: FieldDefinition('src_port', decode_uint16, 'Source port'),
    11: FieldDefinition('dst_port', decode_uint16, 'Destination port'),
    
    # IPv4 addresses
    8: FieldDefinition('src_ip', decode_ipv4, 'Source IPv4 address'),
    9: FieldDefinition('src_mask', decode_uint8, 'Source prefix length'),
    10: FieldDefinition('interface_in', decode_uint32, 'Input interface index'),
    12: FieldDefinition('dst_ip', decode_ipv4, 'Destination IPv4 address'),
    13: FieldDefinition('dst_mask', decode_uint8, 'Destination prefix length'),
    14: FieldDefinition('interface_out', decode_uint32, 'Output interface index'),
    15: FieldDefinition('next_hop', decode_ipv4, 'Next hop IPv4'),
    
    # AS numbers
    16: FieldDefinition('src_as', decode_bytes_auto, 'Source AS number'),
    17: FieldDefinition('dst_as', decode_bytes_auto, 'Destination AS number'),
    
    # BGP
    18: FieldDefinition('bgp_next_hop', decode_ipv4, 'BGP next hop IPv4'),
    
    # Multicast
    19: FieldDefinition('mul_dst_pkts', decode_bytes_auto, 'Multicast destination packets'),
    20: FieldDefinition('mul_dst_bytes', decode_bytes_auto, 'Multicast destination bytes'),
    
    # Timestamps (system uptime based)
    21: FieldDefinition('last_switched', decode_uint32, 'Last packet system uptime'),
    22: FieldDefinition('first_switched', decode_uint32, 'First packet system uptime'),
    
    # Post-NAT counters
    23: FieldDefinition('bytes_out', decode_bytes_auto, 'Outgoing byte count'),
    24: FieldDefinition('packets_out', decode_bytes_auto, 'Outgoing packet count'),
    
    # Min/max packet/header length
    25: FieldDefinition('min_pkt_len', decode_uint16, 'Minimum packet length'),
    26: FieldDefinition('max_pkt_len', decode_uint16, 'Maximum packet length'),
    
    # IPv6 addresses
    27: FieldDefinition('src_ip', decode_ipv6, 'Source IPv6 address'),
    28: FieldDefinition('dst_ip', decode_ipv6, 'Destination IPv6 address'),
    29: FieldDefinition('src_mask_v6', decode_uint8, 'Source IPv6 prefix length'),
    30: FieldDefinition('dst_mask_v6', decode_uint8, 'Destination IPv6 prefix length'),
    31: FieldDefinition('ipv6_flow_label', decode_uint32, 'IPv6 flow label'),
    
    # ICMP
    32: FieldDefinition('icmp_type', decode_uint16, 'ICMP type and code'),
    
    # Sampling
    34: FieldDefinition('sampling_interval', decode_uint32, 'Sampling interval'),
    35: FieldDefinition('sampling_algorithm', decode_uint8, 'Sampling algorithm'),
    
    # Flow timing
    36: FieldDefinition('flow_active_timeout', decode_uint16, 'Active flow timeout'),
    37: FieldDefinition('flow_idle_timeout', decode_uint16, 'Idle flow timeout'),
    
    # Engine
    38: FieldDefinition('engine_type', decode_uint8, 'Engine type'),
    39: FieldDefinition('engine_id', decode_uint8, 'Engine ID'),
    
    # Counters
    40: FieldDefinition('total_bytes_exp', decode_bytes_auto, 'Total bytes exported'),
    41: FieldDefinition('total_pkts_exp', decode_bytes_auto, 'Total packets exported'),
    42: FieldDefinition('total_flows_exp', decode_bytes_auto, 'Total flows exported'),
    
    # MPLS
    46: FieldDefinition('mpls_top_label_type', decode_uint8, 'MPLS top label type'),
    47: FieldDefinition('mpls_top_label_ip', decode_ipv4, 'MPLS top label IP'),
    
    # Sampler
    48: FieldDefinition('sampler_id', decode_uint8, 'Sampler ID'),
    49: FieldDefinition('sampler_mode', decode_uint8, 'Sampler mode'),
    50: FieldDefinition('sampler_interval', decode_uint16, 'Sampler random interval'),
    
    # Min TTL
    52: FieldDefinition('min_ttl', decode_uint8, 'Minimum TTL'),
    53: FieldDefinition('max_ttl', decode_uint8, 'Maximum TTL'),
    54: FieldDefinition('fragment_id', decode_uint32, 'IPv4 fragment ID'),
    
    # DSCP
    55: FieldDefinition('post_ip_dscp', decode_uint8, 'Post DSCP'),
    
    # Replication factor
    56: FieldDefinition('replication_factor', decode_uint32, 'Replication factor'),
    
    # Application info
    57: FieldDefinition('app_desc', decode_string, 'Application description'),
    58: FieldDefinition('app_id', decode_hex, 'Application ID'),
    59: FieldDefinition('app_name', decode_string, 'Application name'),
    
    # Layer 2
    60: FieldDefinition('ip_version', decode_uint8, 'IP version'),
    61: FieldDefinition('direction', decode_uint8, 'Flow direction'),
    62: FieldDefinition('ipv6_next_hop', decode_ipv6, 'IPv6 next hop'),
    63: FieldDefinition('bgp_ipv6_next_hop', decode_ipv6, 'BGP IPv6 next hop'),
    64: FieldDefinition('ipv6_option_headers', decode_uint32, 'IPv6 option headers'),
    
    # MPLS labels
    70: FieldDefinition('mpls_label_1', decode_uint32, 'MPLS label 1'),
    71: FieldDefinition('mpls_label_2', decode_uint32, 'MPLS label 2'),
    72: FieldDefinition('mpls_label_3', decode_uint32, 'MPLS label 3'),
    73: FieldDefinition('mpls_label_4', decode_uint32, 'MPLS label 4'),
    74: FieldDefinition('mpls_label_5', decode_uint32, 'MPLS label 5'),
    75: FieldDefinition('mpls_label_6', decode_uint32, 'MPLS label 6'),
    76: FieldDefinition('mpls_label_7', decode_uint32, 'MPLS label 7'),
    77: FieldDefinition('mpls_label_8', decode_uint32, 'MPLS label 8'),
    78: FieldDefinition('mpls_label_9', decode_uint32, 'MPLS label 9'),
    79: FieldDefinition('mpls_label_10', decode_uint32, 'MPLS label 10'),
    
    # MAC addresses
    80: FieldDefinition('dst_mac', decode_mac, 'Destination MAC address'),
    81: FieldDefinition('src_mac', decode_mac, 'Source MAC address'),
    82: FieldDefinition('if_name', decode_string, 'Interface name'),
    83: FieldDefinition('if_desc', decode_string, 'Interface description'),
    84: FieldDefinition('sampler_name', decode_string, 'Sampler name'),
    
    # Byte counts (64-bit)
    85: FieldDefinition('bytes_in', decode_uint64, 'Octet total count'),
    86: FieldDefinition('packets_in', decode_uint64, 'Packet total count'),
    
    # Fragment offset
    88: FieldDefinition('fragment_offset', decode_uint16, 'Fragment offset'),
    
    # Forwarding status
    89: FieldDefinition('fwd_status', decode_uint8, 'Forwarding status'),
    90: FieldDefinition('mpls_vpn_rd', decode_hex, 'MPLS VPN RD'),
    91: FieldDefinition('mpls_prefix_len', decode_uint8, 'MPLS prefix length'),
    
    # Traffic class
    95: FieldDefinition('app_id', decode_hex, 'Application ID'),
    
    # BGP AS
    128: FieldDefinition('bgp_next_adj_as', decode_uint32, 'BGP next adjacent AS'),
    129: FieldDefinition('bgp_prev_adj_as', decode_uint32, 'BGP previous adjacent AS'),
    
    # Exporter info
    130: FieldDefinition('exporter_ipv4', decode_ipv4, 'Exporter IPv4'),
    131: FieldDefinition('exporter_ipv6', decode_ipv6, 'Exporter IPv6'),
    
    # Dropped counts
    132: FieldDefinition('dropped_bytes', decode_uint64, 'Dropped octet count'),
    133: FieldDefinition('dropped_packets', decode_uint64, 'Dropped packet count'),
    134: FieldDefinition('dropped_byte_total', decode_uint64, 'Dropped octet total'),
    135: FieldDefinition('dropped_packet_total', decode_uint64, 'Dropped packet total'),
    136: FieldDefinition('flow_end_reason', decode_uint8, 'Flow end reason'),
    
    # VRF
    137: FieldDefinition('vrf_id', decode_uint32, 'VRF ID'),
    138: FieldDefinition('vrf_name', decode_string, 'VRF name'),
    
    # Biflow
    139: FieldDefinition('biflow_direction', decode_uint8, 'Biflow direction'),
    
    # Observation domain
    149: FieldDefinition('observation_domain_id', decode_uint32, 'Observation domain ID'),
    
    # Timestamps (absolute)
    150: FieldDefinition('flow_start', decode_uint32, 'Flow start seconds'),
    151: FieldDefinition('flow_end', decode_uint32, 'Flow end seconds'),
    152: FieldDefinition('flow_start_ms', decode_uint64, 'Flow start milliseconds'),
    153: FieldDefinition('flow_end_ms', decode_uint64, 'Flow end milliseconds'),
    154: FieldDefinition('flow_start_us', decode_uint64, 'Flow start microseconds'),
    155: FieldDefinition('flow_end_us', decode_uint64, 'Flow end microseconds'),
    156: FieldDefinition('flow_start_ns', decode_uint64, 'Flow start nanoseconds'),
    157: FieldDefinition('flow_end_ns', decode_uint64, 'Flow end nanoseconds'),
    158: FieldDefinition('flow_start_delta_us', decode_uint32, 'Flow start delta microseconds'),
    159: FieldDefinition('flow_end_delta_us', decode_uint32, 'Flow end delta microseconds'),
    160: FieldDefinition('system_init_ms', decode_uint64, 'System init milliseconds'),
    161: FieldDefinition('flow_duration_ms', decode_uint32, 'Flow duration milliseconds'),
    162: FieldDefinition('flow_duration_us', decode_uint32, 'Flow duration microseconds'),
    
    # Counters
    163: FieldDefinition('observed_flow_total', decode_uint64, 'Observed flow total'),
    164: FieldDefinition('ignored_packet_total', decode_uint64, 'Ignored packet total'),
    165: FieldDefinition('ignored_octet_total', decode_uint64, 'Ignored octet total'),
    166: FieldDefinition('not_sent_flow_total', decode_uint64, 'Not sent flow total'),
    167: FieldDefinition('not_sent_packet_total', decode_uint64, 'Not sent packet total'),
    168: FieldDefinition('not_sent_octet_total', decode_uint64, 'Not sent octet total'),
    
    # Prefix
    169: FieldDefinition('dst_ipv6_prefix', decode_ipv6, 'Destination IPv6 prefix'),
    170: FieldDefinition('src_ipv6_prefix', decode_ipv6, 'Source IPv6 prefix'),
    171: FieldDefinition('post_bytes_total', decode_uint64, 'Post octet total'),
    172: FieldDefinition('post_packets_total', decode_uint64, 'Post packet total'),
    173: FieldDefinition('flow_key_indicator', decode_uint64, 'Flow key indicator'),
    174: FieldDefinition('post_multicast_packet', decode_uint64, 'Post mcast packet'),
    175: FieldDefinition('post_multicast_bytes', decode_uint64, 'Post mcast octets'),
    
    # ICMP (v4/v6)
    176: FieldDefinition('icmp_type_ipv4', decode_uint8, 'ICMP type IPv4'),
    177: FieldDefinition('icmp_code_ipv4', decode_uint8, 'ICMP code IPv4'),
    178: FieldDefinition('icmp_type_ipv6', decode_uint8, 'ICMP type IPv6'),
    179: FieldDefinition('icmp_code_ipv6', decode_uint8, 'ICMP code IPv6'),
    
    # UDP/TCP
    180: FieldDefinition('udp_src_port', decode_uint16, 'UDP source port'),
    181: FieldDefinition('udp_dst_port', decode_uint16, 'UDP destination port'),
    182: FieldDefinition('tcp_src_port', decode_uint16, 'TCP source port'),
    183: FieldDefinition('tcp_dst_port', decode_uint16, 'TCP destination port'),
    184: FieldDefinition('tcp_seq_num', decode_uint32, 'TCP sequence number'),
    185: FieldDefinition('tcp_ack_num', decode_uint32, 'TCP ack number'),
    186: FieldDefinition('tcp_window_size', decode_uint16, 'TCP window size'),
    187: FieldDefinition('tcp_urgent_pointer', decode_uint16, 'TCP urgent pointer'),
    188: FieldDefinition('tcp_header_length', decode_uint8, 'TCP header length'),
    189: FieldDefinition('ip_header_length', decode_uint8, 'IP header length'),
    190: FieldDefinition('ip_total_length', decode_uint16, 'IP total length'),
    
    # More IP fields
    191: FieldDefinition('payload_length_ipv6', decode_uint16, 'IPv6 payload length'),
    192: FieldDefinition('ip_ttl', decode_uint8, 'IP TTL'),
    193: FieldDefinition('next_header_ipv6', decode_uint8, 'IPv6 next header'),
    194: FieldDefinition('mpls_payload_length', decode_uint32, 'MPLS payload length'),
    195: FieldDefinition('ip_dscp', decode_uint8, 'IP DSCP'),
    196: FieldDefinition('ip_precedence', decode_uint8, 'IP precedence'),
    197: FieldDefinition('fragment_flags', decode_uint8, 'Fragment flags'),
    
    # Byte counts
    198: FieldDefinition('bytes_squared', decode_uint64, 'Octet delta squared'),
    199: FieldDefinition('bytes_total_squared', decode_uint64, 'Octet total squared'),
    200: FieldDefinition('mpls_top_label_ttl', decode_uint8, 'MPLS top label TTL'),
    
    # MPLS stack
    201: FieldDefinition('mpls_label_stack_octets', decode_hex, 'MPLS label stack'),
    202: FieldDefinition('mpls_payload_octets', decode_uint32, 'MPLS payload octets'),
    203: FieldDefinition('mpls_top_label_exp', decode_uint8, 'MPLS top label exp'),
    204: FieldDefinition('ip_payload_length', decode_uint32, 'IP payload length'),
    
    # Padding
    210: FieldDefinition('pad_octets', decode_hex, 'Padding octets'),
    213: FieldDefinition('header_length_ipv4', decode_uint8, 'IPv4 header length'),
    214: FieldDefinition('ip_diff_serv_code_point', decode_uint8, 'DSCP'),
    215: FieldDefinition('ip_ecn', decode_uint8, 'ECN'),
    
    # NAT
    225: FieldDefinition('nat_src_ip', decode_ipv4, 'Post-NAT source IPv4'),
    226: FieldDefinition('nat_dst_ip', decode_ipv4, 'Post-NAT destination IPv4'),
    227: FieldDefinition('nat_src_port', decode_uint16, 'Post-NAPT source port'),
    228: FieldDefinition('nat_dst_port', decode_uint16, 'Post-NAPT destination port'),
    229: FieldDefinition('nat_originating_address_realm', decode_uint8, 'NAT address realm'),
    230: FieldDefinition('nat_event', decode_uint8, 'NAT event'),
    
    # Firewall
    231: FieldDefinition('initiator_octets', decode_uint64, 'Initiator octets'),
    232: FieldDefinition('responder_octets', decode_uint64, 'Responder octets'),
    233: FieldDefinition('firewall_event', decode_uint8, 'Firewall event'),
    234: FieldDefinition('ingress_vrf_id', decode_uint32, 'Ingress VRF ID'),
    235: FieldDefinition('egress_vrf_id', decode_uint32, 'Egress VRF ID'),
    236: FieldDefinition('vrf_name', decode_string, 'VRF name'),
    
    # VLAN
    243: FieldDefinition('dot1q_vlan_id', decode_uint16, '802.1Q VLAN ID'),
    244: FieldDefinition('dot1q_priority', decode_uint8, '802.1Q priority'),
    245: FieldDefinition('dot1q_cust_vlan_id', decode_uint16, '802.1Q customer VLAN'),
    246: FieldDefinition('dot1q_cust_priority', decode_uint8, '802.1Q customer priority'),
    
    # Layer 2
    252: FieldDefinition('layer2_segment_id', decode_uint64, 'Layer 2 segment ID'),
    253: FieldDefinition('layer2_octet_delta', decode_uint64, 'Layer 2 octet delta'),
    254: FieldDefinition('layer2_octet_total', decode_uint64, 'Layer 2 octet total'),
    
    # Tunnel
    281: FieldDefinition('tunnel_src_ipv4', decode_ipv4, 'Tunnel source IPv4'),
    282: FieldDefinition('tunnel_dst_ipv4', decode_ipv4, 'Tunnel destination IPv4'),
    289: FieldDefinition('tunnel_src_ipv6', decode_ipv6, 'Tunnel source IPv6'),
    290: FieldDefinition('tunnel_dst_ipv6', decode_ipv6, 'Tunnel destination IPv6'),
    
    # More L2 MAC
    351: FieldDefinition('src_mac', decode_mac, 'Source MAC'),
    352: FieldDefinition('post_dst_mac', decode_mac, 'Post destination MAC'),
    353: FieldDefinition('dst_mac', decode_mac, 'Destination MAC'),
    354: FieldDefinition('post_src_mac', decode_mac, 'Post source MAC'),
    
    # Interface
    365: FieldDefinition('if_name', decode_string, 'Interface name'),
    366: FieldDefinition('if_desc', decode_string, 'Interface description'),
}


# ============================================================================
# SonicWall Enterprise Fields (Enterprise ID: 8741)
# ============================================================================

SONICWALL_ENTERPRISE_ID = 8741

SONICWALL_FIELDS: Dict[int, FieldDefinition] = {
    # Application identification
    1: FieldDefinition('sw_application_id', decode_uint32, 'SonicWall application ID'),
    2: FieldDefinition('sw_application_name', decode_string, 'Application name'),
    3: FieldDefinition('sw_application_category', decode_string, 'Application category'),
    4: FieldDefinition('sw_application_super_category', decode_string, 'Application super category'),
    5: FieldDefinition('sw_application_risk', decode_uint8, 'Application risk level'),
    
    # CORRECTED: Fields 6-9 are IP addresses in SonicWall IPFIX, NOT byte counts!
    # Based on real traffic analysis: field 6 = external destination, field 7 = NAT source
    6: FieldDefinition('dst_ip', decode_ipv4, 'Destination IPv4 address'),
    7: FieldDefinition('src_ip', decode_ipv4, 'Source IPv4 address (NAT)'),
    8: FieldDefinition('dst_port', decode_uint16, 'Destination port'),
    9: FieldDefinition('src_port', decode_uint16, 'Source port'),
    
    # User identification
    10: FieldDefinition('user_name', decode_string, 'User name'),
    11: FieldDefinition('user_domain', decode_string, 'User domain'),
    12: FieldDefinition('user_group', decode_string, 'User group'),
    13: FieldDefinition('user_ip', decode_ipv4, 'User IP address'),
    
    # Connection timing
    14: FieldDefinition('flow_start_ms', decode_uint64, 'Flow start milliseconds'),
    15: FieldDefinition('flow_end_ms', decode_uint64, 'Flow end milliseconds'),
    16: FieldDefinition('flow_duration', decode_uint64, 'Flow duration milliseconds'),
    17: FieldDefinition('conn_start_time', decode_uint64, 'Connection start time'),
    18: FieldDefinition('conn_duration', decode_uint64, 'Connection duration'),
    19: FieldDefinition('idle_timeout', decode_uint32, 'Idle timeout'),
    
    # Security/Rule
    20: FieldDefinition('rule_id', decode_uint32, 'Rule ID'),
    21: FieldDefinition('rule_name', decode_string, 'Rule name'),
    22: FieldDefinition('zone_src', decode_string, 'Source zone'),
    23: FieldDefinition('zone_dst', decode_string, 'Destination zone'),
    24: FieldDefinition('policy_id', decode_uint32, 'Policy ID'),
    25: FieldDefinition('policy_name', decode_string, 'Policy name'),
    26: FieldDefinition('action', decode_string, 'Firewall action'),
    27: FieldDefinition('src_user', decode_string, 'Source user'),
    28: FieldDefinition('dst_user', decode_string, 'Destination user'),
    29: FieldDefinition('interface_in', decode_string, 'Input interface'),
    
    # Connection details
    30: FieldDefinition('connection_id', decode_uint64, 'Connection ID'),
    31: FieldDefinition('session_id', decode_uint64, 'Session ID'),
    32: FieldDefinition('connection_state', decode_uint8, 'Connection state'),
    33: FieldDefinition('connection_flags', decode_uint32, 'Connection flags'),
    
    # Network
    39: FieldDefinition('vlan_id', decode_uint16, 'VLAN ID'),
    
    # Threat information
    40: FieldDefinition('threat_name', decode_string, 'Threat name'),
    41: FieldDefinition('threat_category', decode_string, 'Threat category'),
    42: FieldDefinition('threat_severity', decode_uint8, 'Threat severity'),
    43: FieldDefinition('threat_id', decode_uint32, 'Threat ID'),
    44: FieldDefinition('antivirus_status', decode_uint8, 'Antivirus status'),
    45: FieldDefinition('ips_alert', decode_string, 'IPS alert'),
    46: FieldDefinition('interface_out', decode_string, 'Output interface'),
    47: FieldDefinition('src_port', decode_uint16, 'Source port'),
    48: FieldDefinition('dst_port', decode_uint16, 'Destination port'),
    49: FieldDefinition('protocol', decode_string, 'Protocol name'),
    
    # URL/Content
    50: FieldDefinition('url_host', decode_string, 'URL hostname'),
    51: FieldDefinition('url_path', decode_string, 'URL path'),
    52: FieldDefinition('content_type', decode_string, 'Content type'),
    53: FieldDefinition('referer', decode_string, 'HTTP referer'),
    54: FieldDefinition('user_agent', decode_string, 'HTTP user agent'),
    55: FieldDefinition('http_method', decode_uint8, 'HTTP method'),
    56: FieldDefinition('http_status', decode_string, 'HTTP status'),
    57: FieldDefinition('http_resp_code', decode_uint16, 'HTTP response code'),
    
    # Additional network info
    59: FieldDefinition('dns_query', decode_string, 'DNS query name'),
    
    # Interface names
    60: FieldDefinition('interface_in_name', decode_string, 'Input interface name'),
    61: FieldDefinition('interface_out_name', decode_string, 'Output interface name'),
    62: FieldDefinition('src_zone_id', decode_uint32, 'Source zone ID'),
    63: FieldDefinition('src_zone_name', decode_string, 'Source zone name'),
    64: FieldDefinition('dst_zone_id', decode_uint32, 'Destination zone ID'),
    65: FieldDefinition('dst_zone_type', decode_uint32, 'Destination zone type'),
    66: FieldDefinition('dst_zone_name', decode_string, 'Destination zone name'),
    67: FieldDefinition('nat_type', decode_string, 'NAT type'),
    68: FieldDefinition('nat_src_ip', decode_uint32, 'NAT source IP'),
    69: FieldDefinition('nat_dst_ip', decode_uint32, 'NAT destination IP'),
    
    # VPN
    70: FieldDefinition('vpn_policy_name', decode_string, 'VPN policy name'),
    71: FieldDefinition('vpn_user', decode_string, 'VPN user'),
    
    # NAT
    80: FieldDefinition('nat_policy_id', decode_uint32, 'NAT policy ID'),
    81: FieldDefinition('nat_policy_name', decode_string, 'NAT policy name'),
    
    # Bandwidth management
    90: FieldDefinition('bwm_policy_name', decode_string, 'BWM policy name'),
    91: FieldDefinition('bwm_guaranteed', decode_uint64, 'BWM guaranteed bandwidth'),
    92: FieldDefinition('bwm_maximum', decode_uint64, 'BWM maximum bandwidth'),
    
    # GeoIP
    100: FieldDefinition('geo_src_country', decode_string, 'Source country'),
    101: FieldDefinition('geo_dst_country', decode_string, 'Destination country'),
    102: FieldDefinition('geo_src_region', decode_uint32, 'Source region'),
    103: FieldDefinition('geo_dst_region', decode_uint32, 'Destination region'),
    104: FieldDefinition('src_ip_int', decode_uint32, 'Source IP integer'),
    105: FieldDefinition('dst_ip_int', decode_uint32, 'Destination IP integer'),
    106: FieldDefinition('src_prefix_len', decode_uint8, 'Source prefix length'),
    107: FieldDefinition('dst_prefix_len', decode_uint8, 'Destination prefix length'),
    108: FieldDefinition('next_hop_int', decode_uint32, 'Next hop integer'),
    
    # Extended counters
    111: FieldDefinition('init_bytes_total', decode_uint64, 'Initiator total bytes'),
    112: FieldDefinition('resp_bytes_total', decode_uint64, 'Responder total bytes'),
    113: FieldDefinition('init_packets_total', decode_uint64, 'Initiator total packets'),
    114: FieldDefinition('resp_packets_total', decode_uint64, 'Responder total packets'),
    115: FieldDefinition('tcp_flags', decode_uint8, 'TCP flags'),
    116: FieldDefinition('tos', decode_uint8, 'Type of service'),
    117: FieldDefinition('application', decode_string, 'Application'),
    118: FieldDefinition('app_category_id', decode_uint32, 'App category ID'),
    119: FieldDefinition('app_id', decode_uint32, 'Application ID'),
    120: FieldDefinition('src_as', decode_uint32, 'Source AS'),
    121: FieldDefinition('dst_as', decode_uint32, 'Destination AS'),
    122: FieldDefinition('flow_id', decode_uint64, 'Flow ID'),
    123: FieldDefinition('flow_start_sec', decode_uint32, 'Flow start seconds'),
    124: FieldDefinition('flow_end_sec', decode_uint32, 'Flow end seconds'),
    126: FieldDefinition('sampling_interval', decode_uint32, 'Sampling interval'),
    127: FieldDefinition('sampling_algorithm', decode_uint8, 'Sampling algorithm'),
    
    # SSL/TLS
    134: FieldDefinition('ssl_cn', decode_string, 'SSL common name'),
    135: FieldDefinition('ssl_version', decode_uint8, 'SSL version'),
    136: FieldDefinition('ssl_cipher', decode_uint32, 'SSL cipher'),
    137: FieldDefinition('ssl_session_id', decode_uint64, 'SSL session ID'),
    
    # Extended fields
    145: FieldDefinition('flow_flags', decode_uint32, 'Flow flags'),
    146: FieldDefinition('flow_type', decode_uint8, 'Flow type'),
    147: FieldDefinition('biflow_direction', decode_uint8, 'Biflow direction'),
    148: FieldDefinition('flow_reason', decode_uint8, 'Flow end reason'),
    149: FieldDefinition('exporter_id', decode_uint32, 'Exporter ID'),
    150: FieldDefinition('observation_domain', decode_uint32, 'Observation domain'),
    151: FieldDefinition('observation_point', decode_uint32, 'Observation point'),
    152: FieldDefinition('selector_id', decode_uint32, 'Selector ID'),
    153: FieldDefinition('selector_name', decode_string, 'Selector name'),
    154: FieldDefinition('template_name', decode_string, 'Template name'),
    
    # More counters
    167: FieldDefinition('dropped_packets', decode_uint64, 'Dropped packets'),
    168: FieldDefinition('dropped_bytes', decode_uint64, 'Dropped bytes'),
    169: FieldDefinition('consumed_packets', decode_uint64, 'Consumed packets'),
    170: FieldDefinition('consumed_bytes', decode_uint64, 'Consumed bytes'),
    171: FieldDefinition('flow_count', decode_uint32, 'Flow count'),
    172: FieldDefinition('avg_pkt_size', decode_uint16, 'Average packet size'),
    173: FieldDefinition('min_pkt_size', decode_uint16, 'Minimum packet size'),
    174: FieldDefinition('max_pkt_size', decode_string, 'Maximum packet size'),
    175: FieldDefinition('avg_ttl', decode_uint8, 'Average TTL'),
    176: FieldDefinition('min_ttl_val', decode_uint8, 'Minimum TTL'),
    177: FieldDefinition('max_ttl', decode_string, 'Maximum TTL'),
    179: FieldDefinition('fw_rule_id', decode_uint32, 'Firewall rule ID'),
    180: FieldDefinition('fw_policy_id', decode_uint32, 'Firewall policy ID'),
    181: FieldDefinition('fw_event', decode_uint8, 'Firewall event'),
    182: FieldDefinition('ingress_acl_id', decode_uint32, 'Ingress ACL ID'),
    183: FieldDefinition('egress_acl_id', decode_uint32, 'Egress ACL ID'),
    
    # QoS
    190: FieldDefinition('qos_class', decode_uint8, 'QoS class'),
    191: FieldDefinition('qos_priority', decode_uint8, 'QoS priority'),
    192: FieldDefinition('qos_dscp', decode_uint8, 'QoS DSCP'),
    193: FieldDefinition('qos_marking', decode_uint8, 'QoS marking'),
    194: FieldDefinition('queue_id', decode_uint32, 'Queue ID'),
    
    # Extended info
    260: FieldDefinition('vxlan_id', decode_uint32, 'VXLAN ID'),
    261: FieldDefinition('gre_key', decode_string, 'GRE key'),
    262: FieldDefinition('mpls_label', decode_uint32, 'MPLS label'),
    263: FieldDefinition('mpls_exp', decode_uint8, 'MPLS exp'),
    264: FieldDefinition('mpls_ttl', decode_uint8, 'MPLS TTL'),
    265: FieldDefinition('l2tp_session', decode_uint32, 'L2TP session'),
    
    # Additional
    302: FieldDefinition('category', decode_string, 'Category'),
    305: FieldDefinition('rating_service_id', decode_uint32, 'Rating service ID'),
    306: FieldDefinition('rating_category', decode_uint32, 'Rating category'),
    307: FieldDefinition('content_flags', decode_uint32, 'Content flags'),
    308: FieldDefinition('reputation_score', decode_int32, 'Reputation score'),
    309: FieldDefinition('confidence', decode_uint8, 'Confidence'),
    310: FieldDefinition('priority', decode_uint8, 'Priority'),
    311: FieldDefinition('severity', decode_uint8, 'Severity'),
    312: FieldDefinition('signature', decode_string, 'Signature'),
    314: FieldDefinition('event_id', decode_uint64, 'Event ID'),
    315: FieldDefinition('event_type', decode_uint32, 'Event type'),
}


# ============================================================================
# Cisco Enterprise Fields (Enterprise ID: 9)
# ============================================================================

CISCO_ENTERPRISE_ID = 9

CISCO_FIELDS: Dict[int, FieldDefinition] = {
    12232: FieldDefinition('cisco_app_id', decode_hex, 'Cisco application ID'),
    12233: FieldDefinition('cisco_app_name', decode_string, 'Cisco application name'),
    8: FieldDefinition('cisco_src_ip', decode_ipv4, 'Cisco source IP'),
    12: FieldDefinition('cisco_dst_ip', decode_ipv4, 'Cisco destination IP'),
}


# ============================================================================
# Enterprise Field Registry
# Key: (enterprise_id, field_id), Value: FieldDefinition
# ============================================================================

ENTERPRISE_FIELDS: Dict[tuple, FieldDefinition] = {}

# Register SonicWall fields
for field_id, field_def in SONICWALL_FIELDS.items():
    ENTERPRISE_FIELDS[(SONICWALL_ENTERPRISE_ID, field_id)] = field_def

# Register Cisco fields
for field_id, field_def in CISCO_FIELDS.items():
    ENTERPRISE_FIELDS[(CISCO_ENTERPRISE_ID, field_id)] = field_def


# ============================================================================
# Field Lookup Functions
# ============================================================================

def get_field_definition(field_id: int, enterprise_id: Optional[int] = None) -> Optional[FieldDefinition]:
    """
    Look up field definition by ID and enterprise ID
    
    Args:
        field_id: IPFIX/NetFlow field ID
        enterprise_id: Enterprise number (None for standard IANA fields)
    
    Returns:
        FieldDefinition if found, None otherwise
    """
    # Try enterprise-specific first
    if enterprise_id and enterprise_id > 0:
        key = (enterprise_id, field_id)
        if key in ENTERPRISE_FIELDS:
            return ENTERPRISE_FIELDS[key]
        # Return a generic definition for unknown enterprise fields
        return FieldDefinition(
            f'enterprise_{enterprise_id}_field_{field_id}',
            decode_bytes_auto,
            f'Unknown enterprise field {field_id} (PEN: {enterprise_id})'
        )
    
    # Standard IANA field
    if field_id in STANDARD_FIELDS:
        return STANDARD_FIELDS[field_id]
    
    # Return generic definition for unknown standard fields
    return FieldDefinition(
        f'field_{field_id}',
        decode_bytes_auto,
        f'Unknown IPFIX field {field_id}'
    )


def get_protocol_name(protocol: int) -> str:
    """Get human-readable protocol name"""
    return PROTOCOL_NAMES.get(protocol, f'PROTO_{protocol}')


def decode_tcp_flags(flags: int) -> str:
    """Decode TCP flags to human-readable string"""
    result = []
    for bit, name in TCP_FLAGS.items():
        if flags & bit:
            result.append(name)
    return ','.join(result) if result else 'NONE'


def is_sonicwall_enterprise(enterprise_id: Optional[int]) -> bool:
    """Check if enterprise ID is SonicWall"""
    return enterprise_id == SONICWALL_ENTERPRISE_ID

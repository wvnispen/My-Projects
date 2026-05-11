#!/usr/bin/env python3
"""
SonicWall Flow Reporter - Identity Management UI

FastAPI web application for managing user-to-IP mappings.
"""

import os
import csv
import io
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form, HTTPException, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from passlib.context import CryptContext
from elasticsearch import Elasticsearch
import secrets

from sonicwall_sso import SonicWallSSO

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('swfr.identity-ui')

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBasic()

# Configuration
ES_HOST = os.environ.get('ELASTICSEARCH_HOST', 'localhost')
ES_PORT = int(os.environ.get('ELASTICSEARCH_PORT', '9200'))
ES_PASSWORD = os.environ.get('ELASTIC_PASSWORD', '')
ADMIN_USER = os.environ.get('IDENTITY_ADMIN_USER', os.environ.get('ADMIN_USER', 'admin'))
ADMIN_PASSWORD = os.environ.get('IDENTITY_ADMIN_PASSWORD', os.environ.get('ADMIN_PASSWORD', 'admin'))
SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Elasticsearch client
es_client = None

# SonicWall SSO client
sso_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    global es_client, sso_client
    
    # Startup - connect to Elasticsearch
    es_url = f"http://{ES_HOST}:{ES_PORT}"
    if ES_PASSWORD:
        es_client = Elasticsearch(
            hosts=[es_url],
            basic_auth=("elastic", ES_PASSWORD),
            retry_on_timeout=True
        )
    else:
        es_client = Elasticsearch(
            hosts=[es_url],
            retry_on_timeout=True
        )
    logger.info(f"Connected to Elasticsearch at {ES_HOST}:{ES_PORT}")
    
    # Initialize SonicWall SSO if enabled
    if os.environ.get('SONICWALL_SSO_ENABLED', 'false').lower() == 'true':
        sso_client = SonicWallSSO(
            host=os.environ.get('SONICWALL_HOST', ''),
            port=int(os.environ.get('SONICWALL_API_PORT', '443')),
            username=os.environ.get('SONICWALL_API_USER', ''),
            password=os.environ.get('SONICWALL_API_PASSWORD', '')
        )
        logger.info("SonicWall SSO integration enabled")
    
    yield
    
    # Shutdown
    if es_client:
        es_client.close()


app = FastAPI(
    title="SonicWall Flow Reporter - Identity Management",
    lifespan=lifespan
)

# Mount static files only if directory exists and has content
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir) and os.listdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Templates
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify HTTP Basic auth credentials"""
    is_valid = secrets.compare_digest(credentials.username, ADMIN_USER) and \
               secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    
    if not is_valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# ============================================================================
# Web Routes
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, username: str = Depends(verify_credentials)):
    """Main dashboard page"""
    # Get summary stats
    stats = await get_identity_stats()
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "username": username,
        "stats": stats,
        "sso_enabled": sso_client is not None
    })


@app.get("/mappings", response_class=HTMLResponse)
async def list_mappings(
    request: Request,
    page: int = 1,
    search: str = "",
    username: str = Depends(verify_credentials)
):
    """List all identity mappings"""
    page_size = 50
    offset = (page - 1) * page_size
    
    # Build query
    query = {"bool": {"must": [{"term": {"active": True}}]}}
    
    if search:
        query["bool"]["must"].append({
            "multi_match": {
                "query": search,
                "fields": ["user_name", "user_id", "ip_address", "department", "location"]
            }
        })
    
    try:
        result = es_client.search(
            index="identity-mappings",
            body={
                "query": query,
                "from": offset,
                "size": page_size,
                "sort": [{"updated_at": "desc"}]
            }
        )
        
        mappings = [hit['_source'] | {'id': hit['_id']} for hit in result['hits']['hits']]
        total = result['hits']['total']['value']
        total_pages = (total + page_size - 1) // page_size
        
    except Exception as e:
        logger.error(f"Error fetching mappings: {e}")
        mappings = []
        total = 0
        total_pages = 1
    
    return templates.TemplateResponse("mappings.html", {
        "request": request,
        "username": username,
        "mappings": mappings,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "search": search
    })


@app.get("/mappings/add", response_class=HTMLResponse)
async def add_mapping_form(request: Request, username: str = Depends(verify_credentials)):
    """Show add mapping form"""
    return templates.TemplateResponse("add_mapping.html", {
        "request": request,
        "username": username
    })


@app.post("/mappings/add")
async def add_mapping(
    request: Request,
    ip_address: str = Form(None),
    subnet: str = Form(None),
    user_id: str = Form(...),
    user_name: str = Form(...),
    department: str = Form(None),
    location: str = Form(None),
    description: str = Form(None),
    username: str = Depends(verify_credentials)
):
    """Add a new identity mapping"""
    if not ip_address and not subnet:
        raise HTTPException(400, "Either IP address or subnet is required")
    
    now = datetime.now(timezone.utc).isoformat()
    
    doc = {
        'user_id': user_id,
        'user_name': user_name,
        'department': department or '',
        'location': location or '',
        'description': description or '',
        'source': 'manual',
        'active': True,
        'created_at': now,
        'updated_at': now
    }
    
    if ip_address:
        doc['ip_address'] = ip_address
    
    if subnet:
        # Parse CIDR and store as IP range
        import ipaddress
        try:
            network = ipaddress.ip_network(subnet, strict=False)
            doc['subnet'] = {
                'gte': str(network.network_address),
                'lte': str(network.broadcast_address)
            }
            doc['subnet_cidr'] = subnet
        except ValueError:
            raise HTTPException(400, f"Invalid subnet format: {subnet}")
    
    try:
        doc_id = f"{ip_address or subnet}_{user_id}"
        es_client.index(index="identity-mappings", id=doc_id, document=doc)
        logger.info(f"Added mapping: {doc_id}")
    except Exception as e:
        logger.error(f"Error adding mapping: {e}")
        raise HTTPException(500, "Error saving mapping")
    
    return RedirectResponse(url="/mappings", status_code=303)


@app.post("/mappings/delete/{mapping_id}")
async def delete_mapping(mapping_id: str, username: str = Depends(verify_credentials)):
    """Delete (deactivate) a mapping"""
    try:
        es_client.update(
            index="identity-mappings",
            id=mapping_id,
            body={
                "doc": {
                    "active": False,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        logger.info(f"Deleted mapping: {mapping_id}")
    except Exception as e:
        logger.error(f"Error deleting mapping: {e}")
        raise HTTPException(500, "Error deleting mapping")
    
    return RedirectResponse(url="/mappings", status_code=303)


@app.get("/import", response_class=HTMLResponse)
async def import_form(request: Request, username: str = Depends(verify_credentials)):
    """Show CSV import form"""
    return templates.TemplateResponse("import.html", {
        "request": request,
        "username": username
    })


@app.post("/import")
async def import_csv(
    request: Request,
    file: UploadFile = File(...),
    username: str = Depends(verify_credentials)
):
    """Import mappings from CSV file"""
    content = await file.read()
    
    try:
        # Decode and parse CSV
        text = content.decode('utf-8-sig')  # Handle BOM
        reader = csv.DictReader(io.StringIO(text))
        
        now = datetime.now(timezone.utc).isoformat()
        imported = 0
        errors = []
        
        for row in reader:
            try:
                ip_address = row.get('ip_address', '').strip()
                subnet = row.get('subnet', '').strip()
                user_id = row.get('user_id', '').strip()
                user_name = row.get('user_name', '').strip()
                
                if not user_id or not user_name:
                    continue
                if not ip_address and not subnet:
                    continue
                
                doc = {
                    'user_id': user_id,
                    'user_name': user_name,
                    'department': row.get('department', '').strip(),
                    'location': row.get('location', '').strip(),
                    'description': row.get('description', '').strip(),
                    'source': 'csv_import',
                    'active': True,
                    'created_at': now,
                    'updated_at': now
                }
                
                if ip_address:
                    doc['ip_address'] = ip_address
                
                if subnet:
                    import ipaddress
                    network = ipaddress.ip_network(subnet, strict=False)
                    doc['subnet'] = {
                        'gte': str(network.network_address),
                        'lte': str(network.broadcast_address)
                    }
                    doc['subnet_cidr'] = subnet
                
                doc_id = f"{ip_address or subnet}_{user_id}"
                es_client.index(index="identity-mappings", id=doc_id, document=doc)
                imported += 1
                
            except Exception as e:
                errors.append(f"Row error: {str(e)}")
        
        logger.info(f"Imported {imported} mappings from CSV")
        
        return templates.TemplateResponse("import_result.html", {
            "request": request,
            "username": username,
            "imported": imported,
            "errors": errors
        })
        
    except Exception as e:
        logger.error(f"Error importing CSV: {e}")
        raise HTTPException(400, f"Error parsing CSV: {str(e)}")


@app.get("/sso", response_class=HTMLResponse)
async def sso_settings(request: Request, username: str = Depends(verify_credentials)):
    """SonicWall SSO settings page"""
    return templates.TemplateResponse("sso.html", {
        "request": request,
        "username": username,
        "sso_enabled": sso_client is not None,
        "sso_host": os.environ.get('SONICWALL_HOST', ''),
        "sso_user": os.environ.get('SONICWALL_API_USER', '')
    })


@app.get("/dhcp", response_class=HTMLResponse)
async def dhcp_import_form(request: Request, username: str = Depends(verify_credentials)):
    """Show DHCP static lease import form"""
    return templates.TemplateResponse("dhcp_import.html", {
        "request": request,
        "username": username,
        "sso_enabled": sso_client is not None
    })


@app.post("/dhcp/import")
async def dhcp_import(
    request: Request,
    file: UploadFile = File(...),
    format_type: str = Form(...),
    default_department: str = Form(""),
    default_location: str = Form(""),
    username: str = Depends(verify_credentials)
):
    """Import static DHCP leases from various formats"""
    import re
    
    content = await file.read()
    text = content.decode('utf-8-sig', errors='replace')
    
    now = datetime.now(timezone.utc).isoformat()
    imported = 0
    errors = []
    leases = []
    
    try:
        if format_type == 'sonicwall':
            # SonicWall export format (CSV-like or from CLI)
            # Format: IP,MAC,Name or "IP Address","MAC Address","Name"
            leases = parse_sonicwall_dhcp(text)
        
        elif format_type == 'isc':
            # ISC DHCP dhcpd.conf static host entries
            # host hostname { hardware ethernet xx:xx:xx:xx:xx:xx; fixed-address ip; }
            leases = parse_isc_dhcp(text)
        
        elif format_type == 'dnsmasq':
            # dnsmasq format: dhcp-host=xx:xx:xx:xx:xx:xx,hostname,ip
            leases = parse_dnsmasq_dhcp(text)
        
        elif format_type == 'windows':
            # Windows DHCP export (CSV from PowerShell or MMC export)
            leases = parse_windows_dhcp(text)
        
        elif format_type == 'mikrotik':
            # MikroTik export format
            leases = parse_mikrotik_dhcp(text)
        
        elif format_type == 'opnsense':
            # OPNsense/pfSense XML or CSV export
            leases = parse_opnsense_dhcp(text)
        
        elif format_type == 'csv':
            # Generic CSV: ip,mac,hostname (flexible column names)
            leases = parse_generic_csv(text)
        
        else:
            raise HTTPException(400, f"Unknown format: {format_type}")
        
        # Import parsed leases
        for lease in leases:
            try:
                ip = lease.get('ip', '').strip()
                hostname = lease.get('hostname', '').strip()
                mac = lease.get('mac', '').strip().upper()
                description = lease.get('description', '').strip()
                
                if not ip or not hostname:
                    continue
                
                # Use hostname as both user_id and user_name
                # Clean hostname for use as ID
                user_id = re.sub(r'[^a-zA-Z0-9_-]', '_', hostname.lower())
                
                doc = {
                    'ip_address': ip,
                    'user_id': user_id,
                    'user_name': hostname,
                    'mac_address': mac,
                    'department': default_department,
                    'location': default_location,
                    'description': description or f"DHCP static lease (MAC: {mac})" if mac else "DHCP static lease",
                    'source': 'dhcp_import',
                    'active': True,
                    'created_at': now,
                    'updated_at': now
                }
                
                doc_id = f"{ip}_{user_id}"
                es_client.index(index="identity-mappings", id=doc_id, document=doc)
                imported += 1
                
            except Exception as e:
                errors.append(f"Error importing {lease}: {str(e)}")
        
        logger.info(f"Imported {imported} DHCP static leases")
        
        return templates.TemplateResponse("dhcp_import_result.html", {
            "request": request,
            "username": username,
            "imported": imported,
            "errors": errors,
            "total_parsed": len(leases),
            "sso_enabled": sso_client is not None
        })
        
    except Exception as e:
        logger.error(f"Error importing DHCP leases: {e}")
        raise HTTPException(400, f"Error parsing DHCP file: {str(e)}")


# ============================================================================
# DHCP Parsing Functions
# ============================================================================

def parse_sonicwall_dhcp(text: str) -> list:
    """Parse SonicWall DHCP static lease export"""
    import re
    leases = []
    
    # Try CSV format first
    lines = text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # Remove quotes and split
        parts = [p.strip().strip('"') for p in line.split(',')]
        
        if len(parts) >= 3:
            # Could be IP,MAC,Name or Name,MAC,IP - detect by format
            ip_pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
            mac_pattern = r'^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$'
            
            ip = mac = hostname = None
            
            for part in parts:
                if re.match(ip_pattern, part):
                    ip = part
                elif re.match(mac_pattern, part):
                    mac = part
                elif part and not ip and not mac:
                    hostname = part
                elif part and ip and mac:
                    hostname = part
            
            # If hostname not found, use remaining part
            if ip and not hostname:
                for part in parts:
                    if part != ip and part != mac:
                        hostname = part
                        break
            
            if ip and hostname:
                leases.append({'ip': ip, 'mac': mac or '', 'hostname': hostname})
    
    return leases


def parse_isc_dhcp(text: str) -> list:
    """Parse ISC DHCP dhcpd.conf static host entries"""
    import re
    leases = []
    
    # Match: host hostname { hardware ethernet xx:xx:xx:xx:xx:xx; fixed-address ip; }
    pattern = r'host\s+(\S+)\s*\{[^}]*hardware\s+ethernet\s+([0-9a-fA-F:]+)\s*;[^}]*fixed-address\s+([0-9.]+)\s*;[^}]*\}'
    
    for match in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
        hostname, mac, ip = match.groups()
        leases.append({'ip': ip, 'mac': mac, 'hostname': hostname})
    
    return leases


def parse_dnsmasq_dhcp(text: str) -> list:
    """Parse dnsmasq dhcp-host entries"""
    import re
    leases = []
    
    for line in text.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # dhcp-host=xx:xx:xx:xx:xx:xx,hostname,ip
        # or dhcp-host=xx:xx:xx:xx:xx:xx,ip,hostname
        # or dhcp-host=xx:xx:xx:xx:xx:xx,ip
        match = re.match(r'dhcp-host\s*=\s*([0-9a-fA-F:]+)\s*,\s*([^,]+)\s*(?:,\s*([^,\s]+))?', line, re.IGNORECASE)
        
        if match:
            mac = match.group(1)
            part2 = match.group(2).strip()
            part3 = match.group(3).strip() if match.group(3) else None
            
            ip_pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
            
            if re.match(ip_pattern, part2):
                ip = part2
                hostname = part3 or mac.replace(':', '')
            elif part3 and re.match(ip_pattern, part3):
                hostname = part2
                ip = part3
            else:
                continue
            
            leases.append({'ip': ip, 'mac': mac, 'hostname': hostname})
    
    return leases


def parse_windows_dhcp(text: str) -> list:
    """Parse Windows DHCP server export (CSV from PowerShell)"""
    leases = []
    
    lines = text.strip().split('\n')
    if not lines:
        return leases
    
    # Find header row
    header = None
    header_idx = 0
    for i, line in enumerate(lines):
        if 'IPAddress' in line or 'ClientId' in line or 'ip' in line.lower():
            header = [h.strip().strip('"').lower() for h in line.split(',')]
            header_idx = i
            break
    
    if not header:
        return leases
    
    # Map common column names
    ip_cols = ['ipaddress', 'ip', 'ip address', 'reservedip']
    mac_cols = ['clientid', 'mac', 'macaddress', 'mac address', 'hardwareaddress']
    name_cols = ['name', 'hostname', 'host', 'description', 'scopeid']
    
    ip_idx = mac_idx = name_idx = -1
    
    for i, col in enumerate(header):
        if col in ip_cols:
            ip_idx = i
        elif col in mac_cols:
            mac_idx = i
        elif col in name_cols and name_idx == -1:
            name_idx = i
    
    if ip_idx == -1:
        return leases
    
    for line in lines[header_idx + 1:]:
        parts = [p.strip().strip('"') for p in line.split(',')]
        if len(parts) > ip_idx:
            ip = parts[ip_idx]
            mac = parts[mac_idx] if mac_idx >= 0 and len(parts) > mac_idx else ''
            hostname = parts[name_idx] if name_idx >= 0 and len(parts) > name_idx else ''
            
            if ip and hostname:
                leases.append({'ip': ip, 'mac': mac, 'hostname': hostname})
    
    return leases


def parse_mikrotik_dhcp(text: str) -> list:
    """Parse MikroTik DHCP lease export"""
    import re
    leases = []
    
    # MikroTik export format:
    # add address=192.168.1.100 mac-address=AA:BB:CC:DD:EE:FF server=dhcp1 comment="Hostname"
    pattern = r'add\s+.*?address=([0-9.]+).*?mac-address=([0-9A-Fa-f:]+).*?(?:comment="([^"]*)")?'
    
    for match in re.finditer(pattern, text, re.IGNORECASE):
        ip, mac, comment = match.groups()
        hostname = comment or mac.replace(':', '')
        leases.append({'ip': ip, 'mac': mac, 'hostname': hostname})
    
    # Also try the /export format with name=
    pattern2 = r'add\s+.*?address=([0-9.]+).*?mac-address=([0-9A-Fa-f:]+).*?(?:name="?([^"\s]+)"?)?'
    for match in re.finditer(pattern2, text, re.IGNORECASE):
        ip, mac, name = match.groups()
        if name:
            leases.append({'ip': ip, 'mac': mac, 'hostname': name})
    
    return leases


def parse_opnsense_dhcp(text: str) -> list:
    """Parse OPNsense/pfSense DHCP static mappings"""
    import re
    leases = []
    
    # Try XML format first
    if '<staticmap>' in text:
        # XML format from config.xml
        pattern = r'<staticmap>.*?<mac>([^<]+)</mac>.*?<ipaddr>([^<]+)</ipaddr>.*?(?:<hostname>([^<]*)</hostname>)?.*?</staticmap>'
        for match in re.finditer(pattern, text, re.DOTALL | re.IGNORECASE):
            mac, ip, hostname = match.groups()
            hostname = hostname or mac.replace(':', '')
            leases.append({'ip': ip, 'mac': mac, 'hostname': hostname})
    else:
        # Try CSV format
        leases = parse_generic_csv(text)
    
    return leases


def parse_generic_csv(text: str) -> list:
    """Parse generic CSV with flexible column detection"""
    import re
    leases = []
    
    lines = text.strip().split('\n')
    if not lines:
        return leases
    
    # Try to detect delimiter
    first_line = lines[0]
    if '\t' in first_line:
        delimiter = '\t'
    elif ';' in first_line:
        delimiter = ';'
    else:
        delimiter = ','
    
    # Parse header
    header = [h.strip().strip('"').lower() for h in first_line.split(delimiter)]
    
    # Map columns
    ip_keywords = ['ip', 'ipaddress', 'ip_address', 'address', 'ipaddr']
    mac_keywords = ['mac', 'macaddress', 'mac_address', 'hardware', 'hwaddr', 'clientid']
    name_keywords = ['name', 'hostname', 'host', 'device', 'client', 'description', 'label']
    
    ip_idx = mac_idx = name_idx = -1
    
    for i, col in enumerate(header):
        col_clean = re.sub(r'[^a-z0-9]', '', col)
        if any(kw in col_clean for kw in ip_keywords):
            ip_idx = i
        elif any(kw in col_clean for kw in mac_keywords):
            mac_idx = i
        elif any(kw in col_clean for kw in name_keywords) and name_idx == -1:
            name_idx = i
    
    # If no header detected, try to auto-detect from first data row
    if ip_idx == -1:
        ip_pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
        mac_pattern = r'^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$'
        
        test_row = [p.strip().strip('"') for p in lines[0].split(delimiter)]
        for i, val in enumerate(test_row):
            if re.match(ip_pattern, val):
                ip_idx = i
            elif re.match(mac_pattern, val):
                mac_idx = i
        
        # Start from first line if no header
        start_idx = 0
    else:
        start_idx = 1
    
    for line in lines[start_idx:]:
        parts = [p.strip().strip('"') for p in line.split(delimiter)]
        if len(parts) > max(ip_idx, 0):
            ip = parts[ip_idx] if ip_idx >= 0 else ''
            mac = parts[mac_idx] if mac_idx >= 0 and len(parts) > mac_idx else ''
            hostname = parts[name_idx] if name_idx >= 0 and len(parts) > name_idx else ''
            
            # If no hostname, generate from MAC or IP
            if not hostname and mac:
                hostname = f"device-{mac.replace(':', '')[-6:]}"
            elif not hostname and ip:
                hostname = f"device-{ip.replace('.', '-')}"
            
            if ip:
                leases.append({'ip': ip, 'mac': mac, 'hostname': hostname})
    
    return leases


@app.post("/sso/sync")
async def sso_sync(username: str = Depends(verify_credentials)):
    """Manually trigger SSO sync"""
    if not sso_client:
        raise HTTPException(400, "SonicWall SSO is not enabled")
    
    try:
        users = await sso_client.get_logged_in_users()
        now = datetime.now(timezone.utc).isoformat()
        synced = 0
        
        for user in users:
            doc = {
                'ip_address': user['ip_address'],
                'user_id': user['user_id'],
                'user_name': user['user_name'],
                'department': user.get('group', ''),
                'source': 'sonicwall_sso',
                'active': True,
                'last_seen': now,
                'updated_at': now
            }
            
            doc_id = f"{user['ip_address']}_{user['user_id']}"
            es_client.index(index="identity-mappings", id=doc_id, document=doc)
            synced += 1
        
        logger.info(f"SSO sync: {synced} users")
        return JSONResponse({"status": "success", "synced": synced})
        
    except Exception as e:
        logger.error(f"SSO sync error: {e}")
        raise HTTPException(500, f"SSO sync failed: {str(e)}")


# ============================================================================
# API Routes
# ============================================================================

@app.get("/api/mappings")
async def api_list_mappings(
    search: str = "",
    limit: int = 100,
    username: str = Depends(verify_credentials)
):
    """API: List mappings"""
    query = {"bool": {"must": [{"term": {"active": True}}]}}
    
    if search:
        query["bool"]["must"].append({
            "multi_match": {
                "query": search,
                "fields": ["user_name", "user_id", "ip_address"]
            }
        })
    
    try:
        result = es_client.search(
            index="identity-mappings",
            body={"query": query, "size": limit}
        )
        
        return {
            "mappings": [hit['_source'] | {'id': hit['_id']} for hit in result['hits']['hits']],
            "total": result['hits']['total']['value']
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/lookup/{ip_address}")
async def api_lookup(ip_address: str, username: str = Depends(verify_credentials)):
    """API: Lookup identity by IP"""
    try:
        # Try direct match first
        result = es_client.search(
            index="identity-mappings",
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"ip_address": ip_address}},
                            {"term": {"active": True}}
                        ]
                    }
                },
                "size": 1
            }
        )
        
        if result['hits']['hits']:
            return result['hits']['hits'][0]['_source']
        
        return {"error": "Not found"}
        
    except Exception as e:
        raise HTTPException(500, str(e))


# ============================================================================
# Helper Functions
# ============================================================================

async def get_identity_stats():
    """Get summary statistics for dashboard"""
    try:
        result = es_client.search(
            index="identity-mappings",
            body={
                "size": 0,
                "query": {"term": {"active": True}},
                "aggs": {
                    "total": {"value_count": {"field": "user_id.keyword"}},
                    "by_source": {
                        "terms": {"field": "source.keyword"}
                    },
                    "by_department": {
                        "terms": {"field": "department.keyword", "size": 10}
                    }
                }
            }
        )
        
        aggs = result.get('aggregations', {})
        
        return {
            "total_mappings": result['hits']['total']['value'],
            "by_source": {b['key']: b['doc_count'] for b in aggs.get('by_source', {}).get('buckets', [])},
            "by_department": {b['key']: b['doc_count'] for b in aggs.get('by_department', {}).get('buckets', [])}
        }
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return {"total_mappings": 0, "by_source": {}, "by_department": {}}

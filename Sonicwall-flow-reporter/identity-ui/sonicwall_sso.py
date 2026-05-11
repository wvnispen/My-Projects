#!/usr/bin/env python3
"""
SonicWall SSO Integration

Connects to SonicWall firewall API to retrieve current user-to-IP mappings
from the SSO/Directory Services integration.
"""

import logging
import httpx
from typing import List, Dict, Optional

logger = logging.getLogger('swfr.sonicwall_sso')


class SonicWallSSO:
    """SonicWall API client for SSO user retrieval"""
    
    def __init__(self, host: str, port: int = 443, username: str = '', password: str = ''):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.base_url = f"https://{host}:{port}/api/sonicos"
        self.session_token = None
        
    async def _authenticate(self, client: httpx.AsyncClient) -> bool:
        """Authenticate to SonicWall API"""
        try:
            # SonicOS API authentication
            response = await client.post(
                f"{self.base_url}/auth",
                json={
                    "user": self.username,
                    "password": self.password
                },
                headers={"Content-Type": "application/json"},
                timeout=30.0
            )
            
            if response.status_code == 200:
                # Extract session token from response
                data = response.json()
                self.session_token = data.get('status', {}).get('info', [{}])[0].get('token')
                return True
            else:
                logger.error(f"SonicWall auth failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"SonicWall auth error: {e}")
            return False
    
    async def _logout(self, client: httpx.AsyncClient):
        """Logout from SonicWall API"""
        try:
            if self.session_token:
                await client.delete(
                    f"{self.base_url}/auth",
                    headers={"X-Auth-Token": self.session_token},
                    timeout=10.0
                )
        except Exception:
            pass
    
    async def get_logged_in_users(self) -> List[Dict]:
        """Get list of currently logged-in users from SonicWall SSO"""
        users = []
        
        async with httpx.AsyncClient(verify=False) as client:
            # Authenticate
            if not await self._authenticate(client):
                logger.error("Failed to authenticate to SonicWall")
                return users
            
            try:
                # Get SSO user list
                # Note: The exact API endpoint depends on SonicOS version
                # This covers common endpoints for SSO data
                
                # Try SSO users endpoint
                response = await client.get(
                    f"{self.base_url}/sso/users",
                    headers={
                        "X-Auth-Token": self.session_token,
                        "Accept": "application/json"
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    users = self._parse_sso_users(data)
                else:
                    # Try alternative endpoint for user sessions
                    response = await client.get(
                        f"{self.base_url}/user/sessions",
                        headers={
                            "X-Auth-Token": self.session_token,
                            "Accept": "application/json"
                        },
                        timeout=30.0
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        users = self._parse_user_sessions(data)
                
            except Exception as e:
                logger.error(f"Error fetching SSO users: {e}")
            
            finally:
                await self._logout(client)
        
        logger.info(f"Retrieved {len(users)} users from SonicWall SSO")
        return users
    
    def _parse_sso_users(self, data: dict) -> List[Dict]:
        """Parse SSO users response"""
        users = []
        
        # Handle different response formats
        sso_users = data.get('sso', {}).get('users', [])
        if not sso_users:
            sso_users = data.get('users', [])
        
        for user in sso_users:
            try:
                parsed = {
                    'ip_address': user.get('ip', user.get('ip_address', '')),
                    'user_id': user.get('name', user.get('user_name', '')),
                    'user_name': user.get('name', user.get('user_name', '')),
                    'domain': user.get('domain', ''),
                    'group': user.get('group', user.get('groups', '')),
                    'login_time': user.get('login_time', ''),
                }
                
                if parsed['ip_address'] and parsed['user_id']:
                    users.append(parsed)
                    
            except Exception as e:
                logger.debug(f"Error parsing SSO user: {e}")
        
        return users
    
    def _parse_user_sessions(self, data: dict) -> List[Dict]:
        """Parse user sessions response"""
        users = []
        
        sessions = data.get('user_sessions', data.get('sessions', []))
        
        for session in sessions:
            try:
                parsed = {
                    'ip_address': session.get('source_ip', session.get('ip', '')),
                    'user_id': session.get('user', session.get('username', '')),
                    'user_name': session.get('user', session.get('username', '')),
                    'domain': session.get('domain', ''),
                    'group': session.get('group', ''),
                }
                
                if parsed['ip_address'] and parsed['user_id']:
                    users.append(parsed)
                    
            except Exception as e:
                logger.debug(f"Error parsing session: {e}")
        
        return users
    
    async def test_connection(self) -> Dict:
        """Test connection to SonicWall"""
        async with httpx.AsyncClient(verify=False) as client:
            try:
                if await self._authenticate(client):
                    # Get system info
                    response = await client.get(
                        f"{self.base_url}/system/status",
                        headers={
                            "X-Auth-Token": self.session_token,
                            "Accept": "application/json"
                        },
                        timeout=10.0
                    )
                    
                    await self._logout(client)
                    
                    if response.status_code == 200:
                        return {
                            "status": "success",
                            "message": "Connected to SonicWall"
                        }
                
                return {
                    "status": "error",
                    "message": "Authentication failed"
                }
                
            except Exception as e:
                return {
                    "status": "error",
                    "message": str(e)
                }

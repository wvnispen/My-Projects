from fastapi import Header, HTTPException
from config import settings


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
    if not settings.api_key:
        raise HTTPException(503, "API key not configured on server")
    if x_api_key != settings.api_key:
        raise HTTPException(401, "Invalid API key")

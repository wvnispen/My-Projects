import httpx
from fastapi import APIRouter
from config import settings

router = APIRouter()


@router.get("/api/v1/health")
async def health():
    return {"status": "ok"}


@router.get("/api/v1/status")
async def status():
    result = {}

    async with httpx.AsyncClient(timeout=5) as client:
        # ESP32
        try:
            r = await client.get(f"{settings.esp32_url}/status")
            result["esp32"] = {"reachable": True, **r.json()}
        except Exception:
            result["esp32"] = {"reachable": False}

        # Telegram
        try:
            r = await client.get(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/getMe"
            )
            data = r.json()
            result["telegram"] = {
                "ok": data.get("ok", False),
                "bot": data.get("result", {}).get("username", ""),
            }
        except Exception:
            result["telegram"] = {"ok": False}

        # WAHA
        try:
            r = await client.get(
                f"{settings.waha_url}/api/sessions/{settings.waha_session}",
                headers={"X-Api-Key": settings.waha_api_key},
            )
            data = r.json()
            result["whatsapp"] = {"ok": True, "session": data.get("status", "unknown")}
        except Exception:
            result["whatsapp"] = {"ok": False, "session": "unreachable"}

    return result

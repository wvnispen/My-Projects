import httpx
from config import settings


def _chat_id(number: str) -> str:
    """Normalise a phone number to WhatsApp chatId format (27821234567@c.us)."""
    n = number.strip().lstrip("+")
    return n if "@" in n else f"{n}@c.us"


async def send(to: str, message: str) -> dict:
    number = to or settings.waha_default_number
    if not number:
        return {"status": "error", "channel": "whatsapp", "reason": "missing 'to' number and no default set"}
    if not settings.waha_api_key:
        return {"status": "error", "channel": "whatsapp", "reason": "WAHA not configured"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"{settings.waha_url}/api/sendText",
                headers={"X-Api-Key": settings.waha_api_key},
                json={
                    "chatId": _chat_id(number),
                    "text": message,
                    "session": settings.waha_session,
                },
            )
            r.raise_for_status()
            return {"status": "ok", "channel": "whatsapp"}
    except httpx.HTTPStatusError as e:
        return {"status": "error", "channel": "whatsapp", "reason": e.response.text}
    except Exception as e:
        return {"status": "error", "channel": "whatsapp", "reason": str(e)}

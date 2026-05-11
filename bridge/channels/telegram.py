import httpx
from config import settings


async def send(to: str, message: str) -> dict:
    chat_id = to or settings.telegram_default_chat_id
    if not chat_id:
        return {"status": "error", "channel": "telegram", "reason": "missing chat_id and no default set"}
    if not settings.telegram_bot_token:
        return {"status": "error", "channel": "telegram", "reason": "bot token not configured"}
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json={"chat_id": chat_id, "text": message})
            r.raise_for_status()
            return {"status": "ok", "channel": "telegram"}
    except httpx.HTTPStatusError as e:
        return {"status": "error", "channel": "telegram", "reason": e.response.text}
    except Exception as e:
        return {"status": "error", "channel": "telegram", "reason": str(e)}

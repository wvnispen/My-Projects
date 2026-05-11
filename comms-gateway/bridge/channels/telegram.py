import json
import httpx
from pathlib import Path
from config import settings

_CONTACTS_FILE = Path(__file__).parent.parent / "contacts.json"


def _resolve(to: str) -> str:
    if to and not to.lstrip("-").isdigit():
        try:
            contacts = json.loads(_CONTACTS_FILE.read_text())
            return contacts.get(to.lower(), to)
        except Exception:
            pass
    return to or settings.telegram_default_chat_id


async def send(to: str, message: str) -> dict:
    chat_id = _resolve(to)
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

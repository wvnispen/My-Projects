import httpx
from config import settings


async def send(to: str, message: str) -> dict:
    if not to:
        return {"status": "error", "channel": "sms", "reason": "missing 'to' number"}
    try:
        async with httpx.AsyncClient(timeout=settings.esp32_timeout) as client:
            r = await client.post(
                f"{settings.esp32_url}/send/sms",
                json={"to": to, "message": message},
            )
            r.raise_for_status()
            return {"status": "ok", "channel": "sms"}
    except httpx.ConnectError:
        return {"status": "error", "channel": "sms", "reason": "esp32_unreachable"}
    except httpx.TimeoutException:
        return {"status": "error", "channel": "sms", "reason": "esp32_timeout"}
    except Exception as e:
        return {"status": "error", "channel": "sms", "reason": str(e)}

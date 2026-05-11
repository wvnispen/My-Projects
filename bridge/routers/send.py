from fastapi import APIRouter, Depends
from pydantic import BaseModel
from middleware.auth import verify_api_key
from channels import sms, telegram, whatsapp

router = APIRouter()


class SendRequest(BaseModel):
    channel: str   # sms | telegram | whatsapp
    to: str = ""
    message: str


@router.post("/api/v1/send")
async def send_message(req: SendRequest, _=Depends(verify_api_key)):
    match req.channel:
        case "sms":
            return await sms.send(req.to, req.message)
        case "telegram":
            return await telegram.send(req.to, req.message)
        case "whatsapp":
            return await whatsapp.send(req.to, req.message)
        case _:
            return {"status": "error", "reason": f"unknown channel: {req.channel}"}

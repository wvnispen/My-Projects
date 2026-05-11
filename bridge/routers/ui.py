from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/")
@router.get("/ui")
async def serve_ui():
    return FileResponse("static/index.html")

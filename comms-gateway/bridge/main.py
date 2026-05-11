from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from routers import send, health, ui

app = FastAPI(
    title="CommsGateway",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(send.router)
app.include_router(health.router)
app.include_router(ui.router)

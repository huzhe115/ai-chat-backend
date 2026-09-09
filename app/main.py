from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, chats, tasks

app = FastAPI(title="AI Chat Backend", version="0.1.0")

app.include_router(auth.router)
app.include_router(chats.router)
app.include_router(tasks.router)

# 简易前端:浏览器打开 http://localhost:8000/ 就是聊天页
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse("static/index.html")

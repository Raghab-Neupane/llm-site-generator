from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from app.api.routes import router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

FRONTEND_PATH = (
    Path(__file__).resolve().parent.parent
    / "frontend" / "index.html"
)


@app.get("/", response_class=HTMLResponse)
async def root():
    return FRONTEND_PATH.read_text()
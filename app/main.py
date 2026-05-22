from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.api.routes import router
from app.api.authentication.auth_routes import router as auth_router


app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Main API routes
app.include_router(router)


# Authentication routes
app.include_router(
    auth_router,
    prefix="/auth",
    tags=["Authentication"]
)


FRONTEND_PATH = (
    Path(__file__).resolve().parent.parent
    / "frontend"
    / "index.html"
)


@app.get("/", response_class=HTMLResponse)
async def root():
    return FRONTEND_PATH.read_text()
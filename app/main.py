from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware

from app.credentials.auth_routes import router as auth_router
from app.api.routes import router as crawl_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(crawl_router)


@app.get("/")
def root():

    return {
        "message": "Backend Running"
    }
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.core.config import settings
from app.db.mongo import close_mongo_connection, connect_to_mongo


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    yield
    await close_mongo_connection()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")


@app.get("/")
async def root() -> dict:
    return {
        "message": "Yumigura API",
        "docs": "/docs",
        "health": "/api/v1/health",
    }

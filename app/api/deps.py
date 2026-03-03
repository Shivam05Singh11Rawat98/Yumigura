from motor.motor_asyncio import AsyncIOMotorCollection

from app.db.mongo import get_db


def get_user_collection() -> AsyncIOMotorCollection:
    return get_db()["users"]

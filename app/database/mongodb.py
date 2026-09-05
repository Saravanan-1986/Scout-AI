from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings


class Database:
    client: AsyncIOMotorClient | None = None


db = Database()


async def connect_to_mongo():
    db.client = AsyncIOMotorClient(settings.mongodb_uri)


async def close_mongo_connection():
    if db.client:
        db.client.close()


def get_database():
    if db.client is None:
        db.client = AsyncIOMotorClient(settings.mongodb_uri)
    return db.client[settings.mongodb_db_name]

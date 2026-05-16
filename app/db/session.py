import certifi
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_client() -> AsyncIOMotorClient:
    if _client is None:
        raise RuntimeError("MongoDB client is not initialized. Call init_db() first.")
    return _client


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("MongoDB database is not initialized. Call init_db() first.")
    return _db


async def init_db() -> None:
    """Initialize Motor client and register Beanie document models."""
    global _client, _db
    from app import models

    _client = AsyncIOMotorClient(
        settings.MONGODB_URL,
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=10_000,
    )
    _db = _client[settings.MONGODB_DB]
    await init_beanie(database=_db, document_models=models.__all_documents__)


async def close_db() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None

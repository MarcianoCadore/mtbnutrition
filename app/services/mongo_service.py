from motor.motor_asyncio import AsyncIOMotorClient
from config.settings import settings

_client: AsyncIOMotorClient | None = None

def get_db():
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGODB_URL)
    return _client["mtb_nutrition"]

import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from config.settings import settings

_client: AsyncIOMotorClient | None = None

def get_db():
    global _client
    if _client is None:
        kwargs = {}
        # Atlas (mongodb+srv / *.mongodb.net) exige TLS com a CA do certifi,
        # senão dá erro de certificado em alguns Linux (Amazon Linux/EC2).
        url = settings.MONGODB_URL
        if url.startswith("mongodb+srv://") or "mongodb.net" in url:
            kwargs["tlsCAFile"] = certifi.where()
        _client = AsyncIOMotorClient(url, **kwargs)
    return _client["mtb_nutrition"]

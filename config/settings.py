from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    GEMINI_API_KEY: str = ""
    MONGODB_URL: str = "mongodb://127.0.0.1:27017"
    # Z-API (WhatsApp)
    ZAPI_INSTANCE_ID: str = ""
    ZAPI_TOKEN: str = ""
    ZAPI_CLIENT_TOKEN: str = ""
    WHATSAPP_PHONE: str = ""
    # Garmin Connect
    GARMIN_EMAIL: str = ""
    GARMIN_PASSWORD: str = ""
    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    WHATSAPP_FROM: str = ""
    WHATSAPP_TO: str = ""
    # Content API — template aprovado para notificações proativas (fora da janela de 24h).
    # SID no formato HX... do template "passthrough" com 1 variável {{1}}.
    TWILIO_CONTENT_SID: str = ""

    class Config:
        env_file = ".env"

settings = Settings()

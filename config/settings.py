from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""  # fallback gratuito quando cota Claude esgota
    MONGODB_URL: str = "mongodb://127.0.0.1:27017"
    # Diretório onde os arquivos .fit são salvos. Em produção apontar para um
    # disco persistente (ex.: /opt/mtbnutrition/uploads/fit). Vazio = padrão local.
    UPLOADS_DIR: str = ""
    # Login do portal (legado, mantido para migração).
    # O novo auth usa users no banco; PORTAL_USER/PORTAL_PASSWORD não são mais
    # usados para validar login, apenas como fallback de SECRET_KEY.
    PORTAL_USER: str = "marciano"
    PORTAL_PASSWORD: str = ""
    # Chave secreta para assinar tokens de sessão.
    # Se vazio, cai no fallback: PORTAL_PASSWORD → "dev-secret-mtb".
    # Em produção, defina SECRET_KEY com um valor aleatório forte (ex.: openssl rand -hex 32).
    SECRET_KEY: str = ""
    # Minutos de inatividade até a sessão do portal expirar. O cookie é de sessão
    # (some ao fechar o navegador), mas navegadores que restauram a sessão revivem
    # o cookie — por isso o servidor também expira por tempo (renovado a cada
    # requisição). Reduza para deslogar mais rápido após fechar o navegador.
    PORTAL_SESSAO_MIN: int = 20
    # OTP de verificação de telefone por WhatsApp.
    OTP_EXPIRA_MIN: int = 10
    OTP_MAX_TENTATIVAS: int = 5
    # Z-API (WhatsApp)
    ZAPI_INSTANCE_ID: str = ""
    ZAPI_TOKEN: str = ""
    ZAPI_CLIENT_TOKEN: str = ""
    WHATSAPP_PHONE: str = ""
    # Garmin Connect
    GARMIN_EMAIL: str = ""
    GARMIN_PASSWORD: str = ""
    # Chave Fernet (base64 urlsafe, 32 bytes) para cifrar credenciais do Garmin.
    # Se vazio, crypto_service deriva uma chave determinística de SECRET_KEY (dev).
    # Em produção, gere com: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # ATENÇÃO: mudar a chave invalida todos os segredos já cifrados no banco.
    FERNET_KEY: str = ""
    # Strava OAuth2 (somente leitura de atividades — READ-ONLY).
    # Crie o app em https://www.strava.com/settings/api e preencha:
    #   STRAVA_CLIENT_ID     → "Client ID" exibido na página da API
    #   STRAVA_CLIENT_SECRET → "Client Secret" (clique em "show")
    #   STRAVA_REDIRECT_URI  → URL de callback registrada no app Strava,
    #                          ex.: "http://18.230.110.168:8000/workout/strava/callback"
    STRAVA_CLIENT_ID: str = ""
    STRAVA_CLIENT_SECRET: str = ""
    STRAVA_REDIRECT_URI: str = ""
    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    WHATSAPP_FROM: str = ""
    WHATSAPP_TO: str = ""
    # Content API — template aprovado para notificações proativas (fora da janela de 24h).
    # SID no formato HX... do template "passthrough" com 1 variável {{1}}.
    TWILIO_CONTENT_SID: str = ""
    # Valida a assinatura X-Twilio-Signature no webhook de entrada do WhatsApp.
    # Deixe True em produção; só desligue temporariamente para depurar.
    VALIDAR_TWILIO: bool = True

    class Config:
        env_file = ".env"

settings = Settings()

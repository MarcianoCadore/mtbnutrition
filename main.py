import secrets

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from contextlib import asynccontextmanager
from app.tasks.scheduler import start_scheduler, stop_scheduler
from app.routes import workout, nutrition, whatsapp, portal
from config.settings import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()

app = FastAPI(
    title="MTB Nutrition Bot",
    description="Plano alimentar inteligente para ciclistas MTB com notificações WhatsApp",
    version="1.0.0",
    lifespan=lifespan
)


# Paths liberados sem login (health check do load balancer / uptime monitor).
_PUBLIC_PATHS = {"/health"}


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    """Protege todo o portal com HTTP Basic. Se PORTAL_PASSWORD não estiver
    configurado, o acesso é liberado (modo dev local)."""
    if not settings.PORTAL_PASSWORD or request.url.path in _PUBLIC_PATHS:
        return await call_next(request)

    auth = request.headers.get("authorization", "")
    if auth.startswith("Basic "):
        import base64
        try:
            user, _, pwd = base64.b64decode(auth[6:]).decode("utf-8").partition(":")
        except Exception:
            user, pwd = "", ""
        ok_user = secrets.compare_digest(user, settings.PORTAL_USER)
        ok_pwd = secrets.compare_digest(pwd, settings.PORTAL_PASSWORD)
        if ok_user and ok_pwd:
            return await call_next(request)

    return Response(
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="MTB Nutrition"'},
        content="Não autorizado",
    )


app.include_router(portal.router,   prefix="/portal",    tags=["Portal"])
app.include_router(workout.router,  prefix="/workout",   tags=["Treinos"])
app.include_router(nutrition.router,prefix="/nutrition", tags=["Nutrição"])
app.include_router(whatsapp.router, prefix="/whatsapp",  tags=["WhatsApp"])

@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/portal/")

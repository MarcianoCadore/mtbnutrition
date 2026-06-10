from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
from app.tasks.scheduler import start_scheduler, stop_scheduler
from app.routes import workout, nutrition, whatsapp, portal

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

app.include_router(portal.router,   prefix="/portal",    tags=["Portal"])
app.include_router(workout.router,  prefix="/workout",   tags=["Treinos"])
app.include_router(nutrition.router,prefix="/nutrition", tags=["Nutrição"])
app.include_router(whatsapp.router, prefix="/whatsapp",  tags=["WhatsApp"])

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/portal/")

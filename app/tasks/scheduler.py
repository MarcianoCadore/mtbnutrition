from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
import pytz

from app.services.ai_service import gerar_plano_alimentar
from app.services.whatsapp_service import send_plano_diario, send_lembrete_refeicao
from app.services.mongo_service import get_db

TZ = pytz.timezone("America/Sao_Paulo")
scheduler = AsyncIOScheduler(timezone=TZ)

async def job_plano_diario():
    """Roda às 6h — gera e envia plano do dia"""
    print(f"[{datetime.now()}] Gerando plano alimentar do dia...")
    try:
        db = get_db()

        # Busca treino de hoje no MongoDB
        hoje = datetime.now(TZ).date()
        treino_doc = await db.treinos.find_one({
            "data": {
                "$gte": datetime(hoje.year, hoje.month, hoje.day),
                "$lt": datetime(hoje.year, hoje.month, hoje.day + 1) if hoje.day < 28 else datetime(hoje.year, hoje.month + 1, 1)
            }
        })

        treino = None
        if treino_doc:
            from app.models.models import Treino
            treino = Treino(**treino_doc)

        plano = await gerar_plano_alimentar(treino)

        # Salva no MongoDB
        await db.planos.insert_one(plano.model_dump())

        # Envia WhatsApp
        await send_plano_diario(plano)
        print(f"[{datetime.now()}] Plano enviado com sucesso!")

    except Exception as e:
        print(f"[{datetime.now()}] Erro no job_plano_diario: {e}")

async def job_lembrete_almoco():
    """Roda às 11h30 — lembrete de almoço"""
    try:
        db = get_db()
        hoje = datetime.now(TZ).date()
        plano_doc = await db.planos.find_one({"data": {"$gte": datetime(hoje.year, hoje.month, hoje.day)}})

        if plano_doc:
            refeicoes = plano_doc.get("refeicoes", [])
            almoco = next((r for r in refeicoes if "almoço" in r["nome"].lower() or "almoco" in r["nome"].lower()), None)
            if almoco:
                await send_lembrete_refeicao(almoco["nome"], almoco["itens"])
    except Exception as e:
        print(f"[{datetime.now()}] Erro no lembrete almoço: {e}")

async def job_lembrete_lanche():
    """Roda às 15h — lembrete de lanche"""
    try:
        db = get_db()
        hoje = datetime.now(TZ).date()
        plano_doc = await db.planos.find_one({"data": {"$gte": datetime(hoje.year, hoje.month, hoje.day)}})

        if plano_doc:
            refeicoes = plano_doc.get("refeicoes", [])
            lanche = next((r for r in refeicoes if "lanche" in r["nome"].lower()), None)
            if lanche:
                await send_lembrete_refeicao(lanche["nome"], lanche["itens"])
    except Exception as e:
        print(f"[{datetime.now()}] Erro no lembrete lanche: {e}")

async def job_lembrete_janta():
    """Roda às 20h — lembrete de janta"""
    try:
        db = get_db()
        hoje = datetime.now(TZ).date()
        plano_doc = await db.planos.find_one({"data": {"$gte": datetime(hoje.year, hoje.month, hoje.day)}})

        if plano_doc:
            refeicoes = plano_doc.get("refeicoes", [])
            janta = next((r for r in refeicoes if "janta" in r["nome"].lower()), None)
            if janta:
                await send_lembrete_refeicao(janta["nome"], janta["itens"])
    except Exception as e:
        print(f"[{datetime.now()}] Erro no lembrete janta: {e}")

async def job_garmin_sync():
    """Roda a cada 30 min — sincroniza treinos planejados e atividades do Garmin."""
    from config.settings import settings
    if not settings.GARMIN_EMAIL or not settings.GARMIN_PASSWORD:
        return
    try:
        from app.services.garmin_service import sync_treinos_planejados, sync_atividades
        hoje = datetime.now(TZ).date()
        seg = hoje - timedelta(days=hoje.weekday())
        semana = seg.isoformat()
        pl = await sync_treinos_planejados(semana)
        at = await sync_atividades(semana)
        if pl or at:
            print(f"[{datetime.now()}] Garmin sync: {pl} treinos planejados, {at} atividades")
    except Exception as e:
        print(f"[{datetime.now()}] Erro no job_garmin_sync: {e}")


def start_scheduler():
    scheduler.add_job(job_plano_diario,     CronTrigger(hour=6,  minute=0))
    scheduler.add_job(job_lembrete_almoco,  CronTrigger(hour=11, minute=30))
    scheduler.add_job(job_lembrete_lanche,  CronTrigger(hour=15, minute=0))
    scheduler.add_job(job_lembrete_janta,   CronTrigger(hour=20, minute=0))
    scheduler.add_job(job_garmin_sync,      IntervalTrigger(minutes=30))
    scheduler.start()
    print("✅ Scheduler iniciado — notificações + Garmin sync ativos")

def stop_scheduler():
    scheduler.shutdown()
    print("Scheduler encerrado")

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
import pytz

from app.services.whatsapp_service import send_lembrete_refeicao, send_message
from app.services.nutricao_service import plano_para_tipo, formatar_plano_whatsapp
from app.services.mongo_service import get_db
from config.settings import settings

TZ = pytz.timezone("America/Sao_Paulo")
scheduler = AsyncIOScheduler(timezone=TZ)

async def job_plano_diario():
    """Roda às 6h — envia o plano alimentar fixo do treino de hoje."""
    print(f"[{datetime.now()}] Enviando plano alimentar do dia...")
    try:
        db = get_db()

        # Tipo do treino de hoje a partir da semana salva (db.semanas)
        hoje = datetime.now(TZ).date()
        hoje_iso = hoje.isoformat()
        seg = hoje - timedelta(days=hoje.weekday())
        doc = await db.semanas.find_one({"semana_inicio": seg.isoformat()})

        tipo = "DESCANSO"
        if doc:
            for t in doc.get("treinos", []):
                if t.get("data") == hoje_iso:
                    tipo = t.get("tipo") or "DESCANSO"
                    break

        plano = plano_para_tipo(tipo)

        # Salva versão compatível com os lembretes de refeição (PlanoAlimentar)
        await db.planos.insert_one({
            "data": datetime.now(),
            "tipo_dia": plano["tipo"],
            "kcal_total": plano["kcal_total"],
            "proteina_total_g": plano["proteina_total_g"],
            "refeicoes": [
                {
                    "nome": r["nome"], "horario": r["horario"],
                    "itens": [i["texto"] for i in r["itens"]],
                    "kcal_estimado": r["kcal"], "proteina_g": r["proteina_g"],
                    "carbo_g": 0, "gordura_g": 0,
                }
                for r in plano["refeicoes"]
            ],
        })

        if settings.WHATSAPP_TO:
            await send_message(settings.WHATSAPP_TO, formatar_plano_whatsapp(hoje_iso, plano))
        print(f"[{datetime.now()}] Plano ({tipo}) enviado com sucesso!")

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
            lanche = next((r for r in refeicoes if "lanche" in r["nome"].lower() and "tarde" in r["nome"].lower()), None)
            lanche = lanche or next((r for r in refeicoes if "lanche" in r["nome"].lower()), None)
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

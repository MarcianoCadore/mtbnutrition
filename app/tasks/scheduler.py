from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
import pytz

from app.services.whatsapp_service import send_message
from app.services.nutricao_service import plano_para_tipo, formatar_plano_whatsapp, formatar_lembrete_refeicao
from app.services.config_service import get_horarios
from app.services.mongo_service import get_db
from config.settings import settings

TZ = pytz.timezone("America/Sao_Paulo")
scheduler = AsyncIOScheduler(timezone=TZ)

async def job_plano_diario():
    """Roda às 8h — envia o plano alimentar fixo do treino de hoje."""
    print(f"[{datetime.now()}] Enviando plano alimentar do dia...")
    try:
        db = get_db()

        # Tipo do treino de hoje a partir da semana salva (db.semanas)
        hoje = datetime.now(TZ).date()
        hoje_iso = hoje.isoformat()
        seg = hoje - timedelta(days=hoje.weekday())
        doc = await db.semanas.find_one({"semana_inicio": seg.isoformat()})

        tipo, periodo = "DESCANSO", None
        if doc:
            for t in doc.get("treinos", []):
                if t.get("data") == hoje_iso:
                    tipo = t.get("tipo") or "DESCANSO"
                    periodo = t.get("periodo")
                    break

        from app.services.config_service import get_horarios
        cfg = await get_horarios()
        plano = plano_para_tipo(tipo, hoje_iso, cfg, periodo=periodo)

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
                    "carbo_g": 0, "gordura_g": 0, "observacao": r.get("observacao"),
                }
                for r in plano["refeicoes"]
            ],
        })

        if settings.WHATSAPP_TO:
            await send_message(settings.WHATSAPP_TO, formatar_plano_whatsapp(hoje_iso, plano))
        print(f"[{datetime.now()}] Plano ({tipo}) enviado com sucesso!")

    except Exception as e:
        print(f"[{datetime.now()}] Erro no job_plano_diario: {e}")

async def _treino_hoje() -> tuple[str, str | None]:
    """(tipo, periodo) do treino de hoje a partir da semana salva; (DESCANSO, None)
    se não houver."""
    db = get_db()
    hoje_iso = datetime.now(TZ).date().isoformat()
    seg = datetime.now(TZ).date() - timedelta(days=datetime.now(TZ).date().weekday())
    doc = await db.semanas.find_one({"semana_inicio": seg.isoformat()})
    if doc:
        for t in doc.get("treinos", []):
            if t.get("data") == hoje_iso:
                return (t.get("tipo") or "DESCANSO", t.get("periodo"))
    return "DESCANSO", None


# Refeições para lembrete (chave de horário na config -> nome no cardápio).
LEMBRETES_REFEICAO = [
    ("cafe", "Café da manhã"),
    ("lanche_manha", "Lanche da manhã"),
    ("almoco", "Almoço"),
    ("lanche_tarde", "Lanche da tarde"),
    ("jantar", "Jantar"),
]


async def enviar_lembrete_refeicao_pre(meal_nome: str):
    """Envia, 30 min antes, o que comer na refeição do dia."""
    try:
        hoje_iso = datetime.now(TZ).date().isoformat()
        tipo, periodo = await _treino_hoje()
        cfg = await get_horarios()
        plano = plano_para_tipo(tipo, hoje_iso, cfg, periodo=periodo)
        ref = next((r for r in plano["refeicoes"] if r["nome"] == meal_nome), None)
        if ref and settings.WHATSAPP_TO:
            await send_message(settings.WHATSAPP_TO, formatar_lembrete_refeicao(ref))
            print(f"[{datetime.now()}] Lembrete enviado: {meal_nome}")
    except Exception as e:
        print(f"[{datetime.now()}] Erro no lembrete {meal_nome}: {e}")


async def agendar_lembretes_refeicao():
    """(Re)agenda os lembretes para 30 min antes de cada refeição, conforme a
    config de horários. Chamado no start, periodicamente (auto-cura se o banco
    estava fora no boot) e quando o usuário muda os horários."""
    try:
        cfg = await get_horarios()
    except Exception as e:
        print(f"[{datetime.now()}] Banco indisponível; lembretes não reagendados (tenta de novo): {e}")
        return
    n = 0
    for chave, nome in LEMBRETES_REFEICAO:
        try:
            h, m = map(int, cfg[chave].split(":"))
        except (KeyError, ValueError):
            continue
        total = (h * 60 + m - 30) % (24 * 60)   # 30 min antes
        scheduler.add_job(
            enviar_lembrete_refeicao_pre,
            CronTrigger(hour=total // 60, minute=total % 60, timezone=TZ),
            args=[nome],
            id=f"lembrete_{chave}",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        n += 1
    print(f"🍽️ Lembretes de refeição agendados ({n} refeições, 30 min antes)")

async def job_garmin_sync():
    """Roda a cada 10 min — sincroniza treinos planejados e atividades do Garmin."""
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
    scheduler.add_job(
        job_plano_diario,
        CronTrigger(hour=8, minute=0, timezone=TZ),
        id="plano_diario",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        job_garmin_sync,
        IntervalTrigger(minutes=10),
        id="garmin_sync",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    # Agenda os lembretes uma única vez no boot (3s de atraso para o banco subir).
    # Re-agendamento acontece apenas quando o usuário altera os horários via /nutrition/horarios.
    scheduler.add_job(
        agendar_lembretes_refeicao,
        "date",
        id="boot_lembretes",
        run_date=datetime.now(TZ) + timedelta(seconds=3),
        replace_existing=True,
        misfire_grace_time=120,
    )
    print("✅ Scheduler iniciado — notificações + Garmin sync ativos")

def stop_scheduler():
    scheduler.shutdown()
    print("Scheduler encerrado")

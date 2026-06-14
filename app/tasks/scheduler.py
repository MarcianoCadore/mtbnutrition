import asyncio
import logging

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
logger = logging.getLogger(__name__)

async def _usuarios_ativos() -> list[dict]:
    """Usuários com telefone e WhatsApp ativo (aptos a receber notificações)."""
    from app.services.user_service import listar_usuarios
    todos = await listar_usuarios()
    return [u for u in todos
            if u.get("telefone") and (u.get("whatsapp") or {}).get("ativo")]


def _quer_nutricao(u: dict) -> bool:
    """Plano alimentar e lembretes de refeição só para quem quer perder peso."""
    return bool((u.get("preferencias") or {}).get("perder_peso"))


async def _enviar_plano_diario_usuario(u: dict) -> None:
    """Monta e envia o plano alimentar do dia para UM usuário (se quer nutrição)."""
    if not _quer_nutricao(u):
        return
    user_id = str(u["_id"])
    telefone = u.get("telefone")
    db = get_db()

    hoje = datetime.now(TZ).date()
    hoje_iso = hoje.isoformat()
    seg = hoje - timedelta(days=hoje.weekday())
    doc = await db.semanas.find_one({"semana_inicio": seg.isoformat(), "user_id": user_id})

    tipo, periodo = "DESCANSO", None
    if doc:
        for t in doc.get("treinos", []):
            if t.get("data") == hoje_iso:
                tipo = t.get("tipo") or "DESCANSO"
                periodo = t.get("periodo")
                break

    from app.services.config_service import get_horarios, ajuste_do_dia
    cfg = await get_horarios(user_id)
    ajuste = await ajuste_do_dia(user_id, hoje_iso)
    plano = plano_para_tipo(tipo, hoje_iso, cfg, periodo=periodo,
                            extras=ajuste["extras"], corte_kcal=ajuste["corte_kcal"])

    # Salva versão compatível com os lembretes de refeição (PlanoAlimentar)
    await db.planos.insert_one({
        "data": datetime.now(),
        "user_id": user_id,
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

    if telefone:
        await send_message(telefone, formatar_plano_whatsapp(hoje_iso, plano))


async def job_plano_diario():
    """Roda às 8h — envia o plano alimentar do dia para cada usuário ativo."""
    print(f"[{datetime.now()}] Enviando plano alimentar do dia...")
    usuarios = await _usuarios_ativos()
    enviados = 0
    for u in usuarios:
        try:
            antes = _quer_nutricao(u)
            await _enviar_plano_diario_usuario(u)
            if antes:
                enviados += 1
                await asyncio.sleep(1)   # throttle p/ não estourar a Twilio
        except Exception as e:
            logger.error("job_plano_diario p/ %s: %s", u.get("login"), e)
    print(f"[{datetime.now()}] Plano diário enviado para {enviados} usuário(s).")

async def _treino_hoje(user_id: str) -> tuple[str, str | None]:
    """(tipo, periodo) do treino de hoje a partir da semana salva; (DESCANSO, None)
    se não houver."""
    db = get_db()
    hoje_iso = datetime.now(TZ).date().isoformat()
    seg = datetime.now(TZ).date() - timedelta(days=datetime.now(TZ).date().weekday())
    doc = await db.semanas.find_one({"semana_inicio": seg.isoformat(), "user_id": user_id})
    if doc:
        for t in doc.get("treinos", []):
            if t.get("data") == hoje_iso:
                return (t.get("tipo") or "DESCANSO", t.get("periodo"))
    return "DESCANSO", None


# Refeições para lembrete (chave de horário na config -> nome no cardápio).
LEMBRETES_REFEICAO = [
    ("cafe", "Café da manhã"),
    ("almoco", "Almoço"),
    ("lanche_tarde", "Lanche da tarde"),
    ("jantar", "Jantar"),
]


async def enviar_lembrete_refeicao_pre(user_id: str, meal_nome: str):
    """Envia, 30 min antes, o que comer na refeição do dia, para UM usuário."""
    try:
        from app.services.user_service import get_por_id
        u = await get_por_id(user_id)
        if not u or not _quer_nutricao(u):
            return
        telefone = u.get("telefone")
        if not telefone:
            return
        hoje_iso = datetime.now(TZ).date().isoformat()
        tipo, periodo = await _treino_hoje(user_id)
        cfg = await get_horarios(user_id)
        plano = plano_para_tipo(tipo, hoje_iso, cfg, periodo=periodo)
        ref = next((r for r in plano["refeicoes"] if r["nome"] == meal_nome), None)
        if ref:
            await send_message(telefone, formatar_lembrete_refeicao(ref))
            print(f"[{datetime.now()}] Lembrete enviado ({u.get('login')}): {meal_nome}")
    except Exception as e:
        print(f"[{datetime.now()}] Erro no lembrete {meal_nome} (user={user_id}): {e}")


async def agendar_lembretes_refeicao():
    """(Re)agenda os lembretes de refeição para CADA usuário ativo que quer
    nutrição, conforme os horários dele. Job ids namespaced por user_id.
    Chamado no start, e quando um usuário muda os horários."""
    try:
        usuarios = [u for u in await _usuarios_ativos() if _quer_nutricao(u)]
    except Exception as e:
        print(f"[{datetime.now()}] Banco indisponível; lembretes não reagendados (tenta de novo): {e}")
        return
    n_jobs = 0
    for u in usuarios:
        user_id = str(u["_id"])
        try:
            cfg = await get_horarios(user_id)
        except Exception:
            continue
        for chave, nome in LEMBRETES_REFEICAO:
            try:
                h, m = map(int, cfg[chave].split(":"))
            except (KeyError, ValueError):
                continue
            total = (h * 60 + m - 30) % (24 * 60)   # 30 min antes
            scheduler.add_job(
                enviar_lembrete_refeicao_pre,
                CronTrigger(hour=total // 60, minute=total % 60, timezone=TZ),
                args=[user_id, nome],
                id=f"lembrete_{user_id}_{chave}",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
            )
            n_jobs += 1
    print(f"🍽️ Lembretes de refeição agendados ({n_jobs} job(s) p/ {len(usuarios)} usuário(s))")

async def job_garmin_sync():
    """Roda a cada 10 min — sincroniza treinos planejados e atividades do Garmin.
    Fase 2: itera todos os usuários que têm integracao.tipo == "garmin".
    Um erro em um usuário não derruba os demais (try/except por usuário)."""
    from app.services.garmin_service import sync_treinos_planejados, sync_atividades
    from app.services.user_service import listar_usuarios

    todos = await listar_usuarios()
    # Filtra apenas quem tem Garmin configurado
    com_garmin = [
        u for u in todos
        if (u.get("integracao") or {}).get("tipo") == "garmin"
    ]

    if not com_garmin:
        # Nenhum usuário com Garmin — sai sem log de erro
        return

    hoje = datetime.now(TZ).date()
    seg = hoje - timedelta(days=hoje.weekday())
    semana = seg.isoformat()

    for u in com_garmin:
        user_id = str(u["_id"])
        try:
            pl = await sync_treinos_planejados(user_id, semana)
            at = await sync_atividades(user_id, semana)
            if pl or at:
                print(
                    f"[{datetime.now()}] Garmin sync ({u.get('login')}): "
                    f"{pl} treinos planejados, {at} atividades"
                )
        except Exception as e:
            # Não derruba outros usuários — loga e segue
            logger.error(
                "job_garmin_sync: erro para user_id=%s (%s) — %s",
                user_id, u.get("login"), e,
            )


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

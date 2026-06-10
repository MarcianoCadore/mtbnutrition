import os
import zipfile
import io
import logging
from datetime import datetime, timedelta

from garminconnect import Garmin

from config.settings import settings
from app.services.mongo_service import get_db
from app.services.fit_service import analisar_fit

logger = logging.getLogger(__name__)

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "fit")
TOKEN_DIR = os.path.expanduser("~/.garth_mtb")

_client: Garmin | None = None


def get_garmin_client() -> Garmin:
    global _client
    if _client is not None:
        return _client

    api = Garmin(settings.GARMIN_EMAIL, settings.GARMIN_PASSWORD)

    if os.path.isdir(TOKEN_DIR):
        try:
            api.login(tokenstore=TOKEN_DIR)
            _client = api
            logger.info("Garmin: login via token cacheado")
            return _client
        except Exception:
            logger.warning("Garmin: token expirado, re-autenticando")

    api.login()
    os.makedirs(TOKEN_DIR, exist_ok=True)
    try:
        api.garth.dump(TOKEN_DIR)
    except Exception:
        pass
    _client = api
    logger.info("Garmin: login com credenciais")
    return _client


def _semana_de(data: str) -> str:
    d = datetime.strptime(data, "%Y-%m-%d").date()
    return (d - timedelta(days=d.weekday())).isoformat()


def _extrair_fit_do_zip(data: bytes) -> bytes | None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                if name.lower().endswith(".fit"):
                    return z.read(name)
    except Exception:
        pass
    # pode vir como .fit direto
    if data[:4] == b'.FIT' or len(data) > 12:
        return data
    return None


async def sync_treinos_planejados(semana_inicio: str) -> int:
    """Busca treinos planejados no calendário Garmin e insere no MongoDB."""
    api = get_garmin_client()
    d0 = datetime.strptime(semana_inicio, "%Y-%m-%d").date()
    d1 = d0 + timedelta(days=6)

    importados = 0
    meses = set()
    cur = d0
    while cur <= d1:
        meses.add((cur.year, cur.month))
        cur += timedelta(days=31)
        cur = cur.replace(day=1)

    db = get_db()

    for year, month in meses:
        try:
            raw = api.get_scheduled_workouts(year, month)
        except Exception as e:
            logger.error("Garmin scheduled_workouts error: %s", e)
            continue

        # A resposta pode ser dict com 'calendarItems' ou lista
        items = []
        if isinstance(raw, dict):
            items = raw.get("calendarItems") or raw.get("calendarItems", [])
            if not items:
                # tenta navegar pela estrutura
                for v in raw.values():
                    if isinstance(v, list):
                        items = v
                        break
        elif isinstance(raw, list):
            items = raw

        for item in items:
            date_str = (
                item.get("date")
                or item.get("startDate")
                or item.get("scheduledDate")
                or ""
            )[:10]
            if not date_str or not (d0.isoformat() <= date_str <= d1.isoformat()):
                continue

            workout_id = str(
                item.get("workoutId") or item.get("id") or ""
            )
            nome = (
                item.get("title")
                or item.get("workoutName")
                or item.get("name")
                or ""
            )
            duracao_s = item.get("estimatedDurationInSecs") or item.get("duration") or 0
            duracao_min = round(int(duracao_s) / 60) if duracao_s else None

            semana = _semana_de(date_str)
            doc = await db.semanas.find_one({"semana_inicio": semana})

            treino_entry = {
                "data": date_str,
                "tipo": "Z2_LONGO",
                "descricao": nome,
                "duracao_min": duracao_min,
                "garmin_workout_id": workout_id,
            }

            if not doc:
                await db.semanas.insert_one({
                    "semana_inicio": semana,
                    "objetivo": "",
                    "treinos": [treino_entry],
                })
                importados += 1
            else:
                existe = any(t.get("data") == date_str for t in doc.get("treinos", []))
                if not existe:
                    await db.semanas.update_one(
                        {"semana_inicio": semana},
                        {"$push": {"treinos": treino_entry}},
                    )
                    importados += 1
                else:
                    # atualiza apenas garmin_workout_id se ainda não tiver
                    for t in doc.get("treinos", []):
                        if t.get("data") == date_str and not t.get("garmin_workout_id"):
                            await db.semanas.update_one(
                                {"semana_inicio": semana, "treinos.data": date_str},
                                {"$set": {
                                    "treinos.$.garmin_workout_id": workout_id,
                                    "treinos.$.descricao": t.get("descricao") or nome,
                                }},
                            )

    return importados


async def sync_atividades(semana_inicio: str) -> int:
    """Busca atividades completadas no Garmin e salva como resultado."""
    api = get_garmin_client()
    d0 = datetime.strptime(semana_inicio, "%Y-%m-%d").date()
    d1 = d0 + timedelta(days=6)

    try:
        atividades = api.get_activities_by_date(
            d0.isoformat(), d1.isoformat(), "cycling"
        )
    except Exception as e:
        logger.error("Garmin get_activities_by_date error: %s", e)
        return 0

    db = get_db()
    processadas = 0

    for act in atividades:
        start_local = act.get("startTimeLocal") or ""
        act_date = start_local[:10]
        if not act_date or not (d0.isoformat() <= act_date <= d1.isoformat()):
            continue

        act_id = str(act.get("activityId", ""))
        semana = _semana_de(act_date)

        # verifica se já foi processada — pula a atividade inteira se sim
        doc = await db.semanas.find_one({"semana_inicio": semana})
        ja_processada = doc and any(
            t.get("data") == act_date
            and t.get("resultado", {}).get("garmin_activity_id") == act_id
            for t in doc.get("treinos", [])
        )
        if ja_processada:
            continue

        # download do .fit
        try:
            raw_bytes = api.download_activity(
                act_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL
            )
        except Exception as e:
            logger.error("Garmin download_activity %s error: %s", act_id, e)
            continue

        fit_bytes = _extrair_fit_do_zip(raw_bytes)
        if not fit_bytes:
            logger.warning("Garmin: não foi possível extrair .fit da atividade %s", act_id)
            continue

        dest_dir = os.path.join(UPLOADS_DIR, semana)
        os.makedirs(dest_dir, exist_ok=True)
        fit_filename = f"{act_date}_resultado.fit"
        fit_path = os.path.join(dest_dir, fit_filename)
        with open(fit_path, "wb") as f:
            f.write(fit_bytes)

        analise = analisar_fit(fit_path)

        resultado = {
            "garmin_activity_id": act_id,
            "fit_file": fit_filename,
            "duracao_min": analise.get("duracao_min"),
            "distancia_km": analise.get("distancia_km"),
            "elevacao_m": analise.get("elevacao_m"),
            "avg_hr": analise.get("avg_hr"),
            "max_hr": analise.get("max_hr"),
            "calorias": analise.get("calorias"),
        }

        # busca treino planejado para comparação
        treino_planejado = {}
        if doc:
            for t in doc.get("treinos", []):
                if t.get("data") == act_date:
                    treino_planejado = t
                    break

        # análise IA
        try:
            from app.services.ai_service import analisar_atividade_pos_treino
            analise_ia = await analisar_atividade_pos_treino(treino_planejado, resultado)
            resultado["analise_ia"] = analise_ia
        except Exception as e:
            logger.error("IA pós-treino error: %s", e)

        tipo_real = analise.get("tipo", "Z2_LONGO")

        # salva no MongoDB
        if not doc:
            await db.semanas.insert_one({
                "semana_inicio": semana,
                "objetivo": "",
                "treinos": [{
                    "data": act_date,
                    "tipo": tipo_real,
                    "resultado": resultado,
                }],
            })
        else:
            existe = any(t.get("data") == act_date for t in doc.get("treinos", []))
            if existe:
                await db.semanas.update_one(
                    {"semana_inicio": semana, "treinos.data": act_date},
                    {"$set": {
                        "treinos.$.resultado": resultado,
                        "treinos.$.tipo": tipo_real,
                    }},
                )
            else:
                await db.semanas.update_one(
                    {"semana_inicio": semana},
                    {"$push": {"treinos": {
                        "data": act_date,
                        "tipo": tipo_real,
                        "resultado": resultado,
                    }}},
                )

        # WhatsApp
        try:
            from app.services.whatsapp_service import send_message
            if settings.WHATSAPP_TO and resultado.get("analise_ia"):
                msg = _formatar_pos_treino(act_date, treino_planejado, resultado)
                await send_message(settings.WHATSAPP_TO, msg)
        except Exception as e:
            logger.error("WhatsApp pós-treino error: %s", e)

        processadas += 1

    return processadas


def _formatar_pos_treino(data: str, planejado: dict, resultado: dict) -> str:
    d = datetime.strptime(data, "%Y-%m-%d")
    dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    dia = dias[d.weekday()]
    data_fmt = d.strftime("%d/%m/%Y")
    analise = resultado.get("analise_ia", {})

    linhas = [f"🚵 *Pós-treino — {dia}, {data_fmt}*", ""]

    if analise.get("resumo"):
        linhas += [f"_{analise['resumo']}_", ""]

    if analise.get("pontos_fortes"):
        linhas.append("✅ *Pontos fortes:*")
        for p in analise["pontos_fortes"]:
            linhas.append(f"  • {p}")
        linhas.append("")

    if analise.get("pontos_fracos"):
        linhas.append("⚠️ *A melhorar:*")
        for p in analise["pontos_fracos"]:
            linhas.append(f"  • {p}")
        linhas.append("")

    dur = resultado.get("duracao_min")
    if dur:
        h, m = divmod(dur, 60)
        linhas.append(f"⏱ Duração: {h}h{m:02d}min")
    if resultado.get("distancia_km"):
        linhas.append(f"📍 Distância: {resultado['distancia_km']} km")
    if resultado.get("avg_hr"):
        linhas.append(f"❤️ FC média: {resultado['avg_hr']} bpm")
    if resultado.get("max_hr"):
        linhas.append(f"🔥 FC máx: {resultado['max_hr']} bpm")
    if resultado.get("calorias"):
        linhas.append(f"🔋 Calorias: {resultado['calorias']} kcal")

    if planejado.get("duracao_min"):
        linhas += ["", f"📋 Planejado: {planejado['duracao_min']} min · {planejado.get('tipo','')}"]

    linhas += ["", "_MTB Nutrition Bot 🤖_"]
    return "\n".join(linhas)

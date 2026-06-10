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
    """Busca treinos planejados no calendário Garmin e faz upsert no MongoDB."""
    api = get_garmin_client()
    d0 = datetime.strptime(semana_inicio, "%Y-%m-%d").date()
    d1 = d0 + timedelta(days=6)

    meses = set()
    cur = d0
    while cur <= d1:
        meses.add((cur.year, cur.month))
        cur += timedelta(days=31)
        cur = cur.replace(day=1)

    db = get_db()

    # Snapshot do estado ANTES do sync, para detectar mudanças nos dias de treino.
    # Indexado por garmin_workout_id -> {data, nome}.
    doc_antes = await db.semanas.find_one({"semana_inicio": semana_inicio})
    antes = {}
    if doc_antes:
        for t in doc_antes.get("treinos", []):
            wid = t.get("garmin_workout_id")
            if wid:
                antes[wid] = {"data": t.get("data"), "nome": (t.get("descricao") or "").split("\n")[0]}

    # Coleta todos os workouts da semana antes de processar
    all_workouts = []
    for year, month in meses:
        try:
            raw = api.get_scheduled_workouts(year, month)
        except Exception as e:
            logger.error("Garmin scheduled_workouts error: %s", e)
            continue

        calendar_items = []
        if isinstance(raw, dict):
            calendar_items = raw.get("calendarItems") or []
        elif isinstance(raw, list):
            calendar_items = raw

        workouts = [
            item for item in calendar_items
            if item.get("itemType") == "workout"
            and d0.isoformat() <= (item.get("date") or "")[:10] <= d1.isoformat()
        ]
        all_workouts.extend(workouts)

    logger.info("Garmin semana %s: %d workout(s) planejado(s)", semana_inicio, len(all_workouts))

    # Mapa workout_id -> {data, nome} atual no Garmin (para detectar workouts movidos)
    garmin_info = {
        str(item["workoutId"]): {"data": item["date"][:10], "nome": item.get("title") or ""}
        for item in all_workouts
        if item.get("workoutId")
    }
    garmin_id_para_data = {wid: info["data"] for wid, info in garmin_info.items()}

    sincronizados = 0
    for item in all_workouts:
        date_str = item["date"][:10]
        workout_id = str(item.get("workoutId") or "")
        nome = item.get("title") or ""

        duracao_min = None
        cadencia_rpm = None
        notas = nome

        if workout_id:
            try:
                wk = api.get_workout_by_id(int(workout_id))
                dur_secs = wk.get("estimatedDurationInSecs")
                if dur_secs:
                    duracao_min = max(1, round(dur_secs / 60))
                cads = _extrair_cadencias(wk)
                if cads:
                    cadencia_rpm = cads[0]
                desc = (wk.get("description") or "").strip()
                if desc:
                    notas = f"{nome}\n{desc}".strip() if nome and nome != desc else desc
            except Exception as e:
                logger.warning("Garmin get_workout_by_id %s: %s", workout_id, e)

        if cadencia_rpm is None:
            from app.services.ai_service import extrair_cadencia_texto
            cadencia_rpm = extrair_cadencia_texto(notas)

        semana = _semana_de(date_str)
        doc = await db.semanas.find_one({"semana_inicio": semana})

        tipo_planejado = "Z2_LONGO"
        if nome:
            try:
                from app.services.ai_service import classificar_tipo_treino
                tipo_planejado = await classificar_tipo_treino({
                    "workout_name": nome,
                    "duracao_min": duracao_min,
                    "descricao_existente": notas,
                })
            except Exception:
                pass

        treino_entry = {
            "data": date_str,
            "tipo": tipo_planejado,
            "descricao": notas,
            "garmin_workout_id": workout_id,
        }
        if duracao_min is not None:
            treino_entry["duracao_min"] = duracao_min
        if cadencia_rpm is not None:
            treino_entry["cadencia_rpm"] = cadencia_rpm

        if not doc:
            await db.semanas.insert_one({
                "semana_inicio": semana,
                "objetivo": "",
                "treinos": [treino_entry],
            })
        else:
            existe = any(t.get("data") == date_str for t in doc.get("treinos", []))
            if not existe:
                await db.semanas.update_one(
                    {"semana_inicio": semana},
                    {"$push": {"treinos": treino_entry}},
                )
            else:
                set_fields = {
                    "treinos.$.garmin_workout_id": workout_id,
                    "treinos.$.tipo": tipo_planejado,
                    "treinos.$.descricao": notas,
                }
                if duracao_min is not None:
                    set_fields["treinos.$.duracao_min"] = duracao_min
                if cadencia_rpm is not None:
                    set_fields["treinos.$.cadencia_rpm"] = cadencia_rpm
                await db.semanas.update_one(
                    {"semana_inicio": semana, "treinos.data": date_str},
                    {"$set": set_fields},
                )
        sincronizados += 1

    # Remove entradas de treinos que foram movidos para outra data no Garmin
    doc = await db.semanas.find_one({"semana_inicio": semana_inicio})
    if doc:
        for treino in doc.get("treinos", []):
            wid = treino.get("garmin_workout_id")
            if not wid or wid not in garmin_id_para_data:
                continue
            data_atual_garmin = garmin_id_para_data[wid]
            if treino.get("data") != data_atual_garmin:
                logger.info(
                    "Garmin: workout %s movido de %s para %s — removendo entrada antiga",
                    wid, treino["data"], data_atual_garmin,
                )
                await db.semanas.update_one(
                    {"semana_inicio": semana_inicio},
                    {"$pull": {"treinos": {"garmin_workout_id": wid, "data": treino["data"]}}},
                )

    # Detecta mudanças nos dias de treino e notifica no WhatsApp
    mudancas = []
    for wid, info in garmin_info.items():
        if wid not in antes:
            mudancas.append({"tipo": "novo", "data": info["data"], "nome": info["nome"]})
        elif antes[wid]["data"] != info["data"]:
            mudancas.append({
                "tipo": "movido", "de": antes[wid]["data"],
                "para": info["data"], "nome": info["nome"] or antes[wid]["nome"],
            })
    for wid, info in antes.items():
        if wid not in garmin_info:
            mudancas.append({"tipo": "removido", "data": info["data"], "nome": info["nome"]})

    if mudancas:
        try:
            from app.services.whatsapp_service import send_message
            if settings.WHATSAPP_TO:
                await send_message(settings.WHATSAPP_TO, _formatar_mudancas_treino(mudancas))
        except Exception as e:
            logger.error("WhatsApp mudanças de treino error: %s", e)

    return sincronizados


def _data_br(data_iso: str) -> str:
    """'2026-06-13' -> 'Sábado, 13/06'"""
    d = datetime.strptime(data_iso, "%Y-%m-%d")
    dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    return f"{dias[d.weekday()]}, {d.strftime('%d/%m')}"


def _formatar_mudancas_treino(mudancas: list[dict]) -> str:
    linhas = ["🚵 *Treinos atualizados*", ""]
    for m in mudancas:
        nome = m.get("nome") or "Treino"
        if m["tipo"] == "novo":
            linhas.append(f"➕ Novo: {_data_br(m['data'])} — {nome}")
        elif m["tipo"] == "movido":
            linhas.append(f"🔄 Movido: {_data_br(m['de'])} → {_data_br(m['para'])} — {nome}")
        elif m["tipo"] == "removido":
            linhas.append(f"➖ Removido: {_data_br(m['data'])} — {nome}")
    linhas += ["", "_MTB Nutrition Bot 🤖_"]
    return "\n".join(linhas)


def _extrair_cadencias(wk: dict) -> list[str]:
    """Extrai targets de cadência das etapas do workout Garmin."""
    cadencias = []
    for seg in wk.get("workoutSegments") or []:
        for step in seg.get("workoutSteps") or []:
            tgt_key = (step.get("targetType") or {}).get("workoutTargetTypeKey", "")
            if "cadence" in tgt_key.lower():
                v1 = step.get("targetValueOne")
                v2 = step.get("targetValueTwo")
                if v1 and v2 and abs(v1 - v2) > 1:
                    cadencias.append(f"{int(v1)}-{int(v2)}")
                elif v1:
                    cadencias.append(str(int(v1)))
    return cadencias


_CYCLING_TYPES = {
    "cycling", "mountain_biking", "road_biking", "gravel_cycling",
    "indoor_cycling", "virtual_ride", "bmx", "bike",
}


def _is_cycling(act: dict) -> bool:
    type_key = (act.get("activityType") or {}).get("typeKey", "")
    return any(k in type_key.lower() for k in ("cycl", "bike", "mtb", "mountain"))


async def sync_atividades(semana_inicio: str) -> int:
    """Busca atividades completadas no Garmin e salva como resultado."""
    api = get_garmin_client()
    d0 = datetime.strptime(semana_inicio, "%Y-%m-%d").date()
    d1 = d0 + timedelta(days=6)

    try:
        todas = api.get_activities_by_date(d0.isoformat(), d1.isoformat())
        atividades = [a for a in (todas or []) if _is_cycling(a)]
        logger.info("Garmin atividades encontradas: %d (todas) / %d (bike)", len(todas or []), len(atividades))
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
            and (t.get("resultado") or {}).get("garmin_activity_id") == act_id
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

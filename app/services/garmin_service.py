import os
import zipfile
import io
import asyncio
import logging
from datetime import datetime, timedelta

from garminconnect import Garmin

from config.settings import settings
from app.services.mongo_service import get_db
from app.services.fit_service import analisar_fit

logger = logging.getLogger(__name__)

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "fit")
# Diretório raiz dos tokens. Cada usuário ganha um subdiretório: TOKEN_DIR/<user_id>/
TOKEN_DIR = os.path.expanduser("~/.garth_mtb")

# Cache de clientes autenticados, indexado por user_id (string).
# Evita re-login a cada chamada sem manter um singleton global.
_clients: dict[str, Garmin] = {}


async def get_garmin_client(user_id: str) -> Garmin:
    """Retorna (e inicializa se necessário) um cliente Garmin autenticado para o usuário.

    Estratégia de credenciais:
    1. Lê `integracao.garmin` do doc do usuário no banco (email + senha cifrada).
    2. Back-compat: se o usuário não tem credenciais Garmin mas é o usuário
       configurado em settings.PORTAL_USER e settings.GARMIN_EMAIL/PASSWORD existem,
       usa as credenciais globais — para o Marciano continuar funcionando antes de
       reconectar pelo novo fluxo.
    3. Se nenhuma credencial encontrada → levanta ValueError.

    Tokenstore por usuário: TOKEN_DIR/<user_id>/
    """
    if user_id in _clients:
        return _clients[user_id]

    from app.services.user_service import get_por_id
    from app.services.crypto_service import decifrar

    u = await get_por_id(user_id)
    integracao = (u or {}).get("integracao") or {}
    garmin_cfg = integracao.get("garmin") or {}

    email = garmin_cfg.get("email") or ""
    senha = decifrar(garmin_cfg.get("senha_cifrada") or "") if garmin_cfg.get("senha_cifrada") else ""

    # Back-compat: Marciano ainda sem credenciais no banco → usa as globais
    if not (email and senha):
        login = (u or {}).get("login") or ""
        if login == settings.PORTAL_USER and settings.GARMIN_EMAIL and settings.GARMIN_PASSWORD:
            email = settings.GARMIN_EMAIL
            senha = settings.GARMIN_PASSWORD
            logger.info(
                "Garmin: usando credenciais globais para o usuário '%s' (back-compat)",
                login,
            )

    if not (email and senha):
        raise ValueError(
            f"Usuário {user_id} não tem Garmin conectado. "
            "Configure a integração em /workout/garmin/conectar."
        )

    # Tokenstore exclusivo por usuário
    token_dir = os.path.join(TOKEN_DIR, user_id)
    os.makedirs(token_dir, exist_ok=True)

    api = Garmin(email, senha)

    if os.path.isdir(token_dir) and os.listdir(token_dir):
        try:
            api.login(tokenstore=token_dir)
            _clients[user_id] = api
            logger.info("Garmin: login via token cacheado (user_id=%s)", user_id)
            return _clients[user_id]
        except Exception:
            logger.warning(
                "Garmin: token expirado para user_id=%s, re-autenticando", user_id
            )

    api.login()
    try:
        api.garth.dump(token_dir)
    except Exception:
        pass
    _clients[user_id] = api
    logger.info("Garmin: login com credenciais (user_id=%s)", user_id)
    return _clients[user_id]


def _semana_de(data: str) -> str:
    d = datetime.strptime(data, "%Y-%m-%d").date()
    return (d - timedelta(days=d.weekday())).isoformat()


async def zonas_do_garmin(user_id: str, sport: str = "CYCLING") -> dict:
    """Lê as zonas de FC oficiais do dispositivo direto da API do Garmin.

    Prefere o perfil do esporte pedido (ciclismo), caindo no DEFAULT. Retorna
    {"fc_max", "limiar", "zonas": [{"zona","min","max"}, ...]} — mesmo formato da
    extração por imagem. Os 'floors' do Garmin viram faixas: cada zona vai do seu
    floor até (floor da próxima - 1); a Z5 vai do floor 5 até a FC máxima.
    """
    api = await get_garmin_client(user_id)

    def _fetch():
        return api.connectapi("/biometric-service/heartRateZones")

    dados = await asyncio.to_thread(_fetch)
    if not dados:
        raise ValueError("O Garmin não retornou zonas de FC.")

    escolha = next((d for d in dados if (d.get("sport") or "").upper() == sport.upper()), None)
    if escolha is None:
        escolha = next((d for d in dados if (d.get("sport") or "").upper() == "DEFAULT"), dados[0])

    floors = [escolha.get(f"zone{i}Floor") for i in range(1, 6)]
    if any(f is None for f in floors):
        raise ValueError("Perfil de zonas do Garmin incompleto.")
    fc_max = escolha.get("maxHeartRateUsed")
    limiar = escolha.get("lactateThresholdHeartRateUsed")

    zonas = []
    for i in range(5):
        mn = int(floors[i])
        mx = int(floors[i + 1]) - 1 if i < 4 else int(fc_max or floors[i] + 12)
        zonas.append({"zona": i + 1, "min": mn, "max": mx})

    return {
        "fc_max": int(fc_max) if fc_max else None,
        "limiar": int(limiar) if limiar else None,
        "zonas": zonas,
        "sport": escolha.get("sport"),
    }


async def enviar_zonas_para_garmin(user_id: str, zonas_app: dict) -> dict:
    """Empurra as zonas de FC do app para o Garmin, atualizando TODOS os perfis
    (CYCLING, DEFAULT, etc.) para ficarem iguais ao app. `zonas_app` no formato
    de config_service.get_zonas(). Retorna {"ok": bool, "status": int|None}."""
    floors = [int(z["min"]) for z in zonas_app["zonas"]]
    fc_max = int(zonas_app["fc_max"])
    limiar = int(zonas_app.get("limiar") or fc_max)

    # Resolve o cliente antes de entrar na thread (get_garmin_client é async)
    api = await get_garmin_client(user_id)

    def _push():
        nonlocal api
        atual = api.connectapi("/biometric-service/heartRateZones") or []
        for prof in atual:
            for i in range(5):
                prof[f"zone{i + 1}Floor"] = floors[i]
            prof["maxHeartRateUsed"] = fc_max
            prof["lactateThresholdHeartRateUsed"] = limiar
            prof["changeState"] = "CHANGED"
        resp = api.client.put(
            "connectapi", "/biometric-service/heartRateZones", json=atual, api=False
        )
        return getattr(resp, "status_code", None)

    status = await asyncio.to_thread(_push)
    ok = status in (200, 204)
    if not ok:
        logger.error("Falha ao enviar zonas ao Garmin: status %s", status)
    else:
        logger.info("Zonas de FC enviadas ao Garmin (status %s)", status)
    return {"ok": ok, "status": status}


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


async def sync_treinos_planejados(user_id: str, semana_inicio: str) -> int:
    """Busca treinos planejados no calendário Garmin e faz upsert no MongoDB.
    Escopado ao user_id — cada usuário usa suas próprias credenciais Garmin."""
    api = await get_garmin_client(user_id)
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
    doc_antes = await db.semanas.find_one({"semana_inicio": semana_inicio, "user_id": user_id})
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
        doc = await db.semanas.find_one({"semana_inicio": semana, "user_id": user_id})

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
                "user_id": user_id,
                "objetivo": "",
                "treinos": [treino_entry],
            })
        else:
            existe = any(t.get("data") == date_str for t in doc.get("treinos", []))
            if not existe:
                await db.semanas.update_one(
                    {"semana_inicio": semana, "user_id": user_id},
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
                    {"semana_inicio": semana, "user_id": user_id, "treinos.data": date_str},
                    {"$set": set_fields},
                )
        sincronizados += 1

    # Remove entradas de treinos que foram movidos para outra data no Garmin
    doc = await db.semanas.find_one({"semana_inicio": semana_inicio, "user_id": user_id})
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
                    {"semana_inicio": semana_inicio, "user_id": user_id},
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
    type_key = (act.get("activityType") or {}).get("typeKey", "").lower()
    if type_key in _CYCLING_TYPES:
        return True
    # Fallback por substring para variações novas do Garmin. Usa "bik" (e não
    # "bike") porque road_biking/mountain_biking contêm "biking", não "bike".
    return any(k in type_key for k in ("cycl", "bik", "mtb"))


# Fator de intensidade MÉDIO de sessão por tipo de treino (já contando
# aquecimento, recuperações entre blocos e volta à calma). Usado para estimar o
# TSS planejado (esperado). Calibrado para refletir o IF médio real da sessão —
# por isso TIROS/VO2MAX não são altíssimos: os picos são curtos e há muita
# recuperação no meio, o que derruba a média.
_IF_ESPERADO = {
    "RECUPERACAO": 0.50,
    "Z2_LONGO":    0.65,
    "TEMPO":       0.82,
    "FORCA":       0.78,
    "TIROS":       0.80,
    "VO2MAX":      0.88,
}


def _hrtss(duracao_min, avg_hr, limiar) -> int | None:
    """TSS estimado pela FC (hrTSS): horas × (FCmédia/limiar)² × 100."""
    if not (duracao_min and avg_hr and limiar):
        return None
    return round((duracao_min / 60) * (avg_hr / limiar) ** 2 * 100)


def _tss_esperado(tipo, duracao_min) -> int | None:
    fator = _IF_ESPERADO.get(tipo)
    if not (fator and duracao_min):
        return None
    return round((duracao_min / 60) * fator ** 2 * 100)


def _metricas_extra(planejado: dict, resultado: dict, limiar, avg_speed_ms=None, fit_path=None) -> dict:
    """Velocidade média e TSS (esperado/obtido) para o modal de avaliação.
    Não são enviadas ao WhatsApp — só ficam salvas no resultado para o portal."""
    extra = {}
    vel = None
    if avg_speed_ms:
        vel = avg_speed_ms * 3.6
    elif resultado.get("distancia_km") and resultado.get("duracao_min"):
        vel = resultado["distancia_km"] / (resultado["duracao_min"] / 60)
    if vel:
        extra["velocidade_media_kmh"] = round(vel, 1)

    # TSS obtido: preferir o ponderado por zona (lê amostras de FC do .fit);
    # cair no hrTSS pela FC média quando o .fit não está disponível.
    obtido = None
    if fit_path and limiar:
        from app.services.fit_service import hrtss_ponderado
        obtido = hrtss_ponderado(fit_path, limiar)
    if obtido is None:
        obtido = _hrtss(resultado.get("duracao_min"), resultado.get("avg_hr"), limiar)
    if obtido is not None:
        extra["tss_obtido"] = obtido

    esperado = _tss_esperado((planejado or {}).get("tipo"), (planejado or {}).get("duracao_min"))
    if esperado is not None:
        extra["tss_esperado"] = esperado
    return extra


async def sync_atividades(user_id: str, semana_inicio: str) -> int:
    """Busca atividades completadas no Garmin e salva como resultado.
    Escopado ao user_id — cada usuário usa suas próprias credenciais Garmin."""
    api = await get_garmin_client(user_id)
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

    # Backfill: atividades que já têm resultado salvo são marcadas como
    # processadas para que NÃO sejam notificadas de novo após um restart.
    doc_semana = await db.semanas.find_one({"semana_inicio": semana_inicio, "user_id": user_id})
    if doc_semana:
        for t in doc_semana.get("treinos", []):
            aid = (t.get("resultado") or {}).get("garmin_activity_id")
            if aid:
                await db.atividades_processadas.update_one(
                    {"_id": aid},
                    {"$setOnInsert": {"data": t.get("data"), "processada_em": datetime.now()}},
                    upsert=True,
                )

    for act in atividades:
        start_local = act.get("startTimeLocal") or ""
        act_date = start_local[:10]
        if not act_date or not (d0.isoformat() <= act_date <= d1.isoformat()):
            continue

        act_id = str(act.get("activityId", ""))
        if not act_id:
            continue
        semana = _semana_de(act_date)

        # verifica se já foi processada — pula a atividade inteira se sim
        doc = await db.semanas.find_one({"semana_inicio": semana, "user_id": user_id})
        ja_processada = doc and any(
            t.get("data") == act_date
            and (t.get("resultado") or {}).get("garmin_activity_id") == act_id
            for t in doc.get("treinos", [])
        )
        # Dedup robusto por activity_id (registro persistente). Imune ao
        # "ping-pong" quando há mais de uma atividade no mesmo dia: o slot de
        # resultado é por data, mas o controle de processamento é por activity_id.
        if not ja_processada:
            ja_processada = (
                await db.atividades_processadas.find_one({"_id": act_id}) is not None
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

        # Cadência vem do resumo da atividade do Garmin (média e máxima);
        # cai no valor calculado do .fit se o resumo não trouxer.
        cad_media = act.get("averageBikingCadenceInRevPerMinute")
        cad_max = act.get("maxBikingCadenceInRevPerMinute")
        if cad_media is None and analise.get("cadencia_rpm"):
            try:
                cad_media = float(str(analise["cadencia_rpm"]).split("-")[0])
            except ValueError:
                cad_media = None

        # período do dia a partir da hora real em que o treino foi feito
        from app.services.nutricao_service import periodo_de_hora
        periodo_real = None
        hora_inicio = start_local[11:16] if len(start_local) >= 16 else None
        try:
            periodo_real = periodo_de_hora(int(start_local[11:13]))
        except (ValueError, IndexError):
            pass

        resultado = {
            "garmin_activity_id": act_id,
            "fit_file": fit_filename,
            "hora_inicio": hora_inicio,
            "duracao_min": analise.get("duracao_min"),
            "distancia_km": analise.get("distancia_km"),
            "elevacao_m": analise.get("elevacao_m"),
            "avg_hr": analise.get("avg_hr"),
            "max_hr": analise.get("max_hr"),
            "cadencia_media_rpm": round(cad_media) if cad_media else None,
            "cadencia_max_rpm": round(cad_max) if cad_max else None,
            "calorias": analise.get("calorias"),
            "carga_exercicio": round(act["activityTrainingLoad"]) if act.get("activityTrainingLoad") else None,
        }

        # busca treino planejado para comparação
        treino_planejado = {}
        if doc:
            for t in doc.get("treinos", []):
                if t.get("data") == act_date:
                    treino_planejado = t
                    break

        # métricas extras do modal de avaliação (velocidade, TSS) — NÃO vão ao WhatsApp
        try:
            from app.services.config_service import get_zonas
            limiar = (await get_zonas(user_id)).get("limiar")
        except Exception:
            limiar = None
        resultado.update(_metricas_extra(treino_planejado, resultado, limiar, act.get("averageSpeed"), fit_path))

        # análise IA
        try:
            from app.services.ai_service import analisar_atividade_pos_treino
            analise_ia = await analisar_atividade_pos_treino(treino_planejado, resultado, user_id, fit_path)
            resultado["analise_ia"] = analise_ia
        except Exception as e:
            logger.error("IA pós-treino error: %s", e)

        tipo_real = analise.get("tipo", "Z2_LONGO")

        # salva no MongoDB
        if not doc:
            await db.semanas.insert_one({
                "semana_inicio": semana,
                "user_id": user_id,
                "objetivo": "",
                "treinos": [{
                    "data": act_date,
                    "tipo": tipo_real,
                    "periodo": periodo_real,
                    "resultado": resultado,
                }],
            })
        else:
            existe = any(t.get("data") == act_date for t in doc.get("treinos", []))
            if existe:
                # Preserva o tipo planejado (mais confiável que a classificação do
                # .fit). Só adota o tipo do .fit quando não havia plano (DESCANSO).
                set_fields = {"treinos.$.resultado": resultado}
                tipo_existente = treino_planejado.get("tipo")
                if not tipo_existente or tipo_existente == "DESCANSO":
                    set_fields["treinos.$.tipo"] = tipo_real
                # preenche o período com a hora real do treino
                if periodo_real:
                    set_fields["treinos.$.periodo"] = periodo_real
                await db.semanas.update_one(
                    {"semana_inicio": semana, "user_id": user_id, "treinos.data": act_date},
                    {"$set": set_fields},
                )
            else:
                await db.semanas.update_one(
                    {"semana_inicio": semana, "user_id": user_id},
                    {"$push": {"treinos": {
                        "data": act_date,
                        "tipo": tipo_real,
                        "periodo": periodo_real,
                        "resultado": resultado,
                    }}},
                )

        # Marca como processada ANTES de notificar — claim atômico por activity_id.
        # Garante que o pós-treino seja enviado exatamente uma vez, mesmo que o
        # sync rode de novo antes do WhatsApp concluir.
        primeira_vez = await _claim_atividade(db, act_id, act_date)

        # WhatsApp — só na primeira vez que esta atividade é processada
        if primeira_vez:
            try:
                from app.services.whatsapp_service import send_message
                if settings.WHATSAPP_TO and resultado.get("analise_ia"):
                    msg = _formatar_pos_treino(act_date, treino_planejado, resultado)
                    await send_message(settings.WHATSAPP_TO, msg)
            except Exception as e:
                logger.error("WhatsApp pós-treino error: %s", e)

        processadas += 1

    return processadas


async def _claim_atividade(db, act_id: str, act_date: str) -> bool:
    """Registra a atividade como processada de forma atômica.

    Retorna True apenas na PRIMEIRA vez (quando se deve notificar); False se já
    havia sido registrada. O upsert com $setOnInsert é atômico no MongoDB, então
    duas execuções concorrentes do sync nunca enviam a notificação em duplicidade.
    """
    res = await db.atividades_processadas.update_one(
        {"_id": act_id},
        {"$setOnInsert": {"data": act_date, "processada_em": datetime.now()}},
        upsert=True,
    )
    return res.upserted_id is not None


def _bullet(texto: str, lim: int = 160) -> str:
    """Limpa markdown '**' e encurta um item para caber no WhatsApp."""
    t = (texto or "").replace("**", "").strip()
    if len(t) <= lim:
        return t
    corte = t.find(". ")
    if 0 < corte < lim:
        return t[: corte + 1]
    return t[:lim].rstrip() + "…"


def _formatar_pos_treino(data: str, planejado: dict, resultado: dict) -> str:
    d = datetime.strptime(data, "%Y-%m-%d")
    dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    dia = dias[d.weekday()]
    data_fmt = d.strftime("%d/%m/%Y")
    analise = resultado.get("analise_ia", {})

    linhas = [f"🚵 *Pós-treino — {dia}, {data_fmt}*", ""]

    if analise.get("nota") is not None:
        nota = analise["nota"]
        nota_txt = f"{nota:.1f}".rstrip("0").rstrip(".")
        linhas += [f"⭐ *Nota do treino: {nota_txt}/10*", ""]

    if analise.get("resumo"):
        linhas += [f"_{_bullet(analise['resumo'], 240)}_", ""]

    if analise.get("pontos_fortes"):
        linhas.append("✅ *Pontos fortes:*")
        for p in analise["pontos_fortes"]:
            linhas.append(f"  • {_bullet(p)}")
        linhas.append("")

    if analise.get("pontos_fracos"):
        linhas.append("⚠️ *A melhorar:*")
        for p in analise["pontos_fracos"]:
            linhas.append(f"  • {_bullet(p)}")
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
    if resultado.get("cadencia_media_rpm"):
        cad = f"🦵 Cadência: {resultado['cadencia_media_rpm']} rpm"
        if resultado.get("cadencia_max_rpm"):
            cad += f" (máx {resultado['cadencia_max_rpm']})"
        linhas.append(cad)
    if resultado.get("calorias"):
        linhas.append(f"🔋 Calorias: {resultado['calorias']} kcal")

    if planejado.get("duracao_min"):
        linhas += ["", f"📋 Planejado: {planejado['duracao_min']} min · {planejado.get('tipo','')}"]

    linhas += ["", "_MTB Nutrition Bot 🤖_"]
    msg = "\n".join(linhas)
    # cinto de segurança: o WhatsApp/Twilio recusa acima de 1600 caracteres
    if len(msg) > 1550:
        msg = msg[:1530].rstrip() + "…\n\n_MTB Nutrition Bot 🤖_"
    return msg

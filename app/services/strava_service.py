"""Integração Strava — somente LEITURA de atividades (OAuth2).

Fluxo OAuth:
  1. url_autorizacao(user_id) → redireciona o usuário para o Strava com state=user_id.
  2. Strava chama /workout/strava/callback?code=...&state=user_id.
  3. trocar_codigo(user_id, code) → troca o code por tokens e persiste no banco.
  4. sync_atividades_strava(user_id, semana_inicio) → puxa atividades de bike da semana
     e grava o resultado no mesmo formato do Garmin.

Strava NÃO empurra treinos — nenhum upload/push é feito aqui.
"""

import logging
import time
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx

from config.settings import settings
from app.services.mongo_service import get_db
from app.services.crypto_service import cifrar, decifrar
from app.services.user_service import get_por_id, atualizar_usuario

logger = logging.getLogger(__name__)

# Tipos de atividade ciclística reconhecidos pelo Strava.
# Comparação case-insensitive por substring "ride".
_RIDE_KEYWORDS = ("ride",)   # Ride, VirtualRide, MountainBikeRide, GravelRide, EBikeRide…


def _e_ciclismo(tipo: str) -> bool:
    """Retorna True se o sport_type/type da atividade for ciclismo."""
    return any(kw in tipo.lower() for kw in _RIDE_KEYWORDS)


def url_autorizacao(user_id: str) -> str:
    """Monta a URL de autorização OAuth2 do Strava.

    O parâmetro `state=user_id` é devolvido intacto pelo Strava no callback,
    permitindo identificar o usuário mesmo sem cookie de sessão.
    """
    params = {
        "client_id": settings.STRAVA_CLIENT_ID,
        "redirect_uri": settings.STRAVA_REDIRECT_URI,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": "activity:read,activity:read_all",
        "state": user_id,
    }
    return "https://www.strava.com/oauth/authorize?" + urlencode(params)


async def trocar_codigo(user_id: str, code: str) -> bool:
    """Troca o code OAuth pelo access_token e refresh_token.

    Em sucesso: persiste no doc do usuário (integracao.tipo="strava",
    integracao.strava={athlete_id, access_token, expires_at, refresh_token_cifrado})
    e retorna True. Retorna False em caso de erro.
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://www.strava.com/oauth/token",
                data={
                    "client_id": settings.STRAVA_CLIENT_ID,
                    "client_secret": settings.STRAVA_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            dados = resp.json()
    except Exception as exc:
        logger.error("strava trocar_codigo: erro ao obter token (user_id=%s) — %s", user_id, exc)
        return False

    access_token = dados.get("access_token")
    refresh_token = dados.get("refresh_token")
    expires_at = dados.get("expires_at")   # epoch int
    athlete = dados.get("athlete") or {}
    athlete_id = athlete.get("id")

    if not (access_token and refresh_token):
        logger.error(
            "strava trocar_codigo: resposta sem access_token/refresh_token (user_id=%s)", user_id
        )
        return False

    try:
        await atualizar_usuario(user_id, {
            "integracao.tipo": "strava",
            "integracao.strava": {
                "athlete_id": athlete_id,
                "access_token": access_token,
                "expires_at": int(expires_at) if expires_at else 0,
                "refresh_token_cifrado": cifrar(refresh_token),
            },
        })
    except Exception as exc:
        logger.error("strava trocar_codigo: erro ao salvar tokens no banco (user_id=%s) — %s", user_id, exc)
        return False

    logger.info("strava trocar_codigo: Strava conectado para user_id=%s (athlete=%s)", user_id, athlete_id)
    return True


async def _token_valido(user_id: str) -> str | None:
    """Retorna um access_token válido para o usuário.

    Se o token expirar em menos de 5 minutos, faz o refresh automaticamente
    e atualiza o banco antes de retornar. Retorna None se o usuário não tem
    Strava conectado ou se o refresh falhar.
    """
    u = await get_por_id(user_id)
    if not u:
        return None

    integracao = (u.get("integracao") or {})
    if integracao.get("tipo") != "strava":
        return None

    strava = integracao.get("strava") or {}
    access_token = strava.get("access_token")
    expires_at = int(strava.get("expires_at") or 0)
    refresh_token_cifrado = strava.get("refresh_token_cifrado") or ""

    if not access_token:
        return None

    # Checa se o token ainda é válido por mais de 5 minutos
    margem = 5 * 60  # segundos
    if expires_at - time.time() > margem:
        return access_token

    # Token expirado (ou prestes a expirar) — tenta refresh
    refresh_token = decifrar(refresh_token_cifrado)
    if not refresh_token:
        logger.warning("strava _token_valido: refresh_token vazio para user_id=%s", user_id)
        return None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://www.strava.com/oauth/token",
                data={
                    "client_id": settings.STRAVA_CLIENT_ID,
                    "client_secret": settings.STRAVA_CLIENT_SECRET,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            resp.raise_for_status()
            dados = resp.json()
    except Exception as exc:
        logger.error("strava _token_valido: refresh falhou (user_id=%s) — %s", user_id, exc)
        return None

    novo_access = dados.get("access_token")
    novo_refresh = dados.get("refresh_token")
    novo_expires = dados.get("expires_at")

    if not novo_access:
        logger.error("strava _token_valido: refresh sem access_token (user_id=%s)", user_id)
        return None

    try:
        novo_strava = {
            "athlete_id": strava.get("athlete_id"),
            "access_token": novo_access,
            "expires_at": int(novo_expires) if novo_expires else 0,
            "refresh_token_cifrado": cifrar(novo_refresh or refresh_token),
        }
        await atualizar_usuario(user_id, {"integracao.strava": novo_strava})
    except Exception as exc:
        logger.error("strava _token_valido: erro ao salvar novo token (user_id=%s) — %s", user_id, exc)

    logger.info("strava _token_valido: token renovado para user_id=%s", user_id)
    return novo_access


async def sync_atividades_strava(user_id: str, semana_inicio: str) -> int:
    """Busca atividades de ciclismo do Strava na semana e grava como resultado.

    Segue o mesmo padrão do garmin_service.sync_atividades:
      - Monta o dict `resultado` com os campos equivalentes.
      - Casa com o treino planejado do dia em db.semanas (escopado por user_id).
      - Usa db.atividades_processadas (_id="strava_<activity_id>") para dedup.
      - Retorna o número de atividades novas processadas.

    Strava é READ-ONLY — nenhum upload é feito.
    """
    token = await _token_valido(user_id)
    if not token:
        return 0

    d0 = datetime.strptime(semana_inicio, "%Y-%m-%d")
    d1 = d0 + timedelta(days=6)

    # Épocas para o filtro da API do Strava
    epoch_after = int(d0.timestamp())
    epoch_before = int((d1 + timedelta(days=1)).timestamp())

    # Puxa as atividades da semana
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://www.strava.com/api/v3/athlete/activities",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "after": epoch_after,
                    "before": epoch_before,
                    "per_page": 50,
                },
            )
            resp.raise_for_status()
            atividades = resp.json()
    except Exception as exc:
        logger.error("strava sync_atividades: erro ao buscar atividades (user_id=%s) — %s", user_id, exc)
        return 0

    # Filtra apenas ciclismo
    atividades_bike = [
        a for a in (atividades or [])
        if _e_ciclismo(a.get("sport_type") or a.get("type") or "")
    ]
    logger.info(
        "strava sync_atividades (user_id=%s, semana=%s): %d total / %d bike",
        user_id, semana_inicio, len(atividades or []), len(atividades_bike),
    )

    db = get_db()
    processadas = 0

    from app.services.nutricao_service import periodo_de_hora

    for act in atividades_bike:
        activity_id = act.get("id")
        if not activity_id:
            continue

        # start_date_local é uma string ISO, ex.: "2026-06-14T07:30:00Z"
        start_local = act.get("start_date_local") or ""
        act_date = start_local[:10]  # "YYYY-MM-DD"
        if not act_date:
            continue

        doc_id = f"strava_{activity_id}"

        # Dedup: pula se já processada
        ja_processada = await db.atividades_processadas.find_one({"_id": doc_id})
        if ja_processada:
            continue

        # Backfill: se já existe resultado no banco com este strava_activity_id, marca e pula
        semana = _semana_de(act_date)
        doc_semana = await db.semanas.find_one({"semana_inicio": semana, "user_id": user_id})
        if doc_semana:
            for t in doc_semana.get("treinos", []):
                if (t.get("resultado") or {}).get("strava_activity_id") == str(activity_id):
                    await db.atividades_processadas.update_one(
                        {"_id": doc_id},
                        {"$setOnInsert": {"data": act_date, "processada_em": datetime.now()}},
                        upsert=True,
                    )
                    continue

        # Monta o dict resultado no mesmo formato do Garmin
        hora_inicio = start_local[11:16] if len(start_local) >= 16 else None
        hora_int = None
        try:
            hora_int = int(start_local[11:13])
        except (ValueError, IndexError):
            pass

        periodo_real = periodo_de_hora(hora_int) if hora_int is not None else None

        moving_time = act.get("moving_time")  # segundos
        distance = act.get("distance")         # metros
        elevation = act.get("total_elevation_gain")
        avg_hr = act.get("average_heartrate")
        max_hr = act.get("max_heartrate")
        cadencia = act.get("average_cadence")
        calorias = act.get("calories")

        resultado: dict = {
            "strava_activity_id": str(activity_id),
            "hora_inicio": hora_inicio,
            "duracao_min": round(moving_time / 60, 1) if moving_time else None,
            "distancia_km": round(distance / 1000, 2) if distance else None,
            "elevacao_m": round(elevation) if elevation else None,
            "avg_hr": round(avg_hr) if avg_hr else None,
            "max_hr": round(max_hr) if max_hr else None,
            "cadencia_media_rpm": round(cadencia) if cadencia else None,
            "calorias": round(calorias) if calorias else None,
        }

        # Velocidade média (campo extra para o portal, não vai ao WhatsApp)
        avg_speed = act.get("average_speed")  # m/s
        if avg_speed:
            resultado["velocidade_media_kmh"] = round(avg_speed * 3.6, 1)

        # Busca treino planejado do dia para comparação e preservação do tipo
        treino_planejado: dict = {}
        if doc_semana:
            for t in doc_semana.get("treinos", []):
                if t.get("data") == act_date:
                    treino_planejado = t
                    break

        # Análise IA pós-treino (best-effort)
        try:
            from app.services.ai_service import analisar_atividade_pos_treino
            analise_ia = await analisar_atividade_pos_treino(treino_planejado, resultado, user_id)
            resultado["analise_ia"] = analise_ia
        except Exception as exc:
            logger.warning("strava sync_atividades: IA pós-treino falhou (user_id=%s) — %s", user_id, exc)

        # Persiste em db.semanas
        tipo_existente = treino_planejado.get("tipo")
        # Se não houver tipo planejado, usa um padrão genérico
        tipo_fallback = tipo_existente if tipo_existente and tipo_existente != "DESCANSO" else "Z2_LONGO"

        if not doc_semana:
            await db.semanas.insert_one({
                "semana_inicio": semana,
                "user_id": user_id,
                "objetivo": "",
                "treinos": [{
                    "data": act_date,
                    "tipo": tipo_fallback,
                    "periodo": periodo_real,
                    "resultado": resultado,
                }],
            })
        else:
            existe = any(t.get("data") == act_date for t in doc_semana.get("treinos", []))
            if existe:
                set_fields: dict = {"treinos.$.resultado": resultado}
                # Preserva tipo planejado; só substitui se era DESCANSO ou ausente
                if not tipo_existente or tipo_existente == "DESCANSO":
                    set_fields["treinos.$.tipo"] = tipo_fallback
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
                        "tipo": tipo_fallback,
                        "periodo": periodo_real,
                        "resultado": resultado,
                    }}},
                )

        # Claim atômico — só envia WhatsApp na primeira vez
        primeira_vez = await _claim_atividade(db, doc_id, act_date)

        if primeira_vez:
            try:
                from app.services.whatsapp_service import send_message
                from app.services.user_service import get_por_id as _get_user
                u = await _get_user(user_id)
                telefone = (u or {}).get("telefone")
                if telefone and resultado.get("analise_ia"):
                    msg = _formatar_pos_treino_strava(act_date, treino_planejado, resultado)
                    await send_message(telefone, msg)
            except Exception as exc:
                logger.error("strava sync_atividades: WhatsApp pós-treino falhou (user_id=%s) — %s", user_id, exc)

        processadas += 1

    return processadas


# ─── Helpers internos ──────────────────────────────────────────────────────────

def _semana_de(data: str) -> str:
    """Retorna a segunda-feira da semana de uma data ISO."""
    d = datetime.strptime(data, "%Y-%m-%d").date()
    from datetime import timedelta as _td
    return (d - _td(days=d.weekday())).isoformat()


async def _claim_atividade(db, doc_id: str, act_date: str) -> bool:
    """Marca a atividade como processada de forma atômica (mesmo padrão do Garmin).

    Retorna True apenas na primeira vez; False se já havia sido registrada.
    """
    res = await db.atividades_processadas.update_one(
        {"_id": doc_id},
        {"$setOnInsert": {"data": act_date, "processada_em": datetime.now(), "fonte": "strava"}},
        upsert=True,
    )
    return res.upserted_id is not None


def _bullet(texto: str, lim: int = 160) -> str:
    """Limpa markdown e encurta para caber no WhatsApp."""
    t = (texto or "").replace("**", "").strip()
    if len(t) <= lim:
        return t
    corte = t.find(". ")
    if 0 < corte < lim:
        return t[:corte + 1]
    return t[:lim].rstrip() + "…"


def _formatar_pos_treino_strava(data: str, planejado: dict, resultado: dict) -> str:
    """Monta a mensagem WhatsApp de pós-treino para atividades do Strava."""
    d = datetime.strptime(data, "%Y-%m-%d")
    dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    dia = dias[d.weekday()]
    data_fmt = d.strftime("%d/%m/%Y")
    analise = resultado.get("analise_ia") or {}

    linhas = [f"🚵 *Pós-treino (Strava) — {dia}, {data_fmt}*", ""]

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
        h, m = divmod(int(dur), 60)
        linhas.append(f"⏱ Duração: {h}h{m:02d}min")
    if resultado.get("distancia_km"):
        linhas.append(f"📍 Distância: {resultado['distancia_km']} km")
    if resultado.get("elevacao_m"):
        linhas.append(f"⛰ Elevação: {resultado['elevacao_m']} m")
    if resultado.get("avg_hr"):
        linhas.append(f"❤️ FC média: {resultado['avg_hr']} bpm")
    if resultado.get("max_hr"):
        linhas.append(f"🔥 FC máx: {resultado['max_hr']} bpm")
    if resultado.get("cadencia_media_rpm"):
        linhas.append(f"🦵 Cadência: {resultado['cadencia_media_rpm']} rpm")
    if resultado.get("calorias"):
        linhas.append(f"🔋 Calorias: {resultado['calorias']} kcal")
    if resultado.get("velocidade_media_kmh"):
        linhas.append(f"💨 Velocidade média: {resultado['velocidade_media_kmh']} km/h")

    if planejado.get("duracao_min"):
        linhas += ["", f"📋 Planejado: {planejado['duracao_min']} min · {planejado.get('tipo', '')}"]

    linhas += ["", "_MTB Nutrition Bot 🤖_"]
    msg = "\n".join(linhas)
    if len(msg) > 1550:
        msg = msg[:1530].rstrip() + "…\n\n_MTB Nutrition Bot 🤖_"
    return msg

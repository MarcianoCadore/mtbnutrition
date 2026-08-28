"""Importa o histórico do atleta ao conectar Garmin ou Strava.

Sem isto o assinante novo entra num app vazio: o parecer fisiológico chuta a
carga porque não tem histórico, a primeira semana nasce descalibrada, e a tela
que deveria vender o produto no dia 1 mostra sete quadrados em branco.

O backfill puxa os últimos 90 dias e grava o que já foi pedalado. Ele é
deliberadamente **mais barato** que o sync semanal:

- **sem análise de IA** — 90 dias são ~40 sessões; a preços de Sonnet isso é
  mais caro que a primeira mensalidade do assinante, para avaliar treinos que
  ele fez antes de existir plano nenhum;
- **sem WhatsApp** — ninguém quer 40 mensagens de "pós-treino" de treinos
  antigos ao terminar o cadastro;
- **marca cada atividade como processada**, para o sync normal não reprocessar
  o mesmo treino e disparar a notificação depois.

O que ele grava é o que alimenta as decisões: duração, distância, FC, potência,
TSS e a curva de potência (que dá o eFTP).
"""
import logging
import os
from datetime import datetime, timedelta

import httpx

from app.services import potencia_service
from app.services.mongo_service import get_db

logger = logging.getLogger(__name__)

DIAS_PADRAO = 90


def _semana_de(data_iso: str) -> str:
    d = datetime.strptime(data_iso, "%Y-%m-%d").date()
    return (d - timedelta(days=d.weekday())).isoformat()


async def _ja_importado(db, chave: str) -> bool:
    return await db.atividades_processadas.find_one({"_id": chave}) is not None


async def _marcar(db, chave: str, data_iso: str) -> None:
    """Registra a atividade como processada.

    Vale por dois: evita reimportar no próximo backfill e — mais importante —
    impede o sync normal de tratá-la como nova e mandar o pós-treino no
    WhatsApp semanas depois do treino ter acontecido.
    """
    await db.atividades_processadas.update_one(
        {"_id": chave},
        {"$setOnInsert": {"data": data_iso, "processada_em": datetime.now(),
                          "origem": "backfill"}},
        upsert=True,
    )


async def _gravar_treino(user_id: str, data_iso: str, tipo: str, resultado: dict) -> None:
    """Grava a sessão histórica na semana correspondente.

    Nunca sobrescreve um treino que já existe na data: se o atleta já tem plano
    ou resultado ali, o histórico importado não tem prioridade sobre ele.
    """
    db = get_db()
    semana = _semana_de(data_iso)
    treino = {
        "data": data_iso,
        "tipo": tipo,
        "duracao_min": resultado.get("duracao_min"),
        "origem": "backfill",
        "resultado": resultado,
    }

    doc = await db.semanas.find_one({"semana_inicio": semana, "user_id": user_id})
    if not doc:
        await db.semanas.insert_one({
            "semana_inicio": semana, "user_id": user_id,
            "objetivo": "", "origem": "backfill", "treinos": [treino],
        })
        return

    ocupado = any(
        t.get("data") == data_iso and t.get("origem") != "extra"
        and (t.get("resultado") or t.get("duracao_min"))
        for t in doc.get("treinos", [])
    )
    if ocupado:
        return

    await db.semanas.update_one(
        {"semana_inicio": semana, "user_id": user_id},
        {"$push": {"treinos": treino}},
    )


# ─── Garmin ──────────────────────────────────────────────────────────────────

async def _backfill_garmin(user_id: str, dias: int) -> dict:
    from garminconnect import Garmin

    from app.services.fit_service import analisar_fit, hrtss_ponderado
    from app.services.garmin_service import (
        UPLOADS_DIR, _extrair_fit_do_zip, _is_cycling, get_garmin_client,
    )

    api = await get_garmin_client(user_id)
    fim = datetime.now().date()
    inicio = fim - timedelta(days=dias)

    try:
        todas = api.get_activities_by_date(inicio.isoformat(), fim.isoformat())
    except Exception as exc:
        logger.error("backfill garmin: falha ao listar atividades de %s — %s", user_id, exc)
        return {"importadas": 0, "erro": "Não consegui listar as atividades no Garmin."}

    atividades = [a for a in (todas or []) if _is_cycling(a)]
    db = get_db()
    importadas = 0

    from app.services.config_service import get_zonas, zonas_bpm_map, zonas_watts_map
    from app.services.avaliacao_service import usuario_sem_cinta
    limiar = (await get_zonas(user_id)).get("limiar")
    # Zonas do atleta: o tipo de cada treino importado é lido com a régua dele.
    zonas_bpm = await zonas_bpm_map(user_id)
    zonas_watts = await zonas_watts_map(user_id)
    ignorar_fc = await usuario_sem_cinta(user_id)

    for act in atividades:
        act_id = str(act.get("activityId", ""))
        data_iso = (act.get("startTimeLocal") or "")[:10]
        if not act_id or not data_iso:
            continue
        if await _ja_importado(db, act_id):
            continue

        try:
            raw = api.download_activity(act_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)
            fit_bytes = _extrair_fit_do_zip(raw)
            if not fit_bytes:
                continue
            dest_dir = os.path.join(UPLOADS_DIR, _semana_de(data_iso))
            os.makedirs(dest_dir, exist_ok=True)
            fit_path = os.path.join(dest_dir, f"{data_iso}_{act_id}.fit")
            with open(fit_path, "wb") as f:
                f.write(fit_bytes)
            analise = analisar_fit(fit_path, zonas_bpm=zonas_bpm,
                                   zonas_watts=zonas_watts, ignorar_fc=ignorar_fc)
        except Exception as exc:
            logger.warning("backfill garmin: atividade %s ignorada — %s", act_id, exc)
            continue

        resultado = {
            "garmin_activity_id": act_id,
            "fit_file": os.path.basename(fit_path),
            "duracao_min":  analise.get("duracao_min"),
            "distancia_km": analise.get("distancia_km"),
            "elevacao_m":   analise.get("elevacao_m"),
            "avg_hr":       analise.get("avg_hr"),
            "max_hr":       analise.get("max_hr"),
            "avg_power":    analise.get("avg_power"),
            "norm_power":   analise.get("norm_power"),
            "calorias":     analise.get("calorias"),
            "origem":       "backfill",
        }

        # TSS por FC já dá para calcular agora; o de potência espera o eFTP
        # sair da curva (segunda passada abaixo).
        if not analise.get("norm_power") and limiar:
            try:
                tss = hrtss_ponderado(fit_path, limiar)
                if tss is not None:
                    resultado["tss_obtido"] = tss
            except Exception:
                pass

        await _gravar_treino(user_id, data_iso, analise.get("tipo", "Z2_LONGO"), resultado)
        await potencia_service.processar_fit(user_id, data_iso, fit_path)
        await _marcar(db, act_id, data_iso)
        importadas += 1

    # Segunda passada: agora que a curva de potência produziu um eFTP, as
    # sessões com medidor ganham pTSS. Fazer isso no loop não funcionaria —
    # as primeiras sessões seriam processadas antes de existir FTP algum, e
    # ficariam sem carga justamente as mais antigas, que são a base da média.
    await _preencher_ptss(user_id, inicio.isoformat())

    return {"importadas": importadas}


async def _preencher_ptss(user_id: str, desde: str) -> int:
    """Calcula o pTSS das sessões importadas com potência, usando o eFTP final."""
    from app.services.config_service import get_ftp
    from app.services.fit_service import ptss

    ftp, _ = await get_ftp(user_id)
    if not ftp:
        return 0

    db = get_db()
    preenchidos = 0
    cursor = db.semanas.find({"user_id": user_id, "semana_inicio": {"$gte": _semana_de(desde)}})
    async for doc in cursor:
        mudou = False
        treinos = doc.get("treinos", [])
        for t in treinos:
            r = t.get("resultado") or {}
            if r.get("origem") != "backfill" or r.get("tss_obtido") is not None:
                continue
            valor = ptss(r.get("norm_power"), ftp, r.get("duracao_min"))
            if valor is not None:
                r["tss_obtido"] = valor
                mudou = True
                preenchidos += 1
        if mudou:
            await db.semanas.update_one({"_id": doc["_id"]}, {"$set": {"treinos": treinos}})
    return preenchidos


# ─── Strava ──────────────────────────────────────────────────────────────────

async def _backfill_strava(user_id: str, dias: int) -> dict:
    from app.services.strava_service import _e_ciclismo, _token_valido

    token = await _token_valido(user_id)
    if not token:
        return {"importadas": 0, "erro": "Conta do Strava não conectada."}

    fim = datetime.now()
    inicio = fim - timedelta(days=dias)
    db = get_db()
    importadas = 0
    pagina = 1

    while pagina <= 5:      # 5 × 100 = 500 atividades, teto de sanidade
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    "https://www.strava.com/api/v3/athlete/activities",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"after": int(inicio.timestamp()),
                            "before": int(fim.timestamp()),
                            "per_page": 100, "page": pagina},
                )
                resp.raise_for_status()
                lote = resp.json() or []
        except Exception as exc:
            logger.error("backfill strava: falha na página %d de %s — %s", pagina, user_id, exc)
            break

        if not lote:
            break

        for act in lote:
            if not _e_ciclismo(act.get("sport_type") or act.get("type") or ""):
                continue
            act_id = str(act.get("id", ""))
            data_iso = (act.get("start_date_local") or "")[:10]
            if not act_id or not data_iso:
                continue
            chave = f"strava_{act_id}"
            if await _ja_importado(db, chave):
                continue

            # O Strava entrega só o resumo — sem .fit, não há curva de potência
            # nem tempo em zonas. Serve para carga e volume, que é o que o
            # parecer fisiológico precisa.
            duracao = act.get("moving_time") or act.get("elapsed_time") or 0
            resultado = {
                "strava_activity_id": act_id,
                "duracao_min":  round(duracao / 60) or None,
                "distancia_km": round((act.get("distance") or 0) / 1000, 2) or None,
                "elevacao_m":   round(act.get("total_elevation_gain") or 0) or None,
                "avg_hr":       round(act["average_heartrate"]) if act.get("average_heartrate") else None,
                "max_hr":       round(act["max_heartrate"]) if act.get("max_heartrate") else None,
                "avg_power":    round(act["average_watts"]) if act.get("average_watts") else None,
                "calorias":     round(act["calories"]) if act.get("calories") else None,
                "origem":       "backfill",
            }

            await _gravar_treino(user_id, data_iso, "Z2_LONGO", resultado)
            await _marcar(db, chave, data_iso)
            importadas += 1

        pagina += 1

    return {"importadas": importadas}


# ─── Entrada ─────────────────────────────────────────────────────────────────

async def importar_historico(user_id: str, dias: int = DIAS_PADRAO) -> dict:
    """Importa o histórico da integração conectada. {importadas, [erro]}."""
    from app.services.user_service import get_por_id

    user = await get_por_id(user_id) or {}
    tipo = (user.get("integracao") or {}).get("tipo")

    if tipo == "garmin":
        resultado = await _backfill_garmin(user_id, dias)
    elif tipo == "strava":
        resultado = await _backfill_strava(user_id, dias)
    else:
        return {"importadas": 0, "erro": "Nenhuma plataforma conectada."}

    if resultado.get("importadas"):
        await get_db().users.update_one(
            {"_id": _oid(user_id)},
            {"$set": {"backfill": {"em": datetime.now(), "dias": dias,
                                   "importadas": resultado["importadas"]}}},
        )
    logger.info("backfill %s (%s): %s sessão(ões)", user_id, tipo, resultado.get("importadas"))
    return resultado


def _oid(user_id):
    from bson import ObjectId
    return user_id if isinstance(user_id, ObjectId) else ObjectId(str(user_id))

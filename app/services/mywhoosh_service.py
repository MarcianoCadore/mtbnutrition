"""Integração MyWhoosh — a atividade indoor chega ao Garmin sozinha.

O atleta treina no MyWhoosh e o resultado precisa cair no app. O MyWhoosh não
empurra para o Garmin Connect (nativamente só manda para o Strava), e o caminho
do Strava não resolve: de lá o app recebe a atividade sem o .fit, ou seja, sem
potência, sem NP, sem tempo em zonas e sem TSS — exatamente o que a avaliação
pós-treino usa para julgar um intervalado.

Então a ponte é feita aqui: login na API do MyWhoosh, download do .fit da
atividade e upload no Garmin Connect com o cliente que o usuário já tem
autenticado. Dali para a frente nada muda — o `job_garmin_sync` de 10 em 10 min
lê a atividade no Garmin e avalia como faz com qualquer pedal.

Roda no servidor: não depende do PC do atleta estar ligado quando ele termina o
treino.

Credenciais: `integracao.mywhoosh = {email, senha_cifrada, conectado_em}`, com a
senha cifrada pelo `crypto_service` como a do Garmin. `integracao.tipo` continua
"garmin" — o MyWhoosh alimenta o Garmin, não o substitui.
"""

import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone

import httpx

from app.services.crypto_service import cifrar, decifrar
from app.services.mongo_service import get_db
from app.services.user_service import atualizar_usuario, get_por_id

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://services.mywhoosh.com/http-service/api/login"
_ATIVIDADES_URL = "https://service14.mywhoosh.com/v2/rider/profile/activities"
_DOWNLOAD_URL = "https://service14.mywhoosh.com/v2/rider/profile/download-activity-file"

# Quantas atividades recentes olhar a cada passada. O que já subiu é ignorado
# pelo claim, então a janela só precisa cobrir o intervalo entre duas rodadas do
# job (10 min) com folga para o servidor ter ficado fora do ar um tempo.
_JANELA_PADRAO = 5

_TIMEOUT = httpx.Timeout(30.0, read=60.0)


class MyWhooshErro(Exception):
    """Falha de login ou de leitura da API do MyWhoosh."""


# ── credenciais ──────────────────────────────────────────────────────────────

async def credenciais(user_id: str) -> tuple[str, str] | None:
    """(email, senha) do MyWhoosh do usuário, ou None se não conectou."""
    u = await get_por_id(user_id)
    cfg = ((u or {}).get("integracao") or {}).get("mywhoosh") or {}
    email = cfg.get("email") or ""
    cifrada = cfg.get("senha_cifrada") or ""
    if not (email and cifrada):
        return None
    senha = decifrar(cifrada)
    return (email, senha) if senha else None


async def esta_conectado(user_id: str) -> bool:
    return await credenciais(user_id) is not None


async def conectar(user_id: str, email: str, senha: str) -> bool:
    """Valida as credenciais fazendo login de verdade e só então salva.

    Guardar uma senha que não funciona faria o job falhar de 10 em 10 min sem o
    atleta entender por quê.
    """
    await _login(email, senha)          # levanta MyWhooshErro se não autenticar
    await atualizar_usuario(user_id, {
        "integracao.mywhoosh": {
            "email": email,
            "senha_cifrada": cifrar(senha),
            "conectado_em": datetime.now(timezone.utc),
        },
    })
    logger.info("mywhoosh: conectado para user_id=%s", user_id)
    return True


async def desconectar(user_id: str) -> None:
    """Apaga as credenciais. O histórico de envios fica: se ele reconectar, as
    atividades já enviadas não voltam a subir."""
    await atualizar_usuario(user_id, {"integracao.mywhoosh": None})
    logger.info("mywhoosh: desconectado para user_id=%s", user_id)


# ── API do MyWhoosh ──────────────────────────────────────────────────────────

async def _login(email: str, senha: str) -> dict:
    """Autentica e devolve {"token": ..., "whoosh_id": ...}."""
    payload = {
        "Username": email,
        "Password": senha,
        "Platform": "Android",
        "Action": 1001,
        "CorrelationId": str(uuid.uuid4()),
        "DeviceId": str(uuid.uuid4()),
        "Authorization": "",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.post(_LOGIN_URL, json=payload)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        raise MyWhooshErro(f"não deu para falar com o MyWhoosh: {exc}") from exc

    if not data.get("Success") or not data.get("AccessToken"):
        raise MyWhooshErro(data.get("Message") or "e-mail ou senha do MyWhoosh inválidos")
    return {"token": data["AccessToken"], "whoosh_id": data.get("WhooshId")}


def _extrair_atividades(data) -> list[dict]:
    """A API já mudou de formato mais de uma vez — aceita os que se conhece."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    interno = data.get("data")
    if isinstance(interno, dict):
        return interno.get("results") or []
    if isinstance(interno, list):
        return interno
    for chave in ("activities", "results", "rides"):
        if isinstance(data.get(chave), list):
            return data[chave]
    return []


async def _listar(sessao: dict, limite: int) -> list[dict]:
    """Atividades mais recentes primeiro."""
    headers = {"Authorization": f"Bearer {sessao['token']}",
               "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.post(_ATIVIDADES_URL, headers=headers,
                             json={"page": 1, "limit": limite, "sortDate": "DESC"})
            r.raise_for_status()
            return _extrair_atividades(r.json())
    except httpx.HTTPError as exc:
        raise MyWhooshErro(f"não deu para listar as atividades: {exc}") from exc


def _id_da_atividade(atividade: dict) -> str | None:
    for chave in ("id", "_id", "activityId"):
        valor = atividade.get(chave)
        if valor:
            return str(valor)
    return None


async def _baixar_fit(sessao: dict, atividade: dict) -> bytes:
    """Baixa o .fit: a API devolve uma URL S3 assinada, o arquivo vem de lá."""
    file_id = atividade.get("activityFileId")
    if not file_id:
        raise MyWhooshErro("atividade sem arquivo .fit para baixar")

    headers = {"Authorization": f"Bearer {sessao['token']}",
               "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as c:
            r = await c.post(_DOWNLOAD_URL, headers=headers,
                             json={"key": sessao["whoosh_id"], "fileId": file_id})
            r.raise_for_status()
            data = r.json()
            if data.get("error"):
                raise MyWhooshErro(data.get("message") or "erro ao pedir o arquivo")
            url = data.get("data")
            if not isinstance(url, str) or not url.startswith("http"):
                raise MyWhooshErro("o MyWhoosh não devolveu link de download")

            arq = await c.get(url)
            arq.raise_for_status()
            conteudo = arq.content
    except httpx.HTTPError as exc:
        raise MyWhooshErro(f"não deu para baixar o .fit: {exc}") from exc

    # Assinatura do formato: os bytes 8-11 de todo .fit são ".FIT".
    if len(conteudo) < 14 or conteudo[8:12] != b".FIT":
        raise MyWhooshErro("o arquivo baixado não é um .fit válido")
    return conteudo


# ── controle de duplicata ────────────────────────────────────────────────────

async def _reservar(user_id: str, activity_id: str) -> bool:
    """Reserva o envio desta atividade. True só na PRIMEIRA vez.

    O job roda de 10 em 10 min e a janela olha as últimas atividades sempre: sem
    esta trava o mesmo pedal subiria de novo a cada rodada. Upsert com
    $setOnInsert é atômico — duas execuções simultâneas não passam as duas.
    """
    res = await get_db().mywhoosh_enviadas.update_one(
        {"_id": f"{user_id}:{activity_id}"},
        {"$setOnInsert": {"user_id": str(user_id), "activity_id": activity_id,
                          "enviada_em": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return res.upserted_id is not None


async def _liberar(user_id: str, activity_id: str) -> None:
    """Devolve a reserva quando o envio falhou, para a próxima rodada tentar."""
    try:
        await get_db().mywhoosh_enviadas.delete_one({"_id": f"{user_id}:{activity_id}"})
    except Exception as exc:
        logger.warning("mywhoosh: reserva de %s não liberada — %s", activity_id, exc)


# ── envio para o Garmin ──────────────────────────────────────────────────────

async def _subir_no_garmin(user_id: str, conteudo: bytes, activity_id: str) -> bool:
    """Sobe o .fit no Garmin Connect. True se entrou (ou já estava lá).

    O .fit do MyWhoosh sobe como veio: o Garmin aceita o fabricante dele sem
    reclamar, e reescrever o arquivo para fingir um Edge só serviria para perder
    a rastreabilidade da origem.
    """
    import asyncio

    from app.services.garmin_service import get_garmin_client

    api = await get_garmin_client(user_id)
    caminho = os.path.join(tempfile.gettempdir(), f"mywhoosh_{activity_id}.fit")
    with open(caminho, "wb") as f:
        f.write(conteudo)
    try:
        await asyncio.to_thread(api.upload_activity, caminho)
        return True
    except Exception as exc:
        # 409 = o Garmin já tem essa atividade (o atleta subiu na mão, ou uma
        # rodada anterior conseguiu subir e falhou depois). Não é erro.
        if "409" in str(exc) or "Conflict" in str(exc):
            logger.info("mywhoosh: atividade %s já estava no Garmin", activity_id)
            return True
        raise
    finally:
        try:
            os.remove(caminho)
        except OSError:
            pass


async def sync_para_garmin(user_id: str, limite: int = _JANELA_PADRAO) -> int:
    """Sobe no Garmin as atividades novas do MyWhoosh. Retorna quantas subiram.

    Silencioso quando o usuário não tem MyWhoosh conectado — é o caso da maioria.
    """
    cred = await credenciais(user_id)
    if not cred:
        return 0

    sessao = await _login(*cred)
    atividades = await _listar(sessao, limite)

    enviadas = 0
    for atividade in atividades:
        activity_id = _id_da_atividade(atividade)
        if not activity_id or not atividade.get("activityFileId"):
            continue
        if not await _reservar(user_id, activity_id):
            continue                                   # já subiu antes
        try:
            conteudo = await _baixar_fit(sessao, atividade)
            await _subir_no_garmin(user_id, conteudo, activity_id)
            enviadas += 1
            logger.info("mywhoosh: atividade %s enviada ao Garmin (user=%s)",
                        activity_id, user_id)
        except Exception as exc:
            await _liberar(user_id, activity_id)
            logger.error("mywhoosh: falha ao enviar %s (user=%s) — %s",
                         activity_id, user_id, exc)
    return enviadas

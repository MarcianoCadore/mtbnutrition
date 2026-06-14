"""Serviço para criar e mover treinos na coleção db.semanas,
com suporte a estado pendente de confirmação de colisão (db.conversa_estado).

Regras de negócio:
- Um doc de semana tem: {semana_inicio: str (ISO segunda), user_id: str, objetivo: str, treinos: [{...}]}
- Cada treino tem os campos de TreinoSemana (data, tipo, periodo, duracao_min, etc.)
- "Sem treino" = item com tipo=DESCANSO ou ausente no array.
- Colisão: dia destino já tem treino real (tipo != DESCANSO e duracao_min > 0).
- Estado pendente expira após 15 minutos sem resposta.
- Chave lógica da semana: {semana_inicio, user_id} — dois usuários podem ter a mesma
  semana sem colisão. O _id é automático; filtre sempre por ambos os campos.
"""

import logging
from datetime import datetime, timedelta, timezone
from app.services.mongo_service import get_db

logger = logging.getLogger(__name__)

# ── helpers de data ───────────────────────────────────────────────────────────

def _semana_inicio(data_iso: str) -> str:
    """Retorna a segunda-feira (ISO) da semana que contém data_iso."""
    d = datetime.strptime(data_iso, "%Y-%m-%d").date()
    return (d - timedelta(days=d.weekday())).isoformat()


def _treino_vazio(data_iso: str) -> dict:
    """Retorna um item de treino representando descanso para a data."""
    return {
        "data": data_iso,
        "tipo": "DESCANSO",
        "periodo": None,
        "duracao_min": None,
        "distancia_km": None,
        "elevacao_m": None,
        "cadencia_rpm": None,
        "descricao": None,
        "fit_file": None,
        "garmin_workout_id": None,
        "resultado": None,
    }


def _e_treino_real(treino: dict | None) -> bool:
    """True se o item representa um treino efetivo (não descanso/vazio)."""
    if not treino:
        return False
    tipo = treino.get("tipo") or "DESCANSO"
    return tipo != "DESCANSO" and bool(treino.get("duracao_min"))


# ── leitura ───────────────────────────────────────────────────────────────────

async def get_treino(user_id: str, data_iso: str) -> dict | None:
    """Retorna o dict do treino do dia, ou None se não houver treino real."""
    sem = _semana_inicio(data_iso)
    db = get_db()
    doc = await db.semanas.find_one({"semana_inicio": sem, "user_id": user_id})
    if not doc:
        return None
    for t in doc.get("treinos", []):
        if t.get("data") == data_iso:
            return t if _e_treino_real(t) else None
    return None


# ── garantir que a semana existe e o dia tem item ────────────────────────────

async def _garantir_dia(user_id: str, data_iso: str, db) -> None:
    """Garante que o doc da semana existe e o array treinos tem um item para data_iso.
    Cria com DESCANSO se necessário. Não sobrescreve itens existentes."""
    sem = _semana_inicio(data_iso)
    doc = await db.semanas.find_one({"semana_inicio": sem, "user_id": user_id})
    if not doc:
        # Cria o doc com o único item; user_id gravado como string
        await db.semanas.insert_one({
            "semana_inicio": sem,
            "user_id": str(user_id),
            "objetivo": "",
            "treinos": [_treino_vazio(data_iso)],
        })
        return
    # Doc existe: verifica se o dia já tem item
    tem = any(t.get("data") == data_iso for t in doc.get("treinos", []))
    if not tem:
        await db.semanas.update_one(
            {"semana_inicio": sem, "user_id": user_id},
            {"$push": {"treinos": _treino_vazio(data_iso)}},
        )


# ── operação de gravação de treino em um dia ─────────────────────────────────

async def _set_treino_dia(user_id: str, data_iso: str, campos: dict, db) -> None:
    """Atualiza os campos de treino de data_iso. 'campos' deve incluir todos os
    campos necessários (tipo, duracao_min, etc.) — faz $set no item existente."""
    sem = _semana_inicio(data_iso)
    await _garantir_dia(user_id, data_iso, db)
    # Usa o operador posicional para atualizar o item com a data certa
    update = {f"treinos.$.{k}": v for k, v in campos.items()}
    await db.semanas.update_one(
        {"semana_inicio": sem, "user_id": user_id, "treinos.data": data_iso},
        {"$set": update},
    )


# ── mover treino ─────────────────────────────────────────────────────────────

async def mover_treino(user_id: str, origem_iso: str, destino_iso: str, modo: str) -> dict:
    """Move o treino de origem_iso para destino_iso.

    modo:
      "sobrescrever" — treino da origem vai para destino; origem vira DESCANSO.
      "swap"         — troca os conteúdos de treino entre os dois dias.

    Retorna {"origem": dict_do_que_ficou, "destino": dict_do_que_ficou}.
    Lança ValueError se origem não tiver treino real.
    """
    db = get_db()

    # Lê o treino de origem
    treino_origem = await get_treino(user_id, origem_iso)
    if not treino_origem:
        raise ValueError(f"Não há treino em {origem_iso} para mover.")

    # Lê o treino de destino (pode ser None)
    treino_destino = await get_treino(user_id, destino_iso)

    # Campos que compõem o "conteúdo" do treino (excluindo a data e campos de resultado)
    _CAMPOS_TREINO = ["tipo", "periodo", "duracao_min", "distancia_km",
                      "elevacao_m", "cadencia_rpm", "descricao"]

    if modo == "swap":
        # Extrai conteúdo de cada lado
        conteudo_origem = {c: treino_origem.get(c) for c in _CAMPOS_TREINO}
        if treino_destino:
            conteudo_destino = {c: treino_destino.get(c) for c in _CAMPOS_TREINO}
        else:
            # Destino estava vazio → destino fica com o treino, origem fica como descanso
            conteudo_destino = {c: treino_origem.get(c) for c in _CAMPOS_TREINO}
            conteudo_origem = {c: _treino_vazio(origem_iso).get(c) for c in _CAMPOS_TREINO}

        # Grava em cada dia (preserva garmin_workout_id antigo = None para novo treino)
        campos_para_origem = dict(conteudo_destino)
        campos_para_origem["garmin_workout_id"] = None
        campos_para_destino = dict(conteudo_origem)
        campos_para_destino["garmin_workout_id"] = None

        await _set_treino_dia(user_id, origem_iso, campos_para_origem, db)
        await _set_treino_dia(user_id, destino_iso, campos_para_destino, db)

        resultado_origem = {"data": origem_iso, **campos_para_origem}
        resultado_destino = {"data": destino_iso, **campos_para_destino}

    else:  # sobrescrever
        # Destino recebe o treino da origem
        conteudo = {c: treino_origem.get(c) for c in _CAMPOS_TREINO}
        campos_destino = dict(conteudo)
        campos_destino["garmin_workout_id"] = None

        # Origem vira descanso
        campos_origem = {c: _treino_vazio(origem_iso).get(c) for c in _CAMPOS_TREINO}
        campos_origem["garmin_workout_id"] = None

        await _set_treino_dia(user_id, destino_iso, campos_destino, db)
        await _set_treino_dia(user_id, origem_iso, campos_origem, db)

        resultado_origem = {"data": origem_iso, **campos_origem}
        resultado_destino = {"data": destino_iso, **campos_destino}

    logger.info("mover_treino user=%s: %s → %s (modo=%s)", user_id, origem_iso, destino_iso, modo)
    return {
        "origem": resultado_origem,
        "destino": resultado_destino,
        # IDs antigos (para poder cancelar no Garmin)
        "garmin_id_origem_antigo": treino_origem.get("garmin_workout_id"),
        "garmin_id_destino_antigo": (treino_destino or {}).get("garmin_workout_id"),
    }


# ── criar treino em um dia ───────────────────────────────────────────────────

async def criar_treino_dia(
    user_id: str,
    data_iso: str,
    tipo: str,
    duracao_min: int,
    descricao: str | None = None,
    modo: str | None = None,   # None = caller já verificou colisão; grava direto
) -> dict:
    """Cria/substitui o treino do dia.

    Quando chamada pelo webhook já com o modo resolvido (ou quando não há colisão),
    simplesmente grava. O controle de colisão fica no caller (webhook).

    Retorna o dict do treino gravado.
    """
    db = get_db()

    # Grava na data informada
    garmin_id_antigo = None
    treino_existente = await get_treino(user_id, data_iso)
    if treino_existente:
        garmin_id_antigo = treino_existente.get("garmin_workout_id")

    campos = {
        "tipo": tipo,
        "periodo": None,
        "duracao_min": duracao_min,
        "distancia_km": None,
        "elevacao_m": None,
        "cadencia_rpm": None,
        "descricao": descricao or tipo.replace("_", " ").title(),
        "garmin_workout_id": None,
    }
    await _set_treino_dia(user_id, data_iso, campos, db)

    logger.info("criar_treino_dia user=%s: %s tipo=%s dur=%s", user_id, data_iso, tipo, duracao_min)
    return {
        "data": data_iso,
        **campos,
        "garmin_id_antigo": garmin_id_antigo,
    }


# ── remover treino de um dia (vira descanso) ─────────────────────────────────

async def remover_treino_dia(user_id: str, data_iso: str) -> dict:
    """Transforma o treino do dia em DESCANSO. Retorna o garmin_id antigo (para
    remover do Garmin). Lança ValueError se o dia não tiver treino real."""
    db = get_db()
    treino = await get_treino(user_id, data_iso)
    if not treino:
        raise ValueError(f"Não há treino em {data_iso} para remover.")

    garmin_id_antigo = treino.get("garmin_workout_id")
    tipo_antigo = treino.get("tipo")

    # Zera os campos de treino (vira descanso)
    campos = {c: _treino_vazio(data_iso).get(c) for c in
              ["tipo", "periodo", "duracao_min", "distancia_km",
               "elevacao_m", "cadencia_rpm", "descricao"]}
    campos["garmin_workout_id"] = None
    await _set_treino_dia(user_id, data_iso, campos, db)

    logger.info("remover_treino_dia user=%s: %s (era %s)", user_id, data_iso, tipo_antigo)
    return {
        "data": data_iso,
        "tipo_antigo": tipo_antigo,
        "garmin_id_antigo": garmin_id_antigo,
    }


# ── busca treinos da semana (para o resumo enviado no WhatsApp) ───────────────

async def get_treinos_semana(user_id: str, semana_inicio: str) -> list[dict]:
    """Retorna a lista de treinos do doc da semana (ou lista vazia se não existir)."""
    db = get_db()
    doc = await db.semanas.find_one({"semana_inicio": semana_inicio, "user_id": user_id})
    if not doc:
        return []
    return doc.get("treinos", [])


# ── estado pendente de colisão ────────────────────────────────────────────────
# Keyed por `from_` do WhatsApp (número E.164 completo como "whatsapp:+5551...")
# Pode ficar global (por número de telefone) — sem necessidade de escopar por user_id.

_EXPIRACAO_MINUTOS = 15


async def set_estado(from_: str, acao: str, payload: dict) -> None:
    """Persiste o estado pendente de confirmação para o número 'from_'."""
    db = get_db()
    await db.conversa_estado.replace_one(
        {"_id": from_},
        {
            "_id": from_,
            "acao": acao,
            "payload": payload,
            "criado_em": datetime.now(tz=timezone.utc),
        },
        upsert=True,
    )
    logger.debug("set_estado: from=%s acao=%s payload=%s", from_, acao, payload)


async def get_estado(from_: str) -> dict | None:
    """Retorna o estado pendente se existir e não estiver expirado; caso contrário None."""
    db = get_db()
    doc = await db.conversa_estado.find_one({"_id": from_})
    if not doc:
        return None
    criado_em = doc.get("criado_em")
    if criado_em:
        # Normaliza para UTC aware se vier sem timezone
        if criado_em.tzinfo is None:
            criado_em = criado_em.replace(tzinfo=timezone.utc)
        agora = datetime.now(tz=timezone.utc)
        if (agora - criado_em).total_seconds() > _EXPIRACAO_MINUTOS * 60:
            # Expirou → limpa e retorna None
            await limpar_estado(from_)
            logger.debug("get_estado: estado expirado para %s", from_)
            return None
    return doc


async def limpar_estado(from_: str) -> None:
    """Remove o estado pendente para o número 'from_'."""
    db = get_db()
    await db.conversa_estado.delete_one({"_id": from_})
    logger.debug("limpar_estado: from=%s", from_)

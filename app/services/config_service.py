"""Configurações editáveis pelo usuário, persistidas em db.config."""
import re

from app.services.mongo_service import get_db
from app.services.nutricao_service import DEFAULT_HORARIOS

CHAVE_HORARIOS = "horarios_refeicoes"
_RE_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


async def get_horarios() -> dict:
    """Horários das refeições configurados (ou os padrões)."""
    db = get_db()
    doc = await db.config.find_one({"chave": CHAVE_HORARIOS}, {"_id": 0, "chave": 0})
    return {**DEFAULT_HORARIOS, **(doc or {})}


async def salvar_horarios(cfg: dict) -> dict:
    """Valida e salva os horários (HH:MM). Ignora chaves desconhecidas."""
    limpo = {}
    for k in DEFAULT_HORARIOS:
        v = (cfg.get(k) or "").strip()
        if v and not _RE_HORA.match(v):
            raise ValueError(f"Horário inválido para '{k}': {v} (use HH:MM)")
        if v:
            limpo[k] = v
    db = get_db()
    await db.config.update_one(
        {"chave": CHAVE_HORARIOS},
        {"$set": {**limpo, "chave": CHAVE_HORARIOS}},
        upsert=True,
    )
    return {**DEFAULT_HORARIOS, **limpo}

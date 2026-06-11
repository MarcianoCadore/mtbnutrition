"""Configurações editáveis pelo usuário, persistidas em db.config."""
import re

from app.services.mongo_service import get_db
from app.services.nutricao_service import DEFAULT_HORARIOS

CHAVE_HORARIOS = "horarios_refeicoes"
_RE_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# Ordem natural das refeições no dia (chave -> rótulo amigável).
ORDEM_REFEICOES = [
    ("cafe", "Café da manhã"),
    ("almoco", "Almoço"),
    ("lanche_tarde", "Lanche da tarde"),
    ("jantar", "Jantar"),
]


def _para_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _validar_ordem(cfg: dict) -> None:
    """Garante café < almoço < lanche < jantar (pega confusão de manhã/noite,
    ex.: jantar marcado às 09:00 em vez de 21:00)."""
    prev_min = prev_nome = prev_hora = None
    for chave, nome in ORDEM_REFEICOES:
        atual = _para_min(cfg[chave])
        if prev_min is not None and atual <= prev_min:
            raise ValueError(
                f"{nome} ({cfg[chave]}) precisa ser depois de {prev_nome} ({prev_hora}). "
                f"Confira se não trocou manhã por noite (ex.: 09:00 em vez de 21:00)."
            )
        prev_min, prev_nome, prev_hora = atual, nome, cfg[chave]


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
    # valida a ordem do dia já com os defaults aplicados (campos não enviados)
    _validar_ordem({**DEFAULT_HORARIOS, **limpo})
    db = get_db()
    await db.config.update_one(
        {"chave": CHAVE_HORARIOS},
        {"$set": {**limpo, "chave": CHAVE_HORARIOS}},
        upsert=True,
    )
    return {**DEFAULT_HORARIOS, **limpo}

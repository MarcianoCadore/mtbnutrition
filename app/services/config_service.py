"""Configurações editáveis pelo usuário, persistidas em db.config."""
import re

from app.services.mongo_service import get_db
from app.services.nutricao_service import DEFAULT_HORARIOS

CHAVE_HORARIOS = "horarios_refeicoes"
CHAVE_ZONAS = "zonas_fc"
_RE_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# Zonas de FC padrão (as configuradas hoje no Garmin do Marciano).
DEFAULT_ZONAS = {
    "fc_max": 190,
    "limiar": 172,
    "zonas": [
        {"zona": 1, "min": 123, "max": 145},
        {"zona": 2, "min": 146, "max": 158},
        {"zona": 3, "min": 159, "max": 165},
        {"zona": 4, "min": 166, "max": 177},
        {"zona": 5, "min": 178, "max": 190},
    ],
}

# Ordem natural das refeições no dia (chave -> rótulo amigável).
ORDEM_REFEICOES = [
    ("cafe", "Café da manhã"),
    ("lanche_manha", "Lanche da manhã"),
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


# ── Zonas de frequência cardíaca ──────────────────────────────────────────────

async def get_zonas() -> dict:
    """Zonas de FC configuradas (ou os padrões)."""
    db = get_db()
    doc = await db.config.find_one({"chave": CHAVE_ZONAS}, {"_id": 0, "chave": 0})
    return doc or {k: v for k, v in DEFAULT_ZONAS.items()}


def _validar_zonas(data: dict) -> dict:
    """Valida e normaliza as 5 zonas + fc_max/limiar. Levanta ValueError."""
    zonas_in = data.get("zonas") or []
    if len(zonas_in) != 5:
        raise ValueError("São necessárias exatamente 5 zonas (Z1 a Z5).")

    zonas = []
    prev_max = None
    for i, z in enumerate(sorted(zonas_in, key=lambda x: int(x.get("zona", 0))), start=1):
        try:
            mn = int(z["min"])
            mx = int(z["max"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"Zona {i}: informe min e max em bpm (números inteiros).")
        if not (60 <= mn < mx <= 230):
            raise ValueError(f"Zona {i}: faixa inválida ({mn}-{mx}). Use 60–230 bpm com min < max.")
        if prev_max is not None and mn < prev_max:
            raise ValueError(f"Zona {i} ({mn}) deve começar a partir do fim da zona anterior ({prev_max}).")
        prev_max = mx
        zonas.append({"zona": i, "min": mn, "max": mx})

    fc_max = data.get("fc_max")
    limiar = data.get("limiar")
    try:
        fc_max = int(fc_max) if fc_max not in (None, "") else zonas[-1]["max"]
        limiar = int(limiar) if limiar not in (None, "") else None
    except (TypeError, ValueError):
        raise ValueError("FC máxima e limiar devem ser números inteiros.")

    return {"fc_max": fc_max, "limiar": limiar, "zonas": zonas}


async def salvar_zonas(data: dict) -> dict:
    """Valida e persiste as zonas de FC."""
    limpo = _validar_zonas(data)
    db = get_db()
    await db.config.update_one(
        {"chave": CHAVE_ZONAS},
        {"$set": {**limpo, "chave": CHAVE_ZONAS}},
        upsert=True,
    )
    return limpo


async def zonas_bpm_map() -> dict:
    """Mapa {numero_da_zona: {'min': bpm, 'max': bpm}} para montar os workouts."""
    cfg = await get_zonas()
    return {int(z["zona"]): {"min": int(z["min"]), "max": int(z["max"])} for z in cfg["zonas"]}


# ── Ajustes de "fuga" do plano (o que comi fora, por dia) ─────────────────────

async def extras_do_dia(data: str) -> list:
    """Lista de itens comidos fora do plano numa data (ISO YYYY-MM-DD)."""
    db = get_db()
    doc = await db.ajustes_dia.find_one({"_id": data})
    return (doc or {}).get("extras", [])


async def adicionar_extra_dia(data: str, extra: dict) -> list:
    """Acrescenta um item comido fora do plano ao dia. Retorna a lista atualizada."""
    item = {
        "resumo": str(extra.get("resumo", "")).strip() or "Alimento fora do plano",
        "kcal": max(0, int(extra.get("kcal", 0))),
        "proteina_g": round(float(extra.get("proteina_g", 0)), 1),
    }
    db = get_db()
    await db.ajustes_dia.update_one(
        {"_id": data},
        {"$push": {"extras": item}, "$set": {"data": data}},
        upsert=True,
    )
    return await extras_do_dia(data)


async def remover_ajuste_dia(data: str) -> None:
    """Remove todos os ajustes (extras) de um dia — volta ao plano original."""
    db = get_db()
    await db.ajustes_dia.delete_one({"_id": data})


async def adicionar_corte_dia(data: str, kcal: float) -> None:
    """Acumula kcal de corte de carboidrato no dia (débito de fuga).
    Usa $inc para somar ao valor existente (múltiplas fugas acumulam corretamente)."""
    db = get_db()
    await db.ajustes_dia.update_one(
        {"_id": data},
        {"$inc": {"corte_kcal": int(round(kcal))}, "$set": {"data": data}},
        upsert=True,
    )


async def corte_do_dia(data: str) -> int | None:
    """Retorna o corte de kcal de carboidrato registrado para o dia.

    Semântica especial para retrocompatibilidade com docs legados:
    - Doc sem 'corte_kcal' MAS com 'extras' → retorna None (sinaliza: use o
      fallback de somar extras em plano_para_tipo).
    - Doc com 'corte_kcal' explícito → retorna o valor (pode ser 0).
    - Sem doc → retorna None (idem: fallback de extras).
    """
    db = get_db()
    doc = await db.ajustes_dia.find_one({"_id": data})
    if doc is None:
        return None
    if "corte_kcal" not in doc:
        # doc legado: tem extras mas não tem corte_kcal — sinaliza para o caller
        # usar o fallback de somar as kcal dos extras em plano_para_tipo.
        return None
    return int(doc["corte_kcal"])


async def ajuste_do_dia(data: str) -> dict:
    """Lê extras e corte_kcal numa única consulta ao banco.
    Útil para callers que precisam dos dois campos (reduz round-trips)."""
    db = get_db()
    doc = await db.ajustes_dia.find_one({"_id": data}) or {}
    corte = doc.get("corte_kcal")
    return {
        "extras": doc.get("extras", []),
        # None = sem corte explícito (doc legado ou inexistente) → usar fallback
        "corte_kcal": int(corte) if corte is not None else None,
    }

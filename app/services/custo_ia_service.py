"""Quanto cada assinante custa em IA.

A mensalidade é R$ 24,99 (~US$ 4,50). O parecer fisiológico roda em Opus, o
chat e a análise pós-treino em Sonnet, a geração de semana em Sonnet com
fallback Gemini — sem medir, não dá para saber se a margem é positiva, e o
primeiro sinal de que não é seria a fatura.

Cada chamada grava um documento em `db.uso_ia` com tokens, modelo e custo
estimado. O painel do admin soma por usuário e por mês.

Preços em USD por 1M de tokens (Anthropic, agosto/2026). Cache: leitura ~0,1×
do input, escrita 1,25× (TTL de 5 min) — é o que torna o prompt caching de
`chat_service` e `plano_semana_service` uma economia de verdade e não uma
troca de um custo por outro.
"""
import logging
from datetime import datetime, timezone

from app.services.mongo_service import get_db

logger = logging.getLogger(__name__)

# ─── Tabela de preços (USD por 1M de tokens) ─────────────────────────────────

_PRECOS = {
    # Anthropic
    "claude-opus-5":     {"in": 5.00, "out": 25.00},
    "claude-opus-4-8":   {"in": 5.00, "out": 25.00},
    "claude-opus-4-7":   {"in": 5.00, "out": 25.00},
    "claude-sonnet-5":   {"in": 3.00, "out": 15.00},
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00},
    "claude-haiku-4-5":  {"in": 1.00, "out":  5.00},
    # Google — o fallback gratuito tem cota, mas não é infinito; contabilizar
    # pelo preço de tabela deixa visível quanto o fallback estaria custando.
    "gemini-2.0-flash":       {"in": 0.10, "out": 0.40},
    "gemini-2.5-flash-lite":  {"in": 0.10, "out": 0.40},
}

_PRECO_PADRAO = {"in": 3.00, "out": 15.00}

_FATOR_CACHE_LEITURA = 0.10
_FATOR_CACHE_ESCRITA = 1.25

# Cotação usada para exibir em reais. Aproximada de propósito: serve para o
# admin comparar com os R$ 24,99, não para contabilidade.
USD_BRL = 5.60


def preco_do_modelo(modelo: str) -> dict:
    """Preço por 1M de tokens. Casa por prefixo para tolerar sufixos de data."""
    if modelo in _PRECOS:
        return _PRECOS[modelo]
    for nome, preco in _PRECOS.items():
        if modelo.startswith(nome):
            return preco
    logger.warning("custo_ia: modelo sem preço na tabela (%s) — usando padrão", modelo)
    return _PRECO_PADRAO


def extrair_uso(resp) -> dict:
    """Tokens de uma resposta da Anthropic ou do Gemini, num formato só.

    Os dois SDKs reportam uso em lugares diferentes; normalizar aqui evita
    espalhar `getattr` por todos os serviços.
    """
    u = getattr(resp, "usage", None)
    if u is None:
        # Gemini: usage_metadata com nomes próprios
        m = getattr(resp, "usage_metadata", None)
        if m is None:
            return {}
        return {
            "entrada": int(getattr(m, "prompt_token_count", 0) or 0),
            "saida":   int(getattr(m, "candidates_token_count", 0) or 0),
            "cache_leitura": int(getattr(m, "cached_content_token_count", 0) or 0),
            "cache_escrita": 0,
        }
    return {
        "entrada":       int(getattr(u, "input_tokens", 0) or 0),
        "saida":         int(getattr(u, "output_tokens", 0) or 0),
        "cache_leitura": int(getattr(u, "cache_read_input_tokens", 0) or 0),
        "cache_escrita": int(getattr(u, "cache_creation_input_tokens", 0) or 0),
    }


def custo_usd(modelo: str, uso: dict) -> float:
    """Custo em dólares de uma chamada."""
    if not uso:
        return 0.0
    p = preco_do_modelo(modelo)
    milhao = 1_000_000
    return (
        uso.get("entrada", 0)       * p["in"]  / milhao
        + uso.get("saida", 0)       * p["out"] / milhao
        + uso.get("cache_leitura", 0) * p["in"] * _FATOR_CACHE_LEITURA / milhao
        + uso.get("cache_escrita", 0) * p["in"] * _FATOR_CACHE_ESCRITA / milhao
    )


# ─── Registro ────────────────────────────────────────────────────────────────

async def registrar(user_id, feature: str, modelo: str, resp=None,
                    uso: dict | None = None) -> float:
    """Grava o uso de uma chamada e devolve o custo em USD.

    Nunca levanta: telemetria de custo não pode derrubar a geração de um
    treino. Erro aqui vira log e segue.
    """
    try:
        dados = uso if uso is not None else extrair_uso(resp)
        if not dados:
            return 0.0
        valor = custo_usd(modelo, dados)
        agora = datetime.now(timezone.utc)
        await get_db().uso_ia.insert_one({
            "user_id":  str(user_id) if user_id else None,
            "feature":  feature,
            "modelo":   modelo,
            "mes":      agora.strftime("%Y-%m"),
            "em":       agora,
            "custo_usd": round(valor, 6),
            **dados,
        })
        return valor
    except Exception as exc:
        logger.warning("custo_ia: falha ao registrar uso de %s/%s: %s",
                       feature, modelo, exc)
        return 0.0


# ─── Consultas para o painel ─────────────────────────────────────────────────

async def _agregar(match: dict, chave) -> list[dict]:
    cursor = get_db().uso_ia.aggregate([
        {"$match": match},
        {"$group": {
            "_id": chave,
            "custo_usd": {"$sum": "$custo_usd"},
            "chamadas":  {"$sum": 1},
            "entrada":   {"$sum": "$entrada"},
            "saida":     {"$sum": "$saida"},
        }},
        {"$sort": {"custo_usd": -1}},
    ])
    return await cursor.to_list(length=None)


def mes_atual() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def custo_por_usuario(mes: str | None = None) -> dict[str, dict]:
    """{user_id: {custo_usd, custo_brl, chamadas}} no mês."""
    linhas = await _agregar({"mes": mes or mes_atual()}, "$user_id")
    return {
        (linha["_id"] or "sem_usuario"): {
            "custo_usd": round(linha["custo_usd"], 4),
            "custo_brl": round(linha["custo_usd"] * USD_BRL, 2),
            "chamadas":  linha["chamadas"],
        }
        for linha in linhas
    }


async def custo_por_feature(mes: str | None = None) -> list[dict]:
    """Onde o dinheiro está indo: chat, parecer, semana, análise pós-treino."""
    linhas = await _agregar({"mes": mes or mes_atual()}, "$feature")
    return [
        {
            "feature":   linha["_id"] or "?",
            "custo_usd": round(linha["custo_usd"], 4),
            "custo_brl": round(linha["custo_usd"] * USD_BRL, 2),
            "chamadas":  linha["chamadas"],
            "tokens":    linha["entrada"] + linha["saida"],
        }
        for linha in linhas
    ]


async def total_do_mes(mes: str | None = None) -> dict:
    linhas = await _agregar({"mes": mes or mes_atual()}, None)
    if not linhas:
        return {"custo_usd": 0.0, "custo_brl": 0.0, "chamadas": 0}
    t = linhas[0]
    return {
        "custo_usd": round(t["custo_usd"], 4),
        "custo_brl": round(t["custo_usd"] * USD_BRL, 2),
        "chamadas":  t["chamadas"],
    }


async def garantir_indices() -> None:
    """Índices para o painel não varrer a coleção inteira."""
    db = get_db()
    await db.uso_ia.create_index([("mes", 1), ("user_id", 1)], name="idx_uso_mes_user")
    await db.uso_ia.create_index("em", name="idx_uso_em")

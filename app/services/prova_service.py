"""Camada de dados das provas (competições) — coleção db.provas.

Cada documento é uma prova que o atleta vai disputar. A próxima prova orienta a
periodização dos treinos (base → construção → pico → polimento/taper) e os
"focos até a prova". Todas as funções que tocam o banco são async (motor).

Formato canônico do documento:
{
    _id: ObjectId,
    user_id: str,                 # ObjectId do dono, como string
    nome: str,
    data: "YYYY-MM-DD",
    local: str | None,
    distancia_km: float | None,
    altimetria_m: int | None,
    terreno: str | None,          # ex.: "XCO", "maratona/XCM", "trail", "gravel"
    prioridade: "A" | "B" | "C",
    meta: str | None,             # objetivo / observações livres
    focos: {                      # cache dos "focos até a prova" (gerados por IA)
        "itens": [str],
        "gerado_em": datetime,
    } | None,
    criado_em: datetime,
}
"""
from datetime import date, datetime

from bson import ObjectId

from app.services.mongo_service import get_db

# Limiares de periodização (em semanas até a prova).
_SEMANAS_TAPER = 1      # ≤ 1 semana: polimento/taper (a semana da prova)
_SEMANAS_PICO = 3       # 2–3 semanas: pico
_SEMANAS_CONSTRUCAO = 8  # 4–8 semanas: construção; > 8: base

_PRIORIDADES = {"A", "B", "C"}
_CAMPOS_EDITAVEIS = {
    "nome", "data", "local", "distancia_km",
    "altimetria_m", "terreno", "prioridade", "meta",
}


def _hoje_iso() -> str:
    return date.today().isoformat()


def _limpar(dados: dict) -> dict:
    """Mantém só os campos editáveis e normaliza tipos básicos."""
    out: dict = {}
    for k in _CAMPOS_EDITAVEIS:
        if k not in dados:
            continue
        v = dados[k]
        if k == "prioridade":
            v = str(v).upper().strip() if v else "B"
            v = v if v in _PRIORIDADES else "B"
        elif k == "distancia_km":
            v = float(v) if v not in (None, "") else None
        elif k == "altimetria_m":
            v = int(float(v)) if v not in (None, "") else None
        elif isinstance(v, str):
            v = v.strip() or None
        out[k] = v
    return out


async def criar_prova(user_id: str, dados: dict) -> dict:
    """Cria uma prova para o usuário. Exige nome e data (YYYY-MM-DD)."""
    db = get_db()
    doc = _limpar(dados)
    if not doc.get("nome") or not doc.get("data"):
        raise ValueError("nome e data são obrigatórios")
    doc.setdefault("prioridade", "B")
    doc["user_id"] = str(user_id)
    doc["focos"] = None
    doc["criado_em"] = datetime.now()
    res = await db.provas.insert_one(doc)
    doc["_id"] = str(res.inserted_id)
    return doc


async def listar_provas(user_id: str) -> list[dict]:
    """Lista as provas do usuário, ordenadas por data (mais próxima primeiro)."""
    db = get_db()
    cursor = db.provas.find({"user_id": str(user_id)}).sort("data", 1)
    provas = await cursor.to_list(length=None)
    for p in provas:
        p["_id"] = str(p["_id"])
    return provas


async def proxima_prova(user_id: str, ref: str | None = None) -> dict | None:
    """Próxima prova com data >= ref (hoje por padrão), a mais próxima no tempo."""
    db = get_db()
    ref = ref or _hoje_iso()
    doc = await db.provas.find_one(
        {"user_id": str(user_id), "data": {"$gte": ref}},
        sort=[("data", 1)],
    )
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def atualizar_prova(user_id: str, prova_id: str, campos: dict) -> None:
    """Atualiza parcialmente uma prova do usuário."""
    db = get_db()
    try:
        oid = ObjectId(str(prova_id))
    except Exception:
        raise ValueError(f"prova_id inválido: {prova_id}")
    novos = _limpar(campos)
    if not novos:
        return
    # Editar qualquer campo invalida o cache de focos (será regenerado).
    novos["focos"] = None
    await db.provas.update_one(
        {"_id": oid, "user_id": str(user_id)}, {"$set": novos}
    )


async def remover_prova(user_id: str, prova_id: str) -> None:
    db = get_db()
    try:
        oid = ObjectId(str(prova_id))
    except Exception:
        raise ValueError(f"prova_id inválido: {prova_id}")
    await db.provas.delete_one({"_id": oid, "user_id": str(user_id)})


async def salvar_focos(prova_id: str, itens: list[str]) -> None:
    """Grava o cache dos focos gerados pela IA com timestamp."""
    db = get_db()
    try:
        oid = ObjectId(str(prova_id))
    except Exception:
        return
    await db.provas.update_one(
        {"_id": oid},
        {"$set": {"focos": {"itens": itens, "gerado_em": datetime.now()}}},
    )


# ─── Periodização (helpers puros) ──────────────────────────────────────────────

def dias_ate(data_prova: str, ref: str | None = None) -> int:
    """Dias entre ref (hoje por padrão) e a data da prova. Pode ser negativo."""
    ref_d = date.fromisoformat(ref) if ref else date.today()
    return (date.fromisoformat(data_prova) - ref_d).days


def semanas_ate(data_prova: str, ref: str | None = None) -> int:
    """Semanas inteiras até a prova (arredonda pra cima dias parciais)."""
    d = dias_ate(data_prova, ref)
    return max(0, -(-d // 7))  # ceil para dias positivos


def fase_periodizacao(semanas: int) -> str:
    """Fase de treino conforme semanas restantes até a prova."""
    if semanas <= _SEMANAS_TAPER:
        return "taper"
    if semanas <= _SEMANAS_PICO:
        return "pico"
    if semanas <= _SEMANAS_CONSTRUCAO:
        return "construcao"
    return "base"


# Rótulos amigáveis para exibir no portal.
FASE_LABEL = {
    "base": "Base aeróbica",
    "construcao": "Construção",
    "pico": "Pico",
    "taper": "Polimento (taper)",
}

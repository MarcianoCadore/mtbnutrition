"""Camada de dados de usuários — coleção db.users.

Cada documento representa um atleta cadastrado no portal.
Todas as funções que tocam o banco são async (motor).

Formato canônico do documento (sem senha_hash ao devolver):
{
    _id: ObjectId,
    login: str,               # único, lowercase
    senha_hash: str,          # bcrypt via passlib (removido antes de devolver)
    nome: str,
    telefone: str,            # E.164, ex "+5551999999999" (vazio até verificar)
    telefone_verificado: bool,
    perfil: {
        idade: int,
        peso_kg: float,
        altura_cm: int,
        fc_max: int,
        limiar_bpm: int,
    },
    preferencias: {
        objetivo: str,
        dias_treino: list[int],   # 0=seg .. 6=dom
        perder_peso: bool,
    },
    zonas: {                  # mesmo formato de DEFAULT_ZONAS / get_zonas
        fc_max: int,
        limiar: int | None,
        zonas: [
            {zona: int, min: int, max: int},  # 5 entradas (Z1..Z5)
        ],
    },
    horarios: {               # mesmo formato de DEFAULT_HORARIOS / get_horarios
        cafe: "HH:MM",
        lanche_manha: "HH:MM",
        almoco: "HH:MM",
        lanche_tarde: "HH:MM",
        jantar: "HH:MM",
    },
    nutricao: {
        meta_peso_kg: float | None,
        meta_proteina_g: int | None,
    },
    integracao: {
        tipo: "none" | "garmin" | "strava",
        garmin: None,
        strava: None,
    },
    whatsapp: {
        ativo: bool,
    },
    criado_em: datetime (utc),
}
"""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from passlib.context import CryptContext

from app.services.mongo_service import get_db
from app.services.nutricao_service import DEFAULT_HORARIOS

# ─── Contexto de hashing de senha (bcrypt) ───────────────────────────────────

_crypt = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_senha(senha: str) -> str:
    """Gera o hash bcrypt da senha informada."""
    return _crypt.hash(senha)


def verificar_senha(senha: str, senha_hash: str) -> bool:
    """Retorna True se a senha em texto plano bate com o hash."""
    return _crypt.verify(senha, senha_hash)


# ─── Derivação de zonas de FC ─────────────────────────────────────────────────

def derivar_zonas(fc_max: int, limiar_bpm: int | None = None, metodo: str = "fcmax") -> dict:
    """Deriva as 5 zonas de FC.

    metodo="fcmax" (padrão) — percentuais do FCmáx clássico:
        Z1: 64–76 %  → fácil / regenerativo
        Z2: 77–85 %  → base aeróbica
        Z3: 86–89 %  → aeróbico moderado / tempo
        Z4: 90–94 %  → limiar
        Z5: 95–100 % → máximo / VO2max

    metodo="ll" — percentuais do Limiar Lático (modelo Friel):
        Z1: 65–84 %  → regenerativo
        Z2: 85–89 %  → base aeróbica
        Z3: 90–94 %  → tempo / sub-limiar
        Z4: 95–99 %  → limiar
        Z5: 100–105 % → VO2max (teto = fc_max se disponível)
    """
    if metodo == "ll" and limiar_bpm:
        pcts = [(0.65, 0.84), (0.85, 0.89), (0.90, 0.94), (0.95, 0.99), (1.00, 1.05)]
        ref = limiar_bpm
        zonas = [
            {"zona": i + 1, "min": round(ref * mn), "max": round(ref * mx)}
            for i, (mn, mx) in enumerate(pcts)
        ]
        zonas[-1]["max"] = fc_max if fc_max and fc_max > limiar_bpm else round(ref * 1.05)
    else:
        metodo = "fcmax"
        pcts = [(0.64, 0.76), (0.77, 0.85), (0.86, 0.89), (0.90, 0.94), (0.95, 1.00)]
        zonas = [
            {"zona": i + 1, "min": round(fc_max * mn), "max": round(fc_max * mx)}
            for i, (mn, mx) in enumerate(pcts)
        ]
        zonas[-1]["max"] = fc_max

    return {
        "fc_max": fc_max,
        "limiar": limiar_bpm,
        "metodo": metodo,
        "zonas": zonas,
    }


# ─── Helper: remove senha_hash antes de devolver ─────────────────────────────

def sem_senha(doc: dict | None) -> dict | None:
    """Remove o campo senha_hash do documento antes de devolvê-lo ao caller.
    Retorna None se o doc for None."""
    if doc is None:
        return None
    return {k: v for k, v in doc.items() if k != "senha_hash"}


# ─── CRUD assíncrono ─────────────────────────────────────────────────────────

async def criar_usuario(dados: dict) -> dict:
    """Cria um novo usuário em db.users.

    Parâmetros esperados em `dados`:
        login (str, obrigatório)
        senha (str, obrigatório — será hasheada)
        nome (str)
        telefone (str, padrão "")
        telefone_verificado (bool, padrão False)
        perfil (dict: idade, peso_kg, altura_cm, fc_max, limiar_bpm)
        preferencias (dict: objetivo, dias_treino, perder_peso)
        zonas (dict, opcional — derivado de fc_max se omitido)
        horarios (dict, opcional — DEFAULT_HORARIOS se omitido)
        nutricao (dict: meta_peso_kg, meta_proteina_g)
        integracao (dict: tipo, garmin, strava)
        whatsapp (dict: ativo)

    Lança ValueError se o login já existir.
    Retorna o doc inserido sem senha_hash.
    """
    db = get_db()
    login = dados["login"].strip().lower()

    # Verifica unicidade de login
    existente = await db.users.find_one({"login": login})
    if existente:
        raise ValueError(f"Já existe um usuário com login '{login}'.")

    perfil = dados.get("perfil") or {}
    fc_max = int(perfil.get("fc_max") or 190)
    limiar_bpm = perfil.get("limiar_bpm")
    if limiar_bpm is not None:
        limiar_bpm = int(limiar_bpm)

    # Zonas: usa as fornecidas ou deriva da FCmáx
    zonas = dados.get("zonas") or derivar_zonas(fc_max, limiar_bpm)

    # Horários: usa os fornecidos ou usa os padrões
    horarios = dados.get("horarios") or dict(DEFAULT_HORARIOS)

    doc: dict[str, Any] = {
        "login": login,
        "senha_hash": hash_senha(dados["senha"]),
        "nome": dados.get("nome", "").strip(),
        "telefone": dados.get("telefone", "").strip(),
        "telefone_verificado": bool(dados.get("telefone_verificado", False)),
        "perfil": {
            "idade": int(perfil.get("idade") or 0),
            "peso_kg": float(perfil.get("peso_kg") or 0),
            "altura_cm": int(perfil.get("altura_cm") or 0),
            "sexo": (str(perfil.get("sexo") or "M").upper()[:1]),
            "fc_max": fc_max,
            "limiar_bpm": limiar_bpm,
        },
        "preferencias": {
            "objetivo": dados.get("preferencias", {}).get("objetivo", "performance"),
            "dias_treino": list(dados.get("preferencias", {}).get("dias_treino") or []),
            "perder_peso": bool(dados.get("preferencias", {}).get("perder_peso", False)),
        },
        "zonas": zonas,
        "horarios": horarios,
        "nutricao": {
            "meta_peso_kg": dados.get("nutricao", {}).get("meta_peso_kg"),
            "meta_proteina_g": dados.get("nutricao", {}).get("meta_proteina_g"),
        },
        "integracao": {
            "tipo": dados.get("integracao", {}).get("tipo", "none"),
            "garmin": dados.get("integracao", {}).get("garmin"),
            "strava": dados.get("integracao", {}).get("strava"),
        },
        "whatsapp": {
            "ativo": bool(dados.get("whatsapp", {}).get("ativo", False)),
        },
        "pagamento_confirmado": bool(dados.get("pagamento_confirmado", False)),
        "criado_em": datetime.now(timezone.utc),
    }

    result = await db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    return sem_senha(doc)


async def get_por_id(user_id) -> dict | None:
    """Busca um usuário pelo _id (ObjectId ou string). Retorna None se não encontrar."""
    db = get_db()
    if not isinstance(user_id, ObjectId):
        try:
            user_id = ObjectId(str(user_id))
        except Exception:
            return None
    doc = await db.users.find_one({"_id": user_id})
    return sem_senha(doc)


async def get_por_login(login: str) -> dict | None:
    """Busca um usuário pelo login (case-insensitive). Retorna None se não encontrar.

    ATENÇÃO: devolve o doc COM senha_hash para uso interno no fluxo de autenticação.
    O caller decide se remove o campo.
    """
    db = get_db()
    doc = await db.users.find_one({"login": login.strip().lower()})
    return doc  # mantém senha_hash intencionalmente para auth


async def get_por_telefone(telefone: str) -> dict | None:
    """Busca um usuário pelo telefone (E.164). Retorna None se não encontrar."""
    db = get_db()
    doc = await db.users.find_one({"telefone": telefone.strip()})
    return sem_senha(doc)


async def atualizar_usuario(user_id, campos: dict) -> None:
    """Atualiza parcialmente um usuário com $set dos campos fornecidos."""
    db = get_db()
    if not isinstance(user_id, ObjectId):
        try:
            user_id = ObjectId(str(user_id))
        except Exception:
            raise ValueError(f"user_id inválido: {user_id}")
    await db.users.update_one({"_id": user_id}, {"$set": campos})


async def listar_usuarios() -> list[dict]:
    """Lista todos os usuários (sem senha_hash). Usado pelo scheduler para iterar."""
    db = get_db()
    cursor = db.users.find({}, {"senha_hash": 0})
    return await cursor.to_list(length=None)


async def telefone_notificavel(user_id) -> str | None:
    """Telefone (E.164) para onde notificar ESTE usuário, ou None.

    Só devolve o número se o usuário verificou o telefone E tem o WhatsApp ativo.
    Evita o bug multiusuário de notificações caírem num número global/fixo:
    callers DEVEM usar este helper e, se vier None, simplesmente não enviar.
    """
    u = await get_por_id(user_id)
    if not u or not u.get("telefone_verificado"):
        return None
    if not (u.get("whatsapp") or {}).get("ativo"):
        return None
    tel = (u.get("telefone") or "").strip()
    return tel or None


# ─── Índices únicos ───────────────────────────────────────────────────────────

async def garantir_indices() -> None:
    """Cria índices únicos na coleção db.users.

    Deve ser chamada no startup da aplicação (ex.: lifespan do FastAPI),
    mas NÃO altera main.py — só disponibiliza a função para uso futuro.

    Índices criados:
    - login: unique (sempre obrigatório, nunca vazio)
    - telefone: unique + sparse, pois telefone pode estar vazio ("")
      enquanto o usuário ainda não verificou o número. O índice sparse
      ignora documentos onde o campo é vazio ou ausente, permitindo
      múltiplos usuários sem telefone cadastrado sem violar a unicidade.

    Nota: pymongo / motor criam o índice apenas se ainda não existir,
    então chamar esta função repetidamente é seguro (idempotente).
    """
    db = get_db()

    # Índice único no login (sempre lowercase)
    await db.users.create_index("login", unique=True, name="idx_users_login_unique")

    # Índice único no telefone, mas só para telefones não-vazios:
    # partialFilterExpression indexa apenas docs com telefone > "" (ou seja, exclui
    # string vazia E ausente), permitindo vários usuários ainda sem telefone
    # verificado sem violar a unicidade. Requer MongoDB 3.2+ (Atlas ok).
    await db.users.create_index(
        "telefone",
        unique=True,
        partialFilterExpression={"telefone": {"$gt": ""}},
        name="idx_users_telefone_unique_naovazio",
    )

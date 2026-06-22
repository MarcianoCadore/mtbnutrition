"""Script de migração single-user → multiusuário (Fase 1).

Cria o usuário "Marciano" em db.users a partir dos dados hardcoded e dos
valores de configuração já salvos em db.config. Em seguida, estampa user_id
nos documentos existentes das coleções db.semanas, db.planos,
db.atividades_processadas e db.ajustes_dia.

O script é IDEMPOTENTE: pode ser rodado várias vezes sem efeitos colaterais.

Uso:
    python scripts/migrar_multiusuario.py
"""

import asyncio
import sys
import os

# Garante que a raiz do projeto esteja no sys.path, independente do cwd
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402 (import após path fix)

from app.services.mongo_service import get_db  # noqa: E402
from app.services import user_service  # noqa: E402
from app.services.nutricao_service import DEFAULT_HORARIOS  # noqa: E402
from app.services.crypto_service import cifrar  # noqa: E402
from config.settings import settings  # noqa: E402


async def main() -> None:
    db = get_db()

    print("=" * 60)
    print("Migração multiusuário — Fase 1")
    print("=" * 60)

    # ── 1. Criar (ou reutilizar) o usuário Marciano ───────────────────────────

    login = settings.PORTAL_USER.strip().lower()
    print(f"\n[1] Verificando usuário login='{login}' …")

    usuario_existente = await db.users.find_one({"login": login})

    if usuario_existente:
        # user_id é STRING (str do ObjectId) — convenção do app: as coleções
        # escopadas guardam user_id como string e as queries usam string.
        user_id = str(usuario_existente["_id"])
        print(f"    → Usuário já existe (_id={user_id}). Reutilizando.")
    else:
        # Copiar zonas do db.config se existirem, senão derivar da FCmáx
        zonas_cfg = await db.config.find_one({"chave": "zonas_fc"}, {"_id": 0, "chave": 0})
        if zonas_cfg:
            zonas = zonas_cfg
            print("    → Zonas copiadas de db.config {chave:'zonas_fc'}.")
        else:
            zonas = user_service.derivar_zonas(fc_max=190, limiar_bpm=172)
            print("    → Zonas derivadas da FCmáx=190 (db.config vazio).")

        # Copiar horários do db.config se existirem, senão usar padrões
        horarios_cfg = await db.config.find_one(
            {"chave": "horarios_refeicoes"}, {"_id": 0, "chave": 0}
        )
        if horarios_cfg:
            # Mescla com DEFAULT_HORARIOS para garantir todas as chaves
            horarios = {**DEFAULT_HORARIOS, **horarios_cfg}
            print("    → Horários copiados de db.config {chave:'horarios_refeicoes'}.")
        else:
            horarios = dict(DEFAULT_HORARIOS)
            print("    → Horários padrão usados (db.config vazio).")

        dados_marciano = {
            "login": login,
            "senha": settings.PORTAL_PASSWORD,
            "nome": "Marciano",
            "telefone": settings.WHATSAPP_TO,
            "telefone_verificado": True,
            "perfil": {
                "idade": 34,
                "peso_kg": 85.0,
                "altura_cm": 181,
                "fc_max": 190,
                "limiar_bpm": 172,
            },
            "preferencias": {
                "objetivo": "performance",
                "dias_treino": [0, 1, 2, 3, 4, 5],  # segunda a sábado
                "perder_peso": True,
            },
            "zonas": zonas,
            "horarios": horarios,
            "nutricao": {
                "meta_peso_kg": 78.0,
                "meta_proteina_g": 187,
            },
            "integracao": {
                "tipo": "garmin",
                "garmin": None,
                "strava": None,
            },
            "whatsapp": {
                "ativo": True,
            },
        }

        doc_criado = await user_service.criar_usuario(dados_marciano)
        user_id = str(doc_criado["_id"])  # string — convenção do app
        print(f"    → Usuário criado com sucesso (_id={user_id}).")

    # ── 1b. Migrar credenciais Garmin para o doc do Marciano (idempotente) ──────
    #
    # Se settings.GARMIN_EMAIL e GARMIN_PASSWORD estiverem definidos E o campo
    # integracao.garmin ainda não tiver email salvo, grava as credenciais cifradas.
    # Isso permite que o sync automático continue funcionando enquanto o Marciano
    # não reconectar pelo novo fluxo de /workout/garmin/conectar.

    print("\n[1b] Verificando credenciais Garmin no doc do usuário …")

    doc_atual = await db.users.find_one({"login": login})
    garmin_cfg = ((doc_atual or {}).get("integracao") or {}).get("garmin") or {}

    if settings.GARMIN_EMAIL and settings.GARMIN_PASSWORD and not garmin_cfg.get("email"):
        senha_cifrada = cifrar(settings.GARMIN_PASSWORD)
        await db.users.update_one(
            {"login": login},
            {
                "$set": {
                    "integracao.tipo": "garmin",
                    "integracao.garmin": {
                        "email": settings.GARMIN_EMAIL,
                        "senha_cifrada": senha_cifrada,
                    },
                }
            },
        )
        print(f"    → Credenciais Garmin cifradas e salvas para '{login}'.")
    elif garmin_cfg.get("email"):
        print(f"    → Credenciais Garmin já presentes para '{login}', pulando.")
    else:
        print("    → GARMIN_EMAIL/PASSWORD não configurados, pulando.")

    # ── 2. Marcar coleções simples com user_id (idempotente) ─────────────────
    # Cobre tanto {user_id: {$exists: false}} quanto {user_id: null} porque
    # a migração anterior usava só $exists e deixou docs com user_id: null.

    print("\n[2] Estampando user_id nas coleções existentes …")

    _SEM_USER_ID = {"$or": [{"user_id": {"$exists": False}}, {"user_id": None}]}

    colecoes_simples = [
        "semanas", "planos", "atividades_processadas",
        "chat_nutricao", "overrides_cardapio",
    ]
    for nome_colecao in colecoes_simples:
        resultado = await db[nome_colecao].update_many(
            _SEM_USER_ID,
            {"$set": {"user_id": user_id}},
        )
        print(
            f"    → {nome_colecao}: {resultado.modified_count} doc(s) marcados "
            f"(matched={resultado.matched_count})."
        )

    # ── 3. Migrar db.ajustes_dia (tem _id = data ISO, não ObjectId) ──────────
    #
    # Cada doc tem _id = "YYYY-MM-DD". A migração adiciona:
    #   - user_id: ObjectId do Marciano
    #   - data:    cópia do _id (campo explícito para facilitar queries futuras)
    #
    # É idempotente: só atualiza docs onde user_id ainda não existe.

    print("\n[3] Migrando db.ajustes_dia …")

    cursor = db.ajustes_dia.find(_SEM_USER_ID)
    docs_ajuste = await cursor.to_list(length=None)

    total_ajustes = 0
    for doc in docs_ajuste:
        data_iso = doc["_id"]  # ex.: "2026-06-13"
        await db.ajustes_dia.update_one(
            {"_id": data_iso},
            {"$set": {"user_id": user_id, "data": data_iso}},
        )
        total_ajustes += 1

    print(f"    → ajustes_dia: {total_ajustes} doc(s) migrados.")

    # ── Resumo final ──────────────────────────────────────────────────────────

    print("\n" + "=" * 60)
    print("Migração concluída com sucesso.")
    print(f"  Usuário Marciano: _id={user_id} (login='{login}')")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

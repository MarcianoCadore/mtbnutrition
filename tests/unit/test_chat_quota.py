"""Quota semanal de perguntas do chat (features.chat_limite_semana).

O admin define o limite por usuário no painel; o uso é contado em db.chat_uso
por (user_id, semana) e renova naturalmente na virada de segunda-feira.
"""
import pytest
from bson import ObjectId

import app.services.chat_service as chat
from app.services.chat_service import quota_chat, registrar_pergunta_chat, _semana_atual_iso


async def _seed_user(fake_db, features=None):
    oid = ObjectId()
    await fake_db.users.insert_one({
        "_id": oid, "login": "atleta1", "nome": "Atleta",
        **({"features": features} if features is not None else {}),
    })
    return str(oid)


class TestQuotaChat:
    async def test_sem_limite_configurado_e_ilimitado(self, fake_db):
        uid = await _seed_user(fake_db)
        q = await quota_chat(uid)
        assert q == {"limite": None, "usadas": 0, "restantes": None}

    async def test_limite_zero_ou_invalido_e_ilimitado(self, fake_db):
        uid = await _seed_user(fake_db, {"chat_limite_semana": 0})
        assert (await quota_chat(uid))["limite"] is None
        uid2 = await _seed_user(fake_db, {"chat_limite_semana": "5"})
        assert (await quota_chat(uid2))["limite"] is None

    async def test_limite_sem_uso(self, fake_db):
        uid = await _seed_user(fake_db, {"chat_limite_semana": 5})
        q = await quota_chat(uid)
        assert q == {"limite": 5, "usadas": 0, "restantes": 5}

    async def test_registrar_pergunta_decrementa_restantes(self, fake_db):
        uid = await _seed_user(fake_db, {"chat_limite_semana": 5})
        await registrar_pergunta_chat(uid)
        await registrar_pergunta_chat(uid)
        q = await quota_chat(uid)
        assert q["usadas"] == 2
        assert q["restantes"] == 3

    async def test_uso_de_semana_anterior_nao_conta(self, fake_db):
        uid = await _seed_user(fake_db, {"chat_limite_semana": 5})
        await fake_db.chat_uso.insert_one(
            {"user_id": uid, "semana_inicio": "2020-01-06", "perguntas": 99})
        q = await quota_chat(uid)
        assert q["usadas"] == 0
        assert q["restantes"] == 5

    async def test_restantes_nunca_negativo(self, fake_db):
        uid = await _seed_user(fake_db, {"chat_limite_semana": 2})
        for _ in range(4):
            await registrar_pergunta_chat(uid)
        q = await quota_chat(uid)
        assert q["usadas"] == 4
        assert q["restantes"] == 0

    async def test_uso_e_escopado_por_usuario(self, fake_db):
        uid_a = await _seed_user(fake_db, {"chat_limite_semana": 5})
        uid_b = await _seed_user(fake_db, {"chat_limite_semana": 5})
        await registrar_pergunta_chat(uid_a)
        assert (await quota_chat(uid_a))["usadas"] == 1
        assert (await quota_chat(uid_b))["usadas"] == 0

    def test_semana_atual_e_uma_segunda(self):
        from datetime import date
        assert date.fromisoformat(_semana_atual_iso()).weekday() == 0

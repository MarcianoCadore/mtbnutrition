"""Fixtures para os smoke tests de rotas (TestClient + auth real + DB fake)."""
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

import main

_LONGE = datetime.now(timezone.utc) + timedelta(days=365)
_ONTEM = datetime.now(timezone.utc) - timedelta(days=1)


@pytest.fixture
def client():
    # Instancia SEM o context manager → não dispara o lifespan (scheduler/Garmin).
    return TestClient(main.app)


@pytest.fixture
def auth_client(client):
    """Devolve (client, user_id) já autenticado com um token de sessão válido.

    O user_id é um ObjectId válido (necessário para o middleware inject_chat e
    rotas que fazem ObjectId(user_id)). Sem documento no banco, o gate de
    assinatura deixa passar de propósito — ver `estado_por_id`.
    """
    user_id = str(ObjectId())
    token = main._gerar_token(user_id)
    client.cookies.set(main._COOKIE, token)
    return client, user_id


@pytest.fixture
def vencido_client(client, fake_db, run):
    """(client, user_id) de quem deixou a assinatura vencer — para testar o gate."""
    user_id = ObjectId()
    run(fake_db.users.insert_one({
        "_id": user_id,
        "login": "atleta_vencido",
        "assinatura": {"status": "expirada", "pago_ate": _ONTEM},
    }))
    token = main._gerar_token(str(user_id))
    client.cookies.set(main._COOKIE, token)
    return client, str(user_id)


@pytest.fixture
def run():
    """Executa uma corrotina até concluir (para semear o banco fake em testes sync)."""
    import asyncio

    def _run(coro):
        return asyncio.run(coro)

    return _run


@pytest.fixture(autouse=True)
def _sem_ia(monkeypatch):
    """Neutraliza chamadas à IA na geração de semana (offline, determinístico)."""
    import app.services.plano_semana_service as pss

    def _boom(*a, **k):
        raise RuntimeError("IA desligada no teste")

    monkeypatch.setattr(pss._client, "generate_content", _boom, raising=False)

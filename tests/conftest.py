"""Fixtures compartilhadas da suíte de testes.

Estratégia:
- Variáveis de ambiente determinísticas são definidas ANTES de qualquer import
  da aplicação (settings é instanciado no import de config.settings).
- `fake_db` substitui o cliente Mongo real por um AsyncMongoMockClient
  (mongomock-motor), em memória, sem rede. Como todos os serviços chamam
  `get_db()` — função definida em app.services.mongo_service e que lê o global
  `_client` do próprio módulo — basta sobrescrever esse global para que todos
  os serviços passem a usar o banco fake.
"""
import os

# Settings determinísticas (devem vir antes de importar a app).
os.environ.setdefault("SECRET_KEY", "test-secret-key-fixed")
os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("VALIDAR_TWILIO", "false")

import pytest
from mongomock_motor import AsyncMongoMockClient

import app.services.mongo_service as mongo_service


@pytest.fixture
def fake_db(monkeypatch):
    """Injeta um MongoDB em memória e devolve o handle do db `mtb_nutrition`."""
    client = AsyncMongoMockClient()
    monkeypatch.setattr(mongo_service, "_client", client)
    return client["mtb_nutrition"]


@pytest.fixture
def perfil_completo():
    """Perfil válido para cálculos de TDEE."""
    return {"peso_kg": 80, "altura_cm": 180, "idade": 30, "sexo": "M"}

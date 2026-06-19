"""Testes do whatsapp_service: decisão template/freeform (Twilio mockado) e formatação."""
import pytest

from app.services import whatsapp_service as ws
from config.settings import settings


class _FakeMsg:
    def __init__(self):
        self.sid = "SM123"
        self.status = "queued"
        self.error_code = None


class _FakeMessages:
    def __init__(self):
        self.ultima_chamada = None

    def create(self, **params):
        self.ultima_chamada = params
        return _FakeMsg()


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


@pytest.fixture
def fake_twilio(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(ws, "get_client", lambda: fake)
    monkeypatch.setattr(settings, "WHATSAPP_FROM", "+5511000000000")
    return fake


class TestSendMessage:
    async def test_modo_template_quando_tem_content_sid(self, fake_twilio, monkeypatch):
        monkeypatch.setattr(settings, "TWILIO_CONTENT_SID", "HX123")
        await ws.send_message("+5551999990000", "olá")
        params = fake_twilio.messages.ultima_chamada
        assert params["content_sid"] == "HX123"
        assert "body" not in params
        assert params["to"] == "whatsapp:+5551999990000"

    async def test_modo_freeform_sem_content_sid(self, fake_twilio, monkeypatch):
        monkeypatch.setattr(settings, "TWILIO_CONTENT_SID", "")
        await ws.send_message("+5551999990000", "corpo livre")
        params = fake_twilio.messages.ultima_chamada
        assert params["body"] == "corpo livre"
        assert "content_sid" not in params

    async def test_force_freeform_ignora_template(self, fake_twilio, monkeypatch):
        monkeypatch.setattr(settings, "TWILIO_CONTENT_SID", "HX123")
        await ws.send_message("+5551999990000", "x", force_freeform=True)
        params = fake_twilio.messages.ultima_chamada
        assert "body" in params
        assert "content_sid" not in params

    async def test_retorno_tem_sid_e_status(self, fake_twilio, monkeypatch):
        monkeypatch.setattr(settings, "TWILIO_CONTENT_SID", "")
        out = await ws.send_message("+5551999990000", "x")
        assert out["sid"] == "SM123"
        assert out["status"] == "queued"


class TestFmt:
    def test_adiciona_prefixo(self):
        assert ws._fmt("+5551999") == "whatsapp:+5551999"

    def test_nao_duplica_prefixo(self):
        assert ws._fmt("whatsapp:+5551999") == "whatsapp:+5551999"


class TestFormatSemanaTreinos:
    def _treinos(self):
        return [
            {"data": "2026-06-22", "tipo": "TIROS", "duracao_min": 60, "cadencia_rpm": "90"},
            {"data": "2026-06-23", "tipo": "DESCANSO"},
        ]

    def test_inclui_dia_e_tipo(self):
        txt = ws.format_semana_treinos_whatsapp("2026-06-22", self._treinos())
        assert "Segunda" in txt
        assert "Tiros" in txt
        assert "60 min" in txt

    def test_descanso_marcado(self):
        txt = ws.format_semana_treinos_whatsapp("2026-06-22", self._treinos())
        assert "Descanso" in txt

    def test_descricao_longa_truncada(self):
        treinos = [{"data": "2026-06-22", "tipo": "TEMPO", "duracao_min": 70,
                    "descricao": "x" * 200}]
        txt = ws.format_semana_treinos_whatsapp("2026-06-22", treinos)
        assert "…" in txt  # reticências de truncamento

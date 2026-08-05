"""Quais provas o painel mostra além da próxima.

Só provas futuras, por decisão de produto: o card é sobre o que vem pela
frente. Prova já corrida fica no histórico, em /workout/calendario.
"""
from datetime import date, datetime, timedelta

import pytest
from bson import ObjectId

import main


def _hoje(delta=0):
    return (date.today() + timedelta(days=delta)).isoformat()


@pytest.fixture(autouse=True)
def _sem_focos_ia(monkeypatch):
    """Focos vêm da IA; aqui interessa quais provas entram na resposta."""
    import app.services.ai_service as ais

    async def _vazio(*a, **k):
        return []
    monkeypatch.setattr(ais, "gerar_focos_prova", _vazio)


def _com_provas(client, fake_db, run, provas):
    oid = ObjectId()
    run(fake_db.users.insert_one({"_id": oid, "login": "atleta"}))
    uid = str(oid)
    for p in provas:
        run(fake_db.provas.insert_one({"user_id": uid, **p}))
    client.cookies.set(main._COOKIE, main._gerar_token(uid))
    return client


class TestPainelDeProvas:
    @pytest.mark.parametrize("dias_atras", [1, 4, 30, 120])
    def test_prova_ja_corrida_nao_aparece(self, client, fake_db, run, dias_atras):
        """O card é sobre o que vem pela frente — passada fica no calendário."""
        c = _com_provas(client, fake_db, run, [
            {"nome": "Já corrida", "data": _hoje(-dias_atras)},
            {"nome": "Sananduva",  "data": _hoje(25)},
        ])
        d = c.get("/workout/provas/proxima").json()

        assert d["prova"]["nome"] == "Sananduva"
        assert d["seguintes"] == []
        assert all(p["nome"] != "Já corrida" for p in d["seguintes"])

    def test_provas_futuras_vem_na_ordem_da_data(self, client, fake_db, run):
        c = _com_provas(client, fake_db, run, [
            {"nome": "Terceira", "data": _hoje(120)},
            {"nome": "Primeira", "data": _hoje(10)},
            {"nome": "Segunda",  "data": _hoje(60)},
        ])
        d = c.get("/workout/provas/proxima").json()

        assert d["prova"]["nome"] == "Primeira"
        assert [p["nome"] for p in d["seguintes"]] == ["Segunda", "Terceira"]

    def test_cada_prova_seguinte_traz_a_sua_fase(self, client, fake_db, run):
        """A fase é relativa a cada prova — usar a da próxima para todas diria
        que uma prova de 4 meses está em pico."""
        c = _com_provas(client, fake_db, run, [
            {"nome": "Perto", "data": _hoje(10)},
            {"nome": "Longe", "data": _hoje(150)},
        ])
        d = c.get("/workout/provas/proxima").json()

        assert d["fase_label"] != d["seguintes"][0]["fase_label"]
        assert d["seguintes"][0]["fase_label"] == "Base aeróbica"

    def test_a_propria_prova_em_destaque_nao_se_repete_na_lista(self, client, fake_db, run):
        c = _com_provas(client, fake_db, run, [{"nome": "Única", "data": _hoje(20)}])
        d = c.get("/workout/provas/proxima").json()
        assert d["prova"]["nome"] == "Única"
        assert d["seguintes"] == []

    def test_prova_de_outro_atleta_nao_vaza(self, client, fake_db, run):
        outro = ObjectId()
        run(fake_db.provas.insert_one(
            {"user_id": str(outro), "nome": "Do vizinho", "data": _hoje(5)}))

        c = _com_provas(client, fake_db, run, [{"nome": "Minha", "data": _hoje(20)}])
        d = c.get("/workout/provas/proxima").json()

        assert d["prova"]["nome"] == "Minha"
        assert all(p["nome"] != "Do vizinho" for p in d["seguintes"])

    def test_sem_prova_futura_devolve_vazio(self, client, fake_db, run):
        c = _com_provas(client, fake_db, run, [{"nome": "Só passada", "data": _hoje(-3)}])
        assert c.get("/workout/provas/proxima").json()["prova"] is None

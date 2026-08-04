"""Rotas do portal para o ajuste de FC não confiável (cinta sem bateria/sem cinta)."""
from bson import ObjectId

SEG = "2026-06-22"
TER = "2026-06-23"


def _seed_treino(run, fake_db, user_id, resultado=None):
    run(fake_db.semanas.insert_one({
        "semana_inicio": SEG, "user_id": user_id, "objetivo": "",
        "treinos": [{
            "data": TER, "tipo": "TIROS", "duracao_min": 60,
            "resultado": resultado if resultado is not None else {
                "duracao_min": 58, "avg_hr": 118, "max_hr": 131, "tss_obtido": 40,
                "analise_ia": {"nota": 4.0, "resumo": "faltou intensidade",
                               "pontos_fortes": [], "pontos_fracos": ["FC baixa"]},
            },
        }],
    }))


class TestMarcarFCInvalida:
    def test_marca_e_reavalia(self, auth_client, fake_db, run, monkeypatch):
        import app.services.ai_service as ai

        async def _fake(planejado, resultado, user_id=None, fit_path=None, ignorar_fc=None):
            assert ignorar_fc is True
            return {"nota": 8.0, "resumo": "sem FC", "pontos_fortes": [], "pontos_fracos": []}

        monkeypatch.setattr(ai, "analisar_atividade_pos_treino", _fake)

        client, user_id = auth_client
        _seed_treino(run, fake_db, user_id)

        r = client.post(f"/workout/treino/{SEG}/{TER}/fc-invalida",
                        json={"invalida": True, "motivo": "cinta sem bateria"})
        assert r.status_code == 200
        d = r.json()
        assert d["fc_invalida"] is True and d["nota"] == 8.0

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": user_id}))
        res = doc["treinos"][0]["resultado"]
        assert res["fc_invalida"] is True
        assert res["fc_invalida_motivo"] == "cinta sem bateria"

    def test_treino_inexistente_404(self, auth_client, fake_db, run):
        client, user_id = auth_client
        _seed_treino(run, fake_db, user_id)
        r = client.post(f"/workout/treino/{SEG}/2026-06-25/fc-invalida", json={"invalida": True})
        assert r.status_code == 404

    def test_sem_login_redireciona(self, client):
        r = client.post(f"/workout/treino/{SEG}/{TER}/fc-invalida",
                        json={"invalida": True}, follow_redirects=False)
        assert r.status_code == 303


class TestPreferenciaCinta:
    def test_salva_sem_cinta_e_reavalia_recentes(self, auth_client, fake_db, run, monkeypatch):
        import app.services.ai_service as ai
        import app.utils as utils
        from datetime import date

        monkeypatch.setattr(utils, "hoje_local", lambda: date(2026, 6, 24))

        async def _fake(planejado, resultado, user_id=None, fit_path=None, ignorar_fc=None):
            return {"nota": 7.5, "resumo": "sem FC", "pontos_fortes": [], "pontos_fracos": []}

        monkeypatch.setattr(ai, "analisar_atividade_pos_treino", _fake)

        client, user_id = auth_client
        run(fake_db.users.insert_one({"_id": ObjectId(user_id), "login": "x"}))
        _seed_treino(run, fake_db, user_id)

        r = client.patch("/workout/cinta-fc", json={"usa_cinta": False, "reavaliar_dias": 14})
        assert r.status_code == 200
        assert r.json()["reavaliados"] == [{"data": TER, "nota": 7.5}]

        u = run(fake_db.users.find_one({"_id": ObjectId(user_id)}))
        assert u["preferencias"]["sem_cinta_fc"] is True

    def test_sem_reavaliar_apenas_salva(self, auth_client, fake_db, run):
        client, user_id = auth_client
        run(fake_db.users.insert_one({"_id": ObjectId(user_id), "login": "x"}))
        r = client.patch("/workout/cinta-fc", json={"usa_cinta": True})
        assert r.status_code == 200
        assert r.json()["reavaliados"] == []
        u = run(fake_db.users.find_one({"_id": ObjectId(user_id)}))
        assert u["preferencias"]["sem_cinta_fc"] is False

    def test_body_sem_campo_400(self, auth_client, fake_db):
        client, _ = auth_client
        assert client.patch("/workout/cinta-fc", json={}).status_code == 400


class TestPaginaPerfil:
    def test_placeholder_da_cinta_e_substituido(self, auth_client, fake_db, run):
        client, user_id = auth_client
        run(fake_db.users.insert_one(
            {"_id": ObjectId(user_id), "login": "x",
             "preferencias": {"sem_cinta_fc": True}}))
        html = client.get("/workout/perfil").text
        assert "{{USA_CINTA}}" not in html
        assert "Você usa cinta cardíaca?" in html
        assert "let _usaCinta = '0'" in html

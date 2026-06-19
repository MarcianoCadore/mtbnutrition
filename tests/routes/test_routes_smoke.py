"""Smoke tests das rotas HTTP (auth, treinos, provas, admin)."""
import pytest
from bson import ObjectId


class TestPublicasEAuth:
    def test_health_publico(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_raiz_sem_login_redireciona(self, client):
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/login"

    def test_login_form_publico(self, client):
        assert client.get("/login").status_code == 200

    def test_token_invalido_redireciona(self, client):
        client.cookies.set("mtb_auth", "token.invalido.aqui")
        r = client.get("/workout/provas", follow_redirects=False)
        assert r.status_code == 303


class TestTreinosSemana:
    def test_semana_vazia_estrutura(self, auth_client, fake_db):
        client, _ = auth_client
        r = client.get("/workout/semana/2026-06-22")
        assert r.status_code == 200
        body = r.json()
        assert body["semana_inicio"] == "2026-06-22"
        assert body["treinos"] == []

    def test_gerar_primeira_semana_salva(self, auth_client, fake_db):
        client, uid = auth_client
        r = client.post("/workout/gerar-primeira-semana/2026-06-22")
        assert r.status_code == 200
        plano = r.json()
        assert len(plano["treinos"]) == 7
        # foi persistida no banco com origem=auto
        r2 = client.get("/workout/semana/2026-06-22")
        assert any(t["tipo"] != "DESCANSO" for t in r2.json()["treinos"])

    def test_apagar_primeira_semana(self, auth_client, fake_db):
        client, _ = auth_client
        client.post("/workout/gerar-primeira-semana/2026-06-22")
        r = client.request("DELETE", "/workout/primeira-semana/2026-06-22")
        assert r.status_code == 200
        assert r.json()["status"] == "apagado"
        # semana voltou a ficar vazia
        assert client.get("/workout/semana/2026-06-22").json()["treinos"] == []

    def test_nao_gera_sobre_semana_com_treino(self, auth_client, fake_db):
        client, uid = auth_client
        r1 = client.post("/workout/gerar-primeira-semana/2026-06-22")
        assert r1.status_code == 200
        # segunda tentativa sobre a mesma semana (já tem treinos) → 409
        r2 = client.post("/workout/gerar-primeira-semana/2026-06-22")
        assert r2.status_code == 409


class TestProvas:
    def test_criar_e_listar(self, auth_client, fake_db):
        client, _ = auth_client
        r = client.post("/workout/provas", json={"nome": "XCO", "data": "2026-09-01"})
        assert r.status_code == 200
        provas = client.get("/workout/provas").json()
        assert len(provas) == 1
        assert provas[0]["nome"] == "XCO"

    def test_criar_prova_campo_obrigatorio_faltando(self, auth_client, fake_db):
        client, _ = auth_client
        # Pydantic rejeita o corpo sem 'data' antes de chegar ao serviço.
        r = client.post("/workout/provas", json={"nome": "Sem data"})
        assert r.status_code == 422

    def test_criar_prova_data_vazia_falha_no_servico(self, auth_client, fake_db):
        client, _ = auth_client
        # 'data' presente mas vazia → passa no Pydantic, falha no serviço (400).
        r = client.post("/workout/provas", json={"nome": "X", "data": ""})
        assert r.status_code == 400


class TestAdmin:
    def test_nao_admin_recebe_403(self, auth_client, fake_db, run):
        client, uid = auth_client
        run(fake_db.users.insert_one({"_id": ObjectId(uid), "login": "comum"}))
        r = client.get("/admin")
        assert r.status_code == 403

    def test_admin_marciano_ok(self, client, fake_db, run):
        import main
        uid = str(ObjectId())
        client.cookies.set(main._COOKIE, main._gerar_token(uid))
        run(fake_db.users.insert_one({"_id": ObjectId(uid), "login": "marciano"}))
        r = client.get("/admin")
        assert r.status_code == 200
        assert "Administra" in r.text

    def test_toggle_chat(self, client, fake_db, run):
        import main
        uid, alvo = str(ObjectId()), str(ObjectId())
        client.cookies.set(main._COOKIE, main._gerar_token(uid))
        run(fake_db.users.insert_one({"_id": ObjectId(uid), "login": "marciano"}))
        run(fake_db.users.insert_one({"_id": ObjectId(alvo), "login": "x"}))
        r = client.post("/admin/toggle-chat", json={"user_id": alvo, "ativo": False})
        assert r.status_code == 200
        doc = run(fake_db.users.find_one({"_id": ObjectId(alvo)}))
        assert doc["features"]["chat"] is False

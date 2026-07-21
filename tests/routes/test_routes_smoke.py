"""Smoke tests das rotas HTTP (auth, treinos, provas, admin, potência, perfil)."""
import io
import pytest
from bson import ObjectId


class TestPublicasEAuth:
    def test_health_publico(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_raiz_sem_login_mostra_landing(self, client):
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "24,99" in r.text

    def test_raiz_logado_redireciona_portal(self, client):
        import main
        client.cookies.set(main._COOKIE, main._gerar_token(str(ObjectId())))
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"] == "/portal/"

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

    def test_toggle_pagamento(self, client, fake_db, run):
        import main
        uid, alvo = str(ObjectId()), str(ObjectId())
        client.cookies.set(main._COOKIE, main._gerar_token(uid))
        run(fake_db.users.insert_one({"_id": ObjectId(uid), "login": "marciano"}))
        run(fake_db.users.insert_one({"_id": ObjectId(alvo), "login": "x", "pagamento_confirmado": False}))
        r = client.post("/admin/toggle-pagamento", json={"user_id": alvo, "pago": True})
        assert r.status_code == 200
        doc = run(fake_db.users.find_one({"_id": ObjectId(alvo)}))
        assert doc["pagamento_confirmado"] is True


class TestPerfil:
    def test_get_perfil_retorna_html(self, auth_client, fake_db):
        client, _ = auth_client
        r = client.get("/workout/perfil")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_salvar_perfil_aceita_dados_validos(self, auth_client, fake_db):
        client, _ = auth_client
        r = client.post(
            "/workout/perfil",
            data={"idade": "32", "peso_kg": "78", "altura_cm": "178",
                  "sexo": "M", "objetivo": "performance_mtb"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200

    def test_salvar_perfil_campo_nao_numerico_falha(self, auth_client, fake_db):
        client, _ = auth_client
        r = client.post(
            "/workout/perfil",
            data={"idade": "abc", "peso_kg": "78", "altura_cm": "178",
                  "sexo": "M", "objetivo": "performance_mtb"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 400

    def test_perfil_sem_login_redireciona(self, client):
        r = client.get("/workout/perfil", follow_redirects=False)
        assert r.status_code == 303


class TestZonasPotencia:
    def _seed_user(self, fake_db, uid, run):
        """Insere doc de usuário para que atualizar_usuario encontre o registro."""
        run(fake_db.users.insert_one({"_id": ObjectId(uid)}))

    def test_zonas_dados_sem_ftp(self, auth_client, fake_db):
        client, _ = auth_client
        r = client.get("/workout/zonas/dados")
        assert r.status_code == 200
        d = r.json()
        assert d["potencia"] is None

    def test_salvar_ftp_valido(self, auth_client, fake_db, run):
        client, uid = auth_client
        self._seed_user(fake_db, uid, run)
        r = client.post("/workout/zonas/ftp", json={"ftp": 254, "modo": "indoor"})
        assert r.status_code == 200
        d = r.json()
        assert d["ftp"] == 254
        assert len(d["zonas"]) == 7

    def test_salvar_ftp_invalido_retorna_422(self, auth_client, fake_db):
        client, _ = auth_client
        r = client.post("/workout/zonas/ftp", json={"ftp": 30, "modo": "indoor"})
        assert r.status_code in (400, 422)

    def test_salvar_ftp_acima_700_falha(self, auth_client, fake_db):
        client, _ = auth_client
        r = client.post("/workout/zonas/ftp", json={"ftp": 900, "modo": "sempre"})
        assert r.status_code in (400, 422)

    def test_get_zonas_potencia_sem_ftp(self, auth_client, fake_db):
        client, _ = auth_client
        r = client.get("/workout/zonas/potencia")
        assert r.status_code == 200
        assert r.json() is None

    def test_get_zonas_potencia_com_ftp(self, auth_client, fake_db, run):
        client, uid = auth_client
        self._seed_user(fake_db, uid, run)
        client.post("/workout/zonas/ftp", json={"ftp": 300, "modo": "sempre"})
        r = client.get("/workout/zonas/potencia")
        assert r.status_code == 200
        d = r.json()
        assert d["ftp"] == 300
        assert d["potencia_modo"] == "sempre"

    def test_zonas_dados_reflete_ftp_salvo(self, auth_client, fake_db, run):
        client, uid = auth_client
        self._seed_user(fake_db, uid, run)
        client.post("/workout/zonas/ftp", json={"ftp": 270, "modo": "nunca"})
        r = client.get("/workout/zonas/dados")
        assert r.status_code == 200
        pot = r.json()["potencia"]
        assert pot["ftp"] == 270

    def test_extrair_potencia_sem_imagem_falha(self, auth_client, fake_db):
        client, _ = auth_client
        r = client.post("/workout/zonas/extrair-potencia", files={})
        assert r.status_code == 422

    def test_extrair_potencia_arquivo_nao_imagem_falha(self, auth_client, fake_db):
        client, _ = auth_client
        fake_file = io.BytesIO(b"not an image")
        r = client.post(
            "/workout/zonas/extrair-potencia",
            files={"imagem": ("zonas.txt", fake_file, "text/plain")},
        )
        assert r.status_code == 400

    def test_extrair_potencia_ia_mockada(self, auth_client, fake_db, monkeypatch):
        async def _mock(*_):
            return {
                "ftp": 254,
                "zonas": [
                    {"zona": i, "min": i * 30, "max": i * 30 + 29, "nome": f"Z{i}"}
                    for i in range(1, 8)
                ],
            }
        monkeypatch.setattr(
            "app.services.ai_service.extrair_zonas_potencia_de_imagem", _mock
        )
        client, _ = auth_client
        fake_img = io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        r = client.post(
            "/workout/zonas/extrair-potencia",
            files={"imagem": ("zonas.jpg", fake_img, "image/jpeg")},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["ftp"] == 254
        assert len(d["zonas"]) == 7


class TestZonasFC:
    def test_salvar_zonas_fc_validas(self, auth_client, fake_db):
        client, _ = auth_client
        payload = {
            "fc_max": 185, "limiar": None, "metodo": "fcmax",
            "zonas": [
                {"zona": 1, "min": 118, "max": 140},
                {"zona": 2, "min": 141, "max": 156},
                {"zona": 3, "min": 157, "max": 166},
                {"zona": 4, "min": 167, "max": 176},
                {"zona": 5, "min": 177, "max": 185},
            ],
        }
        r = client.post("/workout/zonas/salvar", json=payload)
        assert r.status_code == 200

    def test_salvar_zonas_com_4_zonas_falha(self, auth_client, fake_db):
        client, _ = auth_client
        payload = {
            "fc_max": 185, "limiar": None, "metodo": "fcmax",
            "zonas": [
                {"zona": 1, "min": 118, "max": 140},
                {"zona": 2, "min": 141, "max": 156},
                {"zona": 3, "min": 157, "max": 166},
                {"zona": 4, "min": 167, "max": 185},
            ],
        }
        r = client.post("/workout/zonas/salvar", json=payload)
        assert r.status_code in (400, 422)

    def test_extrair_arquivo_nao_imagem_falha(self, auth_client, fake_db):
        client, _ = auth_client
        fake_file = io.BytesIO(b"nao e imagem")
        r = client.post(
            "/workout/zonas/extrair",
            files={"imagem": ("zonas.pdf", fake_file, "application/pdf")},
        )
        assert r.status_code == 400

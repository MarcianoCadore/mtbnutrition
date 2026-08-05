"""Gate de assinatura: quem venceu vê o histórico, mas não gera nada novo."""


class TestModoLeitura:
    def test_get_do_calendario_continua_acessivel(self, vencido_client):
        """Trancar o histórico junto só gera raiva — é o que traz de volta."""
        client, _ = vencido_client
        r = client.get("/workout/calendario", follow_redirects=False)
        assert r.status_code == 200

    def test_get_da_semana_continua_acessivel(self, vencido_client):
        client, _ = vencido_client
        r = client.get("/workout/semana/2026-08-03", follow_redirects=False)
        assert r.status_code == 200

    def test_post_bloqueado_com_402(self, vencido_client):
        client, _ = vencido_client
        r = client.post("/workout/gerar-proxima-semana/2026-08-03", follow_redirects=False)
        assert r.status_code == 402
        assert r.json()["redirect"] == "/assinar"

    def test_chat_bloqueado(self, vencido_client):
        client, _ = vencido_client
        r = client.post("/chat/mensagem", json={"texto": "oi"}, follow_redirects=False)
        assert r.status_code == 402

    def test_download_zwo_bloqueado_mesmo_sendo_get(self, vencido_client):
        """Arquivo de treino é entrega de valor novo, não histórico."""
        client, _ = vencido_client
        r = client.get("/workout/zwo/Z2_LONGO", follow_redirects=False)
        assert r.status_code == 402

    def test_sync_garmin_bloqueado(self, vencido_client):
        client, _ = vencido_client
        r = client.get("/workout/garmin/debug/2026-08-03", follow_redirects=False)
        assert r.status_code == 402

    def test_nutricao_bloqueada(self, vencido_client):
        client, _ = vencido_client
        r = client.get("/nutrition/hoje", follow_redirects=False)
        assert r.status_code in (303, 402)

    def test_navegacao_html_redireciona_para_assinar(self, vencido_client):
        client, _ = vencido_client
        r = client.get("/nutrition/guia", headers={"accept": "text/html"},
                       follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/assinar"

    def test_tela_de_assinatura_sempre_acessivel(self, vencido_client):
        client, _ = vencido_client
        r = client.get("/assinar", follow_redirects=False)
        assert r.status_code == 200
        assert "Pix" in r.text or "pix" in r.text

    def test_logout_sempre_acessivel(self, vencido_client):
        client, _ = vencido_client
        r = client.get("/logout", follow_redirects=False)
        assert r.status_code == 303


class TestComAcesso:
    def test_assinante_em_dia_passa(self, auth_client):
        client, _ = auth_client
        r = client.get("/workout/calendario", follow_redirects=False)
        assert r.status_code == 200

    def test_quem_esta_em_trial_baixa_o_zwo(self, client, fake_db, run):
        """O trial é acesso completo — inclusive ao que está atrás do paywall."""
        from datetime import datetime, timezone
        from bson import ObjectId
        import main
        from app.services.assinatura_service import novo_trial

        oid = ObjectId()
        run(fake_db.users.insert_one({
            "_id": oid, "login": "novato",
            "assinatura": novo_trial(datetime.now(timezone.utc)),
        }))
        client.cookies.set(main._COOKIE, main._gerar_token(str(oid)))

        r = client.get("/workout/zwo/Z2_LONGO", follow_redirects=False)
        assert r.status_code != 402


class TestPaginasPublicas:
    def test_termos_sem_login(self, client):
        r = client.get("/termos", follow_redirects=False)
        assert r.status_code == 200
        # O aviso de que a IA não substitui profissional é o motivo da página existir.
        assert "nutricionista" in r.text.lower()
        assert "não substitui" in r.text.lower()

    def test_privacidade_sem_login(self, client):
        r = client.get("/privacidade", follow_redirects=False)
        assert r.status_code == 200
        assert "LGPD" in r.text

    def test_signup_exige_aceite_dos_termos(self, client, fake_db):
        r = client.post("/signup", data={
            "login": "novato", "senha": "123456", "nome": "Novato",
            "telefone": "+5551999990000",
        }, follow_redirects=False)
        assert r.status_code == 200
        assert "aceitar os termos" in r.text

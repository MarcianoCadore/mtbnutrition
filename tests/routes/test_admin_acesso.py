"""Quem chega no painel de admin.

Esconder o botão não é proteção: o que vale é o backend recusar. Estes testes
existem para que uma refatoração no header não passe a impressão de que o
painel continua protegido quando não está mais.
"""
import pytest
from bson import ObjectId

import main


def _login(client, fake_db, run, login):
    oid = ObjectId()
    run(fake_db.users.insert_one({"_id": oid, "login": login, "nome": "X"}))
    client.cookies.set(main._COOKIE, main._gerar_token(str(oid)))
    return client, str(oid)


class TestSomenteOAdmin:
    def test_admin_ve_o_link_e_entra(self, client, fake_db, run):
        c, _ = _login(client, fake_db, run, "marciano")
        assert 'href="/admin"' in c.get("/portal/").text
        assert c.get("/admin", follow_redirects=False).status_code == 200

    @pytest.mark.parametrize("login", ["stefani", "marciano2", "admin", "marcianocadore"])
    def test_qualquer_outro_login_e_recusado(self, client, fake_db, run, login):
        c, uid = _login(client, fake_db, run, login)
        assert 'href="/admin"' not in c.get("/portal/").text
        assert c.get("/admin", follow_redirects=False).status_code == 403

    @pytest.mark.parametrize("rota,payload", [
        ("/admin/toggle-pagamento", {"pago": True}),
        ("/admin/toggle-acesso",    {"ativo": True}),
        ("/admin/toggle-chat",      {"ativo": True}),
        ("/admin/assinatura",       {"acao": "renovar"}),
        ("/admin/chat-limite",      {"limite": 50}),
    ])
    def test_api_do_painel_bloqueia_quem_nao_e_admin(self, client, fake_db, run, rota, payload):
        """A URL é adivinhável — a defesa tem que estar na rota, não na tela."""
        c, uid = _login(client, fake_db, run, "stefani")
        r = c.post(rota, json={"user_id": uid, **payload})
        assert r.status_code == 403

    def test_custo_de_ia_nao_vaza_para_atleta_comum(self, client, fake_db, run):
        c, _ = _login(client, fake_db, run, "stefani")
        assert c.get("/admin/custo-ia").status_code == 403

    def test_login_com_maiuscula_continua_sendo_o_admin(self, client, fake_db, run):
        """Painel e cortesia usam a mesma normalização: sem isso a conta teria
        acesso permanente e 403 no painel."""
        c, _ = _login(client, fake_db, run, "Marciano")
        assert c.get("/admin", follow_redirects=False).status_code == 200


class TestAssinaturaDoAdmin:
    def test_painel_recusa_alterar_a_assinatura_do_admin(self, client, fake_db, run):
        """Um clique errado ali trancaria o dono para fora da plataforma."""
        c, _ = _login(client, fake_db, run, "marciano")
        oid = ObjectId()
        run(fake_db.users.insert_one({"_id": oid, "login": "marciano_alvo"}))
        # o próprio admin é o alvo
        alvo = run(fake_db.users.find_one({"login": "marciano"}))

        r = c.post("/admin/assinatura",
                   json={"user_id": str(alvo["_id"]), "acao": "expirar"})
        assert r.status_code == 400
        assert "permanente" in r.json()["erro"]

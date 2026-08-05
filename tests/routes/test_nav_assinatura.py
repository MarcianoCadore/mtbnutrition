"""Link de Assinatura na navegação.

A faixa do topo só aparece perto do vencimento. Sem este link, quem está no dia
2 do trial não vê quantos dias tem nem chega na tela de pagamento — nem querendo
pagar.
"""
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

import main
from app.services.assinatura_service import novo_trial


def _login(client, fake_db, run, assinatura):
    oid = ObjectId()
    run(fake_db.users.insert_one({"_id": oid, "login": "atleta", "assinatura": assinatura}))
    client.cookies.set(main._COOKIE, main._gerar_token(str(oid)))
    return client


class TestLinkNaNavegacao:
    def test_trial_mostra_os_dias_restantes(self, client, fake_db, run):
        inicio = datetime.now(timezone.utc) - timedelta(days=3)
        c = _login(client, fake_db, run, novo_trial(inicio))

        html = c.get("/workout/calendario").text
        assert 'href="/assinar"' in html
        assert "Teste · 11d" in html

    def test_assinante_em_dia_ve_o_vencimento(self, client, fake_db, run):
        ate = datetime.now(timezone.utc) + timedelta(days=20)
        c = _login(client, fake_db, run, {"status": "ativa", "pago_ate": ate})

        html = c.get("/workout/calendario").text
        assert f"Ativa até {ate.strftime('%d/%m')}" in html

    def test_vencido_ve_convite_para_assinar(self, client, fake_db, run):
        ontem = datetime.now(timezone.utc) - timedelta(days=1)
        c = _login(client, fake_db, run, {"status": "expirada", "pago_ate": ontem})

        html = c.get("/workout/calendario").text
        assert 'href="/assinar"' in html
        assert "Assinar" in html

    def test_nao_se_repete_na_propria_tela_de_assinatura(self, client, fake_db, run):
        c = _login(client, fake_db, run, novo_trial())
        assert "assinatura-nav-link" not in c.get("/assinar").text

    @pytest.mark.parametrize("tela", ["/workout/perfil", "/workout/zonas",
                                      "/workout/integracao"])
    def test_aparece_em_todas_as_telas(self, client, fake_db, run, tela):
        """O link é injetado no middleware justamente para não depender de cada
        template ter lembrado dele — as navs são diferentes em cada tela."""
        c = _login(client, fake_db, run, novo_trial())
        assert 'href="/assinar"' in c.get(tela).text

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


def _login(client, fake_db, run, assinatura, login="atleta"):
    oid = ObjectId()
    run(fake_db.users.insert_one({"_id": oid, "login": login, "assinatura": assinatura}))
    client.cookies.set(main._COOKIE, main._gerar_token(str(oid)))
    return client


class TestLinkNaNavegacao:
    def test_trial_mostra_os_dias_restantes(self, client, fake_db, run):
        inicio = datetime.now(timezone.utc) - timedelta(days=3)
        c = _login(client, fake_db, run, novo_trial(inicio))

        html = c.get("/workout/calendario").text
        assert 'href="/assinar"' in html
        assert "🎁 11d" in html

    def test_assinante_em_dia_ve_o_vencimento_no_tooltip(self, client, fake_db, run):
        """O vencimento vai no title, não no rótulo: a barra já tem itens demais."""
        ate = datetime.now(timezone.utc) + timedelta(days=20)
        c = _login(client, fake_db, run, {"status": "ativa", "pago_ate": ate})

        html = c.get("/workout/calendario").text
        assert "💚 Assinatura" in html
        assert f"ativa até {ate.strftime('%d/%m/%Y')}" in html

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


class TestContaDoAdmin:
    def test_admin_nao_ve_cobranca_na_navegacao(self, client, fake_db, run):
        """Quem opera a plataforma não paga por ela — nada a cobrar, nada a
        mostrar."""
        c = _login(client, fake_db, run, {}, login="marciano")
        assert 'href="/assinar"' not in c.get("/workout/calendario").text

    def test_admin_entra_mesmo_com_assinatura_vencida_no_banco(self, client, fake_db, run):
        """A regra é por login, não por campo: um erro de migração ou um script
        mal rodado não pode trancar o dono para fora."""
        ontem = datetime.now(timezone.utc) - timedelta(days=1)
        c = _login(client, fake_db, run,
                   {"status": "expirada", "pago_ate": ontem}, login="marciano")

        r = c.post("/workout/gerar-proxima-semana/2026-08-03", follow_redirects=False)
        assert r.status_code != 402

    def test_cortesia_tambem_nao_ve_cobranca(self, client, fake_db, run):
        c = _login(client, fake_db, run, {"status": "cortesia"}, login="socio")
        assert 'href="/assinar"' not in c.get("/workout/calendario").text

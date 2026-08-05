"""Estado da assinatura: trial, vencimento, renovação e soma de saldo."""
from datetime import datetime, timedelta, timezone

import pytest

from app.services import assinatura_service as asg

AGORA = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


def _user(**assinatura):
    return {"login": "atleta", "assinatura": assinatura}


class TestTrial:
    def test_trial_novo_tem_14_dias(self):
        u = {"assinatura": asg.novo_trial(AGORA)}
        est = asg.estado(u, AGORA)
        assert est["status"] == "trial"
        assert est["acesso"] is True
        assert est["em_trial"] is True
        assert est["dias"] == asg.TRIAL_DIAS == 14

    def test_ultimo_dia_ainda_da_acesso(self):
        u = {"assinatura": asg.novo_trial(AGORA)}
        est = asg.estado(u, AGORA + timedelta(days=13, hours=23))
        assert est["acesso"] is True
        assert est["dias"] == 1

    def test_no_instante_do_vencimento_perde_acesso(self):
        u = {"assinatura": asg.novo_trial(AGORA)}
        est = asg.estado(u, AGORA + timedelta(days=14))
        assert est["status"] == "expirada"
        assert est["acesso"] is False
        assert est["dias"] == 0

    def test_vencimento_calculado_na_leitura_mesmo_com_status_velho(self):
        """O job diário pode não ter rodado — ninguém entra por causa disso."""
        u = _user(status="trial", trial_fim=AGORA - timedelta(days=2))
        assert asg.estado(u, AGORA)["acesso"] is False

    def test_data_sem_timezone_do_mongo_nao_quebra(self):
        u = _user(status="trial", trial_fim=(AGORA + timedelta(days=5)).replace(tzinfo=None))
        assert asg.estado(u, AGORA)["dias"] == 5


class TestAssinaturaPaga:
    def test_ativa_dentro_do_prazo(self):
        u = _user(status="ativa", pago_ate=AGORA + timedelta(days=12))
        est = asg.estado(u, AGORA)
        assert est["acesso"] is True
        assert est["em_trial"] is False
        assert est["dias"] == 12

    def test_ativa_vencida_perde_acesso(self):
        u = _user(status="ativa", pago_ate=AGORA - timedelta(hours=1))
        assert asg.estado(u, AGORA)["acesso"] is False

    def test_cancelada_nao_tem_acesso(self):
        assert asg.estado(_user(status="cancelada"), AGORA)["acesso"] is False


class TestCortesia:
    def test_admin_tem_acesso_permanente(self):
        est = asg.estado({"login": "marciano"}, AGORA)
        assert est["status"] == "cortesia"
        assert est["acesso"] is True
        assert est["dias"] is None

    def test_admin_ignora_assinatura_vencida_no_banco(self):
        """A regra é por login: um erro de migração não pode trancar o dono."""
        u = {"login": "marciano",
             "assinatura": {"status": "expirada", "pago_ate": AGORA - timedelta(days=90)}}
        assert asg.estado(u, AGORA)["acesso"] is True

    def test_login_do_admin_e_case_insensitive(self):
        assert asg.e_cortesia({"login": "Marciano"}) is True
        assert asg.e_cortesia({"login": " marciano "}) is True

    def test_cortesia_explicita_tem_acesso_sem_vencer(self):
        est = asg.estado({"login": "socio", "assinatura": {"status": "cortesia"}}, AGORA)
        assert est["acesso"] is True
        assert est["dias"] is None

    def test_atleta_comum_nao_e_cortesia(self):
        assert asg.e_cortesia({"login": "stefani"}) is False

    def test_cortesia_nao_entra_na_faixa_de_aviso(self):
        """`dias is None` mantém a conta fora de AVISOS_DIAS — ninguém recebe
        cobrança de algo que não paga."""
        est = asg.estado({"login": "marciano"}, AGORA)
        assert est["dias"] not in asg.AVISOS_DIAS


@pytest.mark.asyncio
class TestDarCortesia:
    async def test_concede_acesso_permanente(self, fake_db):
        from bson import ObjectId
        oid = ObjectId()
        await fake_db.users.insert_one({"_id": oid, "login": "parceiro"})

        await asg.dar_cortesia(str(oid), motivo="parceria")

        u = await fake_db.users.find_one({"_id": oid})
        est = asg.estado(u)
        assert est["status"] == "cortesia"
        assert est["acesso"] is True
        assert u["assinatura"]["motivo"] == "parceria"


class TestContasLegadas:
    def test_conta_sem_bloco_de_assinatura_mantem_acesso(self):
        """Migração é responsabilidade do script — não trancar ninguém fora."""
        est = asg.estado({"login": "antigo"}, AGORA)
        assert est["acesso"] is True
        assert est["dias"] is None

    def test_usuario_inexistente_nao_tem_acesso(self):
        assert asg.estado(None, AGORA)["acesso"] is False


class TestDiasRestantes:
    def test_arredonda_para_cima(self):
        u = _user(status="ativa", pago_ate=AGORA + timedelta(hours=30))
        assert asg.dias_restantes(u, AGORA) == 2

    def test_fracao_de_dia_ainda_conta_como_um(self):
        u = _user(status="ativa", pago_ate=AGORA + timedelta(minutes=20))
        assert asg.dias_restantes(u, AGORA) == 1

    def test_sem_vencimento_devolve_none(self):
        assert asg.dias_restantes(_user(status="ativa", pago_ate=None), AGORA) is None


@pytest.mark.asyncio
class TestConfirmarPagamento:
    async def test_libera_30_dias(self, fake_db):
        from bson import ObjectId
        oid = ObjectId()
        await fake_db.users.insert_one({"_id": oid, "login": "a"})

        info = await asg.confirmar_pagamento(str(oid))
        assert info["status"] == "ativa"

        u = await fake_db.users.find_one({"_id": oid})
        est = asg.estado(u)
        assert est["acesso"] is True
        assert est["dias"] == asg.CICLO_DIAS

    async def test_pagar_durante_o_trial_soma_os_dias_que_sobraram(self, fake_db):
        """Quem paga no dia 10 de 14 não pode perder os 4 dias restantes."""
        from bson import ObjectId
        oid = ObjectId()
        inicio = datetime.now(timezone.utc) - timedelta(days=10)
        await fake_db.users.insert_one(
            {"_id": oid, "login": "a", "assinatura": asg.novo_trial(inicio)})

        await asg.confirmar_pagamento(str(oid))

        u = await fake_db.users.find_one({"_id": oid})
        assert asg.estado(u)["dias"] == asg.CICLO_DIAS + 4

    async def test_renovar_apos_vencido_conta_do_zero(self, fake_db):
        from bson import ObjectId
        oid = ObjectId()
        await fake_db.users.insert_one({
            "_id": oid, "login": "a",
            "assinatura": {"status": "ativa",
                           "pago_ate": datetime.now(timezone.utc) - timedelta(days=40)},
        })

        await asg.confirmar_pagamento(str(oid))

        u = await fake_db.users.find_one({"_id": oid})
        assert asg.estado(u)["dias"] == asg.CICLO_DIAS

    async def test_confirmar_limpa_avisos_para_o_proximo_ciclo(self, fake_db):
        from bson import ObjectId
        oid = ObjectId()
        await fake_db.users.insert_one({
            "_id": oid, "login": "a",
            "assinatura": {"status": "trial", "avisos_enviados": ["trial:3", "trial:1"]},
        })

        await asg.confirmar_pagamento(str(oid))

        u = await fake_db.users.find_one({"_id": oid})
        assert u["assinatura"]["avisos_enviados"] == []


@pytest.mark.asyncio
class TestEstadoPorId:
    async def test_usuario_apagado_devolve_none(self, fake_db):
        from bson import ObjectId
        assert await asg.estado_por_id(str(ObjectId())) is None

    async def test_id_invalido_devolve_none(self, fake_db):
        assert await asg.estado_por_id("nao-e-objectid") is None

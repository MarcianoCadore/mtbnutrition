"""Curva de potência e FTP estimado.

O eFTP reescreve os alvos em watts de toda a semana e o conteúdo do .zwo —
errar para cima aqui manda o atleta treinar acima do que aguenta.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services import potencia_service as pot
from app.services.fit_service import melhores_esforcos

HOJE = datetime.now(timezone.utc).date().isoformat()


def _dias_atras(n: int) -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=n)).isoformat()


class TestMelhoresEsforcos:
    def test_potencia_constante_e_a_mesma_em_toda_janela(self):
        r = melhores_esforcos([200] * 1300)
        assert r[5] == 200 and r[60] == 200 and r[1200] == 200

    def test_acha_o_pico_no_meio_da_sessao(self):
        # 10 min a 150W, 20 min a 300W, 10 min a 150W
        valores = [150] * 600 + [300] * 1200 + [150] * 600
        r = melhores_esforcos(valores)
        assert r[1200] == 300

    def test_janela_maior_que_a_sessao_e_omitida(self):
        r = melhores_esforcos([250] * 100)   # 100s de treino
        assert 60 in r
        assert 300 not in r and 1200 not in r

    def test_media_de_janela_e_de_verdade_media(self):
        """Um pico de 1s não pode inflar a janela de 60s — é assim que um
        eFTP errado nasceria."""
        valores = [100] * 3600
        valores[0] = 1500
        r = melhores_esforcos(valores)
        assert r[60] < 130

    def test_sem_potencia_devolve_vazio(self):
        assert melhores_esforcos([]) == {}


class TestEstimarFtp:
    def test_20_minutos_aplica_fator_de_95_por_cento(self):
        ftp, como = pot.estimar_ftp({1200: {"watts": 300, "data": HOJE}})
        assert ftp == 285
        assert "20 min" in como

    def test_uma_hora_e_o_ftp_direto(self):
        ftp, como = pot.estimar_ftp({3600: {"watts": 270, "data": HOJE}})
        assert ftp == 270
        assert "60 min" in como

    def test_hora_tem_prioridade_sobre_20_minutos(self):
        """A hora é o FTP por definição; o fator de 20 min é aproximação."""
        ftp, _ = pot.estimar_ftp({
            3600: {"watts": 270, "data": HOJE},
            1200: {"watts": 400, "data": HOJE},
        })
        assert ftp == 270

    def test_sem_esforco_longo_nao_estima(self):
        ftp, como = pot.estimar_ftp({5: {"watts": 1200, "data": HOJE},
                                     60: {"watts": 600, "data": HOJE}})
        assert ftp is None and como == ""

    def test_valor_absurdo_e_limitado(self):
        ftp, _ = pot.estimar_ftp({1200: {"watts": 5000, "data": HOJE}})
        assert ftp == pot.FTP_MAX


@pytest.mark.asyncio
class TestCurva:
    async def test_guarda_o_recorde_por_duracao(self, fake_db):
        await pot.registrar_esforcos("u1", _dias_atras(10), {1200: 250})
        await pot.registrar_esforcos("u1", HOJE, {1200: 280})

        curva = await pot.get_curva("u1")
        assert curva[1200]["watts"] == 280

    async def test_esforco_pior_nao_derruba_o_recorde(self, fake_db):
        await pot.registrar_esforcos("u1", _dias_atras(10), {1200: 280})
        await pot.registrar_esforcos("u1", HOJE, {1200: 200})

        curva = await pot.get_curva("u1")
        assert curva[1200]["watts"] == 280

    async def test_recorde_fora_da_janela_de_90_dias_e_descartado(self, fake_db):
        """A forma de 4 meses atrás não é a de hoje."""
        await pot.registrar_esforcos("u1", _dias_atras(200), {1200: 350})
        assert await pot.get_curva("u1") == {}

    async def test_recorde_vencido_e_substituido_por_um_pior(self, fake_db):
        """Passados 90 dias, o número novo vale mesmo sendo menor — senão o
        recorde antigo ficaria eterno."""
        await pot.registrar_esforcos("u1", _dias_atras(200), {1200: 350})
        await pot.registrar_esforcos("u1", HOJE, {1200: 240})

        curva = await pot.get_curva("u1")
        assert curva[1200]["watts"] == 240


@pytest.mark.asyncio
class TestAtualizarFtp:
    async def _usuario(self, fake_db, **campos):
        from bson import ObjectId
        oid = ObjectId()
        await fake_db.users.insert_one({"_id": oid, "login": "a", **campos})
        return str(oid)

    async def test_cria_ftp_para_quem_nunca_testou(self, fake_db):
        uid = await self._usuario(fake_db)
        await pot.registrar_esforcos(uid, HOJE, {1200: 300})

        r = await pot.talvez_atualizar_ftp(uid)
        assert r["ftp"] == 285

        doc = await fake_db.users.find_one({"login": "a"})
        assert doc["ftp"] == 285
        assert doc["ftp_origem"] == "estimado"

    async def test_sobe_quando_o_atleta_melhora(self, fake_db):
        uid = await self._usuario(fake_db, ftp=250, potencia_modo="sempre")
        await pot.registrar_esforcos(uid, HOJE, {1200: 300})

        assert (await pot.talvez_atualizar_ftp(uid))["ftp"] == 285

    async def test_nunca_desce_sozinho(self, fake_db):
        """Um treino fraco não pode rebaixar o FTP e estragar a semana toda."""
        uid = await self._usuario(fake_db, ftp=300)
        await pot.registrar_esforcos(uid, HOJE, {1200: 250})

        assert await pot.talvez_atualizar_ftp(uid) is None
        doc = await fake_db.users.find_one({"login": "a"})
        assert doc["ftp"] == 300

    async def test_ganho_dentro_do_ruido_nao_reescreve(self, fake_db):
        uid = await self._usuario(fake_db, ftp=285)
        await pot.registrar_esforcos(uid, HOJE, {1200: 302})   # ~287W, +0,7%

        assert await pot.talvez_atualizar_ftp(uid) is None

    async def test_preserva_a_preferencia_de_potencia(self, fake_db):
        """Estimar o FTP muda o número, não onde os watts aparecem."""
        uid = await self._usuario(fake_db, ftp=200, potencia_modo="sempre")
        await pot.registrar_esforcos(uid, HOJE, {1200: 300})

        await pot.talvez_atualizar_ftp(uid)
        doc = await fake_db.users.find_one({"login": "a"})
        assert doc["potencia_modo"] == "sempre"

    async def test_nao_conta_como_teste_de_ftp(self, fake_db):
        """Senão o alerta de 'hora de testar seu FTP' nunca mais dispararia."""
        uid = await self._usuario(fake_db, ultimo_teste_ftp="2026-01-01")
        await pot.registrar_esforcos(uid, HOJE, {1200: 300})

        await pot.talvez_atualizar_ftp(uid)
        doc = await fake_db.users.find_one({"login": "a"})
        assert doc["ultimo_teste_ftp"] == "2026-01-01"

    async def test_sem_curva_nao_faz_nada(self, fake_db):
        uid = await self._usuario(fake_db, ftp=250)
        assert await pot.talvez_atualizar_ftp(uid) is None

    async def test_fit_ilegivel_nao_derruba_o_registro_do_treino(self, fake_db):
        uid = await self._usuario(fake_db)
        assert await pot.processar_fit(uid, HOJE, "/caminho/que/nao/existe.fit") is None

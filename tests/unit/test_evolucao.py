"""Tela de evolução: carga semanal, curva de potência e FTP no tempo."""
from datetime import datetime, timedelta, timezone

import pytest

from app.services import evolucao_service as ev


def _semana_de(offset_semanas: int) -> str:
    hoje = datetime.now(timezone.utc).date()
    d = hoje - timedelta(weeks=offset_semanas)
    return (d - timedelta(days=d.weekday())).isoformat()


@pytest.mark.asyncio
class TestResumoSemanal:
    async def test_devolve_a_janela_inteira_mesmo_sem_treino(self, fake_db):
        """Semana vazia é informação — é onde a rotina furou."""
        linhas = await ev.resumo_semanal("u1", semanas=12)
        assert len(linhas) == 12
        assert all(linha["tss"] == 0 for linha in linhas)

    async def test_ordena_da_mais_antiga_para_a_mais_nova(self, fake_db):
        linhas = await ev.resumo_semanal("u1", semanas=6)
        semanas = [linha["semana"] for linha in linhas]
        assert semanas == sorted(semanas)
        assert semanas[-1] == _semana_de(0)

    async def test_soma_carga_volume_e_distancia(self, fake_db):
        await fake_db.semanas.insert_one({
            "user_id": "u1", "semana_inicio": _semana_de(0),
            "treinos": [
                {"data": _semana_de(0), "tipo": "TEMPO",
                 "resultado": {"tss_obtido": 70, "duracao_min": 60, "distancia_km": 30.5}},
                {"data": _semana_de(0), "tipo": "Z2_LONGO",
                 "resultado": {"tss_obtido": 110, "duracao_min": 150, "distancia_km": 62.0}},
            ],
        })
        atual = (await ev.resumo_semanal("u1", semanas=4))[-1]
        assert atual["tss"] == 180
        assert atual["minutos"] == 210
        assert atual["km"] == 92.5
        assert atual["sessoes"] == 2

    async def test_descanso_nao_conta_como_planejado(self, fake_db):
        await fake_db.semanas.insert_one({
            "user_id": "u1", "semana_inicio": _semana_de(0),
            "treinos": [
                {"data": _semana_de(0), "tipo": "DESCANSO"},
                {"data": _semana_de(0), "tipo": "TIROS",
                 "resultado": {"tss_obtido": 80, "duracao_min": 60}},
            ],
        })
        atual = (await ev.resumo_semanal("u1", semanas=4))[-1]
        assert atual["planejados"] == 1
        assert atual["aderencia"] == 100

    async def test_aderencia_conta_planejado_nao_executado(self, fake_db):
        await fake_db.semanas.insert_one({
            "user_id": "u1", "semana_inicio": _semana_de(0),
            "treinos": [
                {"data": _semana_de(0), "tipo": "TIROS", "duracao_min": 60},
                {"data": _semana_de(0), "tipo": "TEMPO",
                 "resultado": {"tss_obtido": 80, "duracao_min": 60}},
            ],
        })
        atual = (await ev.resumo_semanal("u1", semanas=4))[-1]
        assert atual["aderencia"] == 50

    async def test_treino_importado_nao_infla_a_aderencia(self, fake_db):
        """O backfill traz treinos que nunca foram planejados por aqui —
        contá-los como plano cumprido daria uma aderência fantasiosa."""
        await fake_db.semanas.insert_one({
            "user_id": "u1", "semana_inicio": _semana_de(0),
            "treinos": [{"data": _semana_de(0), "tipo": "Z2_LONGO", "origem": "backfill",
                         "resultado": {"tss_obtido": 90, "duracao_min": 120}}],
        })
        atual = (await ev.resumo_semanal("u1", semanas=4))[-1]
        assert atual["sessoes"] == 1
        assert atual["planejados"] == 0
        assert atual["aderencia"] is None

    async def test_nao_mistura_usuarios(self, fake_db):
        await fake_db.semanas.insert_one({
            "user_id": "outro", "semana_inicio": _semana_de(0),
            "treinos": [{"data": _semana_de(0), "tipo": "TIROS",
                         "resultado": {"tss_obtido": 999, "duracao_min": 60}}],
        })
        atual = (await ev.resumo_semanal("u1", semanas=4))[-1]
        assert atual["tss"] == 0


@pytest.mark.asyncio
class TestHistoricoFtp:
    async def test_registra_e_devolve_em_ordem(self, fake_db):
        await ev.registrar_ftp("u1", 250, "teste")
        pontos = await ev.historico_ftp("u1")
        assert pontos[0]["ftp"] == 250
        assert pontos[0]["origem"] == "teste"

    async def test_dois_registros_no_mesmo_dia_viram_um_ponto(self, fake_db):
        """Várias sessões num dia não podem virar vários pontos no gráfico."""
        await ev.registrar_ftp("u1", 250, "teste")
        await ev.registrar_ftp("u1", 262, "estimado")

        pontos = await ev.historico_ftp("u1")
        assert len(pontos) == 1
        assert pontos[0]["ftp"] == 262

    async def test_salvar_ftp_alimenta_a_serie(self, fake_db):
        """A série existe porque salvar_ftp a alimenta — sem isso o gráfico de
        FTP fica sempre vazio."""
        from bson import ObjectId
        from app.services.config_service import salvar_ftp

        oid = ObjectId()
        await fake_db.users.insert_one({"_id": oid, "login": "a"})
        await salvar_ftp(str(oid), 280)

        assert (await ev.historico_ftp(str(oid)))[0]["ftp"] == 280


@pytest.mark.asyncio
class TestResumo:
    async def test_atleta_novo_devolve_estrutura_vazia_sem_quebrar(self, fake_db):
        from bson import ObjectId
        oid = ObjectId()
        await fake_db.users.insert_one({"_id": oid, "login": "a"})

        r = await ev.resumo(str(oid))
        assert r["totais"]["sessoes"] == 0
        assert r["curva"] == []
        assert r["ftp"]["atual"] is None
        assert len(r["semanal"]) == ev.SEMANAS_PADRAO

    async def test_junta_curva_ftp_e_totais(self, fake_db):
        from bson import ObjectId
        from app.services.potencia_service import registrar_esforcos

        oid = ObjectId()
        uid = str(oid)
        await fake_db.users.insert_one({"_id": oid, "login": "a", "ftp": 260})
        await registrar_esforcos(uid, datetime.now(timezone.utc).date().isoformat(),
                                 {60: 420, 1200: 280})
        await fake_db.semanas.insert_one({
            "user_id": uid, "semana_inicio": _semana_de(0),
            "treinos": [{"data": _semana_de(0), "tipo": "TEMPO",
                         "resultado": {"tss_obtido": 75, "duracao_min": 60,
                                       "distancia_km": 32.0}}],
        })

        r = await ev.resumo(uid)
        assert r["ftp"]["atual"] == 260
        assert r["ftp"]["estimado"] == 266        # 280 × 0,95
        assert len(r["curva"]) == 2
        assert r["totais"]["sessoes"] == 1
        assert r["totais"]["km"] == 32

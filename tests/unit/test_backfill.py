"""Importação do histórico ao conectar Garmin/Strava.

O que mais importa aqui não é o que o backfill faz, é o que ele NÃO faz:
não chama IA (seriam ~40 análises por assinante novo) e não manda WhatsApp
(seriam 40 mensagens de pós-treino de treinos antigos).
"""
from datetime import datetime, timedelta

import pytest

from app.services import backfill_service as bf


def _dias_atras(n: int) -> str:
    return (datetime.now().date() - timedelta(days=n)).isoformat()


class TestSemanaDe:
    def test_domingo_pertence_a_semana_que_comecou_na_segunda(self):
        assert bf._semana_de("2026-08-09") == "2026-08-03"

    def test_segunda_e_o_proprio_inicio(self):
        assert bf._semana_de("2026-08-03") == "2026-08-03"


@pytest.mark.asyncio
class TestGravarTreino:
    async def test_cria_a_semana_quando_nao_existe(self, fake_db):
        await bf._gravar_treino("u1", "2026-08-05", "Z2_LONGO",
                                {"duracao_min": 90, "origem": "backfill"})

        doc = await fake_db.semanas.find_one({"user_id": "u1"})
        assert doc["semana_inicio"] == "2026-08-03"
        assert doc["treinos"][0]["origem"] == "backfill"

    async def test_acrescenta_a_uma_semana_existente(self, fake_db):
        await fake_db.semanas.insert_one({
            "semana_inicio": "2026-08-03", "user_id": "u1",
            "treinos": [{"data": "2026-08-04", "tipo": "TIROS", "duracao_min": 60}],
        })
        await bf._gravar_treino("u1", "2026-08-05", "Z2_LONGO", {"duracao_min": 90})

        doc = await fake_db.semanas.find_one({"user_id": "u1"})
        assert len(doc["treinos"]) == 2

    async def test_nao_sobrescreve_treino_que_ja_existe_na_data(self, fake_db):
        """Histórico importado não tem prioridade sobre o que já estava lá."""
        await fake_db.semanas.insert_one({
            "semana_inicio": "2026-08-03", "user_id": "u1",
            "treinos": [{"data": "2026-08-05", "tipo": "VO2MAX", "duracao_min": 62,
                         "resultado": {"avg_hr": 160}}],
        })
        await bf._gravar_treino("u1", "2026-08-05", "Z2_LONGO", {"duracao_min": 200})

        doc = await fake_db.semanas.find_one({"user_id": "u1"})
        assert len(doc["treinos"]) == 1
        assert doc["treinos"][0]["tipo"] == "VO2MAX"

    async def test_semanas_de_usuarios_diferentes_nao_se_misturam(self, fake_db):
        await bf._gravar_treino("u1", "2026-08-05", "Z2_LONGO", {"duracao_min": 90})
        await bf._gravar_treino("u2", "2026-08-05", "TIROS", {"duracao_min": 60})

        assert await fake_db.semanas.count_documents({"semana_inicio": "2026-08-03"}) == 2


@pytest.mark.asyncio
class TestDedup:
    async def test_marca_e_reconhece_atividade_ja_importada(self, fake_db):
        assert await bf._ja_importado(fake_db, "act-1") is False
        await bf._marcar(fake_db, "act-1", "2026-08-05")
        assert await bf._ja_importado(fake_db, "act-1") is True

    async def test_marcacao_impede_o_sync_de_notificar_depois(self, fake_db):
        """Sem isto o sync trataria o treino antigo como novo e mandaria o
        pós-treino no WhatsApp semanas depois."""
        await bf._marcar(fake_db, "act-1", "2026-08-05")
        doc = await fake_db.atividades_processadas.find_one({"_id": "act-1"})
        assert doc["origem"] == "backfill"


@pytest.mark.asyncio
class TestImportarHistorico:
    async def test_sem_integracao_conectada_avisa(self, fake_db):
        from bson import ObjectId
        oid = ObjectId()
        await fake_db.users.insert_one({"_id": oid, "login": "a"})

        r = await bf.importar_historico(str(oid))
        assert r["importadas"] == 0
        assert "conectada" in r["erro"]

    async def test_registra_o_backfill_no_usuario(self, fake_db, monkeypatch):
        from bson import ObjectId
        oid = ObjectId()
        await fake_db.users.insert_one({
            "_id": oid, "login": "a", "integracao": {"tipo": "garmin"}})

        async def _fake(user_id, dias):
            return {"importadas": 7}
        monkeypatch.setattr(bf, "_backfill_garmin", _fake)

        r = await bf.importar_historico(str(oid), dias=90)
        assert r["importadas"] == 7

        doc = await fake_db.users.find_one({"_id": oid})
        assert doc["backfill"]["importadas"] == 7
        assert doc["backfill"]["dias"] == 90


@pytest.mark.asyncio
class TestPreencherPtss:
    async def test_calcula_tss_das_sessoes_com_potencia(self, fake_db):
        """O pTSS só sai depois do eFTP existir — por isso é segunda passada."""
        from bson import ObjectId
        oid = ObjectId()
        await fake_db.users.insert_one({"_id": oid, "login": "a", "ftp": 250})
        await fake_db.semanas.insert_one({
            "semana_inicio": "2026-08-03", "user_id": str(oid),
            "treinos": [{
                "data": "2026-08-05", "tipo": "TEMPO",
                "resultado": {"origem": "backfill", "norm_power": 250, "duracao_min": 60},
            }],
        })

        n = await bf._preencher_ptss(str(oid), "2026-08-03")
        assert n == 1

        doc = await fake_db.semanas.find_one({"user_id": str(oid)})
        # NP == FTP por 1h → IF 1.0 → 100 TSS
        assert doc["treinos"][0]["resultado"]["tss_obtido"] == 100

    async def test_nao_toca_em_treino_que_ja_tem_tss(self, fake_db):
        from bson import ObjectId
        oid = ObjectId()
        await fake_db.users.insert_one({"_id": oid, "login": "a", "ftp": 250})
        await fake_db.semanas.insert_one({
            "semana_inicio": "2026-08-03", "user_id": str(oid),
            "treinos": [{
                "data": "2026-08-05", "tipo": "TEMPO",
                "resultado": {"origem": "backfill", "norm_power": 250,
                              "duracao_min": 60, "tss_obtido": 42},
            }],
        })

        await bf._preencher_ptss(str(oid), "2026-08-03")
        doc = await fake_db.semanas.find_one({"user_id": str(oid)})
        assert doc["treinos"][0]["resultado"]["tss_obtido"] == 42

    async def test_sem_ftp_nao_calcula_nada(self, fake_db):
        from bson import ObjectId
        oid = ObjectId()
        await fake_db.users.insert_one({"_id": oid, "login": "a"})

        assert await bf._preencher_ptss(str(oid), "2026-08-03") == 0

"""Testes da camada de dados de treinos da semana (treino_semana_service)."""
import pytest

from app.services import treino_semana_service as tss

UID = "user-xyz"
# 2026-06-25 = quinta; semana_inicio = 2026-06-22 (segunda)
QUI = "2026-06-25"
SEG = "2026-06-22"


class TestGetTreino:
    async def test_sem_doc_retorna_none(self, fake_db):
        assert await tss.get_treino(UID, QUI) is None

    async def test_descanso_retorna_none(self, fake_db):
        await fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": UID,
            "treinos": [{"data": QUI, "tipo": "DESCANSO", "duracao_min": None}],
        })
        assert await tss.get_treino(UID, QUI) is None

    async def test_treino_real_retornado(self, fake_db):
        await fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": UID,
            "treinos": [{"data": QUI, "tipo": "TIROS", "duracao_min": 60}],
        })
        t = await tss.get_treino(UID, QUI)
        assert t["tipo"] == "TIROS"

    async def test_ignora_extra_mesma_data(self, fake_db):
        # "extra" listado ANTES do primário no array — trava o caso em que a
        # ordem por si só não poderia ser usada pra achar o treino certo.
        await fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": UID,
            "treinos": [
                {"data": QUI, "tipo": "ACADEMIA", "duracao_min": 60,
                 "origem": "extra", "id": "extra-1"},
                {"data": QUI, "tipo": "TIROS", "duracao_min": 60},
            ],
        })
        t = await tss.get_treino(UID, QUI)
        assert t["tipo"] == "TIROS"


class TestGetTreinosSemana:
    async def test_vazio_sem_doc(self, fake_db):
        assert await tss.get_treinos_semana(UID, SEG) == []

    async def test_retorna_lista(self, fake_db):
        await fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": UID,
            "treinos": [{"data": QUI, "tipo": "TEMPO", "duracao_min": 70}],
        })
        treinos = await tss.get_treinos_semana(UID, SEG)
        assert len(treinos) == 1


class TestCriarTreinoDia:
    async def test_cria_em_semana_inexistente(self, fake_db):
        # _garantir_dia deve criar o doc da semana
        out = await tss.criar_treino_dia(UID, QUI, "VO2MAX", 60, "4x4 Z5")
        assert out["tipo"] == "VO2MAX"
        t = await tss.get_treino(UID, QUI)
        assert t is not None
        assert t["duracao_min"] == 60

    async def test_descricao_default(self, fake_db):
        out = await tss.criar_treino_dia(UID, QUI, "Z2_LONGO", 120)
        assert out["descricao"]  # gera a partir do tipo

    async def test_data_so_com_extra_cria_primario_sem_corromper_extra(self, fake_db):
        # Só existe um "extra" na data (nenhum primário ainda) — _garantir_dia
        # não pode achar que o dia "já tem item" por causa do extra.
        await fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": UID,
            "treinos": [{"data": QUI, "tipo": "ACADEMIA", "duracao_min": 60,
                         "origem": "extra", "id": "extra-1"}],
        })
        out = await tss.criar_treino_dia(UID, QUI, "TIROS", 60)
        assert out["tipo"] == "TIROS"

        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        extras = [t for t in doc["treinos"] if t.get("origem") == "extra"]
        primarios = [t for t in doc["treinos"] if t.get("origem") != "extra"]
        assert len(extras) == 1 and extras[0]["id"] == "extra-1"
        assert len(primarios) == 1 and primarios[0]["tipo"] == "TIROS"


class TestRemoverTreinoDia:
    async def test_remove_vira_descanso(self, fake_db):
        await tss.criar_treino_dia(UID, QUI, "TIROS", 60)
        await tss.remover_treino_dia(UID, QUI)
        assert await tss.get_treino(UID, QUI) is None  # virou descanso

    async def test_remover_sem_treino_lanca(self, fake_db):
        with pytest.raises(ValueError):
            await tss.remover_treino_dia(UID, QUI)


class TestMoverTreino:
    async def test_sobrescrever(self, fake_db):
        await tss.criar_treino_dia(UID, "2026-06-23", "TIROS", 60)  # terça
        await tss.mover_treino(UID, "2026-06-23", "2026-06-24", "sobrescrever")
        assert await tss.get_treino(UID, "2026-06-23") is None       # origem virou descanso
        assert (await tss.get_treino(UID, "2026-06-24"))["tipo"] == "TIROS"

    async def test_mover_sem_treino_origem_lanca(self, fake_db):
        with pytest.raises(ValueError):
            await tss.mover_treino(UID, "2026-06-23", "2026-06-24", "sobrescrever")

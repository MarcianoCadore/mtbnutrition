"""Regressão: excluir/mover treino pelo chat deve cancelar o workout no Garmin.

Bug reportado: pedir ao chat para remover quarta e mover sexta→domingo funciona
no banco, mas ao salvar+sincronizar os treinos voltavam. Causa: o chat zerava o
`garmin_workout_id` no banco sem deletar o agendamento no Garmin, deixando-o
órfão — e o pull do sync o re-importava.

Estes testes garantem que o chat chama deletar_workout_garmin com o id antigo.
"""
import pytest

import app.services.chat_service as chat
import app.services.garmin_workout_service as gws

SEG = "2026-06-22"  # segunda
QUA = "2026-06-24"  # quarta
SEX = "2026-06-26"  # sexta
DOM = "2026-06-28"  # domingo
UID = "user-chat-1"


@pytest.fixture
def _spy_deletar(monkeypatch):
    """Registra os ids passados para deletar_workout_garmin."""
    chamados = []

    async def _fake(user_id, gid):
        chamados.append(gid)
        return True

    monkeypatch.setattr(gws, "deletar_workout_garmin", _fake)
    return chamados


async def _seed(fake_db, treinos):
    await fake_db.semanas.insert_one({
        "semana_inicio": SEG, "user_id": UID, "objetivo": "", "treinos": treinos,
    })


class TestRemover:
    async def test_remover_cancela_workout_no_garmin(self, fake_db, _spy_deletar):
        await _seed(fake_db, [
            {"data": QUA, "tipo": "TIROS", "duracao_min": 60, "garmin_workout_id": "gid-qua"},
        ])
        await chat._executar_ferramenta(UID, "remover_treino", {"data": QUA})
        assert _spy_deletar == ["gid-qua"]

    async def test_remover_sem_garmin_id_nao_chama(self, fake_db, _spy_deletar):
        await _seed(fake_db, [
            {"data": QUA, "tipo": "TIROS", "duracao_min": 60},
        ])
        await chat._executar_ferramenta(UID, "remover_treino", {"data": QUA})
        assert _spy_deletar == []


class TestMover:
    async def test_mover_cancela_agendamento_antigo(self, fake_db, _spy_deletar):
        # Sexta tem treino agendado no Garmin; move para domingo (vazio).
        await _seed(fake_db, [
            {"data": SEX, "tipo": "Z2_LONGO", "duracao_min": 120, "garmin_workout_id": "gid-sex"},
        ])
        await chat._executar_ferramenta(
            UID, "mover_treino", {"origem": SEX, "destino": DOM, "modo": "sobrescrever"}
        )
        # O agendamento antigo da sexta foi cancelado no Garmin.
        assert "gid-sex" in _spy_deletar
        # E o banco reflete: sexta virou descanso, domingo tem o treino.
        doc = await fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": UID})
        por_data = {t["data"]: t for t in doc["treinos"]}
        assert por_data[SEX]["tipo"] == "DESCANSO"
        assert por_data[DOM]["tipo"] == "Z2_LONGO"
        assert por_data[DOM].get("garmin_workout_id") is None

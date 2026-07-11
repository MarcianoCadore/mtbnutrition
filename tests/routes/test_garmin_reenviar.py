"""Regressão: excluir/mover treino no portal e sincronizar Garmin.

Bug reportado: ao excluir um treino no portal e clicar em "Enviar + Sincronizar
Garmin", o treino voltava. Causa: o envio (reenviar-garmin) lia o estado antigo
do banco e re-criava no Garmin o workout excluído; o pull seguinte o trazia de
volta. Além disso, dias que viravam DESCANSO mantinham o agendamento no Garmin.

Estes testes cobrem o backend:
- reenviar-garmin remove do Garmin um dia que virou DESCANSO e ainda tinha
  garmin_workout_id (senão o pull o re-importa);
- salvar-semana preserva o bloco `academia` que não existe no modelo TreinoSemana
  (senão o auto-save do botão de sincronizar o apagaria).
"""
import pytest

SEG = "2026-06-22"  # segunda
QUA = "2026-06-24"  # quarta
SEX = "2026-06-26"  # sexta


@pytest.fixture
def _mock_garmin(monkeypatch):
    """Substitui as chamadas reais ao Garmin e registra o que foi invocado."""
    import app.services.garmin_workout_service as gws

    chamadas = {"deletados": [], "enviados": []}

    async def _fake_deletar(user_id, gid):
        chamadas["deletados"].append(gid)
        return True

    async def _fake_upload(user_id, *, tipo, duracao_min, nome, data_iso, descricao=None, **_):
        chamadas["enviados"].append(data_iso)
        return f"novo-gid-{data_iso}"

    monkeypatch.setattr(gws, "deletar_workout_garmin", _fake_deletar)
    monkeypatch.setattr(gws, "upload_e_agendar", _fake_upload)
    return chamadas


class TestReenviarGarmin:
    async def _seed(self, fake_db, uid, treinos):
        await fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "", "treinos": treinos,
        })

    def test_dia_descanso_com_workout_e_removido_do_garmin(
        self, auth_client, fake_db, run, _mock_garmin
    ):
        client, uid = auth_client
        # Quarta virou descanso mas ainda carrega o agendamento antigo do Garmin.
        run(self._seed(fake_db, uid, [
            {"data": QUA, "tipo": "DESCANSO", "garmin_workout_id": "gid-quarta"},
            {"data": SEX, "tipo": "TIROS", "duracao_min": 60, "garmin_workout_id": "gid-sexta"},
        ]))

        r = client.post(f"/workout/reenviar-garmin/{SEG}")
        assert r.status_code == 200

        # O workout órfão da quarta foi deletado do Garmin...
        assert "gid-quarta" in _mock_garmin["deletados"]
        # ...e o garmin_workout_id foi removido do banco para o pull não re-importar.
        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        quarta = next(t for t in doc["treinos"] if t["data"] == QUA)
        assert "garmin_workout_id" not in quarta
        # A sexta (treino real) continua sendo re-enviada.
        assert SEX in _mock_garmin["enviados"]

    def test_dia_descanso_sem_workout_nao_chama_garmin(
        self, auth_client, fake_db, run, _mock_garmin
    ):
        client, uid = auth_client
        run(self._seed(fake_db, uid, [
            {"data": QUA, "tipo": "DESCANSO"},
        ]))
        r = client.post(f"/workout/reenviar-garmin/{SEG}")
        assert r.status_code == 200
        assert _mock_garmin["deletados"] == []


class TestSalvarPreservaAcademia:
    def test_academia_nao_e_apagada_ao_salvar(self, auth_client, fake_db, run):
        client, uid = auth_client
        academia = {"descricao": "Agachamento 4x8", "exercicios": ["squat"]}
        run(fake_db.semanas.insert_one({
            "semana_inicio": SEG, "user_id": uid, "objetivo": "base",
            "treinos": [{"data": QUA, "tipo": "TIROS", "duracao_min": 60, "academia": academia}],
        }))

        # O cliente re-salva a semana SEM enviar o bloco academia (o modelo o
        # descarta). O bloco salvo deve ser preservado a partir do banco.
        r = client.post("/workout/semana", json={
            "semana_inicio": SEG, "objetivo": "base",
            "treinos": [{"data": QUA, "tipo": "TIROS", "duracao_min": 60}],
        })
        assert r.status_code == 200

        doc = run(fake_db.semanas.find_one({"semana_inicio": SEG, "user_id": uid}))
        quarta = next(t for t in doc["treinos"] if t["data"] == QUA)
        assert quarta.get("academia") == academia

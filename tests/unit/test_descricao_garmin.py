"""A nota que chega no relógio passa pela mesma limpeza da exibição no portal.

O nome do workout enviado ao Garmin é o tipo real ("VO2MAX — 2026-08-24"), mas a
descrição vinha crua do banco — com o rótulo que a IA escreveu no texto ("Tiros —
75 min..."). No aparelho os dois apareciam juntos, contradizendo um ao outro, que
é exatamente a confusão reportada em 2026-08-23 no card do portal.
"""
import pytest
from bson import ObjectId


class _GarminFake:
    """Captura o payload em vez de falar com o Garmin."""

    def __init__(self):
        self.enviados = []

    def get_scheduled_workouts(self, ano, mes):
        return []

    def upload_cycling_workout(self, workout):
        self.enviados.append(workout.to_dict())
        return {"workoutId": "123"}

    def schedule_workout(self, wid, data):
        pass


@pytest.mark.asyncio
class TestDescricaoEnviadaAoGarmin:
    async def _enviar(self, fake_db, monkeypatch, descricao):
        import app.services.garmin_service as gs
        from app.services.garmin_workout_service import upload_e_agendar

        oid = ObjectId()
        await fake_db.users.insert_one({
            "_id": oid, "login": "a",
            "zonas": {"fc_max": 190, "limiar": 172, "zonas": [
                {"zona": z, "min": 100 + z * 10, "max": 109 + z * 10} for z in range(1, 6)
            ]},
        })

        api = _GarminFake()

        async def _fake_client(_user_id):
            return api

        monkeypatch.setattr(gs, "get_garmin_client", _fake_client)
        await upload_e_agendar(
            str(oid), tipo="VO2MAX", duracao_min=75, nome="VO2MAX — 2026-08-24",
            data_iso="2026-08-24", descricao=descricao,
        )
        return api.enviados[-1]["description"]

    async def test_rotulo_de_tipo_nao_chega_no_relogio(self, fake_db, monkeypatch):
        desc = await self._enviar(
            fake_db, monkeypatch,
            "Tiros — 75 min. 5×2 min em Z4/Z5 com 2 min de recuperação Z1.",
        )
        assert not desc.startswith("Tiros")
        assert desc.startswith("75 min.")
        assert "5×2 min em Z4/Z5" in desc

    async def test_bpm_e_cabecalho_de_round_trip_tambem_saem(self, fake_db, monkeypatch):
        desc = await self._enviar(
            fake_db, monkeypatch,
            "VO2MAX — 2026-08-24\n4x4 min em Z5 (177-192 bpm) com 4 min Z2.",
        )
        assert "VO2MAX — 2026-08-24" not in desc
        assert "bpm" not in desc
        assert "4x4 min em Z5" in desc

    async def test_prescricao_sem_rotulo_passa_intacta(self, fake_db, monkeypatch):
        s = "15 min aquecimento. 5×4 min Z5 com 4 min Z2. 10 min volta à calma."
        assert await self._enviar(fake_db, monkeypatch, s) == s

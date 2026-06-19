"""Testes de config_service (horários, zonas, ajustes de dia) com Mongo fake."""
import pytest

from app.services import config_service, user_service


async def _criar_user(fake_db):
    u = await user_service.criar_usuario({
        "login": "u1", "senha": "x", "nome": "U Um",
        "telefone": "+5551999990000",
        "perfil": {"idade": 30, "peso_kg": 80, "altura_cm": 180, "fc_max": 190},
    })
    return str(u["_id"])


class TestHorarios:
    async def test_get_default_sem_config(self, fake_db):
        uid = await _criar_user(fake_db)
        h = await config_service.get_horarios(uid)
        assert "cafe" in h and "jantar" in h

    async def test_salvar_e_ler(self, fake_db):
        uid = await _criar_user(fake_db)
        await config_service.salvar_horarios(uid, {"cafe": "07:00"})
        h = await config_service.get_horarios(uid)
        assert h["cafe"] == "07:00"

    async def test_horario_invalido_lanca(self, fake_db):
        uid = await _criar_user(fake_db)
        with pytest.raises(ValueError):
            await config_service.salvar_horarios(uid, {"cafe": "25:99"})

    async def test_ordem_invalida_lanca(self, fake_db):
        uid = await _criar_user(fake_db)
        with pytest.raises(ValueError):
            await config_service.salvar_horarios(uid, {"jantar": "06:00"})


class TestZonas:
    async def test_get_default_sem_config(self, fake_db):
        uid = await _criar_user(fake_db)
        z = await config_service.get_zonas(uid)
        assert len(z["zonas"]) == 5

    async def test_salvar_e_mapear_bpm(self, fake_db):
        uid = await _criar_user(fake_db)
        await config_service.salvar_zonas(uid, {
            "fc_max": 190, "limiar": 170,
            "zonas": [
                {"zona": 1, "min": 120, "max": 140},
                {"zona": 2, "min": 141, "max": 155},
                {"zona": 3, "min": 156, "max": 165},
                {"zona": 4, "min": 166, "max": 177},
                {"zona": 5, "min": 178, "max": 190},
            ],
        })
        mapa = await config_service.zonas_bpm_map(uid)
        assert mapa[5] == {"min": 178, "max": 190}


class TestAjustesDia:
    async def test_extras_vazio_inicial(self, fake_db):
        assert await config_service.extras_do_dia("u", "2026-06-19") == []

    async def test_adicionar_extra(self, fake_db):
        extras = await config_service.adicionar_extra_dia(
            "u", "2026-06-19", {"resumo": "Pizza", "kcal": 800, "proteina_g": 30})
        assert len(extras) == 1
        assert extras[0]["resumo"] == "Pizza"
        assert extras[0]["kcal"] == 800

    async def test_remover_ajuste(self, fake_db):
        await config_service.adicionar_extra_dia("u", "2026-06-19", {"resumo": "X", "kcal": 100})
        await config_service.remover_ajuste_dia("u", "2026-06-19")
        assert await config_service.extras_do_dia("u", "2026-06-19") == []

    async def test_corte_acumula(self, fake_db):
        await config_service.adicionar_corte_dia("u", "2026-06-19", 200)
        await config_service.adicionar_corte_dia("u", "2026-06-19", 150)
        assert await config_service.corte_do_dia("u", "2026-06-19") == 350

    async def test_corte_none_sem_doc(self, fake_db):
        assert await config_service.corte_do_dia("u", "2026-06-19") is None

    async def test_ajuste_do_dia_combina(self, fake_db):
        await config_service.adicionar_extra_dia("u", "2026-06-19", {"resumo": "X", "kcal": 100})
        await config_service.adicionar_corte_dia("u", "2026-06-19", 80)
        aj = await config_service.ajuste_do_dia("u", "2026-06-19")
        assert len(aj["extras"]) == 1
        assert aj["corte_kcal"] == 80

    async def test_isola_por_usuario(self, fake_db):
        await config_service.adicionar_extra_dia("ua", "2026-06-19", {"resumo": "X", "kcal": 100})
        assert await config_service.extras_do_dia("ub", "2026-06-19") == []

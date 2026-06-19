"""Testes dos helpers puros de data dos serviços de treino."""
import pytest

from app.services.treino_semana_service import (
    _semana_inicio, _treino_vazio, _e_treino_real,
)
from app.services.plano_semana_service import _proxima_semana, _shift_data


class TestSemanaInicio:
    def test_segunda_retorna_ela_mesma(self):
        # 2026-06-22 é segunda
        assert _semana_inicio("2026-06-22") == "2026-06-22"

    def test_meio_da_semana_volta_pra_segunda(self):
        # 2026-06-25 (quinta) → segunda 2026-06-22
        assert _semana_inicio("2026-06-25") == "2026-06-22"

    def test_domingo_volta_pra_segunda_anterior(self):
        # 2026-06-28 (domingo) → segunda 2026-06-22
        assert _semana_inicio("2026-06-28") == "2026-06-22"


class TestProximaSemana:
    def test_soma_7_dias(self):
        assert _proxima_semana("2026-06-22") == "2026-06-29"

    def test_atravessa_mes(self):
        assert _proxima_semana("2026-06-29") == "2026-07-06"


class TestShiftData:
    def test_positivo(self):
        assert _shift_data("2026-06-22", 6) == "2026-06-28"

    def test_negativo(self):
        assert _shift_data("2026-06-22", -1) == "2026-06-21"

    def test_zero(self):
        assert _shift_data("2026-06-22", 0) == "2026-06-22"


class TestTreinoVazio:
    def test_estrutura_descanso(self):
        t = _treino_vazio("2026-06-22")
        assert t["data"] == "2026-06-22"
        assert t["tipo"] == "DESCANSO"
        assert t["duracao_min"] is None
        assert t["resultado"] is None


class TestETreinoReal:
    def test_none_e_falso(self):
        assert _e_treino_real(None) is False

    def test_descanso_e_falso(self):
        assert _e_treino_real({"tipo": "DESCANSO", "duracao_min": 60}) is False

    def test_sem_duracao_e_falso(self):
        assert _e_treino_real({"tipo": "TIROS", "duracao_min": None}) is False

    def test_treino_com_duracao_e_real(self):
        assert _e_treino_real({"tipo": "TIROS", "duracao_min": 60}) is True

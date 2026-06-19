"""Testes dos helpers puros de periodização de provas (prova_service)."""
import pytest

from app.services.prova_service import (
    dias_ate, semanas_ate, fase_periodizacao, _limpar, FASE_LABEL,
)


class TestDiasAte:
    def test_dias_positivos(self):
        assert dias_ate("2026-06-20", ref="2026-06-19") == 1
        assert dias_ate("2026-07-19", ref="2026-06-19") == 30

    def test_dia_da_prova_zero(self):
        assert dias_ate("2026-06-19", ref="2026-06-19") == 0

    def test_prova_passada_negativo(self):
        assert dias_ate("2026-06-18", ref="2026-06-19") == -1


class TestSemanasAte:
    def test_arredonda_pra_cima(self):
        # 8 dias = 2 semanas (ceil)
        assert semanas_ate("2026-06-27", ref="2026-06-19") == 2
        # 7 dias = 1 semana
        assert semanas_ate("2026-06-26", ref="2026-06-19") == 1

    def test_prova_passada_zero(self):
        assert semanas_ate("2026-06-01", ref="2026-06-19") == 0


class TestFasePeriodizacao:
    @pytest.mark.parametrize("semanas,fase", [
        (0, "taper"),
        (1, "taper"),
        (2, "pico"),
        (3, "pico"),
        (4, "construcao"),
        (8, "construcao"),
        (9, "base"),
        (20, "base"),
    ])
    def test_fronteiras(self, semanas, fase):
        assert fase_periodizacao(semanas) == fase

    def test_todas_fases_tem_label(self):
        for fase in ("base", "construcao", "pico", "taper"):
            assert fase in FASE_LABEL


class TestLimpar:
    def test_prioridade_normalizada(self):
        assert _limpar({"prioridade": "a"})["prioridade"] == "A"
        assert _limpar({"prioridade": "x"})["prioridade"] == "B"  # inválida → B
        assert _limpar({"prioridade": ""})["prioridade"] == "B"

    def test_distancia_e_altimetria_tipos(self):
        out = _limpar({"distancia_km": "42.5", "altimetria_m": "1200"})
        assert out["distancia_km"] == 42.5
        assert out["altimetria_m"] == 1200

    def test_vazios_viram_none(self):
        out = _limpar({"distancia_km": "", "altimetria_m": "", "local": "  "})
        assert out["distancia_km"] is None
        assert out["altimetria_m"] is None
        assert out["local"] is None

    def test_ignora_campos_nao_editaveis(self):
        out = _limpar({"nome": "XCO", "user_id": "hack", "_id": "hack"})
        assert out == {"nome": "XCO"}

"""Testes dos helpers puros de periodização de provas (prova_service)."""
import pytest

from app.services.prova_service import (
    dias_ate, semanas_ate, fase_periodizacao, _limpar, FASE_LABEL,
    estagio_taper, carga_alvo_taper,
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
        (2, "taper"),      # polimento passou a ser de 2 semanas (descarga + prova)
        (3, "pico"),
        (4, "pico"),
        (5, "construcao"),
        (8, "construcao"),
        (9, "base"),
        (20, "base"),
    ])
    def test_fronteiras(self, semanas, fase):
        assert fase_periodizacao(semanas) == fase

    def test_todas_fases_tem_label(self):
        for fase in ("base", "construcao", "pico", "taper"):
            assert fase in FASE_LABEL


class TestEstagioTaper:
    @pytest.mark.parametrize("semanas,estagio", [
        (0, "prova"),        # prova nesta semana
        (1, "prova"),
        (2, "descarga"),     # prova na semana que vem
        (3, None),           # ainda em pico
        (10, None),
    ])
    def test_estagios(self, semanas, estagio):
        assert estagio_taper(semanas) == estagio

    def test_coerente_com_a_fase(self):
        """Todo estágio de taper só existe dentro da fase taper, e vice-versa."""
        for s in range(0, 15):
            assert (estagio_taper(s) is not None) == (fase_periodizacao(s) == "taper")


class TestCargaAlvoTaper:
    def test_descarga_corta_40pct(self):
        assert carga_alvo_taper(500, semanas=2) == 300

    def test_semana_da_prova_corta_65pct(self):
        assert carga_alvo_taper(500, semanas=1) == 175
        assert carga_alvo_taper(500, semanas=0) == 175

    def test_fora_do_taper_nao_tem_alvo(self):
        assert carga_alvo_taper(500, semanas=3) is None
        assert carga_alvo_taper(500, semanas=12) is None

    @pytest.mark.parametrize("cronica", [None, 0])
    def test_sem_carga_cronica_nao_inventa_numero(self, cronica):
        """Atleta sem TSS medido cai nas regras qualitativas, não num alvo falso."""
        assert carga_alvo_taper(cronica, semanas=1) is None

    def test_escala_com_o_atleta(self):
        """A prescrição é fração da carga própria — serve p/ 200 e p/ 600 TSS/sem."""
        assert carga_alvo_taper(200, semanas=1) == 70
        assert carga_alvo_taper(600, semanas=1) == 210


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

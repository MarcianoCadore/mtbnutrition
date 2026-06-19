"""Testes das funções puras de metabolismo e nutrição (nutricao_service)."""
import pytest

from app.services.nutricao_service import (
    bmr_mifflin, manutencao_basal, estimar_kcal_treino,
    periodo_de_hora, resolver_nutricao_prova, orientacao_prova,
)


class TestBmrMifflin:
    def test_homem_valor_conhecido(self):
        # 10*80 + 6.25*180 - 5*30 + 5 = 1780
        assert bmr_mifflin(80, 180, 30, "M") == 1780

    def test_mulher_valor_conhecido(self):
        # 10*60 + 6.25*165 - 5*30 - 161 = 1320.25
        assert bmr_mifflin(60, 165, 30, "F") == pytest.approx(1320.25)

    def test_sexo_default_masculino(self):
        assert bmr_mifflin(80, 180, 30) == bmr_mifflin(80, 180, 30, "M")


class TestManutencaoBasal:
    def test_aplica_fator_basal(self, perfil_completo):
        # 1780 * 1.2 = 2136
        assert manutencao_basal(perfil_completo) == pytest.approx(2136.0)

    def test_perfil_incompleto_retorna_none(self):
        assert manutencao_basal({"peso_kg": 80}) is None
        assert manutencao_basal({}) is None
        assert manutencao_basal(None) is None


class TestEstimarKcalTreino:
    def test_vo2max_60min(self):
        assert estimar_kcal_treino("VO2MAX", 60) == 720  # 12 kcal/min

    def test_descanso_zero(self):
        assert estimar_kcal_treino("DESCANSO", 60) == 0

    def test_tipo_desconhecido_usa_default(self):
        assert estimar_kcal_treino("ZUMBA", 60) == 480  # default 8 kcal/min

    def test_duracao_none_zero(self):
        assert estimar_kcal_treino("TIROS", None) == 0


class TestPeriodoDeHora:
    @pytest.mark.parametrize("hora,periodo", [
        (5, "manha"), (10, "manha"),
        (11, "meio_dia"), (13, "meio_dia"),
        (14, "tarde"), (17, "tarde"),
        (18, "noite"), (23, "noite"), (4, "noite"),
    ])
    def test_fronteiras(self, hora, periodo):
        assert periodo_de_hora(hora) == periodo


class TestResolverNutricaoProva:
    def test_carga_quando_proximo_da_prova(self):
        prova = {"nome": "XCO"}
        modo, menu, bloco = resolver_nutricao_prova("TEMPO", prova, 2, "pico", False)
        assert modo == "carga"
        assert menu == "Z2_LONGO"
        assert bloco is not None

    def test_deficit_na_base_querendo_emagrecer(self):
        modo, menu, bloco = resolver_nutricao_prova("TEMPO", None, None, "base", True)
        assert modo == "deficit"
        assert bloco is None

    def test_performance_sem_emagrecer(self):
        modo, menu, bloco = resolver_nutricao_prova("TEMPO", None, None, None, False)
        assert modo == "performance"

    def test_performance_emagrecer_fora_da_base(self):
        prova = {"nome": "XCO"}
        # 10 dias da prova (fora janela de carga), fase pico, quer emagrecer
        modo, _, _ = resolver_nutricao_prova("TEMPO", prova, 10, "pico", True)
        assert modo == "performance"


class TestOrientacaoProva:
    def test_fora_da_janela_none(self):
        assert orientacao_prova(None, {"nome": "X"}) is None
        assert orientacao_prova(-1, {"nome": "X"}) is None
        assert orientacao_prova(4, {"nome": "X"}) is None

    def test_dia_da_prova(self):
        b = orientacao_prova(0, {"nome": "Maratona"})
        assert b["fase"] == "dia"
        assert "Maratona" in b["titulo"]
        assert len(b["itens"]) > 0

    def test_vespera(self):
        assert orientacao_prova(1, {"nome": "X"})["fase"] == "vespera"

    def test_carga(self):
        assert orientacao_prova(3, {"nome": "X"})["fase"] == "carga"

    def test_nome_default(self):
        b = orientacao_prova(0, {})
        assert "prova" in b["titulo"].lower()

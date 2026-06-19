"""Testes dos helpers determinísticos do ai_service (sem chamar a IA)."""
import pytest

from app.services.ai_service import (
    _e_cota, _nota_valida, _zona_de,
    extrair_cadencia_texto, classificar_por_texto, _limpar_datas,
)


class TestECota:
    @pytest.mark.parametrize("msg", [
        "Error 429 too many requests",
        "rate limit exceeded",
        "quota exhausted for the day",
        "RATE_LIMIT hit",
    ])
    def test_detecta_cota(self, msg):
        assert _e_cota(Exception(msg)) is True

    def test_erro_comum_nao_e_cota(self):
        assert _e_cota(Exception("connection refused")) is False


class TestNotaValida:
    def test_dentro_da_faixa(self):
        assert _nota_valida(7.456) == 7.5

    def test_clampa_acima(self):
        assert _nota_valida(15) == 10.0

    def test_clampa_abaixo(self):
        assert _nota_valida(-3) == 0.0

    def test_invalida_retorna_none(self):
        assert _nota_valida("abc") is None
        assert _nota_valida(None) is None


class TestZonaDe:
    ZONAS = [
        {"zona": 1, "min": 100, "max": 140},
        {"zona": 2, "min": 141, "max": 155},
        {"zona": 3, "min": 156, "max": 165},
        {"zona": 4, "min": 166, "max": 177},
        {"zona": 5, "min": 178, "max": 190},
    ]

    def test_bpm_no_meio(self):
        assert _zona_de(150, self.ZONAS) == 2
        assert _zona_de(185, self.ZONAS) == 5

    def test_acima_do_maximo_vira_z5(self):
        assert _zona_de(210, self.ZONAS) == 5

    def test_abaixo_do_minimo_vira_z1(self):
        assert _zona_de(80, self.ZONAS) == 1


class TestExtrairCadencia:
    def test_faixa(self):
        assert extrair_cadencia_texto("manter 85-95 rpm na subida") == "85-95"

    def test_valor_unico(self):
        assert extrair_cadencia_texto("cadência alvo 90rpm") == "90"

    def test_sem_cadencia(self):
        assert extrair_cadencia_texto("treino de tiros forte") is None

    def test_primeiro_texto_com_dado_vence(self):
        assert extrair_cadencia_texto(None, "100 rpm") == "100"


class TestClassificarPorTexto:
    def test_vo2max(self):
        assert classificar_por_texto("Treino VO2 Max 4x4") == "VO2MAX"

    def test_tiros(self):
        assert classificar_por_texto("Sprints all-out") == "TIROS"

    def test_descanso(self):
        assert classificar_por_texto("Dia de descanso") == "DESCANSO"

    def test_titulo_tem_peso_maior(self):
        # título "recuperação" (peso 3) vence "tempo" da descrição (peso 1)
        assert classificar_por_texto("Recuperação", "um pouco de tempo z3") == "RECUPERACAO"

    def test_sem_palavra_chave_retorna_none(self):
        assert classificar_por_texto("xpto qwerty") is None


class TestLimparDatas:
    def test_remove_iso_e_dia_semana(self):
        out = _limpar_datas("treino 2026-06-08 segunda-feira tiros")
        assert "2026" not in out
        assert "segunda" not in out.lower()
        assert "tiros" in out

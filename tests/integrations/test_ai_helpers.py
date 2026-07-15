"""Testes dos helpers determinísticos do ai_service (sem chamar a IA)."""
import pytest

from app.services.ai_service import (
    _e_cota, _nota_valida, _zona_de,
    extrair_cadencia_texto, classificar_por_texto, _limpar_datas,
    tipo_definitivo,
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

    def test_serie_z5_em_minutos_e_vo2max_apesar_do_aquecimento(self):
        # Caso real (dia da terça): o aquecimento Z1/Z2 e a "recuperação entre
        # blocos" NÃO podem rebaixar um treino cuja série principal é 5×4 min Z5.
        desc = (
            "15 min aquecimento progressivo: 8 min Z1, 5 min Z2, 2 min Z3. "
            "Sessão principal: 5×4 min Z5 | alvo >318W, cadência 90-100 rpm. "
            "Recuperação de 4 min Z1-Z2 entre cada bloco. 15 min volta à calma Z1."
        )
        assert classificar_por_texto(desc) == "VO2MAX"

    def test_titulo_recuperacao_nao_vence_serie_z5_da_descricao(self):
        # O nome do workout do app ("RECUPERACAO — …") NÃO pode ganhar da série
        # principal de Z5 que está na descrição (era o loop do sync).
        assert classificar_por_texto(
            "RECUPERACAO — 2026-07-14",
            "5×4 min Z5 | alvo >318W",
        ) == "VO2MAX"

    def test_default_vo2max_do_app_classifica_vo2max(self):
        assert classificar_por_texto("4x4 min Z5 com 4 min recuperação Z2.") == "VO2MAX"

    def test_serie_z5_em_segundos_e_tiros(self):
        assert classificar_por_texto(
            "8x30s Z5 all-out com 3.5 min recuperação Z1.") == "TIROS"

    def test_serie_z3z4_nao_vira_vo2max_nem_tiros(self):
        # Série em Z3-Z4 (não Z5) não pode ser confundida com esforço de Z5.
        tipo = classificar_por_texto(
            "15 min aquecimento. 3×15 min Z3-Z4, recuperação Z2. Cadência 88-95 rpm.")
        assert tipo not in ("VO2MAX", "TIROS")


class TestTipoDefinitivo:
    def test_minutos_z5(self):
        assert tipo_definitivo("Série: 5×4 min Z5 | >318W") == "VO2MAX"

    def test_segundos_z5(self):
        assert tipo_definitivo("10×45s Z5 máximo") == "TIROS"

    def test_sem_z5_retorna_none(self):
        assert tipo_definitivo("90 min base aeróbica Z2, cadência 85-95 rpm.") is None
        assert tipo_definitivo("3×15 min Z3-Z4, recuperação Z2.") is None

    def test_recuperacao_pura_retorna_none(self):
        assert tipo_definitivo("75 min recuperação ativa Z1. Sem esforço.") is None


class TestLimparDatas:
    def test_remove_iso_e_dia_semana(self):
        out = _limpar_datas("treino 2026-06-08 segunda-feira tiros")
        assert "2026" not in out
        assert "segunda" not in out.lower()
        assert "tiros" in out

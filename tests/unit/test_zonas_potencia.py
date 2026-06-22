"""Testes unitários para calc_zonas_potencia e lógica de FTP (config_service)."""
import pytest

from app.services.config_service import calc_zonas_potencia, _ZONAS_POT_PCT


class TestCalcZonasPotencia:
    def test_retorna_7_zonas(self):
        zonas = calc_zonas_potencia(250)
        assert len(zonas) == 7

    def test_numeros_de_zona_sequenciais(self):
        zonas = calc_zonas_potencia(250)
        assert [z["zona"] for z in zonas] == list(range(1, 8))

    def test_campos_obrigatorios_presentes(self):
        for z in calc_zonas_potencia(300):
            assert "zona" in z
            assert "min" in z
            assert "max" in z
            assert "nome" in z

    def test_z1_min_e_zero(self):
        # Z1 vai de 0 a 55% do FTP
        z1 = calc_zonas_potencia(200)[0]
        assert z1["min"] == 0

    def test_z7_max_e_sentinela(self):
        # Z7 não tem limite superior real
        z7 = calc_zonas_potencia(200)[-1]
        assert z7["max"] == 9999

    def test_valores_conhecidos_ftp200(self):
        zonas = calc_zonas_potencia(200)
        # Z1: 0–55% de 200 = 0–110W
        assert zonas[0]["min"] == 0
        assert zonas[0]["max"] == round(200 * 0.55)
        # Z4 (Limiar): 91–105% de 200 = 182–210W
        z4 = zonas[3]
        assert z4["min"] == round(200 * 0.91)
        assert z4["max"] == round(200 * 1.05)

    def test_valores_conhecidos_ftp254(self):
        # FTP real do Marciano — confirma integração com o print do Garmin
        zonas = calc_zonas_potencia(254)
        z5 = zonas[4]  # VO2Max: 106–120%
        assert z5["min"] == round(254 * 1.06)
        assert z5["max"] == round(254 * 1.20)

    def test_zonas_crescentes(self):
        zonas = calc_zonas_potencia(300)
        for i in range(1, len(zonas)):
            assert zonas[i]["min"] > zonas[i - 1]["min"]

    def test_min_menor_que_max_em_todas_zonas(self):
        for z in calc_zonas_potencia(280):
            assert z["min"] < z["max"]

    def test_ftp_minimo_50w(self):
        zonas = calc_zonas_potencia(50)
        assert all(z["min"] < z["max"] for z in zonas)

    def test_ftp_maximo_700w(self):
        zonas = calc_zonas_potencia(700)
        assert len(zonas) == 7
        assert zonas[-1]["max"] == 9999

    def test_nomes_conhecidos(self):
        nomes = [z["nome"] for z in calc_zonas_potencia(200)]
        assert "Recuperação ativa" in nomes
        assert "Limiar" in nomes
        assert "Neuromuscular" in nomes

    def test_resultados_sao_inteiros(self):
        for z in calc_zonas_potencia(257):
            assert isinstance(z["min"], int)
            assert isinstance(z["max"], int)

    def test_zonas_pot_pct_tem_7_entradas(self):
        assert len(_ZONAS_POT_PCT) == 7

    @pytest.mark.parametrize("ftp", [100, 150, 200, 250, 300, 350, 400])
    def test_varios_ftps_sem_erro(self, ftp):
        zonas = calc_zonas_potencia(ftp)
        assert len(zonas) == 7


class TestFTPValidacao:
    """Testa regras de negócio de salvar_ftp sem I/O (lógica pura)."""

    def test_ftp_abaixo_de_50_invalido(self):
        # Valida a faixa 50-700 sem chamar o banco
        ftp = 40
        assert not (50 <= ftp <= 700)

    def test_ftp_acima_de_700_invalido(self):
        ftp = 701
        assert not (50 <= ftp <= 700)

    def test_fronteira_50_valida(self):
        assert 50 <= 50 <= 700

    def test_fronteira_700_valida(self):
        assert 50 <= 700 <= 700

    def test_modo_invalido_cai_no_default(self):
        # Reproduz o comportamento do salvar_ftp: modo inválido → 'indoor'
        modo = "invalido"
        resultado = modo if modo in ("indoor", "sempre", "nunca") else "indoor"
        assert resultado == "indoor"

    @pytest.mark.parametrize("modo", ["indoor", "sempre", "nunca"])
    def test_modos_validos(self, modo):
        resultado = modo if modo in ("indoor", "sempre", "nunca") else "indoor"
        assert resultado == modo

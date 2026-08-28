"""O tipo do treino REALIZADO é lido com a régua do atleta.

Antes as faixas de bpm estavam cravadas no módulo ("zonas do Marciano, FC max
192"): a mesma sessão era classificada com a fisiologia de outra pessoa, e nem
para ele valia quando a cinta falhava ou o pedal era no rolo por watts.
"""
import pytest

from app.services.fit_service import _classify, _fracao_por_zona

# FC máx alta — Z2 dele vai até 153 bpm.
ZONAS_A = {1: {"min": 100, "max": 134}, 2: {"min": 135, "max": 153},
           3: {"min": 154, "max": 164}, 4: {"min": 165, "max": 177},
           5: {"min": 178, "max": 195}}
# FC máx baixa — 150 bpm já é Z5.
ZONAS_B = {1: {"min": 90, "max": 110}, 2: {"min": 111, "max": 125},
           3: {"min": 126, "max": 136}, 4: {"min": 137, "max": 148},
           5: {"min": 149, "max": 165}}

# Zonas de potência (Coggan 1-7, de calc_zonas_potencia) de um FTP de 250 W.
ZONAS_W = {1: {"min": 0, "max": 137}, 2: {"min": 138, "max": 187},
           3: {"min": 188, "max": 225}, 4: {"min": 226, "max": 262},
           5: {"min": 263, "max": 300}, 6: {"min": 301, "max": 375},
           7: {"min": 376, "max": 9999}}


class TestReguaDoAtleta:
    def test_mesma_fc_dois_atletas_tipos_diferentes(self):
        """150 bpm constante: Z2 para quem tem FC máx alta, Z5 para quem não tem."""
        serie = [150] * 3000
        assert _classify(serie, ZONAS_A) == "Z2_LONGO"
        assert _classify(serie, ZONAS_B) == "VO2MAX"

    def test_sem_zonas_nao_chuta_pela_fc(self):
        """Sem as faixas do atleta não há como dizer o que 150 bpm significa."""
        assert _classify([150] * 3000, None) == "Z2_LONGO"

    def test_zonas_novas_mudam_a_leitura(self):
        """A FC do atleta muda com o tempo: mesma sessão, zonas atualizadas para
        cima, e o que era limiar vira aeróbico."""
        serie = [160] * 3000
        antigas = {**ZONAS_A}
        novas = {1: {"min": 110, "max": 145}, 2: {"min": 146, "max": 165},
                 3: {"min": 166, "max": 176}, 4: {"min": 177, "max": 188},
                 5: {"min": 189, "max": 205}}
        assert _classify(serie, antigas) == "TEMPO"
        assert _classify(serie, novas) == "Z2_LONGO"


class TestFCNaoConfiavel:
    def test_ignorar_fc_le_pelos_watts(self):
        """Sem cinta (ou cinta falhando), a FC não pode decidir: manda o watt."""
        fc_ruim = [150] * 3000          # pela régua B seria VO2máx
        watts_z2 = [160] * 3000
        assert _classify(fc_ruim, ZONAS_B, power_values=watts_z2,
                         zonas_watts=ZONAS_W, ignorar_fc=True) == "Z2_LONGO"

    def test_watts_acima_do_limiar_e_vo2(self):
        watts = [280] * 600 + [120] * 1400   # 30% do tempo em Z5
        assert _classify([], None, power_values=watts, zonas_watts=ZONAS_W,
                         ignorar_fc=True) == "VO2MAX"

    def test_sem_fc_e_sem_watts_cai_no_padrao(self):
        assert _classify([], None) == "Z2_LONGO"

    def test_picos_de_potencia_ainda_sao_tiros(self):
        """A forma da curva (VI) não depende de zona e continua valendo."""
        assert _classify([140] * 100, ZONAS_A, avg_power=150, norm_power=200) == "TIROS"


class TestFracaoPorZona:
    def test_abaixo_da_primeira_e_acima_da_ultima_contam_nas_pontas(self):
        fr = _fracao_por_zona([50, 250], ZONAS_A)
        assert fr[1] == 0.5 and fr[5] == 0.5

    @pytest.mark.parametrize("valores,zonas", [([], ZONAS_A), ([150], None), ([], None)])
    def test_sem_dado_volta_vazio(self, valores, zonas):
        assert _fracao_por_zona(valores, zonas) == {}

"""NP calculada do .fit e FC zerada descartada.

Dois defeitos que se somaram num VO2máx real (31/08/2026) e produziram uma
avaliação errada:

- o .fit não trazia `normalized_power` na mensagem de sessão, então o app caía
  na potência MÉDIA (207 W). A NP de verdade era 243 W — a diferença entre um
  IF de 0.69 ("Z2/recuperação") e um IF de 0.81 (limiar), num treino com 12% do
  tempo em Z5/Z6;
- a cinta estava sem bateria e gravou 0 bpm o treino inteiro. Zero contava como
  batimento, caía todo na primeira zona e o classificador lia a sessão como
  100% Z1 — o VO2máx virava "RECUPERACAO".
"""
import pytest

from app.services.fit_service import (
    _classify, _fc_utilizavel, potencia_normalizada,
)

ZONAS_BPM = {1: {"min": 100, "max": 134}, 2: {"min": 135, "max": 153},
             3: {"min": 154, "max": 164}, 4: {"min": 165, "max": 177},
             5: {"min": 178, "max": 195}}
# Coggan para FTP 300 W.
ZONAS_W = {1: {"min": 0, "max": 165}, 2: {"min": 166, "max": 225},
           3: {"min": 226, "max": 270}, 4: {"min": 271, "max": 315},
           5: {"min": 316, "max": 360}, 6: {"min": 361, "max": 450},
           7: {"min": 451, "max": 9999}}


class TestPotenciaNormalizada:
    def test_esforco_constante_np_igual_a_media(self):
        """Sem variação não há custo extra: NP ≈ média."""
        assert potencia_normalizada([200] * 600) == pytest.approx(200, abs=1)

    def test_intervalado_np_acima_da_media(self):
        """É para isso que a NP existe: 30s a 450 W e 30s a 100 W custam mais que
        os 275 W da média aritmética."""
        serie = ([450] * 30 + [100] * 30) * 30
        media = sum(serie) / len(serie)
        np_ = potencia_normalizada(serie)
        assert np_ > media

    def test_serie_curta_demais_nao_tem_np(self):
        """Menos que a janela de 30s não dá média móvel nenhuma."""
        assert potencia_normalizada([200] * 10) is None

    @pytest.mark.parametrize("valores", [None, []])
    def test_sem_potencia_volta_none(self, valores):
        assert potencia_normalizada(valores) is None


class TestFCUtilizavel:
    def test_cinta_morta_zera_a_serie(self):
        """0 bpm não é FC baixa — é ausência de FC."""
        assert _fc_utilizavel([0] * 3990, 3990) == []

    def test_fc_boa_passa_inteira(self):
        assert _fc_utilizavel([150] * 3000, 3000) == [150] * 3000

    def test_dropout_curto_e_limpo_mas_a_serie_vale(self):
        """Falha de alguns segundos não invalida o treino: some o zero, fica o resto."""
        assert _fc_utilizavel([150] * 2900 + [0] * 100, 3000) == [150] * 2900

    def test_fc_de_meia_sessao_nao_vale(self):
        """Cinta que caiu na metade descreve meia sessão — melhor ler pelos watts
        do que julgar o treino inteiro pelo pedaço que sobrou."""
        assert _fc_utilizavel([150] * 1000 + [0] * 2000, 3000) == []


class TestVO2MaxComCintaMorta:
    """Regressão do treino de 31/08/2026."""

    SERIE_VO2 = [340] * 480 + [180] * 3510   # 12% acima do limiar, resto Z2

    def test_fc_zerada_nao_vira_recuperacao(self):
        fc_morta = _fc_utilizavel([0] * 3990, 3990)
        tipo = _classify(fc_morta, ZONAS_BPM, power_values=self.SERIE_VO2,
                         zonas_watts=ZONAS_W)
        assert tipo == "VO2MAX", "cinta sem bateria não pode rebaixar o treino"

    def test_sem_o_filtro_o_bug_apareceria(self):
        """Prova que o zero era mesmo o culpado: entregue cru, ele rotula Z1."""
        assert _classify([0] * 3990, ZONAS_BPM, power_values=self.SERIE_VO2,
                         zonas_watts=ZONAS_W) == "RECUPERACAO"

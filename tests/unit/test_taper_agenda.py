"""Regras de agenda do polimento (taper) — dois estágios e o dia da prova.

O polimento deixou de ser uma regra fixa de 1 semana e passou a ter dois
degraus: a semana de DESCARGA (prova na semana seguinte) ainda treina, e a
SEMANA DA PROVA é só manutenção. Estes testes prendem os tetos de duração e
garantem que o dia da prova nunca é sobrescrito pelo longão de fim de semana.
"""
import pytest

from app.services.plano_semana_service import (
    _aplicar_regras_agenda, _bloco_carga_taper, _LONGAO_MIN, _MAX_MIN_DIA_UTIL,
)

SABADO = "2026-08-08"     # dia do longão no padrão seg–sáb
QUARTA = "2026-08-05"     # dia útil
DOMINGO = "2026-08-09"    # fora dos dias de treino no padrão


def agenda(data, tipo="TEMPO", duracao=150, fase=None, estagio=None, data_prova=None):
    return _aplicar_regras_agenda(
        data, tipo, duracao, "desc", None,
        preferencias=None, fase=fase, estagio_taper=estagio, data_prova=data_prova,
    )


class TestLongaoPorEstagio:
    def test_fora_do_taper_longao_inteiro(self):
        tipo, dur, _, _ = agenda(SABADO)
        assert (tipo, dur) == ("Z2_LONGO", _LONGAO_MIN)

    def test_descarga_encolhe_para_2h(self):
        tipo, dur, desc, _ = agenda(SABADO, fase="taper", estagio="descarga")
        assert (tipo, dur) == ("Z2_LONGO", 120)
        assert "descarga" in desc.lower()

    def test_semana_da_prova_encolhe_para_1h30(self):
        tipo, dur, desc, _ = agenda(SABADO, fase="taper", estagio="prova")
        assert (tipo, dur) == ("Z2_LONGO", 90)
        assert "taper" in desc.lower()

    def test_descarga_treina_mais_que_a_semana_da_prova(self):
        _, dur_desc, _, _ = agenda(SABADO, fase="taper", estagio="descarga")
        _, dur_prova, _, _ = agenda(SABADO, fase="taper", estagio="prova")
        assert dur_desc > dur_prova


class TestTetoDiaUtil:
    @pytest.mark.parametrize("estagio,teto", [
        (None, _MAX_MIN_DIA_UTIL),
        ("descarga", 90),
        ("prova", 60),
    ])
    def test_tetos(self, estagio, teto):
        fase = "taper" if estagio else None
        _, dur, _, _ = agenda(QUARTA, duracao=150, fase=fase, estagio=estagio)
        assert dur == teto

    def test_nao_estica_treino_curto(self):
        """O teto corta o que passa; não infla o que já é curto."""
        _, dur, _, _ = agenda(QUARTA, duracao=40, fase="taper", estagio="prova")
        assert dur == 40


class TestDiaDaProva:
    def test_prova_no_sabado_nao_vira_longao(self):
        """Sem isso, a regra do longão de sábado sobrescrevia a própria prova."""
        tipo, dur, _, _ = agenda(
            SABADO, tipo="TEMPO", duracao=180,
            fase="taper", estagio="prova", data_prova=SABADO,
        )
        assert tipo == "TEMPO"
        assert dur == 180

    def test_prova_em_dia_util_nao_recebe_teto(self):
        _, dur, _, _ = agenda(
            QUARTA, duracao=200, fase="taper", estagio="prova", data_prova=QUARTA,
        )
        assert dur == 200

    def test_dia_que_nao_e_o_da_prova_segue_as_regras(self):
        tipo, dur, _, _ = agenda(
            SABADO, fase="taper", estagio="prova", data_prova=QUARTA,
        )
        assert (tipo, dur) == ("Z2_LONGO", 90)


class TestCompatibilidade:
    def test_taper_sem_estagio_cai_no_corte_conservador(self):
        """Chamada antiga (só `fase`) não pode virar semana cheia de treino."""
        _, dur_sem, _, _ = agenda(SABADO, fase="taper")
        _, dur_prova, _, _ = agenda(SABADO, fase="taper", estagio="prova")
        assert dur_sem == dur_prova

    def test_dia_fora_dos_dias_de_treino_ainda_e_descanso(self):
        tipo, dur, _, _ = agenda(DOMINGO, fase="taper", estagio="prova")
        assert tipo == "DESCANSO"
        assert dur is None

    def test_estagio_ignorado_fora_do_taper(self):
        """Estágio só vale dentro da fase taper — sem fase, longão inteiro."""
        _, dur, _, _ = agenda(SABADO, fase=None, estagio="prova")
        assert dur == _LONGAO_MIN


class TestBlocoCargaTaper:
    def test_sem_alvo_nao_gera_texto(self):
        assert _bloco_carga_taper(None, None) == ""
        assert _bloco_carga_taper(0, 500) == ""

    def test_com_alvo_cita_os_dois_numeros(self):
        txt = _bloco_carga_taper(175, 500)
        assert "175 TSS" in txt
        assert "500 TSS/semana" in txt

    def test_avisa_que_a_prova_fica_fora_da_conta(self):
        assert "NÃO entra" in _bloco_carga_taper(175, 500)

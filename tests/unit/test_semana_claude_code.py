"""A semana escrita fora da API passa pelas mesmas travas da semana da API.

Desde 12/09/2026 quem monta o plano é o Claude Code no terminal (o crédito da
API acabou e o dono não quer pagar). O risco novo é óbvio: plano entrando no
banco sem passar pelas regras que protegem o atleta. `normalizar_plano` é o
funil por onde todo plano tem que passar, venha de onde vier.
"""
import pytest

from app.services.plano_semana_service import (
    normalizar_plano, _MAX_MIN_DIA_UTIL, _LONGAO_MIN,
)

SEGUNDA = "2026-09-21"    # dia útil
SABADO = "2026-09-26"     # dia do longão


def ctx(**extra):
    base = {
        "proxima": "2026-09-21",
        "preferencias": None,
        "fase_prova": None,
        "estagio_prova": None,
        "data_prova": None,
        "zonas_lista": [],
        "zonas_pot_user": [],
        "quantos_com_potencia": None,
        "parecer": None,
    }
    base.update(extra)
    return base


def plano(treinos, **resto):
    d = {"analise_semana": "ok", "progressao": "ok", "treinos": treinos}
    d.update(resto)
    return d


class TestTravasDoPlanoExterno:
    def test_tipo_inventado_vira_descanso(self):
        # Um tipo que o app não conhece viraria treino sem prescrição no Garmin.
        saida = normalizar_plano(
            plano([{"data": SEGUNDA, "tipo": "SPINNING_DO_YOUTUBE", "duracao_min": 60,
                    "descricao": "x"}]), ctx(), modelo_usado="claude-code")
        assert saida["treinos"][0]["tipo"] == "DESCANSO"

    def test_duracao_absurda_e_cortada_no_teto_do_dia_util(self):
        saida = normalizar_plano(
            plano([{"data": SEGUNDA, "tipo": "TEMPO", "duracao_min": 400,
                    "descricao": "x"}]), ctx(), modelo_usado="claude-code")
        assert saida["treinos"][0]["duracao_min"] <= _MAX_MIN_DIA_UTIL

    def test_longao_do_fim_de_semana_e_imposto_pelo_codigo(self):
        saida = normalizar_plano(
            plano([{"data": SABADO, "tipo": "RECUPERACAO", "duracao_min": 30,
                    "descricao": "voltinha"}]), ctx(), modelo_usado="claude-code")
        assert saida["treinos"][0]["duracao_min"] == _LONGAO_MIN

    def test_taper_encolhe_o_longao_mesmo_vindo_do_terminal(self):
        saida = normalizar_plano(
            plano([{"data": SABADO, "tipo": "Z2_LONGO", "duracao_min": 240,
                    "descricao": "longo"}]),
            ctx(fase_prova="taper", estagio_prova="prova"), modelo_usado="claude-code")
        assert saida["treinos"][0]["duracao_min"] == 90

    def test_origem_do_plano_fica_registrada(self):
        saida = normalizar_plano(plano([]), ctx(), modelo_usado="claude-code")
        assert saida["modelo_usado"] == "claude-code"

    def test_descanso_nao_carrega_duracao(self):
        saida = normalizar_plano(
            plano([{"data": SEGUNDA, "tipo": "DESCANSO", "duracao_min": 60, "descricao": ""}]),
            ctx(), modelo_usado="claude-code")
        assert saida["treinos"][0]["duracao_min"] is None


class TestLegendaDeZonas:
    def test_legenda_sai_do_cadastro_do_atleta_nao_do_texto_gerado(self):
        # O modelo cita "Zona 4"; quem escreve os bpm é o código, com as faixas
        # reais do atleta. Número inventado vira alvo errado no relógio.
        zonas = [{"zona": 4, "min": 166, "max": 177}]
        saida = normalizar_plano(
            plano([{"data": SEGUNDA, "tipo": "TEMPO", "duracao_min": 60,
                    "descricao": "20 min na Zona 4"}]),
            ctx(zonas_lista=zonas), modelo_usado="claude-code")
        assert "166" in saida["treinos"][0]["descricao"]

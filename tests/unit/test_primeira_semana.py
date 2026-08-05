"""Testes do gerador de primeira semana (cold start, sem histórico)."""
from datetime import date

import pytest

from app.services.plano_semana_service import (
    _montar_primeira_semana_template, _PRIMEIRA_SEMANA_LONGAO_MIN,
    _primeiro_dia_planejavel, dias_treino_do_usuario,
)

# 2026-06-22 é uma segunda-feira (início de semana ISO).
SEG = "2026-06-22"
TODOS_OS_DIAS = [0, 1, 2, 3, 4, 5, 6]


def _por_data(treinos):
    return {t["data"]: t for t in treinos}


class TestTemplatePrimeiraSemana:
    def test_sempre_7_dias(self):
        t = _montar_primeira_semana_template(SEG, "performance_mtb", [0, 1, 2, 3, 4, 5])
        assert len(t) == 7

    def test_dias_fora_de_treino_sao_descanso(self):
        # treina só seg, qua, sex (0,2,4)
        t = _por_data(_montar_primeira_semana_template(SEG, "performance_mtb", [0, 2, 4]))
        assert t["2026-06-23"]["tipo"] == "DESCANSO"  # terça
        assert t["2026-06-25"]["tipo"] == "DESCANSO"  # quinta
        assert t["2026-06-28"]["tipo"] == "DESCANSO"  # domingo
        assert t["2026-06-22"]["tipo"] != "DESCANSO"  # segunda

    def test_descanso_nao_tem_duracao(self):
        t = _montar_primeira_semana_template(SEG, "performance_mtb", [0])
        for treino in t:
            if treino["tipo"] == "DESCANSO":
                assert treino["duracao_min"] is None

    def test_sabado_vira_longao_leve(self):
        t = _por_data(_montar_primeira_semana_template(SEG, "performance_mtb", [0, 1, 5]))
        sabado = t["2026-06-27"]
        assert sabado["tipo"] == "Z2_LONGO"
        assert sabado["duracao_min"] == _PRIMEIRA_SEMANA_LONGAO_MIN

    def test_domingo_longao_se_nao_ha_sabado(self):
        # treina seg e dom (0,6) → domingo recebe o longão
        t = _por_data(_montar_primeira_semana_template(SEG, "base_aerobica", [0, 6]))
        assert t["2026-06-28"]["tipo"] == "Z2_LONGO"

    def test_objetivo_desconhecido_usa_default(self):
        # não deve lançar; cai no template performance_mtb
        t = _montar_primeira_semana_template(SEG, "objetivo_inexistente", [0, 1, 2])
        assert len(t) == 7

    def test_volume_conservador_dias_uteis(self):
        # nenhum treino de dia útil passa de 75 min (semana de iniciante)
        t = _montar_primeira_semana_template(SEG, "aumentar_potencia", [0, 1, 2, 3, 4])
        for treino in t:
            if treino["duracao_min"]:
                assert treino["duracao_min"] <= 75

    def test_dias_treino_vazio_usa_padrao(self):
        # lista vazia → padrão seg-sáb, não quebra
        t = _montar_primeira_semana_template(SEG, "performance_mtb", [])
        assert len(t) == 7
        assert any(x["tipo"] != "DESCANSO" for x in t)


class TestCadastroNoMeioDaSemana:
    """Quem entra na quarta não recebe treino para a segunda que já passou."""

    def test_dias_ja_vencidos_viram_descanso(self):
        # "hoje" = quarta 2026-06-24
        t = _por_data(_montar_primeira_semana_template(
            SEG, "performance_mtb", TODOS_OS_DIAS, hoje=date(2026, 6, 24)))
        assert t["2026-06-22"]["tipo"] == "DESCANSO"   # segunda (passou)
        assert t["2026-06-23"]["tipo"] == "DESCANSO"   # terça (passou)
        assert t["2026-06-24"]["tipo"] != "DESCANSO"   # hoje já treina

    def test_sequencia_comeca_hoje_e_nao_se_gasta_no_passado(self):
        # A 1ª sessão da sequência do objetivo tem que cair em "hoje", não na segunda.
        inteira = _montar_primeira_semana_template(
            SEG, "performance_mtb", TODOS_OS_DIAS, hoje=date(2026, 6, 22))
        parcial = _por_data(_montar_primeira_semana_template(
            SEG, "performance_mtb", TODOS_OS_DIAS, hoje=date(2026, 6, 24)))
        assert parcial["2026-06-24"]["tipo"] == inteira[0]["tipo"]

    def test_semana_futura_e_planejada_inteira(self):
        t = _montar_primeira_semana_template(
            SEG, "performance_mtb", TODOS_OS_DIAS, hoje=date(2026, 6, 15))
        assert all(x["tipo"] != "DESCANSO" for x in t)

    def test_semana_passada_e_planejada_inteira(self):
        # regerar histórico não pode zerar a semana inteira
        t = _montar_primeira_semana_template(
            SEG, "performance_mtb", TODOS_OS_DIAS, hoje=date(2026, 7, 20))
        assert all(x["tipo"] != "DESCANSO" for x in t)

    def test_cadastro_no_domingo_so_planeja_domingo(self):
        t = _por_data(_montar_primeira_semana_template(
            SEG, "performance_mtb", TODOS_OS_DIAS, hoje=date(2026, 6, 28)))
        assert t["2026-06-28"]["tipo"] != "DESCANSO"
        assert all(v["tipo"] == "DESCANSO" for k, v in t.items() if k < "2026-06-28")

    def test_longao_do_sabado_sobrevive_ao_inicio_no_meio(self):
        t = _por_data(_montar_primeira_semana_template(
            SEG, "performance_mtb", TODOS_OS_DIAS, hoje=date(2026, 6, 25)))
        assert t["2026-06-27"]["duracao_min"] == _PRIMEIRA_SEMANA_LONGAO_MIN

    def test_primeiro_dia_planejavel(self):
        assert _primeiro_dia_planejavel(SEG, date(2026, 6, 24)) == "2026-06-24"
        assert _primeiro_dia_planejavel(SEG, date(2026, 6, 22)) == SEG
        assert _primeiro_dia_planejavel(SEG, date(2026, 6, 10)) == SEG   # futura
        assert _primeiro_dia_planejavel(SEG, date(2026, 7, 10)) == SEG   # passada


class TestDiasTreinoDoUsuario:
    def test_dias_fixos_tem_precedencia_sobre_frequencia(self):
        assert dias_treino_do_usuario(
            {"dias_treino": [0, 3], "frequencia_semanal": 5}) == [0, 3]

    def test_frequencia_define_os_dias(self):
        for freq in range(1, 8):
            dias = dias_treino_do_usuario({"frequencia_semanal": freq})
            assert len(dias) == freq
            assert dias == sorted(set(dias))
            assert all(0 <= d <= 6 for d in dias)

    def test_frequencia_baixa_pega_o_fim_de_semana(self):
        # quem só treina 1x tem que ser no fim de semana (é onde cabe o longão)
        assert dias_treino_do_usuario({"frequencia_semanal": 1}) == [5]

    def test_sem_nada_cai_no_padrao(self):
        assert dias_treino_do_usuario({}) == [0, 1, 2, 3, 4, 5]
        assert dias_treino_do_usuario(None) == [0, 1, 2, 3, 4, 5]

    def test_valores_sujos_sao_ignorados(self):
        assert dias_treino_do_usuario({"dias_treino": ["2", 9, None, "x", 4]}) == [2, 4]
        assert dias_treino_do_usuario({"frequencia_semanal": "3"}) == [1, 3, 5]
        assert dias_treino_do_usuario({"frequencia_semanal": 99}) == [0, 1, 2, 3, 4, 5]

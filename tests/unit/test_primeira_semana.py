"""Testes do gerador de primeira semana (cold start, sem histórico)."""
import pytest

from app.services.plano_semana_service import (
    _montar_primeira_semana_template, _PRIMEIRA_SEMANA_LONGAO_MIN,
)

# 2026-06-22 é uma segunda-feira (início de semana ISO).
SEG = "2026-06-22"


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

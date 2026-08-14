"""Meta de volume semanal (preferencias.volume_semanal_min).

O atleta que quer "no mínimo 10h por semana" configura isso uma vez no perfil em
vez de repetir no chat toda semana. É OPCIONAL: sem meta, quem decide o volume
continua sendo a IA — nenhum caminho pode passar a exigir o campo.
"""
from datetime import date

import pytest

from app.services.plano_semana_service import (
    VOLUME_SEMANAL_MAX_H,
    VOLUME_SEMANAL_MIN_H,
    _MAX_MIN_DIA_UTIL,
    _montar_primeira_semana_template,
    formatar_horas,
    volume_semanal_do_usuario,
)


class TestLeituraDaPreferencia:
    def test_meta_em_minutos(self):
        assert volume_semanal_do_usuario({"volume_semanal_min": 600}) == 600

    def test_string_do_mongo_tambem_serve(self):
        assert volume_semanal_do_usuario({"volume_semanal_min": "600"}) == 600

    @pytest.mark.parametrize("pref", [
        None, {}, {"volume_semanal_min": None}, {"volume_semanal_min": 0},
        {"volume_semanal_min": ""}, {"volume_semanal_min": "dez horas"},
    ])
    def test_sem_meta_devolve_none(self, pref):
        assert volume_semanal_do_usuario(pref) is None

    @pytest.mark.parametrize("minutos", [
        VOLUME_SEMANAL_MIN_H * 60 - 1, VOLUME_SEMANAL_MAX_H * 60 + 1, -600, 99999,
    ])
    def test_valor_fora_da_faixa_e_ignorado(self, minutos):
        assert volume_semanal_do_usuario({"volume_semanal_min": minutos}) is None


class TestFormatacao:
    @pytest.mark.parametrize("minutos,esperado", [
        (600, "10h"), (630, "10h30"), (450, "7h30"), (60, "1h"), (None, "—"), (0, "—"),
    ])
    def test_horas_legiveis(self, minutos, esperado):
        assert formatar_horas(minutos) == esperado


class TestPrimeiraSemanaEscalada:
    """Quem configura 10h não é iniciante e não pode receber uma semana de 5h30
    só porque ainda não tem histórico."""

    SEG = "2026-09-07"
    DIAS = [0, 1, 2, 3, 4, 5]
    ANTES = date(2026, 9, 1)   # semana toda ainda no futuro

    def _semana(self, meta):
        return _montar_primeira_semana_template(
            self.SEG, "performance_mtb", self.DIAS,
            hoje=self.ANTES, volume_alvo_min=meta,
        )

    def _total(self, treinos):
        return sum(t.get("duracao_min") or 0 for t in treinos)

    def test_sem_meta_mantem_o_template_gentil(self):
        assert self._total(self._semana(None)) == 330

    def test_com_meta_a_semana_cresce_ate_ela(self):
        total = self._total(self._semana(600))
        assert abs(total - 600) <= 15, total

    def test_meta_menor_encolhe_a_semana(self):
        total = self._total(self._semana(240))
        assert abs(total - 240) <= 15, total

    def test_dia_util_nunca_passa_do_teto(self):
        for t in self._semana(900):
            if not t.get("duracao_min"):
                continue
            if date.fromisoformat(t["data"]).weekday() <= 4:
                assert t["duracao_min"] <= _MAX_MIN_DIA_UTIL, t

    def test_meta_impossivel_chega_perto_sem_furar_teto(self):
        """Meta que não cabe nos dias configurados não autoriza treino de 4h numa
        terça — entrega o que couber."""
        treinos = self._semana(VOLUME_SEMANAL_MAX_H * 60)
        assert self._total(treinos) < VOLUME_SEMANAL_MAX_H * 60
        assert all(
            t["duracao_min"] <= _MAX_MIN_DIA_UTIL
            for t in treinos
            if t.get("duracao_min") and date.fromisoformat(t["data"]).weekday() <= 4
        )

    def test_descanso_continua_descanso(self):
        treinos = self._semana(600)
        domingos = [t for t in treinos if date.fromisoformat(t["data"]).weekday() == 6]
        assert domingos and all(t["tipo"] == "DESCANSO" for t in domingos)
        assert all(t["duracao_min"] is None for t in domingos)

    def test_duracoes_em_multiplos_de_5(self):
        for t in self._semana(600):
            if t.get("duracao_min"):
                assert t["duracao_min"] % 5 == 0, t

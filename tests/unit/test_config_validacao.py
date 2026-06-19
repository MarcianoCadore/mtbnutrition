"""Testes das validações puras de config_service (horários e zonas)."""
import pytest

from app.services.config_service import (
    _para_min, _validar_ordem, _validar_zonas, DEFAULT_HORARIOS,
)


class TestParaMin:
    def test_converte_hhmm(self):
        assert _para_min("00:00") == 0
        assert _para_min("01:30") == 90
        assert _para_min("23:59") == 1439


class TestValidarOrdem:
    def test_ordem_correta_passa(self):
        # defaults já estão em ordem crescente
        _validar_ordem(dict(DEFAULT_HORARIOS))  # não deve lançar

    def test_jantar_antes_do_cafe_falha(self):
        cfg = dict(DEFAULT_HORARIOS)
        cfg["jantar"] = "08:00"  # antes do almoço/lanche → inválido
        with pytest.raises(ValueError):
            _validar_ordem(cfg)

    def test_refeicoes_iguais_falham(self):
        cfg = dict(DEFAULT_HORARIOS)
        cfg["almoco"] = cfg["lanche_manha"]  # almoço == lanche manhã
        with pytest.raises(ValueError):
            _validar_ordem(cfg)


class TestValidarZonas:
    def _zonas_validas(self):
        return {
            "fc_max": 190,
            "limiar": 170,
            "zonas": [
                {"zona": 1, "min": 120, "max": 140},
                {"zona": 2, "min": 141, "max": 155},
                {"zona": 3, "min": 156, "max": 165},
                {"zona": 4, "min": 166, "max": 177},
                {"zona": 5, "min": 178, "max": 190},
            ],
        }

    def test_zonas_validas_normalizam(self):
        out = _validar_zonas(self._zonas_validas())
        assert out["fc_max"] == 190
        assert out["limiar"] == 170
        assert len(out["zonas"]) == 5
        assert [z["zona"] for z in out["zonas"]] == [1, 2, 3, 4, 5]

    def test_numero_errado_de_zonas_falha(self):
        d = self._zonas_validas()
        d["zonas"] = d["zonas"][:4]
        with pytest.raises(ValueError):
            _validar_zonas(d)

    def test_min_maior_que_max_falha(self):
        d = self._zonas_validas()
        d["zonas"][0] = {"zona": 1, "min": 150, "max": 120}
        with pytest.raises(ValueError):
            _validar_zonas(d)

    def test_fora_da_faixa_60_230_falha(self):
        d = self._zonas_validas()
        d["zonas"][4] = {"zona": 5, "min": 178, "max": 999}
        with pytest.raises(ValueError):
            _validar_zonas(d)

    def test_zona_sobrepoe_anterior_falha(self):
        d = self._zonas_validas()
        # zona 2 começa antes do fim da zona 1 (140)
        d["zonas"][1] = {"zona": 2, "min": 130, "max": 155}
        with pytest.raises(ValueError):
            _validar_zonas(d)

    def test_fc_max_default_do_ultimo_max(self):
        d = self._zonas_validas()
        d["fc_max"] = ""  # vazio → assume max da Z5
        out = _validar_zonas(d)
        assert out["fc_max"] == 190

    def test_min_max_nao_inteiro_falha(self):
        d = self._zonas_validas()
        d["zonas"][0] = {"zona": 1, "min": "abc", "max": 140}
        with pytest.raises(ValueError):
            _validar_zonas(d)

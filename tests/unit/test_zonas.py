"""Testes de user_service.derivar_zonas e hashing de senha (lógica pura)."""
import pytest

from app.services.user_service import derivar_zonas, hash_senha, verificar_senha


class TestDerivarZonas:
    def test_estrutura_retornada(self):
        z = derivar_zonas(190)
        assert z["fc_max"] == 190
        assert z["limiar"] is None
        assert len(z["zonas"]) == 5
        assert [x["zona"] for x in z["zonas"]] == [1, 2, 3, 4, 5]

    def test_limiar_propagado(self):
        z = derivar_zonas(190, 170)
        assert z["limiar"] == 170

    def test_z5_max_e_exatamente_fc_max(self):
        # Evita erro de arredondamento: Z5.max deve bater com fc_max.
        for fc in (180, 185, 190, 195, 201):
            z = derivar_zonas(fc)
            assert z["zonas"][-1]["max"] == fc

    def test_zonas_sao_crescentes_e_contiguas(self):
        z = derivar_zonas(190)
        zonas = z["zonas"]
        for i in range(len(zonas)):
            assert zonas[i]["min"] < zonas[i]["max"]
            if i > 0:
                # cada zona começa onde a anterior está perto de terminar
                assert zonas[i]["min"] >= zonas[i - 1]["min"]

    def test_valores_conhecidos_fc190(self):
        # Z1: 64-76% de 190 = 122-144 (round)
        z = derivar_zonas(190)
        z1 = z["zonas"][0]
        assert z1["min"] == round(190 * 0.64)
        assert z1["max"] == round(190 * 0.76)


class TestHashSenha:
    def test_roundtrip(self):
        h = hash_senha("segredo123")
        assert h != "segredo123"  # não armazena em texto plano
        assert verificar_senha("segredo123", h) is True

    def test_senha_errada_falha(self):
        h = hash_senha("segredo123")
        assert verificar_senha("outra", h) is False

    def test_hashes_diferentes_para_mesma_senha(self):
        # bcrypt usa salt aleatório → hashes distintos
        assert hash_senha("x") != hash_senha("x")

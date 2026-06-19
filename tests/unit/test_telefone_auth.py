"""Testes de normalização de telefone e tokens de sessão (main.py)."""
import time

import pytest

import main


class TestNormalizarTelefone:
    @pytest.mark.parametrize("entrada,esperado", [
        ("+55 51 99999-9999", "+5551999999999"),
        ("5551999999999", "+5551999999999"),
        ("+5551999999999", "+5551999999999"),
        ("(51) 99999-9999", "+51999999999"),  # 11 dígitos, sem DDI
        ("  +55 (51) 9.9999-9999 ", "+5551999999999"),
    ])
    def test_formatos_aceitos(self, entrada, esperado):
        assert main._normalizar_telefone(entrada) == esperado

    def test_sempre_comeca_com_mais(self):
        assert main._normalizar_telefone("51999998888").startswith("+")

    def test_remove_todos_nao_digitos(self):
        assert main._normalizar_telefone("+55-51-9999") == "+55519999"


class TestTokensSessao:
    def test_roundtrip_valido(self):
        token = main._gerar_token("user123", ttl=3600)
        uid, ttl = main._token_valido(token)
        assert uid == "user123"
        assert ttl == 3600

    def test_ttl_padrao_quando_none(self):
        token = main._gerar_token("u1")
        uid, ttl = main._token_valido(token)
        assert uid == "u1"
        assert ttl == main.settings.PORTAL_SESSAO_MIN * 60

    def test_assinatura_adulterada_invalida(self):
        token = main._gerar_token("user123", ttl=3600)
        adulterado = token[:-4] + "0000"
        assert main._token_valido(adulterado) == (None, None)

    def test_user_id_trocado_invalida(self):
        # trocar o user_id sem reassinar invalida (sig não confere)
        _, ts, ttl, sig = main._gerar_token("user123", ttl=3600).split(".")
        forjado = f"hacker.{ts}.{ttl}.{sig}"
        assert main._token_valido(forjado) == (None, None)

    def test_formato_invalido(self):
        assert main._token_valido("lixo") == (None, None)
        assert main._token_valido("a.b") == (None, None)
        assert main._token_valido("") == (None, None)

    def test_token_expirado(self):
        # ts no passado além do ttl → inválido, mesmo com assinatura correta
        ts = int(time.time()) - 7200
        ttl = 3600
        sig = main._assinar("user123", ts, ttl)
        expirado = f"user123.{ts}.{ttl}.{sig}"
        assert main._token_valido(expirado) == (None, None)

    def test_token_legado_3_partes(self):
        # formato antigo sem ttl, ainda aceito
        ts = int(time.time())
        sig = main._assinar_legado("user123", ts)
        legado = f"user123.{ts}.{sig}"
        uid, ttl = main._token_valido(legado)
        assert uid == "user123"
        assert ttl == main.settings.PORTAL_SESSAO_MIN * 60

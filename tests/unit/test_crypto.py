"""Testes de cifragem simétrica (crypto_service)."""
import pytest

from app.services import crypto_service


class TestCifrarDecifrar:
    def test_roundtrip(self):
        token = crypto_service.cifrar("minha-senha-garmin")
        assert token != "minha-senha-garmin"  # cifrado, não em texto plano
        assert crypto_service.decifrar(token) == "minha-senha-garmin"

    def test_texto_vazio_cifra_vazio(self):
        assert crypto_service.cifrar("") == ""
        assert crypto_service.cifrar(None) == ""

    def test_token_vazio_decifra_vazio(self):
        assert crypto_service.decifrar("") == ""
        assert crypto_service.decifrar(None) == ""

    def test_token_invalido_retorna_vazio(self):
        # token corrompido → "" (não lança), com log de aviso
        assert crypto_service.decifrar("nao-eh-um-token-fernet") == ""

    def test_cifragens_diferentes_mesmo_texto(self):
        # Fernet embute timestamp/IV → tokens distintos, ambos decifram igual
        a = crypto_service.cifrar("x")
        b = crypto_service.cifrar("x")
        assert a != b
        assert crypto_service.decifrar(a) == crypto_service.decifrar(b) == "x"

    def test_unicode(self):
        original = "café ☕ açaí 🚵"
        assert crypto_service.decifrar(crypto_service.cifrar(original)) == original

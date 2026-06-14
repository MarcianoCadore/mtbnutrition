"""Serviço de criptografia simétrica para segredos armazenados no banco.

Usa Fernet (AES-128-CBC + HMAC-SHA256) da biblioteca `cryptography`.

Configuração da chave:
- Se `settings.FERNET_KEY` estiver definido (base64 urlsafe, 32 bytes), usa-o.
- Caso contrário, deriva uma chave determinística de `settings.SECRET_KEY`
  (ou do fallback "dev-secret-mtb") via SHA-256. Útil em dev sem configuração extra.

ATENÇÃO: mudar a chave invalida todos os segredos já cifrados no banco.
Para rotacionar a chave é necessário descriptografar com a chave antiga e
re-cifrar com a nova antes de trocar o valor de FERNET_KEY.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from config.settings import settings

logger = logging.getLogger(__name__)

_fernet_instance: Fernet | None = None


def _fernet() -> Fernet:
    """Retorna (e inicializa se necessário) o objeto Fernet singleton."""
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance

    if settings.FERNET_KEY:
        # Chave fornecida explicitamente em produção
        chave = settings.FERNET_KEY.encode()
    else:
        # Deriva chave determinística de SECRET_KEY (modo dev/staging).
        # Nunca use em produção sem definir FERNET_KEY.
        secret_raw = (
            settings.SECRET_KEY
            or settings.PORTAL_PASSWORD
            or "dev-secret-mtb"
        )
        digest = hashlib.sha256(secret_raw.encode()).digest()
        chave = base64.urlsafe_b64encode(digest)

    _fernet_instance = Fernet(chave)
    return _fernet_instance


def cifrar(texto: str) -> str:
    """Cifra `texto` e retorna o token Fernet como string.

    Retorna "" se o texto for vazio ou None.
    """
    if not texto:
        return ""
    return _fernet().encrypt(texto.encode()).decode()


def decifrar(token: str) -> str:
    """Decifra um token Fernet e retorna o texto original.

    Retorna "" se o token for vazio, None ou inválido (log de aviso em caso
    de falha de descriptografia — possível chave trocada ou dado corrompido).
    """
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        logger.warning(
            "crypto_service.decifrar: token inválido — chave trocada ou dado corrompido"
        )
        return ""
    except Exception as e:
        logger.error("crypto_service.decifrar: erro inesperado — %s", e)
        return ""

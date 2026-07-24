from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from .config import settings


class CredentialError(RuntimeError):
    pass


def _fernet() -> Fernet:
    if len(settings.credential_secret) < 32:
        raise CredentialError(
            "Define AHG_CREDENTIAL_SECRET con un valor aleatorio de al menos 32 caracteres."
        )
    digest = hashlib.sha256(settings.credential_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise CredentialError("No se pudo descifrar la credencial fiscal almacenada.") from exc


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "********"
    return f"{value[:4]}...{value[-4:]}"

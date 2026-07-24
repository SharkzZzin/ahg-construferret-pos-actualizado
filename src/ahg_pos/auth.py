from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from typing import Any


SESSION_COOKIE = "ahg_session"
SESSION_TTL_HOURS = 12
PASSWORD_KEY_LENGTH = 64


@dataclass(frozen=True)
class AuthUser:
    id: int
    name: str
    email: str
    phone: str
    role: str

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
        }


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=PASSWORD_KEY_LENGTH,
    )
    return f"scrypt${salt.hex()}${key.hex()}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    try:
        algorithm, salt_hex, key_hex = stored_hash.split("$", 2)
        if algorithm != "scrypt":
            return False
        expected = bytes.fromhex(key_hex)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=2**14,
            r=8,
            p=1,
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def normalize_identifier(value: str) -> str:
    return value.strip().lower()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(48)


def session_expiration() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)).isoformat(timespec="seconds")


def parse_cookie_token(cookie_header: str | None) -> str:
    if not cookie_header:
        return ""
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    morsel = cookie.get(SESSION_COOKIE)
    return morsel.value if morsel else ""


def session_cookie(token: str, secure: bool = False) -> str:
    attributes = [
        f"{SESSION_COOKIE}={token}",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
        f"Max-Age={SESSION_TTL_HOURS * 3600}",
    ]
    if secure:
        attributes.append("Secure")
    return "; ".join(attributes)


def clear_session_cookie(secure: bool = False) -> str:
    attributes = [
        f"{SESSION_COOKIE}=",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
        "Max-Age=0",
    ]
    if secure:
        attributes.append("Secure")
    return "; ".join(attributes)


def initial_admin_credentials() -> tuple[str, str, str, str]:
    return (
        os.getenv("AHG_ADMIN_NAME", "Administrador AHG").strip(),
        os.getenv("AHG_ADMIN_EMAIL", "admin@ahg.local").strip().lower(),
        "".join(ch for ch in os.getenv("AHG_ADMIN_PHONE", "8090000000") if ch.isdigit()),
        os.getenv("AHG_ADMIN_PASSWORD", "Cambiar123!"),
    )

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

ALL_MODULES = (
    "sale",
    "products",
    "clients",
    "suppliers",
    "preinvoices",
    "assistant",
    "inventory",
    "fiscal",
    "reports",
    "cash",
    "audit",
    "admin",
)

ROLE_DEFAULT_MODULES = {
    "admin": ALL_MODULES,
    "gerente": tuple(module for module in ALL_MODULES if module != "admin"),
    "cajero": ("sale", "clients", "preinvoices", "reports", "cash"),
    "vendedor": ("sale", "clients", "preinvoices", "assistant", "reports"),
    "almacen": ("products", "suppliers", "inventory"),
}


def normalize_user_modules(value: Any, role: str) -> tuple[str, ...]:
    if value is None or value == "":
        return tuple(ROLE_DEFAULT_MODULES.get(role, ()))
    if isinstance(value, str):
        try:
            import json

            value = json.loads(value)
        except (TypeError, ValueError):
            value = []
    selected = set(value if isinstance(value, (list, tuple, set)) else [])
    modules = tuple(module for module in ALL_MODULES if module in selected)
    return ALL_MODULES if role == "admin" else modules


@dataclass(frozen=True)
class AuthUser:
    id: int
    name: str
    email: str
    phone: str
    role: str
    modules: tuple[str, ...] = ()

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "modules": list(self.modules),
        }

    def can_access(self, module: str) -> bool:
        return module in self.modules


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


def initial_admin_credentials(allow_defaults: bool = True) -> tuple[str, str, str, str]:
    configured_password = os.getenv("AHG_ADMIN_PASSWORD", "")
    configured_email = os.getenv("AHG_ADMIN_EMAIL", "")
    if not allow_defaults and (not configured_password or not configured_email):
        raise ValueError(
            "Una base PostgreSQL nueva requiere AHG_ADMIN_EMAIL y AHG_ADMIN_PASSWORD."
        )
    return (
        os.getenv("AHG_ADMIN_NAME", "Administrador AHG").strip(),
        (configured_email or "admin@ahg.local").strip().lower(),
        "".join(ch for ch in os.getenv("AHG_ADMIN_PHONE", "8090000000") if ch.isdigit()),
        configured_password or "Cambiar123!",
    )

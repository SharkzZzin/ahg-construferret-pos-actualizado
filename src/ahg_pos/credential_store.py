"""Persistencia local de la clave maestra usando DPAPI en Windows."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

_STORE_NAME = "credential_secret.dpapi"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _protect(value: str) -> bytes:
    if sys.platform != "win32":
        return b""
    raw = value.encode("utf-8")
    source = ctypes.create_string_buffer(raw)
    source_blob = _Blob(len(raw), ctypes.cast(source, ctypes.POINTER(ctypes.c_char)))
    result_blob = _Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source_blob), "AHG POS credential secret", None, None, None, 0, ctypes.byref(result_blob)):
        raise OSError("Windows no pudo proteger la clave local.")
    try:
        return ctypes.string_at(result_blob.pbData, result_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(result_blob.pbData)


def _unprotect(value: bytes) -> str:
    if sys.platform != "win32":
        return ""
    source = ctypes.create_string_buffer(value)
    source_blob = _Blob(len(value), ctypes.cast(source, ctypes.POINTER(ctypes.c_char)))
    result_blob = _Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source_blob), None, None, None, None, 0, ctypes.byref(result_blob)):
        return ""
    try:
        return ctypes.string_at(result_blob.pbData, result_blob.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(result_blob.pbData)


def save_credential_secret(secret: str, data_dir: Path) -> bool:
    """Guarda la clave cifrada y vinculada al usuario actual de Windows."""
    if not secret.strip() or sys.platform != "win32":
        return False
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / _STORE_NAME
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(_protect(secret.strip()))
    os.replace(temporary, target)
    return True


def load_credential_secret(data_dir: Path) -> str:
    """Recupera la clave solo para el usuario de Windows que la guardó."""
    if sys.platform != "win32":
        return ""
    try:
        return _unprotect((data_dir / _STORE_NAME).read_bytes()).strip()
    except (OSError, ValueError):
        return ""

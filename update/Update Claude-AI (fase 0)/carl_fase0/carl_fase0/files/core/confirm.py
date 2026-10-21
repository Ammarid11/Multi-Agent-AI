# core/confirm.py
"""Konfirmasi dua langkah untuk aksi destruktif: aksi ditahan, pengguna mengetik /confirm <kode>."""
import secrets
import threading
import time
from typing import Any, Dict, Optional

TTL_SECONDS = 180
_MAX_PENDING = 20
_pending: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def _prune(now: float) -> None:
    for code in [c for c, item in _pending.items() if item["expires"] < now]:
        del _pending[code]
    while len(_pending) > _MAX_PENDING:
        oldest = min(_pending, key=lambda c: _pending[c]["expires"])
        del _pending[oldest]


def request_confirmation(kind: str, payload: Dict[str, Any], description: str) -> str:
    now = time.time()
    with _lock:
        _prune(now)
        code = secrets.token_hex(3)
        _pending[code] = {"kind": kind, "payload": payload, "description": description, "expires": now + TTL_SECONDS}
    return code


def consume(code: str) -> Optional[Dict[str, Any]]:
    """Ambil dan hapus aksi tertunda (sekali pakai). None jika kode salah/kedaluwarsa."""
    now = time.time()
    with _lock:
        _prune(now)
        return _pending.pop(code.strip().lower(), None)


def confirmation_hint(code: str) -> str:
    return f"Ketik `/confirm {code}` dalam {TTL_SECONDS // 60} menit untuk melanjutkan, atau abaikan untuk membatalkan."

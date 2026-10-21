# core/privacy.py
"""Kebijakan privasi & izin: perintah sensitif tidak boleh masuk riwayat, dan daftar izin untuk perangkat remote."""

SENSITIVE_COMMANDS = ("/unlock", "/lock", "/secure", "/reveal", "/brankas")

# Perangkat non-lokal hanya boleh: tanya-jawab/baca/riset web. Selebihnya ditolak.
REMOTE_ALLOWED_COMMANDS = {
    "/help", "/menu", "/bantuan", "/new", "/reset", "/clear",
    "/web", "/search", "/browsing", "/googling",
    "/read", "/baca", "/think", "/analisis", "/evaluasi",
    "/sintesis", "/connect", "/briefing", "/morning", "/fokus",
    "/rules", "/aturan-aktif",
}
REMOTE_ALLOWED_INTENTS = {"default", "think", "web", "sintesis"}


def _first_token(prompt: str) -> str:
    parts = (prompt or "").strip().lower().split(None, 1)
    return parts[0] if parts else ""


def is_sensitive(prompt: str) -> bool:
    """True bila pesan adalah perintah brankas (isi/hasilnya tidak boleh disimpan di riwayat, ringkasan, atau log)."""
    return _first_token(prompt) in SENSITIVE_COMMANDS


def mask_for_log(prompt: str) -> str:
    return f"{_first_token(prompt)} ****" if is_sensitive(prompt) else prompt


def command_allowed_for_remote(prompt: str) -> bool:
    token = _first_token(prompt)
    if not token.startswith("/"):
        return True
    return token in REMOTE_ALLOWED_COMMANDS


def intent_allowed_for_remote(intent: str) -> bool:
    return intent in REMOTE_ALLOWED_INTENTS

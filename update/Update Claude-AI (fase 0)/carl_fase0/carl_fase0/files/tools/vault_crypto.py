# tools/vault_crypto.py
"""
Frontier L: Zero-Knowledge Encrypted Vault Partition (v2).
- KDF: scrypt dengan salt ACAK per berkas
- Cipher: AES-256-GCM (autentikasi bawaan)
- Verifier passphrase: berkas 04-Secure/.carl_verifier.json (passphrase salah ditolak saat /unlock)
- Sesi di RAM saja, terkunci otomatis setelah idle (config.VAULT_UNLOCK_IDLE_SECONDS)
- Format v1 (Fernet + salt tetap) masih bisa DIBACA; simpan ulang dengan /secure untuk migrasi.
"""

import base64
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

import config
from core import vault_io

LEGACY_SALT = b"Carl-Level5-Vault-ZeroKnowledge-2026"   # hanya untuk membaca berkas v1
MIN_PASSPHRASE = 8
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 1
_AAD = b"carl-vault-v2"
_VERIFY_PLAINTEXT = b"carl-vault-ok"
VERIFIER_NAME = ".carl_verifier.json"

_state_lock = threading.Lock()
_active_passphrase: Optional[str] = None
_last_activity: float = 0.0


# ── KDF & AEAD ──────────────────────────────────────────────────────────────
def _scrypt_key(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(passphrase.encode("utf-8"))


def encrypt_blob(passphrase: str, plaintext: bytes) -> str:
    salt, nonce = os.urandom(16), os.urandom(12)
    ciphertext = AESGCM(_scrypt_key(passphrase, salt)).encrypt(nonce, plaintext, _AAD)
    return "v2:" + base64.urlsafe_b64encode(salt + nonce + ciphertext).decode("ascii")


def decrypt_blob(passphrase: str, token: str) -> bytes:
    raw = base64.urlsafe_b64decode(token[3:].encode("ascii"))
    salt, nonce, ciphertext = raw[:16], raw[16:28], raw[28:]
    return AESGCM(_scrypt_key(passphrase, salt)).decrypt(nonce, ciphertext, _AAD)


def _legacy_decrypt(passphrase: str, token: str) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=LEGACY_SALT, iterations=100_000)
    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
    return Fernet(key).decrypt(token.encode("utf-8"))


def _decrypt_any(passphrase: str, token: str) -> bytes:
    token = token.strip()
    return decrypt_blob(passphrase, token) if token.startswith("v2:") else _legacy_decrypt(passphrase, token)


# ── Sesi ────────────────────────────────────────────────────────────────────
def _expire_if_idle() -> None:
    global _active_passphrase
    with _state_lock:
        if _active_passphrase is not None and time.time() - _last_activity > config.VAULT_UNLOCK_IDLE_SECONDS:
            _active_passphrase = None


def _touch() -> None:
    global _last_activity
    with _state_lock:
        _last_activity = time.time()


def is_session_unlocked() -> bool:
    _expire_if_idle()
    return _active_passphrase is not None


def lock_session() -> Dict[str, Any]:
    global _active_passphrase
    with _state_lock:
        _active_passphrase = None
    return {"success": True, "message": "🔒 Brankas terkunci kembali. Seluruh catatan rahasia terlindungi aman."}


def _secure_dir(vault_path: str = None) -> Path:
    return Path(vault_path or config.VAULT_PATH) / "04-Secure"


def _verifier_path(vault_path: str = None) -> Path:
    return _secure_dir(vault_path) / VERIFIER_NAME


def list_secure_notes(vault_path: str = None) -> List[str]:
    directory = _secure_dir(vault_path)
    return [f.name for f in directory.glob("*.enc.md")] if directory.exists() else []


def _extract_ciphertext(text: str) -> Optional[str]:
    match = re.search(r"```encrypted-carl-vault\s*\n(.*?)\n```", text, re.DOTALL)
    return match.group(1).strip() if match else None


def _write_verifier(passphrase: str, vault_path: str = None) -> None:
    path = _verifier_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"v": 2, "data": encrypt_blob(passphrase, _VERIFY_PLAINTEXT)}), encoding="utf-8")


def _verify_passphrase(passphrase: str, vault_path: str = None) -> Optional[bool]:
    """True/False bila ada pembanding (verifier atau catatan lama); None bila brankas masih kosong."""
    path = _verifier_path(vault_path)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))["data"]
            return decrypt_blob(passphrase, data) == _VERIFY_PLAINTEXT
        except Exception:
            return False
    for name in list_secure_notes(vault_path):
        token = _extract_ciphertext((_secure_dir(vault_path) / name).read_text(encoding="utf-8", errors="replace"))
        if token:
            try:
                _decrypt_any(passphrase, token)
                return True
            except Exception:
                return False
    return None


def unlock_session(passphrase: str) -> Dict[str, Any]:
    global _active_passphrase
    if not passphrase:
        return {"success": False, "error": "Passphrase tidak boleh kosong."}
    verdict = _verify_passphrase(passphrase)
    if verdict is False:
        return {"success": False, "error": "Passphrase salah."}
    if verdict is None and len(passphrase) < MIN_PASSPHRASE:     # aturan panjang hanya untuk passphrase baru
        return {"success": False, "error": f"Passphrase baru minimal {MIN_PASSPHRASE} karakter."}
    created = False
    if verdict is None or not _verifier_path().exists():
        _write_verifier(passphrase)
        created = True
    with _state_lock:
        _active_passphrase = passphrase
    _touch()
    note = " Passphrase baru ditetapkan untuk brankas ini; **jangan sampai lupa, tidak bisa dipulihkan**." if created and verdict is None else ""
    minutes = config.VAULT_UNLOCK_IDLE_SECONDS // 60
    return {"success": True, "message": f"🔓 Brankas dibuka (terkunci otomatis setelah {minutes} menit tanpa aktivitas).{note}"}


# ── Simpan & baca catatan ───────────────────────────────────────────────────
def save_encrypted_note(title: str, content: str, passphrase: Optional[str] = None, vault_path: str = None) -> Dict[str, Any]:
    _expire_if_idle()
    effective = passphrase or _active_passphrase
    if not effective:
        return {"success": False, "error": "Brankas terkunci! Harap buka sesi terlebih dahulu dengan: `/unlock <passphrase>`"}
    if passphrase and _verify_passphrase(passphrase, vault_path) is False:
        return {"success": False, "error": "Passphrase salah."}

    token = encrypt_blob(effective, content.encode("utf-8"))
    clean_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()[:80] or "Catatan Rahasia"
    filename = f"{clean_title}.enc.md"
    file_path = _secure_dir(vault_path) / filename

    import datetime
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    envelope = (
        "---\n"
        f"title: {json.dumps(clean_title + ' (Encrypted)', ensure_ascii=False)}\n"
        "type: zero-knowledge-vault\n"
        "cipher: AES-256-GCM\n"
        "kdf: scrypt\n"
        f'encrypted_at: "{now_str}"\n'
        'tags: ["brankas", "rahasia", "encrypted"]\n'
        "---\n\n"
        f"# 🔐 Catatan Terenkripsi: {clean_title}\n"
        "> ⚠️ Terenkripsi AES-256-GCM. Hanya dapat dibaca melalui Carl dengan passphrase yang sah.\n\n"
        f"```encrypted-carl-vault\n{token}\n```\n"
    )
    try:
        vault_io.atomic_write(file_path, envelope)
        _touch()
        return {"success": True, "title": clean_title, "filename": filename, "file_path": str(file_path), "encrypted_at": now_str}
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_encrypted_note(filename_or_title: str, passphrase: Optional[str] = None, vault_path: str = None) -> Dict[str, Any]:
    _expire_if_idle()
    effective = passphrase or _active_passphrase
    if not effective:
        return {"success": False, "error": "Brankas terkunci! Harap buka sesi terlebih dahulu dengan: `/unlock <passphrase>`"}

    secure_dir = _secure_dir(vault_path)
    clean = filename_or_title.strip()
    target_file = None
    for candidate in (clean, f"{clean}.enc.md", f"{clean}.md"):
        if "/" not in candidate and "\\" not in candidate and (secure_dir / candidate).is_file():
            target_file = secure_dir / candidate
            break
    if target_file is None and secure_dir.exists():
        for f in secure_dir.glob("*.enc.md"):
            if clean.lower() and clean.lower() in f.stem.lower():
                target_file = f
                break
    if not target_file:
        return {"success": False, "error": f"Catatan terenkripsi '{filename_or_title}' tidak ditemukan di 04-Secure/."}

    token = _extract_ciphertext(target_file.read_text(encoding="utf-8", errors="replace"))
    if not token:
        return {"success": False, "error": "Format amplop ciphertext tidak valid."}
    try:
        plaintext = _decrypt_any(effective, token).decode("utf-8")
    except (InvalidToken, Exception):
        return {"success": False, "error": "❌ Passphrase salah atau berkas rusak. Gagal mendekripsi."}
    _touch()
    return {
        "success": True,
        "title": target_file.name.replace(".enc.md", ""),
        "filename": target_file.name,
        "plaintext": plaintext,
        "legacy_format": not token.startswith("v2:"),
    }


def run_crypto_command(command_str: str) -> str:
    """/unlock <pass> · /lock · /secure <judul> | <isi> · /reveal <judul> · (status)"""
    cmd = command_str.strip()
    p_lower = cmd.lower()

    if p_lower.startswith(("unlock ", "/unlock ")):
        parts = cmd.split(maxsplit=1)
        res = unlock_session(parts[1].strip() if len(parts) > 1 else "")
        return res["message"] if res["success"] else f"❌ {res['error']}"

    if p_lower in ("lock", "/lock", "kunci", "/kunci"):
        return lock_session()["message"]

    if p_lower.startswith(("secure ", "/secure ")):
        raw = cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else ""
        if "|" not in raw:
            return "⚠️ Format salah. Gunakan: `/secure <judul_catatan> | <isi_rahasia>`"
        title, content = (part.strip() for part in raw.split("|", 1))
        res = save_encrypted_note(title, content)
        if res["success"]:
            return (
                "🔐 **[Zero-Knowledge Encrypted Vault]**\n"
                "Catatan rahasia dienkripsi AES-256-GCM dan disimpan:\n"
                f"- **Berkas:** `04-Secure/{res['filename']}`\n"
                f"- **Waktu Enkripsi:** {res['encrypted_at']}\n"
                "💡 *Pesan ini dan isinya tidak disimpan di riwayat obrolan.*"
            )
        return f"❌ {res.get('error')}"

    if p_lower.startswith(("reveal ", "/reveal ")):
        target = cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else ""
        res = read_encrypted_note(target)
        if res["success"]:
            legacy = "\n\n⚠️ *Berkas ini memakai format enkripsi lama; simpan ulang dengan `/secure` untuk migrasi.*" if res.get("legacy_format") else ""
            return (
                f"🔓 **[Dekripsi Berhasil: {res['title']}]**\n\n{res['plaintext']}{legacy}\n\n"
                "--- \n🔒 *Ketik `/lock` jika sudah selesai.*"
            )
        return f"❌ {res.get('error')}"

    status = "🔓 Terbuka (Sesi Aktif)" if is_session_unlocked() else "🔒 Terkunci (Zero-Knowledge)"
    notes = list_secure_notes()
    lines = [
        "🔐 **[Frontier L: Zero-Knowledge Encrypted Vault Partition]**",
        f"- **Status Brankas Sesi:** {status}",
        f"- **Jumlah Catatan Terenkripsi:** {len(notes)} berkas di `04-Secure/`\n",
        "**Perintah Brankas:**",
        f"• `/unlock <passphrase>` : Buka sesi (min. {MIN_PASSPHRASE} karakter)",
        "• `/lock` : Kunci brankas & bersihkan memori RAM",
        "• `/secure <judul> | <isi>` : Simpan catatan terenkripsi",
        "• `/reveal <judul>` : Buka dan baca catatan rahasia",
    ]
    if notes:
        lines.append("\n📁 **Daftar Berkas Terenkripsi:**")
        lines.extend(f"- `{n}`" for n in notes)
    return "\n".join(lines)

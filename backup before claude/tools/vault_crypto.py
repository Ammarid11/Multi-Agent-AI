# tools/vault_crypto.py
"""
Frontier L: Zero-Knowledge Encrypted Vault Partition
Menyediakan brankas catatan terenkripsi AES-256 (PBKDF2-HMAC-SHA256 + Fernet).
Catatan rahasia/sensitif disimpan dalam format terenkripsi di folder 04-Secure/
dan hanya dapat dibaca/ditulis jika pengguna memasukkan Session Passphrase.
"""

import os
import re
import base64
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import config

# SALT tetap untuk derivasi kunci vault lokal
VAULT_SALT = b"Carl-Level5-Vault-ZeroKnowledge-2026"

# Status sesi brankas di memori RAM (Zero-Knowledge: tidak pernah ditulis ke disk)
_active_passphrase: Optional[str] = None


def _derive_fernet_key(passphrase: str) -> bytes:
    """Menurunkan kunci enkripsi 32-byte Fernet dari passphrase menggunakan PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=VAULT_SALT,
        iterations=100_000,
    )
    key = kdf.derive(passphrase.encode("utf-8"))
    return base64.urlsafe_b64encode(key)


def unlock_session(passphrase: str) -> Dict[str, Any]:
    """Membuka sesi brankas terenkripsi menggunakan passphrase pengguna."""
    global _active_passphrase
    if not passphrase or len(passphrase) < 4:
        return {"success": False, "error": "Passphrase minimal harus 4 karakter."}
    _active_passphrase = passphrase
    return {"success": True, "message": "🔓 Brankas sesi berhasil dibuka! Anda dapat membaca dan menyimpan catatan rahasia."}


def lock_session() -> Dict[str, Any]:
    """Mengunci kembali brankas dan menghapus passphrase dari RAM."""
    global _active_passphrase
    _active_passphrase = None
    return {"success": True, "message": "🔒 Brankas terkunci kembali. Seluruh catatan rahasia terlindungi aman."}


def is_session_unlocked() -> bool:
    """Memeriksa apakah sesi brankas saat ini terbuka."""
    global _active_passphrase
    return _active_passphrase is not None


def save_encrypted_note(
    title: str,
    content: str,
    passphrase: Optional[str] = None,
    vault_path: str = config.VAULT_PATH
) -> Dict[str, Any]:
    """
    Mengenkripsi konten dengan AES-256 dan menyimpannya ke 04-Secure/ di Obsidian Vault.
    """
    effective_pass = passphrase or _active_passphrase
    if not effective_pass:
        return {
            "success": False,
            "error": "Brankas terkunci! Harap buka sesi terlebih dahulu dengan: `/unlock <passphrase>`"
        }

    key = _derive_fernet_key(effective_pass)
    fernet = Fernet(key)

    # Enkripsi konten
    ciphertext = fernet.encrypt(content.encode("utf-8")).decode("utf-8")

    vault = Path(vault_path)
    secure_dir = vault / "04-Secure"
    secure_dir.mkdir(parents=True, exist_ok=True)

    clean_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip() or "Catatan Rahasia"
    filename = f"{clean_title}.enc.md"
    file_path = secure_dir / filename

    import datetime
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    envelope = f"""---
title: "{clean_title} (Encrypted)"
type: zero-knowledge-vault
cipher: AES-256-Fernet
encrypted_at: "{now_str}"
tags: ["brankas", "rahasia", "encrypted"]
---

# 🔐 Catatan Terenkripsi: {clean_title}
> ⚠️ **PERINGATAN:** Catatan ini terenkripsi AES-256 militer. Hanya dapat dibaca melalui Carl dengan passphrase yang sah.

```encrypted-carl-vault
{ciphertext}
```
"""

    try:
        file_path.write_text(envelope, encoding="utf-8")
        return {
            "success": True,
            "title": clean_title,
            "filename": filename,
            "file_path": str(file_path),
            "encrypted_at": now_str
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_encrypted_note(
    filename_or_title: str,
    passphrase: Optional[str] = None,
    vault_path: str = config.VAULT_PATH
) -> Dict[str, Any]:
    """Mendekripsi dan membaca catatan dari 04-Secure/ jika passphrase cocok."""
    effective_pass = passphrase or _active_passphrase
    if not effective_pass:
        return {
            "success": False,
            "error": "Brankas terkunci! Harap buka sesi terlebih dahulu dengan: `/unlock <passphrase>`"
        }

    vault = Path(vault_path)
    secure_dir = vault / "04-Secure"

    # Cari file
    clean = filename_or_title.strip()
    target_file = None
    if (secure_dir / clean).exists():
        target_file = secure_dir / clean
    elif (secure_dir / f"{clean}.enc.md").exists():
        target_file = secure_dir / f"{clean}.enc.md"
    elif (secure_dir / f"{clean}.md").exists():
        target_file = secure_dir / f"{clean}.md"
    else:
        # Cari fuzzy
        for f in secure_dir.glob("*.enc.md"):
            if clean.lower() in f.stem.lower():
                target_file = f
                break

    if not target_file or not target_file.exists():
        return {"success": False, "error": f"Catatan terenkripsi '{filename_or_title}' tidak ditemukan di 04-Secure/."}

    text = target_file.read_text(encoding="utf-8", errors="replace")

    # Ekstrak ciphertext dari code block
    m = re.search(r"```encrypted-carl-vault\s*\n(.*?)\n```", text, re.DOTALL)
    if not m:
        return {"success": False, "error": "Format amplop ciphertext tidak valid."}

    ciphertext = m.group(1).strip()
    key = _derive_fernet_key(effective_pass)
    fernet = Fernet(key)

    try:
        decrypted_bytes = fernet.decrypt(ciphertext.encode("utf-8"))
        plaintext = decrypted_bytes.decode("utf-8")
        return {
            "success": True,
            "title": target_file.name.replace(".enc.md", ""),
            "filename": target_file.name,
            "plaintext": plaintext
        }
    except Exception:
        return {
            "success": False,
            "error": "❌ Passphrase salah! Gagal mendekripsi berkas ini."
        }


def list_secure_notes(vault_path: str = config.VAULT_PATH) -> List[str]:
    """Mendaftar semua berkas terenkripsi di folder 04-Secure/."""
    vault = Path(vault_path)
    secure_dir = vault / "04-Secure"
    if not secure_dir.exists():
        return []
    return [f.name for f in secure_dir.glob("*.enc.md")]


def run_crypto_command(command_str: str) -> str:
    """
    Menangani perintah brankas:
    - /unlock <passphrase>
    - /lock
    - /secure <judul> | <isi>
    - /reveal <judul>
    - /vault-status
    """
    cmd = command_str.strip()
    p_lower = cmd.lower()

    if p_lower.startswith("unlock ") or p_lower.startswith("/unlock "):
        parts = cmd.split(maxsplit=1)
        passphrase = parts[1].strip() if len(parts) > 1 else ""
        res = unlock_session(passphrase)
        return res["message"] if res["success"] else f"❌ {res['error']}"

    if p_lower in ("lock", "/lock", "kunci"):
        res = lock_session()
        return res["message"]

    if p_lower.startswith("secure ") or p_lower.startswith("/secure "):
        raw = cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else ""
        if "|" not in raw:
            return "⚠️ Format salah. Gunakan: `/secure <judul_catatan> | <isi_rahasia>`"
        parts = raw.split("|", 1)
        title = parts[0].strip()
        content = parts[1].strip()
        res = save_encrypted_note(title, content)
        if res["success"]:
            return (
                f"🔐 **[Zero-Knowledge Encrypted Vault]**\n"
                f"Catatan rahasia berhasil dienkripsi AES-256 dan disimpan:\n"
                f"- **Berkas:** `04-Secure/{res['filename']}`\n"
                f"- **Waktu Enkripsi:** {res['encrypted_at']}\n"
                f"💡 *Terkunci aman di harddisk! Hanya Anda yang memegang kuncinya.*"
            )
        return f"❌ {res.get('error')}"

    if p_lower.startswith("reveal ") or p_lower.startswith("/reveal "):
        target = cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else ""
        res = read_encrypted_note(target)
        if res["success"]:
            return (
                f"🔓 **[Dekripsi Berhasil: {res['title']}]**\n\n"
                f"{res['plaintext']}\n\n"
                f"--- \n🔒 *Ketik `/lock` jika sudah selesai untuk langsung menutup brankas kembali.*"
            )
        return f"❌ {res.get('error')}"

    # Default: status brankas
    status = "🔓 Terbuka (Sesi Aktif)" if is_session_unlocked() else "🔒 Terkunci (Zero-Knowledge)"
    notes = list_secure_notes()
    lines = [
        "🔐 **[Frontier L: Zero-Knowledge Encrypted Vault Partition]**",
        f"- **Status Brankas Sesi:** {status}",
        f"- **Jumlah Catatan Terenkripsi:** {len(notes)} berkas di `04-Secure/`\n",
        "**Perintah Brankas:**",
        "• `/unlock <passphrase>` : Buka sesi brankas",
        "• `/lock` : Kunci brankas & bersihkan memori RAM",
        "• `/secure <judul> | <isi>` : Simpan catatan terenkripsi AES-256",
        "• `/reveal <judul>` : Buka dan baca catatan rahasia"
    ]
    if notes:
        lines.append("\n📁 **Daftar Berkas Terenkripsi:**")
        for n in notes:
            lines.append(f"- `{n}`")
    return "\n".join(lines)


# tools/tool_delete.py
"""Hapus catatan: dua langkah (konfirmasi) dan masuk .trash (bisa dipulihkan dengan /undo), bukan penghapusan permanen."""
import os
import glob

import config
from core import vault_io
from core.confirm import request_confirmation, confirmation_hint


def _resolve_exact(filename: str):
    requested = filename.strip().replace("\\", "/")
    if not requested:
        return None, "❌ Nama file kosong. Tidak ada file yang dihapus."
    if not requested.lower().endswith(".md"):
        requested += ".md"

    vault_root = os.path.abspath(config.VAULT_PATH)
    try:
        direct_path = str(vault_io.safe_path(requested))
    except ValueError:
        return None, "❌ Path harus berada di dalam Vault. Tidak ada file yang dihapus."

    if os.path.isfile(direct_path):
        matches = [direct_path]
    elif "/" in requested:
        matches = []
    else:
        matches = glob.glob(os.path.join(vault_root, "**", os.path.basename(requested)), recursive=True)
        matches = [p for p in matches if os.path.isfile(p)]

    if not matches:
        return None, f"❌ Catatan '{filename}' tidak ditemukan. Tidak ada file yang dihapus."
    if len(matches) > 1:
        choices = [os.path.relpath(p, vault_root).replace("\\", "/") for p in sorted(matches)]
        return None, (
            "⚠️ Ada beberapa catatan dengan nama sama; tidak ada yang dihapus. "
            "Kirim ulang dengan path Vault lengkap:\n- " + "\n- ".join(choices)
        )
    if vault_io.is_blocked_path(matches[0]):
        return None, "❌ Catatan di 04-Secure tidak dapat dihapus lewat perintah ini."
    return matches[0], None


def delete_file(filename: str) -> str:
    """Langkah 1: validasi target eksak, lalu minta konfirmasi. Tidak ada yang dihapus di langkah ini."""
    path, error = _resolve_exact(filename)
    if error:
        return error
    rel = os.path.relpath(path, config.VAULT_PATH).replace("\\", "/")
    code = request_confirmation("delete", {"rel": rel}, f"Hapus catatan {rel}")
    return (
        f"⚠️ Akan menghapus `{rel}` (dipindahkan ke `.trash`, bisa dipulihkan dengan `/undo`).\n"
        f"{confirmation_hint(code)}"
    )


def delete_file_confirmed(rel: str) -> str:
    """Langkah 2 (setelah /confirm): pindahkan ke .trash."""
    path, error = _resolve_exact(rel)
    if error:
        return error
    try:
        vault_io.move_to_trash(path)
    except (OSError, ValueError) as err:
        return f"❌ Gagal menghapus file: {err}"
    return f"🗑️ Catatan '{rel}' dipindahkan ke .trash. Pulihkan dengan `/undo {os.path.basename(rel)}`."

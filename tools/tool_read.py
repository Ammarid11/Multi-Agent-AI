import os
from pathlib import Path

import config
from core import vault_io


def find_vault_file_candidates(filename: str) -> list[str]:
    """Find exact Vault path matches without choosing between duplicate basenames."""
    requested = filename.strip().replace("\\", "/")
    if not requested:
        return []
    if not requested.lower().endswith(".md"):
        requested += ".md"

    relative_path = Path(requested)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("Path harus berada di dalam Vault.")

    vault_root = Path(config.VAULT_PATH).resolve()
    if "/" in requested:
        direct_path = (vault_root / relative_path).resolve()
        try:
            common_path = os.path.commonpath([str(vault_root), str(direct_path)])
        except ValueError as error:
            raise ValueError("Path tidak valid.") from error
        if common_path != str(vault_root):
            raise ValueError("Path harus berada di dalam Vault.")
        if direct_path.is_file():
            return [direct_path.relative_to(vault_root).as_posix()]
        return []

    basename = relative_path.name.casefold()
    matches = []
    for path in vault_root.rglob("*"):
        if not path.is_file() or path.name.casefold() != basename:
            continue
        resolved_path = path.resolve()
        try:
            if os.path.commonpath([str(vault_root), str(resolved_path)]) != str(vault_root):
                continue
        except ValueError:
            continue
        matches.append(resolved_path.relative_to(vault_root).as_posix())
    return sorted(matches, key=str.casefold)


def read_file(filename: str) -> str:
    """Read a Vault note only when its requested path resolves unambiguously."""
    try:
        candidates = find_vault_file_candidates(filename)
    except ValueError as error:
        return f"❌ {error} Tidak ada file yang dibaca."
    except OSError as error:
        return f"❌ Gagal mencari file di Vault: {error}"

    if not candidates:
        return f"❌ Catatan '{filename}' tidak ditemukan di Vault Obsidian!"
    if len(candidates) > 1:
        return (
            f"⚠️ Ada beberapa file bernama sama dengan '{Path(filename).name}'. "
            "Saya belum membaca file mana pun. Pilih satu dengan mengirim path Vault lengkap:\n- "
            + "\n- ".join(candidates)
        )

    vault_root = Path(config.VAULT_PATH).resolve()
    filepath = vault_root / Path(candidates[0])
    if vault_io.is_blocked_path(filepath):
        return "❌ Catatan di 04-Secure hanya dapat dibaca lewat `/reveal` dengan brankas terbuka."
    try:
        with filepath.open("r", encoding="utf-8") as file:
            return f"📄 **Isi File '{filepath.name}':**\n\n{file.read()}"
    except OSError as error:
        return f"❌ Gagal membaca file '{candidates[0]}': {error}"

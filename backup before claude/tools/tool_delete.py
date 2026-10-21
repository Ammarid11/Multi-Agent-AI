# tools/tool_delete.py
import os
import glob
import config


def delete_file(filename: str) -> str:
    """Delete only an exact Vault path; never choose a fuzzy or newest match."""
    requested = filename.strip().replace("\\", "/")
    if not requested:
        return "❌ Nama file kosong. Tidak ada file yang dihapus."
    if not requested.lower().endswith(".md"):
        requested += ".md"

    vault_root = os.path.abspath(config.VAULT_PATH)
    direct_path = os.path.abspath(os.path.join(vault_root, requested))
    try:
        if os.path.commonpath([vault_root, direct_path]) != vault_root:
            return "❌ Path harus berada di dalam Vault. Tidak ada file yang dihapus."
    except ValueError:
        return "❌ Path tidak valid. Tidak ada file yang dihapus."

    if os.path.isfile(direct_path):
        matches = [direct_path]
    elif "/" in requested:
        matches = []
    else:
        matches = glob.glob(
            os.path.join(vault_root, "**", os.path.basename(requested)),
            recursive=True,
        )
        matches = [path for path in matches if os.path.isfile(path)]

    if not matches:
        return f"❌ Catatan '{filename}' tidak ditemukan. Tidak ada file yang dihapus."
    if len(matches) > 1:
        choices = [
            os.path.relpath(path, vault_root).replace("\\", "/")
            for path in sorted(matches)
        ]
        return (
            "⚠️ Ada beberapa catatan dengan nama sama; tidak ada yang dihapus. "
            "Kirim ulang dengan path Vault lengkap:\n- " + "\n- ".join(choices)
        )

    filepath = matches[0]
    try:
        os.remove(filepath)
        return f"🗑️ Catatan '{os.path.relpath(filepath, vault_root)}' berhasil dihapus!"
    except OSError as error:
        return f"❌ Gagal menghapus file: {error}"
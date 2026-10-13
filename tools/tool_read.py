# tools/tool_read.py
import os
from tools.tool_append import find_file_in_vault


def read_file(filename: str) -> str:
    """Membaca isi lengkap file catatan dari Vault Obsidian."""
    filepath = find_file_in_vault(filename)
    if not os.path.exists(filepath):
        return f"❌ Catatan '{filename}' tidak ditemukan di Vault Obsidian!"

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f"📄 **Isi File '{os.path.basename(filepath)}':**\n\n{f.read()}"
    except Exception as e:
        return f"❌ Gagal membaca file: {str(e)}"
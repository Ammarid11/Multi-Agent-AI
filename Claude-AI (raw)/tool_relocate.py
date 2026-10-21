# tools/tool_relocate.py
import os
from typing import Optional
from tools.tool_append import find_file_in_vault, append_file


def relocate_content(source_file: str, target_file: str, content_snippet: str, target_section: Optional[str] = None) -> str:
    """Memindahkan cuplikan teks dari satu file ke file lain di Vault."""
    src_path = find_file_in_vault(source_file)
    if not os.path.exists(src_path):
        return f"❌ File asal '{source_file}' tidak ditemukan!"

    try:
        with open(src_path, 'r', encoding='utf-8') as f:
            src_text = f.read()

        snippet = content_snippet.strip()
        target_str = None
        if snippet in src_text:
            target_str = snippet
        elif snippet.replace('\r\n', '\n') in src_text.replace('\r\n', '\n'):
            target_str = snippet.replace('\r\n', '\n')
            src_text = src_text.replace('\r\n', '\n')

        if target_str:
            target_name = os.path.splitext(os.path.basename(target_file))[0]
            new_src_text = src_text.replace(target_str, f"*(Dipindahkan ke [[{target_name}]])*")
            with open(src_path, 'w', encoding='utf-8') as f:
                f.write(new_src_text)

            append_file(target_file, content_snippet, section=target_section)
            return f"🚚 Berhasil memindahkan materi ke '{os.path.basename(target_file)}'!"
        return "❌ Teks yang ingin dipindahkan tidak ditemukan di file asal."
    except Exception as e:
        return f"❌ Gagal memindahkan teks: {str(e)}"
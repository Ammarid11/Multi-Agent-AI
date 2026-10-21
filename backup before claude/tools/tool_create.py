# tools/tool_create.py
import os
import re
from datetime import datetime
import config
from tools.tool_append import append_file, find_file_in_vault
from tools.clean_markdown import clean_and_refactor_file


def create_file(filename: str, content: str) -> str:
    """
    Membuat file catatan baru di Vault Obsidian dan otomatis memformatnya
    sesuai standar Obsidian (YAML frontmatter, emoji heading, dan interlink).
    """
    # Bersihkan nama file dari sapaan asisten seperti 'Carl - ' atau 'Cart - '
    dir_part = os.path.dirname(filename)
    base_part = os.path.basename(filename)
    clean_base = re.sub(r'^(carl|cart|bot|asisten)\s*[-_:]*\s*', '', base_part, flags=re.IGNORECASE).strip()
    clean_filename = os.path.join(dir_part, clean_base) if dir_part else clean_base

    filepath = find_file_in_vault(clean_filename)

    # Proteksi: Hanya beralih ke append jika nama file fisik benar-benar sama, bukan hasil fuzzy ke file lain
    target_base = clean_base.lower() if clean_base.lower().endswith('.md') else clean_base.lower() + '.md'
    actual_base = os.path.basename(filepath).lower()

    if os.path.exists(filepath) and actual_base == target_base and os.path.getsize(filepath) > 50:
        return append_file(filename, content)
    elif os.path.exists(filepath) and actual_base != target_base:
        # Fuzzy match merujuk ke file yang beda judul. Buat file baru sesuai judul asli yang diminta
        filepath = os.path.join(config.VAULT_PATH, clean_filename if clean_filename.endswith('.md') else clean_filename + '.md')

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    final_content = content.strip()
    if not final_content.startswith("---"):
        final_content = f"---\ncreated: {now_str}\n---\n\n{final_content}"
    elif "created:" not in final_content:
        final_content = final_content.replace("---", f"---\ncreated: {now_str}", 1)

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(final_content + "\n")

        # AUTO-CLEAN: Otomatis rapikan format dokumen baru sesuai standar Obsidian
        base_name = os.path.basename(filepath)
        if "profil" not in base_name.lower():
            cleanup_result = clean_and_refactor_file(filepath)
            if not cleanup_result.startswith("✅") or "⚠️" in cleanup_result:
                return (
                    f"✅ Catatan '{base_name}' berhasil dibuat, tetapi perapihan otomatis "
                    f"belum tuntas:\n{cleanup_result}"
                )
            return f"✅ Catatan '{base_name}' berhasil dibuat dan hasil format terverifikasi."

        return (
            f"✅ Catatan '{base_name}' berhasil dibuat. Perapihan otomatis dilewati "
            "untuk menjaga struktur catatan profil."
        )
    except Exception as e:
        return f"❌ Gagal membuat file: {str(e)}"
# agents/quality_gate.py
"""
Critic-Actor Quality Gate (Pilar 7 Level 4 AI):
Memvalidasi, menguji standar format Obsidian, dan memastikan integritas
konten sebelum hasil kerja diserahkan ke pengguna atau disimpan ke disk.
"""
import re
from typing import Tuple


def inspect_obsidian_markdown(text: str) -> Tuple[bool, str, str]:
    """
    Menguji kepatuhan Markdown terhadap standar Obsidian Properties:
    Return: (is_valid, polished_text, reason)
    """
    if not text or not text.strip():
        return False, text, "Konten kosong."

    polished = text.strip()

    # 1. Pastikan tag code block markdown ``` terluar dibersihkan jika tidak sengaja terpasang
    if polished.startswith("```markdown"):
        polished = polished[11:].strip()
    elif polished.startswith("```"):
        polished = polished[3:].strip()
    if polished.endswith("```"):
        polished = polished[:-3].strip()

    # 2. Sanitasi Tag Numerik di YAML frontmatter (Obsidian tidak menerima integer tag murni seperti 2026)
    def _fix_numeric_tags(match):
        block = match.group(0)
        return re.sub(r'(?<=[\[,\s-])(\d{4})(?=[\]\s,\n])', r'tahun-\1', block)

    polished = re.sub(r'tags:\s*(\[[^\]]+\]|(\n\s*-\s*[^\n]+)+)', _fix_numeric_tags, polished)

    # 3. Validasi Heading: Pastikan ada Heading Utama dengan pola `# `
    if not re.search(r'^#\s+', polished, re.MULTILINE):
        # Tambahkan emoji heading otomatis jika terlewat
        first_line = polished.split('\n')[0].strip().replace('#', '').strip()
        title = first_line if len(first_line) > 3 and len(first_line) < 60 else "Catatan Ringkasan"
        polished = f"# 📌 {title}\n\n{polished}"

    return True, polished, "Lolos verifikasi kualitas."


def verify_and_polish_output(content: str) -> str:
    """Quality Gate Wrapper: Mengembalikan teks yang sudah melalui audit kualitas mandiri."""
    _, polished, _ = inspect_obsidian_markdown(content)
    return polished


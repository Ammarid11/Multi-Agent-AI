# tools/tool_append.py
import os
import glob
import re
from datetime import datetime
from typing import Optional, List
import config

GENERIC_HEADERS = {"profil", "daftar profil", "profil orang lain", "catatan terkait", "resource", "resources"}
OVERWRITE_SINGLE_FIELDS = {
    "nama", "nama lengkap", "nama lengkap / asli", "nama panggilan", 
    "nama panggilan / sosmed", "usia", "usia saat ini", "umur", 
    "tanggal lahir", "tanggal lahir / ulang tahun", "tgl lahir", 
    "jenis kelamin", "gender"
}


def find_file_in_vault(filename: str) -> str:
    """Mencari lokasi pasti file di dalam vault secara dinamis dan menangani nama ganda via mtime."""
    clean = filename.replace("\\", "/")
    if not clean.endswith('.md'):
        clean += '.md'

    direct_path = os.path.join(config.VAULT_PATH, clean)
    if os.path.exists(direct_path):
        return direct_path

    # 1. Cari rekursif berdasarkan nama file persis (Exact Match)
    base = os.path.basename(clean)
    matches = glob.glob(os.path.join(config.VAULT_PATH, "**", base), recursive=True)

    if matches:
        matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return matches[0]

    # Jika path mengandung folder eksplisit atau berupa tanggal (YYYY-MM-DD), jangan lakukan fuzzy match ke file lain
    is_date = bool(re.search(r'\d{4}-\d{2}-\d{2}', base))
    has_dir = "/" in clean

    if not is_date and not has_dir:
        # 2. Smart Fuzzy Match: Cari file yang mengandung kata kunci utama jika exact match gagal
        search_words = [w.lower() for w in re.findall(r'\w+', os.path.splitext(base)[0]) if len(w) > 2 and w.lower() not in ['catatan', 'file', 'note', 'buat', '2026']]
        if search_words and len(search_words) >= 2:
            all_md_files = glob.glob(os.path.join(config.VAULT_PATH, "**", "*.md"), recursive=True)
            best_candidate = None
            max_matches = 0
            for md_path in all_md_files:
                md_name = os.path.basename(md_path).lower()
                match_count = sum(1 for w in search_words if w in md_name)
                if match_count > max_matches and match_count >= 2:
                    max_matches = match_count
                    best_candidate = md_path
            if best_candidate:
                return best_candidate
        elif len(search_words) == 1:
            w = search_words[0]
            all_md_files = glob.glob(os.path.join(config.VAULT_PATH, "**", "*.md"), recursive=True)
            for md_path in all_md_files:
                stem = os.path.splitext(os.path.basename(md_path))[0].lower()
                if stem == w or stem.startswith(w + " ") or stem.endswith(" " + w):
                    return md_path


    # Jika file belum ada dan path mengandung folder spesifik, periksa keberadaan folder
    target_dir = os.path.dirname(direct_path)
    if not os.path.exists(target_dir):
        # Cari folder alternatif (misal cari folder Resources)
        folder_base = os.path.basename(target_dir).lower().replace("03-", "")
        for root, dirs, _ in os.walk(config.VAULT_PATH):
            for d in dirs:
                if folder_base in d.lower():
                    return os.path.join(root, d, base)

    return direct_path



def _find_section_index(lines: List[str], section: str) -> int:
    """Helper: Mencari indeks baris heading sub-bagian yang spesifik (hanya Level 2 & 3)."""
    sec_lower = section.lower().strip()
    if sec_lower in GENERIC_HEADERS:
        return -1

    for i, line in enumerate(lines):
        clean = line.strip().lower()
        if clean.startswith("###") and sec_lower in clean:
            return i

    for i, line in enumerate(lines):
        clean = line.strip().lower()
        if clean.startswith("##") and sec_lower in clean and not any(g in clean for g in GENERIC_HEADERS):
            return i
    return -1


def _find_section_end(lines: List[str], start_idx: int) -> int:
    """Helper: Mencari batas akhir section."""
    for i in range(start_idx + 1, len(lines)):
        clean = lines[i].strip()
        if clean.startswith("---") or (clean.startswith("#") and not clean.startswith("####")):
            return i
    return len(lines)


def _append_new_section(lines: List[str], section: str, content: str) -> List[str]:
    """Helper: Menambahkan section baru tepat sebelum Catatan Terkait atau di akhir."""
    existing_nums = [
        int(m.group(1)) for l in lines 
        if (m := re.match(r'^#{2,3}\s+(\d+)\.', l.strip()))
    ]
    next_num = max(existing_nums) + 1 if existing_nums else None
    heading = f"### {next_num}. {section}" if next_num else f"### {section}"
    new_block = f"\n{heading}\n{content.strip()}\n"

    for i, line in enumerate(lines):
        if "catatan terkait" in line.lower() and line.strip().startswith("#"):
            insert_at = i - 1 if (i > 0 and lines[i - 1].strip() == "---") else i
            lines.insert(insert_at, new_block + "\n")
            return lines

    lines.append(new_block)
    return lines


def _merge_field_value(old_line: str, new_line: str, key: str) -> str:
    """Helper: Menggabungkan nilai field dengan koma jika bersifat kumulatif (misal: hobi, aktivitas)."""
    if key in OVERWRITE_SINGLE_FIELDS:
        return new_line.strip() + "\n"

    old_val = old_line.split("**")[-1].replace(":", "").strip() if "**" in old_line else ""
    new_val = new_line.split("**")[-1].replace(":", "").strip() if "**" in new_line else ""

    if not old_val:
        return new_line.strip() + "\n"
    if not new_val or new_val.lower() in old_val.lower():
        return old_line.strip() + "\n"

    prefix = new_line.split(":**")[0] + ":**" if ":**" in new_line else f"- **{key.title()}:**"
    return f"{prefix} {old_val}, {new_val}\n"


def _update_field_in_section(lines: List[str], start_idx: int, end_idx: int, line_to_add: str) -> bool:
    """Helper: Memperbarui baris field in-place (menggabungkan data baru dengan koma)."""
    if "**" not in line_to_add:
        return False

    parts = line_to_add.split("**")
    if len(parts) < 2:
        return False

    key = parts[1].replace(":", "").strip().lower()
    for i in range(start_idx + 1, end_idx):
        if f"**{key}**" in lines[i].lower() or f"**{key}:**" in lines[i].lower():
            lines[i] = _merge_field_value(lines[i], line_to_add, key)
            return True
    return False


def _update_existing_section(lines: List[str], target_idx: int, content: str) -> List[str]:
    """Helper: Memperbarui isi sub-bagian yang sudah ada."""
    end_idx = _find_section_end(lines, target_idx)

    for raw_line in content.strip().splitlines():
        line_to_add = raw_line.strip()
        if not line_to_add:
            continue

        if not _update_field_in_section(lines, target_idx, end_idx, line_to_add):
            pos = end_idx
            while pos > target_idx + 1 and lines[pos - 1].strip() == "":
                pos -= 1
            lines.insert(pos, line_to_add + "\n")
            end_idx += 1

    return lines


def append_file(filename: str, content: str, section: Optional[str] = None) -> str:
    """Menambahkan atau memperbarui catatan di Vault Obsidian."""
    filepath = find_file_in_vault(filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    if not os.path.exists(filepath):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        header = f"---\ncreated: {now_str}\n---\n\n"
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(header + content.strip() + "\n")
        return f"📝 File '{os.path.basename(filepath)}' berhasil dibuat di '{os.path.relpath(filepath, config.VAULT_PATH)}'!"

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        if not section:
            lines.append(f"\n{content.strip()}\n")
        else:
            target_idx = _find_section_index(lines, section)
            if target_idx == -1:
                lines = _append_new_section(lines, section, content)
            else:
                lines = _update_existing_section(lines, target_idx, content)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        return f"✅ Berhasil memperbarui data di '{os.path.relpath(filepath, config.VAULT_PATH)}'!"
    except Exception as e:
        return f"❌ Gagal memperbarui file: {str(e)}"
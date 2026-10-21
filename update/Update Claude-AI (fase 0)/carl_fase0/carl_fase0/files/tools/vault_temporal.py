# tools/vault_temporal.py
"""
Temporal Intelligence & Daily Briefing (Pilar 4 Level 4 AI):
Menghubungkan kalender, tenggat waktu (deadline), daftar tugas aktif,
dan catatan harian (Daily Notes) ke dalam laporan briefing strategis.
"""
import os
import re
import glob
from datetime import datetime, timedelta
from typing import List, Dict, Any
import config
from memory.vault_scanner import is_indexable_note
from tools.tool_append import find_file_in_vault, append_file


def scan_deadlines_and_tasks() -> Dict[str, List[Dict[str, str]]]:
    """Memindai seluruh catatan di Vault untuk mencari deadline dan checkbox tugas."""
    findings = {"deadlines": [], "tasks": []}
    if not os.path.exists(config.VAULT_PATH):
        return findings

    for filepath in glob.glob(os.path.join(config.VAULT_PATH, "**", "*.md"), recursive=True):
        if not is_indexable_note(filepath, config.VAULT_PATH):
            continue

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            base_name = os.path.basename(filepath)

            for line in lines:
                clean_l = line.strip()
                # 1. Deteksi deadline (contoh: deadline: 2026-11-01 atau target: ...)
                dl_match = re.search(r'(?:deadline|tenggat|target)\s*:\s*([0-9\-\/A-Za-z\s]+)', clean_l, re.IGNORECASE)
                if dl_match:
                    dl_val = dl_match.group(1).strip()
                    findings["deadlines"].append({
                        "file": base_name,
                        "deadline": dl_val,
                        "text": clean_l
                    })

                # 2. Deteksi tugas belum selesai (- [ ] ...)
                if clean_l.startswith("- [ ]") and len(clean_l) > 6:
                    task_text = clean_l[5:].strip()
                    if task_text:
                        findings["tasks"].append({
                            "file": base_name,
                            "task": task_text
                        })
        except Exception:
            continue

    return findings


def generate_daily_briefing(user_name: str = "Pengguna") -> str:
    """Menghasilkan laporan briefing strategis harian."""
    now = datetime.now()
    now_str = now.strftime("%A, %d %B %Y pukul %H:%M WIB")
    findings = scan_deadlines_and_tasks()

    # Catatan yang baru dimodifikasi (24 jam terakhir)
    recent_modified = []
    cutoff = (now - timedelta(hours=48)).timestamp()
    for filepath in glob.glob(os.path.join(config.VAULT_PATH, "**", "*.md"), recursive=True):
        if is_indexable_note(filepath, config.VAULT_PATH):
            try:
                if os.path.getmtime(filepath) > cutoff:
                    recent_modified.append(os.path.basename(filepath))
            except Exception:
                pass

    recent_str = ", ".join(recent_modified[:5]) if recent_modified else "Belum ada perubahan baru."

    lines = [
        f"### 🌅 Morning & Strategic Briefing untuk {user_name}\n",
        f"📅 **Waktu:** `{now_str}`\n",
        f"📂 **Catatan Aktif (48 Jam Terakhir):**\n- {recent_str}\n"
    ]

    # Bagian Deadline
    lines.append("⏳ **Tenggat Waktu / Target Terdeteksi:**")
    if findings["deadlines"]:
        for d in findings["deadlines"][:4]:
            lines.append(f"- 📌 `{d['file']}`: **{d['deadline']}**")
    else:
        lines.append("- *Tidak ada tenggat waktu spesifik yang terpasang.*")

    lines.append("")

    # Bagian Tugas Terbuka
    lines.append("📝 **Daftar Tugas Belum Selesai (- [ ]):**")
    if findings["tasks"]:
        for t in findings["tasks"][:5]:
            lines.append(f"- [ ] **[{t['file']}]** {t['task']}")
    else:
        lines.append("- *Semua tugas di catatan telah tertuntaskan!*")

    lines.append("")
    lines.append("💡 **Fokus Prioritas Hari Ini:**")
    lines.append("1. Lanjutkan pengembangan proyek aktif.")
    lines.append("2. Tuntaskan tugas-tugas di atas dan perbarui statusnya.")
    lines.append("3. Hubungkan ide-ide baru ke catatan utama menggunakan format Wikilinks.")

    briefing_text = "\n".join(lines)

    # Otomatis catat ke Daily Note hari ini jika folder 05-Daily Notes tersedia
    today_str = now.strftime("%Y-%m-%d")
    daily_note = f"05-Daily Notes/{today_str}.md"
    try:
        append_file(daily_note, f"\n## 🌅 Briefing Sistem ({now.strftime('%H:%M WIB')})\n{briefing_text}\n")
    except Exception:
        pass

    return briefing_text


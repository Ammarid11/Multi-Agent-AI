# memory/rules_engine.py
"""
Procedural Rules & SOP Learning Engine (Pilar 3 Level 4 AI):
Mencatat, mengelola, dan menerapkan aturan operasional serta SOP kustom
yang diajarkan oleh pengguna ke dalam seluruh alur kerja agen.
"""
import os
import json
import re
from datetime import datetime
from typing import List, Dict, Optional
import config

RULES_FILE = config.state_file(".system_rules.json")


def load_rules() -> List[Dict[str, str]]:
    """Memuat seluruh aturan operasional aktif dari disk."""
    if not os.path.exists(RULES_FILE):
        return []
    try:
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("rules", [])
    except Exception:
        return []


def save_rules(rules: List[Dict[str, str]]) -> None:
    """Menyimpan daftar aturan operasional ke disk."""
    try:
        os.makedirs(os.path.dirname(RULES_FILE), exist_ok=True)
        with open(RULES_FILE, "w", encoding="utf-8") as f:
            json.dump({"rules": rules}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def add_rule(rule_text: str, category: str = "general") -> str:
    """Menambahkan aturan operasional baru."""
    clean_text = rule_text.strip()
    if not clean_text:
        return "❌ Aturan tidak boleh kosong."

    rules = load_rules()
    # Hindari duplikat persis
    for r in rules:
        if r.get("text", "").lower() == clean_text.lower():
            return f"⚠️ Aturan sudah ada sebelumnya: '{clean_text}'"

    new_rule = {
        "id": f"rule_{len(rules) + 1}",
        "category": category,
        "text": clean_text,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    rules.append(new_rule)
    save_rules(rules)
    return f"✅ **Aturan Baru Berhasil Disimpan:**\n> \"{clean_text}\"\n*(Aturan ini akan otomatis diterapkan di setiap pembuatan/perapihan catatan)*"


def delete_rule(identifier: str) -> str:
    """Menghapus aturan berdasarkan ID atau kata kunci teks."""
    rules = load_rules()
    clean_id = identifier.strip().lower()
    initial_count = len(rules)

    rules = [
        r for r in rules
        if r.get("id", "").lower() != clean_id and clean_id not in r.get("text", "").lower()
    ]

    if len(rules) < initial_count:
        save_rules(rules)
        return f"🗑️ Aturan '{identifier}' berhasil dihapus."
    return f"❌ Aturan dengan ID/kata kunci '{identifier}' tidak ditemukan."


def format_rules_summary() -> str:
    """Menampilkan daftar aturan operasional yang sedang aktif."""
    rules = load_rules()
    if not rules:
        return "ℹ️ Belum ada aturan operasional khusus yang tersimpan.\n*(Tips: Ketik `/rule <isi aturan>` untuk menambahkan aturan baru)*"

    lines = ["### 📜 Daftar Aturan Operasional (Procedural SOP) Aktif:"]
    for idx, r in enumerate(rules, 1):
        lines.append(f"{idx}. `[{r.get('id')}]` {r.get('text')} *(Dibuat: {r.get('created_at', '-')})*")
    return "\n".join(lines)


def get_rules_prompt_context() -> str:
    """Membentuk blok instruksi aturan untuk diinjeksikan ke system prompt agen."""
    rules = load_rules()
    if not rules:
        return ""

    rule_lines = [f"- {r.get('text')}" for r in rules]
    return (
        "═══ ATURAN PROSEDURAL KHUSUS DARI PENGGUNA (WAJIB DITERAPKAN) ═══\n"
        + "\n".join(rule_lines)
        + "\n════════════════════════════════════════════════════════════════\n"
    )


def detect_and_register_rule(user_input: str) -> Optional[str]:
    """
    Mendeteksi apakah pengguna secara eksplisit mengajari aturan operasional baru.
    🛡️ Proteksi Anti-Halu: Menolak kalimat tanya atau percakapan biasa menjadi SOP permanen.
    """
    text = user_input.strip()

    # 1. Tolak jika mengandung tanda tanya '?'
    if "?" in text:
        return None

    # 2. Tolak perintah slash lain
    if text.startswith("/") and not text.startswith("/rule"):
        return None

    # 3. Hanya terima format eksplisit SOP / Aturan dengan titik dua atau awalan deklaratif tegas
    match = re.search(r'^(?:ingat\s*:|aturan\s*:|sop\s*:|mulai sekarang\s*:|wajib selalu\s*:)\s*(.+)', text, re.IGNORECASE)
    if match and len(match.group(1).strip()) > 8:
        extracted = match.group(1).strip()
        # 4. Validasi isi aturan tidak diawali kata tanya
        interrogatives = ("apa", "apakah", "bagaimana", "kenapa", "mengapa", "kapan", "siapa")
        first_word = extracted.lower().split()[0] if extracted.split() else ""
        if first_word in interrogatives:
            return None
        return add_rule(extracted, category="user_instruction")

    return None


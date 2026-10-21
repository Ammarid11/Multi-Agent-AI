# memory/user_profile.py
"""
Dynamic User Profiling & Episodic Memory:
Mencatat preferensi, gaya komunikasi, minat, dan proyek aktif pengguna
secara dinamis agar AI semakin hari semakin memahami pribadi pengguna.
"""
import os
import json
import re
from datetime import datetime
from typing import Dict, List, Any
import config

PROFILE_FILE = os.path.join(config.DB_PATH, ".user_profile.json")


def load_user_profile(user_name: str = "Pengguna") -> Dict[str, Any]:
    """Memuat profil pengguna dari disk dengan nilai default adaptif."""
    default_profile = {
        "user_name": user_name,
        "interests": [],
        "active_projects": [],
        "communication_style": "Terstruktur, ramah, kritis, dan to-the-point",
        "key_facts": [],
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M")
    }

    if not os.path.exists(PROFILE_FILE):
        return default_profile

    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data["user_name"] = user_name or data.get("user_name", "Pengguna")
            return data
    except Exception:
        return default_profile


def save_user_profile(profile: Dict[str, Any]) -> None:
    """Menyimpan profil pengguna ke disk."""
    try:
        os.makedirs(os.path.dirname(PROFILE_FILE), exist_ok=True)
        profile["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_user_profile_context(user_name: str = "Pengguna") -> str:
    """Membentuk string konteks profil ringkas untuk diinjeksikan ke prompt asisten."""
    profile = load_user_profile(user_name)
    interests_str = ", ".join(profile.get("interests", [])[:5])
    projects_str = ", ".join(profile.get("active_projects", [])[:4])
    style_str = profile.get("communication_style", "Terstruktur dan solutif")

    lines = [
        "═══ PROFIL & PREFERENSI PERSONAL PENGGUNA ═══",
        f"- Nama Lengkap / Panggilan: {profile.get('user_name', user_name)}",
        f"- Minat & Domain Utama: {interests_str}",
        f"- Proyek / Fokus Saat Ini: {projects_str}",
        f"- Preferensi Gaya Jawaban: {style_str}",
    ]

    facts = profile.get("key_facts", [])[-3:]
    if facts:
        lines.append("- Fakta Penting Diketahui:")
        for fact in facts:
            lines.append(f"  • {fact}")

    lines.append("═══════════════════════════════════════════════")
    return "\n".join(lines) + "\n"


def update_profile_from_interaction(user_input: str, user_name: str = "Pengguna") -> None:
    """
    Menganalisis masukan pengguna secara ringan (0 ms lag) untuk memperbarui minat / proyek aktif.
    🛡️ Proteksi Anti-Halu: Hanya menyerap pernyataan deklaratif tegas, menolak pertanyaan & pengandaian.
    """
    text = user_input.strip()
    if len(text) < 10:
        return

    # 1. Tolak perintah slash (/search, /simulate, dll)
    if text.startswith("/"):
        return

    # 2. Tolak semua kalimat yang mengandung tanda tanya '?'
    if "?" in text:
        return

    # 3. Tolak jika diawali kata tanya atau partikel pengandaian
    lowered = text.lower()
    interrogatives = (
        "apa", "apakah", "bagaimana", "kenapa", "mengapa", "kapan", "siapa",
        "dimana", "di mana", "berapa", "adakah", "benarkah", "kalau", "jika",
        "seandainya", "misal", "misalkan", "umpama", "bila"
    )
    first_word = lowered.split()[0] if lowered.split() else ""
    if first_word in interrogatives or any(lowered.startswith(q + " ") for q in interrogatives):
        return

    profile = load_user_profile(user_name)
    changed = False

    # 4. Deteksi deklarasi proyek baru (harus deklaratif afirmatif)
    project_match = re.search(r'(?:saya sedang|fokus saya saat ini|proyek saya|sedang mengerjakan proyek)\s+([A-Za-z0-9\s]{4,30})', text, re.IGNORECASE)
    if project_match:
        cand = project_match.group(1).strip().title()
        if cand and cand not in profile.get("active_projects", []) and len(cand.split()) <= 4:
            profile.setdefault("active_projects", []).append(cand)
            profile["active_projects"] = profile["active_projects"][-6:]  # Batasi 6 proyek aktif
            changed = True

    # 5. Deteksi fakta diri afirmatif (misal: "saya suka X", "saya adalah X", "target saya X")
    fact_match = re.search(r'^saya\s+(?:adalah|suka|ingin|targetkan|lebih suka|fokus)\s+([^.,;?!]{4,40})', text, re.IGNORECASE)
    if fact_match:
        cand_fact = fact_match.group(0).strip().capitalize()
        # Pastikan tidak mengandung kata tanya di dalam frasa
        if not any(q in cand_fact.lower() for q in ["kenapa", "bagaimana", "apa"]):
            if cand_fact not in profile.get("key_facts", []):
                profile.setdefault("key_facts", []).append(cand_fact)
                profile["key_facts"] = profile["key_facts"][-5:]  # Batasi 5 fakta kunci
                changed = True

    if changed:
        save_user_profile(profile)


def clear_user_facts(user_name: str = "Pengguna") -> str:
    """Membersihkan fakta kunci profil pengguna jika terdapat entri yang tidak diinginkan."""
    profile = load_user_profile(user_name)
    profile["key_facts"] = []
    save_user_profile(profile)
    return "🧹 Fakta profil pengguna berhasil dibersihkan!"

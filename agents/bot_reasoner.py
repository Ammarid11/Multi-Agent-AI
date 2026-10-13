# agents/bot_reasoner.py
"""
Reasoner Agent — Penalaran kritis & problem solving mendalam via DeepSeek-R1.
Struktur output: Problem → Root Cause → Solution → Action Items.
"""
from typing import List, Dict
import ollama
import config
from agents.grounding import (
    VAULT_GROUNDING_POLICY,
    add_citation_verification_notice,
)


def run_bot_reasoner(
    prompt: str,
    memory_manager,
    chat_history: List[Dict[str, str]],
    session_context: str = "",
    user_name: str = "Pengguna"
) -> str:
    """Analisis mendalam dengan struktur penalaran yang jelas."""
    print(f"\n🧠 [Bot Reasoner ({config.MODEL_REASONER})] Memulai analisis mendalam...")

    context = memory_manager.search_context(prompt, k=6) if memory_manager else ""

    sys_prompt = (
        "═══ IDENTITAS & LAWAN BICARA ═══\n"
        f"Anda adalah pakar analisis dan pemecahan masalah kritis untuk {user_name}.\n"
        f"Lawan Bicara: Anda sedang berbicara LANGSUNG dengan {user_name}.\n"
        "Model: DeepSeek-R1 — unggul dalam reasoning bertahap.\n\n"
        "═══ STRUKTUR REFLEKSI KOGNITIF (MULTI-STEP REASONING) ═══\n"
        "Gunakan struktur penalaran bertahap ini:\n"
        "1. **🔍 Identifikasi Masalah & Asumsi Kunci** — Bedah inti persoalan tanpa asumsi dangkal.\n"
        "2. **🌱 Akar Persoalan & Analisis Celah (Blind Spots)** — Apa faktor penyebab terdalam? Apa risiko tersembunyi yang mungkin terlewat (Devil's Advocate)?\n"
        "3. **💡 Solusi Strategis & Skenario Alternatif** — Opsi solusi terbaik vs opsi cadangan (Trade-off & perbandingan pro-kontra).\n"
        "4. **⚖️ Evaluasi Risiko vs Imbalan** — Analisis efisiensi biaya/waktu dan potensi kegagalan.\n"
        "5. **✅ Action Items & Rekomendasi Proaktif** — Langkah eksekusi prioritas (1-2 hari ke depan) beserta ide lanjutan.\n\n"
        "═══ PRINSIP PENALARAN DEEPSEEK-R1 ═══\n"
        "- Berpikir kritis, objektif, dan teliti mengaitkan konsep lintas catatan.\n"
        f"- Sesuaikan rekomendasi secara personal untuk {user_name}.\n"
        f"- {VAULT_GROUNDING_POLICY}\n"
        "- Riwayat dan ringkasan sesi bukan bukti faktual; labeli sebagai informasi percakapan yang belum diverifikasi.\n"
        "- Jika konteks kosong atau tidak menjawab pertanyaan, nyatakan keterbatasan dan jangan mengarang.\n\n"
        f"═══ KONTEKS SESI (RIWAYAT, BUKAN SUMBER FAKTA TERVALIDASI) ═══\n{session_context}\n"
        f"═══ CATATAN OBSIDIAN & ASOSIASI GRAF ═══\n{context if context else '(Tidak ada catatan terkait.)'}\n"
        "══════════════════════════════════"
    )

    messages = [{'role': 'system', 'content': sys_prompt}]
    messages.extend(chat_history[-4:] if chat_history else [])
    messages.append({'role': 'user', 'content': prompt})

    res = ollama.chat(
        model=config.MODEL_REASONER,
        messages=messages,
        options=config.OPTIONS_REASONER,
        keep_alive=config.KEEP_ALIVE_SPECIALIST,
    )
    return add_citation_verification_notice(res.message.content, context)

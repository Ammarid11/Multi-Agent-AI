# agents/bot_reasoner.py
"""
Reasoner Agent — Penalaran kritis & problem solving mendalam via DeepSeek-R1.
Struktur output: Problem → Root Cause → Solution → Action Items.
"""
import re
from typing import List, Dict
import ollama
import config
from agents.grounding import (
    VAULT_GROUNDING_POLICY,
    add_citation_verification_notice,
)

_DEEP_REASONING_CUES = re.compile(
    r"\b(?:"
    r"analisis|analisa|bandingkan|perbandingan|trade[\s-]?off|pro[\s-]?kontra|"
    r"dampak|konsekuensi|sebab[\s-]?akibat|strategi|prioritaskan|prioritas|"
    r"optimalkan|pemecahan masalah|pecahkan masalah|langkah demi langkah|"
    r"logika|buktikan|evaluasi kritis|pilih yang terbaik|rencana|"
    r"hitung|perhitungan|selesaikan persamaan"
    r")\b",
    re.IGNORECASE,
)
_CONDITIONAL_REASONING_CUES = re.compile(
    r"\b(?:jika|apabila|andaikan|dengan syarat|berdasarkan)\b",
    re.IGNORECASE,
)
_MULTI_PART_CUES = re.compile(
    r"\b(?:dan|lalu|kemudian|sementara|dibandingkan|dengan|serta)\b",
    re.IGNORECASE,
)


def should_use_deep_reasoning(prompt: str) -> bool:
    """Escalate explicit analytical, comparative, planning, or calculation requests."""
    normalized = prompt.strip()
    if not normalized:
        return False
    if _DEEP_REASONING_CUES.search(normalized):
        return True
    return bool(
        _CONDITIONAL_REASONING_CUES.search(normalized)
        and _MULTI_PART_CUES.search(normalized)
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
        "═══ METODE ANALISIS ═══\n"
        "Untuk menjawab, identifikasi tujuan dan batasan, pisahkan fakta dari asumsi, "
        "uraikan faktor yang relevan, bandingkan alternatif bila memang ada, lalu "
        "periksa bahwa kesimpulan menjawab semua bagian pertanyaan dan tidak "
        "bertentangan dengan bukti. Sesuaikan kedalaman dengan kompleksitas tugas; "
        "jangan memaksakan daftar panjang pada pertanyaan sederhana.\n"
        "Sampaikan jawaban akhir yang ringkas dan alasan utama yang dapat diperiksa. "
        "Jangan tampilkan monolog internal atau seluruh rantai pemikiran.\n\n"
        "═══ PRINSIP PENALARAN DEEPSEEK-R1 ═══\n"
        "- Berpikir kritis, objektif, dan teliti mengaitkan konsep lintas catatan.\n"
        "- Jika data penting tidak ada, nyatakan asumsi atau minta klarifikasi; jangan mengisi kekosongan dengan tebakan.\n"
        "- Untuk hitungan, tunjukkan rumus, nilai yang dipakai, dan hasil agar dapat diverifikasi.\n"
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

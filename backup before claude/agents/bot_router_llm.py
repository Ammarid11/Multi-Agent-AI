# agents/bot_router_llm.py
"""
LLM-based Intent Classifier untuk routing cerdas.
Menggantikan keyword matching dengan pemahaman bahasa alami.
"""
import logging

import ollama
import config

logger = logging.getLogger(__name__)

INTENT_LABELS = {
    "web":      "Pencarian informasi dari internet/web, berita terkini, info real-time, googling",
    "think":    "Analisis mendalam, penalaran kritis, problem solving, evaluasi strategi",
    "coder":    "Pembuatan kode, debugging, skrip Python, pemrograman, algoritma",
    "sintesis": "Menghubungkan ide antar-catatan, knowledge graph, pola tersembunyi",
    "file":     "Buat, simpan, hapus, baca, atau perbarui file/catatan di vault",
    "clean":    "Rapikan, audit, perbaiki format file atau struktur folder vault",
    "default":  "Obrolan umum, tanya jawab dari catatan Second Brain, pertanyaan santai",
}


def classify_intent(prompt: str) -> str:
    """
    Klasifikasi intent user menggunakan LLM.
    Return: salah satu key dari INTENT_LABELS.
    """
    label_desc = "\n".join([f'  "{k}": {v}' for k, v in INTENT_LABELS.items()])

    sys_prompt = (
        "Anda adalah classifier intent percakapan AI Second Brain.\n"
        "Tugas: analisis pesan pengguna dan pilih intent yang paling sesuai.\n\n"
        f"Pilihan intent yang tersedia:\n{label_desc}\n\n"
        "ATURAN KETAT:\n"
        "- Kembalikan HANYA satu kata intent (contoh: web, think, coder, dll).\n"
        "- TANPA penjelasan, TANPA tanda kutip, TANPA teks lain.\n"
        "- Jika ragu antara 2 intent, pilih yang paling dominan.\n"
        "- Jika tidak ada yang cocok, pilih: default"
    )

    try:
        res = ollama.chat(
            model=config.MODEL_WRITER,
            messages=[
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': prompt},
            ],
            options={"temperature": 0.0},  # deterministic
            keep_alive=config.KEEP_ALIVE_DEFAULT,
        )
        raw_out = res.message.content.strip().lower().strip('"\'')
        words = raw_out.split()
        intent = words[0] if words else "default"
        return intent if intent in INTENT_LABELS else "default"
    except Exception:
        logger.exception("Intent classification failed; routing to the default agent.")
        return "default"

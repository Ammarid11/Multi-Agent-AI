# memory/session_memory.py
"""
Rolling Session Memory Manager dengan Persistent Storage (48 Jam).
Meringkas riwayat percakapan otomatis dan menyimpannya ke disk (.session_history.json)
agar AI mengingat obrolan kemarin, namun terbebas dari konteks basi masa lalu.
"""
import os
import json
import time
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from typing import List, Dict, Tuple
import ollama
import config

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "..", ".session_history.json")
SUMMARIZE_THRESHOLD = 8   # Ringkas jika percakapan mencapai 8 giliran
KEEP_RECENT = 4           # Pertahankan 4 pesan terbaru setelah diringkas
MAX_AGE_SECONDS = 48 * 3600  # 48 Jam
logger = logging.getLogger(__name__)
_summary_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="carl-summary")


def _load_persisted_summaries() -> List[str]:
    """Muat ringkasan yang belum kedaluwarsa (< 48 jam) dari disk."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        now = time.time()
        # Ambil hanya entri yang dibuat dalam 48 jam terakhir
        valid_entries = [
            item["summary"] for item in data.get("summaries", [])
            if now - item.get("timestamp", 0) < MAX_AGE_SECONDS
        ]
        return valid_entries[-3:]  # Maksimal 3 summary terbaru
    except Exception:
        logger.exception("Unable to load persisted session summaries.")
        return []


def _save_persisted_summary(summary_text: str) -> bool:
    """Simpan summary baru ke disk bersama timestamp."""
    try:
        existing = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                existing = data.get("summaries", [])

        # Filter entri lama
        now = time.time()
        filtered = [item for item in existing if now - item.get("timestamp", 0) < MAX_AGE_SECONDS]
        filtered.append({"summary": summary_text, "timestamp": now})

        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump({"summaries": filtered[-5:]}, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        logger.exception("Unable to persist session summary.")
        return False


def clear_session_history() -> None:
    """Hapus riwayat sesi untuk memulai sesi baru yang bersih."""
    try:
        if os.path.exists(HISTORY_FILE):
            os.remove(HISTORY_FILE)
    except Exception:
        logger.exception("Unable to clear persisted session history.")
        raise


def _summarize_batch(messages: List[Dict], user_name: str = "Pengguna") -> str:
    """Buat ringkasan singkat dari sekumpulan pesan."""
    if not messages:
        return ""

    convo_text = "\n".join([
        f"{user_name if m['role'] == 'user' else 'Carl (AI)'}: {m['content'][:300]}"
        for m in messages
    ])

    sys_prompt = (
        "Buat ringkasan singkat percakapan berikut dalam 3-5 poin penting.\n"
        "Fokus pada: topik, pernyataan eksplisit pengguna, keputusan/aksi, dan hal yang masih belum pasti.\n"
        "Bedakan dengan jelas informasi yang dinyatakan pengguna dari klaim atau saran yang dibuat Carl.\n"
        "Jangan mengubah dugaan atau jawaban Carl menjadi fakta terverifikasi; pertahankan atribusi dan ketidakpastian.\n"
        "Format: bullet points ringkas dalam Bahasa Indonesia.\n"
        "KEMBALIKAN HANYA bullet points, tanpa heading atau penjelasan tambahan."
    )

    try:
        res = ollama.chat(
            model=config.MODEL_WRITER,
            messages=[
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': convo_text},
            ],
            options={"temperature": 0.1},
            keep_alive=config.KEEP_ALIVE_DEFAULT,
        )
        return res.message.content.strip()
    except Exception:
        logger.exception("Unable to summarize the conversation batch.")
        return ""


def load_initial_session_summaries() -> List[str]:
    """Inisialisasi memori sesi dari disk saat aplikasi start."""
    return _load_persisted_summaries()


def manage_history(
    chat_history: List[Dict],
    session_summaries: List[str],
    user_name: str = "Pengguna"
) -> Tuple[List[Dict], List[str]]:
    """
    Periksa apakah chat_history perlu diringkas.
    Jika ya: ringkas, simpan ke memori dan file disk, lalu potong history.
    """
    if len(chat_history) < SUMMARIZE_THRESHOLD:
        return chat_history, session_summaries

    to_summarize = chat_history[:-KEEP_RECENT]
    recent = chat_history[-KEEP_RECENT:]

    print(f"\n📝 [Session Memory] Meringkas {len(to_summarize)} pesan obrolan...")
    summary = _summarize_batch(to_summarize, user_name=user_name)

    if not summary:
        return chat_history, session_summaries

    if not _save_persisted_summary(summary):
        return chat_history, session_summaries

    session_summaries = session_summaries + [summary]
    if len(session_summaries) > 3:
        session_summaries = session_summaries[-3:]

    return recent, session_summaries


def summarize_and_persist_history(
    messages: List[Dict],
    user_name: str = "Pengguna",
) -> str:
    """Summarize and persist a history snapshot for background execution."""
    summary = _summarize_batch(messages, user_name=user_name)
    if not summary or not _save_persisted_summary(summary):
        return ""
    return summary


def submit_history_summary(
    messages: List[Dict],
    user_name: str = "Pengguna",
) -> Future[str]:
    """Schedule a stable history snapshot for summarization."""
    snapshot = [message.copy() for message in messages]
    return _summary_executor.submit(
        summarize_and_persist_history,
        snapshot,
        user_name,
    )


def get_session_context(session_summaries: List[str]) -> str:
    """Format session summaries jadi string context untuk system prompt."""
    if not session_summaries:
        return ""
    recent = session_summaries[-2:]
    joined = "\n---\n".join(recent)
    return (
        "📋 RIWAYAT SESI TERAKHIR (48 Jam; ringkasan percakapan, bukan sumber fakta terverifikasi):\n"
        f"{joined}\n"
    )

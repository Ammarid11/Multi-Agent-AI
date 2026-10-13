# memory/query_expander.py
"""
Query Expansion untuk meningkatkan recall pada hybrid search.
Menghasilkan variasi query sinonim sebelum masuk ke vector search.
"""
import ollama
import config
from typing import List


def expand_query(query: str) -> List[str]:
    """
    Expand satu query menjadi 2-3 variasi sinonim/parafrase.
    Meningkatkan peluang menemukan dokumen relevan di vault.

    Return: list query (original + variasi), maks 3 total.
    """
    if len(query.strip()) < 5:
        return [query]

    sys_prompt = (
        "Buat 2 variasi alternatif dari query pencarian berikut dalam Bahasa Indonesia.\n"
        "Gunakan sinonim atau cara phrasing yang berbeda, tapi maknanya sama.\n"
        "ATURAN:\n"
        "- Kembalikan HANYA 2 baris, masing-masing satu variasi.\n"
        "- Tanpa nomor, tanpa bullet, tanpa penjelasan.\n"
        "- Tetap singkat (maks 10 kata per variasi)."
    )

    try:
        res = ollama.chat(
            model=config.MODEL_WRITER,
            messages=[
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': query},
            ],
            options={"temperature": 0.4},
            keep_alive=config.KEEP_ALIVE_DEFAULT,
        )
        lines = [
            ln.strip().lstrip("0123456789.-) ")
            for ln in res.message.content.strip().split('\n')
            if ln.strip()
        ]
        variations = [ln for ln in lines[:2] if ln and ln.lower() != query.lower()]
        return [query] + variations
    except Exception:
        return [query]


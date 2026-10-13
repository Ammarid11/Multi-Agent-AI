# agents/bot_curator.py
import json
import re
from typing import List, Dict
import ollama
import config
from tools.vault_indexer import generate_or_get_vault_map
from tools.tool_relocate import relocate_content


def _extract_json(text: str) -> dict:
    """Ekstrak JSON dari respons model secara aman dan tahan terhadap unescaped newlines."""
    clean_text = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean_text, re.DOTALL)
    if match:
        clean_text = match.group(1).strip()
    else:
        match_obj = re.search(r"\{.*\}", clean_text, re.DOTALL)
        if match_obj:
            clean_text = match_obj.group(0).strip()

    try:
        return json.loads(clean_text, strict=False)
    except Exception:
        pass
    return {}



def run_bot_curator(prompt: str, chat_history: List[Dict[str, str]]) -> str:
    """Menganalisis dan memindahkan materi catatan yang salah tempat."""
    print("\n🧹 [Vault Curator] Menganalisis pemindahan catatan...")

    vault_map = generate_or_get_vault_map()
    sys_prompt = (
        "Anda adalah kurator penataan berkas Obsidian.\n"
        f"{vault_map}\n\n"
        "TUGAS: Analisis teks yang ingin dipindahkan, lalu kembalikan HANYA format JSON murni (tanpa penjelasan tambahan):\n"
        '{"source_file": "file_asal.md", "target_file": "file_tujuan.md", "content_snippet": "isi teks", "target_section": "nama_section"}'
    )

    clean_history = [m for m in chat_history[-3:] if not m['content'].startswith('{')]
    messages = [{'role': 'system', 'content': sys_prompt}]
    messages.extend(clean_history)
    messages.append({'role': 'user', 'content': prompt})

    try:
        res = ollama.chat(
            model=config.MODEL_WRITER,
            messages=messages,
            options=config.OPTIONS_WRITER,
            keep_alive=config.KEEP_ALIVE_DEFAULT,
        )
        raw = res.message.content
        data = _extract_json(raw)
        if not data:
            return f"❌ Gagal memproses relokasi: model tidak mengembalikan JSON yang valid.\nRaw: {raw}"

        result = relocate_content(
            source_file=data.get("source_file", ""),
            target_file=data.get("target_file", ""),
            content_snippet=data.get("content_snippet", ""),
            target_section=data.get("target_section")
        )
        return result
    except Exception as e:
        return f"❌ Gagal memproses relokasi: {str(e)}"

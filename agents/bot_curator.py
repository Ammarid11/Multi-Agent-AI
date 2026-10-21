# agents/bot_curator.py
import json
import re
from typing import List, Dict
import ollama
import config
from tools.vault_indexer import generate_or_get_vault_map
from core import vault_io
from core.confirm import request_confirmation, confirmation_hint


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

        source_file = str(data.get("source_file", ""))
        target_file = str(data.get("target_file", ""))
        snippet = str(data.get("content_snippet", ""))
        src_path, src_error = vault_io.resolve_write_path(source_file)
        tgt_path, tgt_error = vault_io.resolve_write_path(target_file)
        if src_error or tgt_error:
            return f"❌ Rencana relokasi tidak valid: {src_error or tgt_error}"
        if not src_path.exists():
            return f"❌ File asal '{source_file}' tidak ditemukan."
        if not snippet.strip() or src_path.read_text(encoding="utf-8").replace("\r\n", "\n").count(snippet.strip().replace("\r\n", "\n")) != 1:
            return "❌ Cuplikan yang diusulkan tidak ditemukan tepat satu kali di file asal; tidak ada yang dipindahkan."

        payload = {
            "source_file": src_path.relative_to(vault_io.vault_root()).as_posix(),
            "target_file": tgt_path.relative_to(vault_io.vault_root()).as_posix(),
            "content_snippet": snippet,
            "target_section": data.get("target_section"),
        }
        code = request_confirmation("relocate", payload, "Relokasi materi catatan")
        preview = snippet.strip()[:200] + ("…" if len(snippet.strip()) > 200 else "")
        return (
            "🚚 **Rencana relokasi (belum dijalankan):**\n"
            f"- Dari: `{payload['source_file']}`\n- Ke: `{payload['target_file']}`"
            + (f" (bagian: {payload['target_section']})" if payload["target_section"] else "")
            + f"\n- Cuplikan: \"{preview}\"\n\n{confirmation_hint(code)}"
        )
    except Exception as e:
        return f"❌ Gagal memproses relokasi: {str(e)}"

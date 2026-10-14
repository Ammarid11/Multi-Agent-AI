# agents/bot_coder.py
from typing import List, Dict
import config
from agents.streaming import chat_with_optional_stream
from tools.tool_create_py import create_python_file

coder_tools = [create_python_file]


def run_bot_coder(prompt: str, chat_history: List[Dict[str, str]]) -> str:
    """Spesialis pembuatan kode dan skrip Python."""
    print(f"\n⚡ [Bot Coder ({config.MODEL_CODER})] Memproses kode...")

    sys_prompt = (
        "Anda adalah pakar pemrograman Python dan perangkat lunak.\n"
        "Buatlah kode yang bersih, efisien, rapi, dan berikan penjelasan singkat.\n\n"
        "ATURAN FORMAT KODE OBSIDIAN (WAJIB):\n"
        "1. SELALU bungkus kode dengan blok kode Markdown lengkap menggunakan triple backticks dan nama bahasa pemrograman (contoh: ```python\\n<kode>\\n```).\n"
        "2. DILARANG KERAS menulis kode program sebagai teks mentah biasa tanpa triple backticks.\n"
        "3. Pastikan penulisan sintaks dan indentasi 4 spasi terjaga rapi agar nyaman dibaca di Obsidian."
    )
    messages = [{'role': 'system', 'content': sys_prompt}]
    messages.extend(chat_history[-4:] if chat_history else [])
    messages.append({'role': 'user', 'content': prompt})

    res = chat_with_optional_stream(
        model=config.MODEL_CODER,
        messages=messages,
        options=config.OPTIONS_CODER,
        keep_alive=config.KEEP_ALIVE_SPECIALIST,
    )
    return res.message.content

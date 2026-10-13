# agents/bot_file_manager.py
import os
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import ollama
import config
from tools.tool_create import create_file
from tools.tool_append import append_file
from tools.tool_read import read_file
from tools.tool_delete import delete_file
from tools.vault_indexer import generate_or_get_vault_map

_SAVE_PREVIOUS_RESPONSE_PATTERNS = (
    re.compile(
        r"\b(?:catat|simpan|rekam|masukkan|buat(?:kan)?)\b"
        r".*\b(?:yang\s+di\s+atas|di\s+atas|tadi|sebelumnya|rangkuman|ringkasan|jawaban|ini)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:catat|simpan|rekam|masukkan)\b.*\bcatatan\s+baru\b",
        re.IGNORECASE,
    ),
)


def is_contextual_save_request(prompt: str) -> bool:
    """Identify save requests that refer to the prior assistant response."""
    return any(pattern.search(prompt) for pattern in _SAVE_PREVIOUS_RESPONSE_PATTERNS)


def _topic_from_recent_turns(chat_history: List[Dict[str, str]], response: str) -> str:
    """Extract a conservative title from explicit topic wording, else use a neutral title."""
    prior_user = next(
        (
            message["content"]
            for message in reversed(chat_history)
            if message.get("role") == "user" and message.get("content", "").strip()
        ),
        "",
    )
    candidates = [prior_user, response[:1200]]
    topic_pattern = re.compile(
        r"\b(?:tentang|mengenai|topik(?:nya)?\s*[:=])\s*[\"“]?([^\"”\n.!?:]+)",
        re.IGNORECASE,
    )
    for candidate in candidates:
        match = topic_pattern.search(candidate)
        if match:
            topic = re.sub(r"\s+", " ", match.group(1)).strip(" -*#")
            if topic:
                return topic[:60]
    return "Percakapan"


def _save_previous_response(chat_history: List[Dict[str, str]]) -> str:
    """Persist the latest assistant answer verbatim in a new, verified Vault note."""
    previous_response = next(
        (
            message["content"].strip()
            for message in reversed(chat_history)
            if message.get("role") == "assistant" and message.get("content", "").strip()
        ),
        "",
    )
    if not previous_response:
        return "⚠️ Belum ada jawaban sebelumnya untuk dicatat. Tidak ada file yang dibuat."

    topic = _topic_from_recent_turns(chat_history, previous_response)
    safe_topic = re.sub(r'[<>:"/\\|?*]', "", topic).strip(" .")[:60] or "Percakapan"
    title = f"Rangkuman - {safe_topic}"
    topic_tag = re.sub(r"[^\w-]+", "-", safe_topic.lower()).strip("-")
    vault_root = Path(config.VAULT_PATH).resolve()
    target_dir = vault_root / "00-Inbox"
    target_dir.mkdir(parents=True, exist_ok=True)

    created = datetime.now().astimezone().isoformat(timespec="seconds")
    tags = ["rangkuman-percakapan"]
    if topic_tag and topic_tag not in tags:
        tags.append(topic_tag)
    note_content = (
        "---\n"
        f"title: {json.dumps(title, ensure_ascii=False)}\n"
        f"created: {json.dumps(created)}\n"
        f'category: "Rangkuman"\n'
        "tags:\n"
        + "".join(f"  - {json.dumps(tag, ensure_ascii=False)}\n" for tag in tags)
        + f"---\n\n# {title}\n\n{previous_response}\n"
    )

    base_path = target_dir / f"{title}.md"
    filepath = base_path
    suffix = 1
    while True:
        try:
            with filepath.open("x", encoding="utf-8", newline="") as note_file:
                note_file.write(note_content)
            break
        except FileExistsError:
            suffix += 1
            filepath = target_dir / f"{title} ({suffix}).md"

    with filepath.open("r", encoding="utf-8", newline="") as note_file:
        persisted_content = note_file.read()
    if persisted_content != note_content or previous_response not in persisted_content:
        return (
            f"❌ File `{filepath.relative_to(vault_root).as_posix()}` dibuat, "
            "tetapi verifikasi isi gagal. Jangan anggap rangkuman sudah tersimpan dengan benar."
        )

    return (
        f"✅ Rangkuman jawaban sebelumnya berhasil dicatat dan diverifikasi di "
        f"`{filepath.relative_to(vault_root).as_posix()}`."
    )


def _extract_json(text: str) -> dict:
    """
    Ekstrak JSON dari respons model secara aman dan tahan terhadap
    unescaped newline / karakter kontrol markdown di dalam string JSON.
    """
    clean_text = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean_text, re.DOTALL)
    if match:
        clean_text = match.group(1).strip()
    else:
        match_obj = re.search(r"\{.*\}", clean_text, re.DOTALL)
        if match_obj:
            clean_text = match_obj.group(0).strip()

    # 1. Coba parse dengan strict=False (membolehkan literal newline/enter)
    try:
        return json.loads(clean_text, strict=False)
    except Exception:
        pass

    # 2. Robust Fallback Regex Parser jika tanda kutip terpotong
    parsed = {}
    action_m = re.search(r'"action"\s*:\s*"([^"]+)"', clean_text, re.IGNORECASE)
    if action_m:
        parsed["action"] = action_m.group(1).strip()

    filename_m = re.search(r'"filename"\s*:\s*"([^"]+)"', clean_text, re.IGNORECASE)
    if filename_m:
        parsed["filename"] = filename_m.group(1).strip()

    section_m = re.search(r'"section"\s*:\s*"([^"]+)"', clean_text, re.IGNORECASE)
    if section_m:
        parsed["section"] = section_m.group(1).strip()

    content_m = re.search(r'"content"\s*:\s*"(.*?)(?:"\s*,\s*"section"|"\s*,\s*"filename"|"\s*\}|\s*"$)', clean_text, re.DOTALL)
    if content_m:
        parsed["content"] = content_m.group(1).strip()
    elif '"content"' in clean_text:
        parts = clean_text.split('"content":', 1)
        if len(parts) > 1:
            raw_c = parts[1].strip().lstrip('"')
            if raw_c.endswith('"}') or raw_c.endswith('}'):
                raw_c = raw_c.rsplit('}', 1)[0].rstrip('"\n\r ')
            parsed["content"] = raw_c

    if parsed.get("action") and (parsed.get("filename") or parsed.get("content")):
        return parsed

    return {}


def _clean_filename(filename: str) -> str:
    """Membersihkan nama file dari kata sapaan asisten (Carl, Cart, Bot) yang tidak sengaja terbawa."""
    if not filename:
        return filename
    dirname = os.path.dirname(filename)
    basename = os.path.basename(filename)
    # Hapus kata 'Carl - ', 'Cart - ', 'Carl_', dll
    cleaned_base = re.sub(r'^(carl|cart|bot|asisten)\s*[-_:]*\s*', '', basename, flags=re.IGNORECASE).strip()
    return os.path.join(dirname, cleaned_base) if dirname else cleaned_base


def _dispatch_action(action: str, filename: str, content: str, section: Optional[str]) -> str:
    """Helper: Eksekusi tool berdasarkan aksi (Dictionary Dispatcher)."""
    clean_fn = _clean_filename(filename)
    actions = {
        "create": lambda: create_file(clean_fn, content),
        "append": lambda: append_file(clean_fn, content, section=section),
        "read": lambda: read_file(clean_fn),
        "delete": lambda: delete_file(clean_fn),
    }
    handler = actions.get(action)
    return handler() if handler else "❌ Aksi tidak dikenali."


def run_bot_file_manager(prompt: str, chat_history: List[Dict[str, str]]) -> str:
    """Mengeksekusi pembuatan, penambahan, pembacaan, atau penghapusan file di Vault."""
    print("\n⚙️ [Tool Agent] Menjalankan operasi file...")

    if is_contextual_save_request(prompt):
        try:
            return _save_previous_response(chat_history)
        except OSError as e:
            return f"❌ Gagal menyimpan rangkuman sebelumnya: {e}"

    today = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%A, %d %B %Y %H:%M WIB")
    vault_map = generate_or_get_vault_map()

    sys_prompt = (
        "Anda adalah asisten pengelola file Second Brain Obsidian.\n"
        f"WAKTU: {now_str}, HARI INI: {today}\n"
        f"{vault_map}\n\n"
        "ATURAN MEMBUAT FILE BARU (action: 'create'):\n"
        "1. NAMA FILE (filename): HANYA gunakan topik murni catatan (contoh: '01-Projects/Strategi Marketing 2026.md').\n"
        "   - DILARANG KERAS memasukkan nama Anda ('Carl') atau kata sapaan/perintah ke dalam nama file (Contoh SALAH: 'Carl - Strategi Marketing 2026.md')!\n"
        "2. Buat isi catatan (content) dengan struktur ringkas dan teratur.\n"
        "   - PENTING UNTUK TAGS OBSIDIAN: Tag WAJIB berupa kata teks alfabet (string). DILARANG menggunakan angka mentah tanpa huruf (contoh salah: 2026; contoh benar: bisnis atau rencana).\n\n"


        "ATURAN OPERASI PROFIL ORANG (03-Resources/Data Profil Orang Lain.md):\n"
        "1. MENAMBAH TEMAN / ORANG BARU (misal: 'tambahkan teman saya namanya dini'):\n"
        "   - filename: '03-Resources/Data Profil Orang Lain.md'\n"
        "   - section: Nama orang tersebut (misal: 'Dini') -> DILARANG isi section dengan 'Profil Orang Lain'!\n"
        "   - content format baku:\n"
        "     - **Nama Lengkap / Asli:** <Nama>\n"
        "     - **Nama Panggilan / Sosmed:** <Nama>\n"
        "     - **Hubungan:** Teman\n\n"
        "2. UPDATE DATA ORANG (misal: 'dia perempuan', 'umur 20'):\n"
        "   - filename: '03-Resources/Data Profil Orang Lain.md'\n"
        "   - section: Nama orang tersebut (misal: 'Dini')\n"
        "   - content: '- **Field:** Nilai'\n\n"
        "3. HANYA gunakan action 'read' jika pengguna SECARA EKSPLISIT meminta 'baca file' atau '/read'.\n\n"
        "Kembalikan HANYA JSON murni (tanpa penjelasan tambahan):\n"
        '{"action": "create"|"append"|"read"|"delete", "filename": "path/file.md", "content": "isi teks", "section": "NamaOrang"}'
    )

    clean_history = [m for m in chat_history[-4:] if not m['content'].startswith('{')]
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
            return f"❌ Gagal memproses perintah file: model tidak mengembalikan JSON yang valid.\nRaw: {raw}"

        if data.get("action") == "delete":
            return (
                "⚠️ Penghapusan tidak dijalankan dari interpretasi model. "
                "Pastikan target secara eksplisit, lalu gunakan `/delete path/di-vault.md`."
            )

        result = _dispatch_action(
            action=data.get("action", "append"),
            filename=data.get("filename", "03-Resources/Data Profil Orang Lain.md"),
            content=data.get("content", prompt),
            section=data.get("section")
        )
        return result
    except Exception as e:
        return f"❌ Gagal memproses perintah file: {str(e)}"

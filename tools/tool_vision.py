# tools/tool_vision.py
"""
Frontier D: Multi-Modal Vision & PDF Document Ingestion.
Menyediakan kemampuan analisis dokumen visual:
- Ekstraksi teks & tabel dari berkas PDF (pypdf) langsung menjadi catatan Obsidian Properties.
- Analisis gambar/screenshot/diagram arsitektur via model vision lokal (Ollama llava / qwen2.5-vl).
"""

import os
import sys
import base64
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from PIL import Image
import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from config import VAULT_PATH, OLLAMA_HOST
from core import vault_io

_ALLOWED_SUFFIXES = {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tif', '.tiff'}


def _allowed_roots() -> List[Path]:
    roots = [Path(VAULT_PATH), Path(config.WORKSPACE_PATH), *(Path(d) for d in config.INPUT_ALLOWED_DIRS)]
    resolved = []
    for root in roots:
        try:
            resolved.append(root.resolve())
        except OSError:
            continue
    return resolved


def _is_allowed_input(path: Path) -> bool:
    """Hanya berkas PDF/gambar di dalam Vault, folder kerja, atau CARL_INPUT_DIRS; tidak boleh di 04-Secure."""
    try:
        resolved = path.resolve()
    except OSError:
        return False
    if resolved.suffix.lower() not in _ALLOWED_SUFFIXES or not resolved.is_file():
        return False
    if vault_io.is_blocked_path(resolved):
        return False
    return any(vault_io.is_inside(root, resolved) for root in _allowed_roots())


def _find_file_path(filename: str) -> Optional[Path]:
    """Mencari berkas yang DIIZINKAN. Path di luar folder yang diizinkan diperlakukan sebagai tidak ditemukan."""
    clean = filename.strip(' "\'')
    if not clean:
        return None
    p = Path(clean)
    if p.exists() and _is_allowed_input(p):
        return p

    inbox_p = Path(VAULT_PATH) / "00-Inbox" / p.name
    if inbox_p.exists() and _is_allowed_input(inbox_p):
        return inbox_p

    wanted = p.name.lower()
    for root, dirs, files in os.walk(VAULT_PATH):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d.casefold() not in vault_io.BLOCKED_DIRS]
        for f in files:
            if f.lower() == wanted:
                candidate = Path(root) / f
                if _is_allowed_input(candidate):
                    return candidate
    return None


def _get_available_vision_model() -> Optional[str]:
    """Memeriksa apakah ada model vision yang terpasang di Ollama lokal."""
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        if resp.status_code == 200:
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            for candidate in ["qwen2.5-vl:7b", "llava:7b", "llama3.2-vision:11b", "llava:latest", "bakllava:latest"]:
                for m in models:
                    if candidate in m.lower():
                        return m
    except Exception:
        pass
    return None


def ingest_pdf(pdf_path_str: str, folder_target: str = "03-Resources") -> Dict[str, Any]:
    """
    Mengekstrak seluruh teks dan metadata dari berkas PDF dan merapikannya
    menjadi catatan Obsidian terstruktur dengan Frontmatter YAML.
    """
    file_path = _find_file_path(pdf_path_str)
    if not file_path or not file_path.exists():
        return {"success": False, "error": f"Berkas PDF tidak ditemukan atau berada di luar folder yang diizinkan (Vault, folder kerja, CARL_INPUT_DIRS): '{pdf_path_str}'"}

    try:
        from pypdf import PdfReader
        reader = PdfReader(str(file_path))
        num_pages = len(reader.pages)
        if num_pages == 0:
            return {"success": False, "error": "Berkas PDF kosong (0 halaman)."}

        # Ekstrak teks per halaman
        extracted_sections: List[str] = []
        total_words = 0
        for i, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            cleaned = re.sub(r'[ \t]+', ' ', text).strip()
            if cleaned:
                total_words += len(cleaned.split())
                extracted_sections.append(f"### 📄 Halaman {i}\n\n{cleaned}")

        # Buat judul catatan
        stem_name = file_path.stem
        safe_title = re.sub(r'[\\/*?:"<>|]', '', stem_name).strip()[:60]
        note_filename = f"Dokumen - {safe_title}.md"

        target_dir = Path(VAULT_PATH) / folder_target
        target_dir.mkdir(parents=True, exist_ok=True)
        note_path = target_dir / note_filename

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        content = (
            f"---\n"
            f"created: {now}\n"
            f"type: pdf-document\n"
            f"source_file: {file_path.name}\n"
            f"total_pages: {num_pages}\n"
            f"total_words: {total_words}\n"
            f"tags:\n"
            f"  - referensi\n"
            f"  - dokumen-pdf\n"
            f"---\n\n"
            f"# 📑 {safe_title}\n\n"
            f"> Diekstrak otomatis oleh Carl PDF Parser pada {now}.\n"
            f"- **Berkas Asli:** `{file_path.name}`\n"
            f"- **Jumlah Halaman:** {num_pages} halaman\n"
            f"- **Estimasi Kata:** ~{total_words} kata\n\n"
            f"## 📖 Ringkasan & Isi Dokumen\n\n"
            + "\n\n".join(extracted_sections[:30])  # Maksimal 30 halaman awal
        )

        vault_io.atomic_write(note_path, content)

        msg = (
            f"📑 **Ekstraksi Dokumen PDF Sukses!**\n\n"
            f"- **Catatan Dibuat:** `[[{note_filename.replace('.md', '')}]]`\n"
            f"- **Lokasi:** `{folder_target}/{note_filename}`\n"
            f"- **Jumlah Halaman:** {num_pages} halaman ({total_words} kata)\n"
            f"- **Metadata:** Dilengkapi Frontmatter YAML & tag `#dokumen-pdf`."
        )

        return {
            "success": True,
            "message": msg,
            "note_path": str(note_path),
            "pages": num_pages,
            "words": total_words
        }

    except Exception as e:
        return {"success": False, "error": f"Gagal mengekstrak PDF: {str(e)}"}


def analyze_image(image_path_str: str, user_prompt: str = "") -> Dict[str, Any]:
    """
    Menganalisis gambar/diagram/screenshot menggunakan model vision lokal Ollama (jika tersedia),
    serta membuat catatan visual terlampir di Obsidian.
    """
    file_path = _find_file_path(image_path_str)
    if not file_path or not file_path.exists():
        return {"success": False, "error": f"Berkas gambar tidak ditemukan atau berada di luar folder yang diizinkan (Vault, folder kerja, CARL_INPUT_DIRS): '{image_path_str}'"}

    try:
        # 1. Baca metadata gambar dengan Pillow
        with Image.open(str(file_path)) as img:
            width, height = img.size
            img_format = img.format
            img_mode = img.mode

        file_size_kb = round(file_path.stat().st_size / 1024, 1)

        # 2. Salin gambar ke folder lampiran Obsidian agar bisa dilihat via ![[...]]
        attachments_dir = Path(VAULT_PATH) / "00-Inbox" / "Attachments"
        attachments_dir.mkdir(parents=True, exist_ok=True)
        dest_img_path = attachments_dir / file_path.name
        if dest_img_path.resolve() != file_path.resolve():
            shutil.copy2(file_path, dest_img_path)

        # 3. Cek ketersediaan model vision di Ollama
        vision_model = _get_available_vision_model()
        ai_description = ""

        if vision_model:
            print(f"👁️ [Carl Vision] Menganalisis gambar menggunakan model: {vision_model}...")
            with open(file_path, "rb") as f:
                b64_image = base64.b64encode(f.read()).decode("utf-8")

            prompt = user_prompt or (
                "Jelaskan isi gambar ini secara detail dan terstruktur dalam Bahasa Indonesia. "
                "Jika ada teks, transkripsikan (OCR). Jika ada diagram/arsitektur, jelaskan komponen dan alurnya."
            )

            payload = {
                "model": vision_model,
                "prompt": prompt,
                "images": [b64_image],
                "stream": False,
                "options": {"temperature": 0.2}
            }

            resp = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=90)
            if resp.status_code == 200:
                ai_description = resp.json().get("response", "").strip()

        # 4. Buat catatan Obsidian
        safe_title = re.sub(r'[\\/*?:"<>|]', '', file_path.stem).strip()[:50]
        note_filename = f"Visual - {safe_title}.md"
        target_dir = Path(VAULT_PATH) / "00-Inbox"
        note_path = target_dir / note_filename

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        desc_body = ai_description if ai_description else (
            f"*Gambar berhasil dilampirkan ke Vault.* \n\n"
            f"> 💡 **Tips AI Vision:** Model vision lokal belum terpasang di Ollama Anda.\n"
            f"> Untuk mengaktifkan OCR & analisis otomatis visual, ketik di terminal: `ollama run llava:7b`"
        )

        content = (
            f"---\n"
            f"created: {now}\n"
            f"type: visual-note\n"
            f"resolution: {width}x{height}\n"
            f"size_kb: {file_size_kb}\n"
            f"tags:\n"
            f"  - visual\n"
            f"  - screenshot\n"
            f"---\n\n"
            f"# 🖼️ {safe_title}\n\n"
            f"![[{file_path.name}]]\n\n"
            f"### 📋 Metadata Gambar\n"
            f"- **Dimensi:** {width} x {height} piksel\n"
            f"- **Format:** {img_format} ({img_mode})\n"
            f"- **Ukuran:** {file_size_kb} KB\n\n"
            f"### 🔍 Analisis Visual AI\n"
            f"{desc_body}\n"
        )

        vault_io.atomic_write(note_path, content)

        msg = (
            f"👁️ **Analisis Visual Berhasil!**\n\n"
            f"- **Catatan Dibuat:** `[[{note_filename.replace('.md', '')}]]`\n"
            f"- **Dimensi:** {width} x {height} piksel ({file_size_kb} KB)\n"
            f"- **Lampiran:** Disimpan ke `00-Inbox/Attachments/{file_path.name}`\n\n"
            f"{'🧠 **Hasil Analisis AI:**\n' + ai_description if ai_description else '*(Catatan visual telah terindeks rapi di 00-Inbox)*'}"
        )

        return {
            "success": True,
            "message": msg,
            "note_path": str(note_path),
            "dimensions": f"{width}x{height}",
            "ai_description": ai_description
        }

    except Exception as e:
        return {"success": False, "error": f"Gagal menganalisis gambar: {str(e)}"}


def run_vision_command(query: str) -> str:
    """Wrapper untuk dieksekusi via slash command /vision atau /pdf."""
    clean = query.strip()
    if not clean:
        return "❌ Format perintah: `/vision <nama_berkas_gambar_atau_pdf>` (contoh: `/vision screenshot.png` atau `/vision ebook.pdf`)"

    low = clean.lower()
    if low.endswith(".pdf"):
        res = ingest_pdf(clean)
    else:
        # Asumsikan gambar
        res = analyze_image(clean)

    if res["success"]:
        return res["message"]
    return f"❌ {res.get('error', 'Terjadi kesalahan sistem visual')}"


if __name__ == "__main__":
    print("Menguji modul Vision & PDF Parser...")
    # Uji deteksi model
    m = _get_available_vision_model()
    print("Model Vision lokal terdeteksi:", m or "Belum ada (Fallback metadata mode aktif)")


# tools/clean_markdown.py
import os
import re
import glob
from datetime import datetime
from typing import Optional, Tuple
import ollama
import config
from core import vault_io


def _resolve_markdown_file(filename: str) -> Tuple[Optional[str], Optional[str]]:
    """Resolve only exact Markdown paths; never guess between duplicate notes."""
    vault_path = os.path.realpath(config.VAULT_PATH)
    requested = filename.strip().strip("'\"")
    if not requested.lower().endswith(".md"):
        requested += ".md"

    def _inside_vault(path: str) -> bool:
        try:
            return os.path.commonpath(
                [os.path.normcase(vault_path), os.path.normcase(os.path.realpath(path))]
            ) == os.path.normcase(vault_path)
        except ValueError:
            return False

    if os.path.isabs(requested):
        candidate = os.path.realpath(requested)
        if not _inside_vault(candidate):
            return None, "Path file harus berada di dalam Vault."
        if os.path.isfile(candidate):
            return candidate, None
        return None, f"File '{filename}' tidak ditemukan."

    relative = requested.replace("\\", os.sep).replace("/", os.sep)
    candidate = os.path.realpath(os.path.join(vault_path, relative))
    if not _inside_vault(candidate):
        return None, "Path file harus berada di dalam Vault."
    if os.path.isfile(candidate):
        return candidate, None
    if os.path.dirname(relative) not in ("", "."):
        return None, f"File '{filename}' tidak ditemukan pada path tersebut."

    matches = [
        os.path.realpath(path)
        for path in glob.glob(os.path.join(vault_path, "**", os.path.basename(relative)), recursive=True)
        if os.path.isfile(path) and _inside_vault(path)
    ]
    if len(matches) > 1:
        paths = sorted(os.path.relpath(path, vault_path).replace("\\", "/") for path in matches)
        return None, (
            f"⚠️ Ada beberapa catatan bernama '{os.path.basename(relative)}'; tidak ada yang diubah. "
            "Kirim path Vault lengkap:\n- " + "\n- ".join(paths)
        )
    if matches:
        return matches[0], None
    return None, f"File '{filename}' tidak ditemukan."


def _write_and_verify(filepath: str, content: str) -> None:
    """Tulis atomik (snapshot versi lama, bisa /undo) lalu verifikasi byte hasil tulis."""
    vault_io.atomic_write(filepath, content.rstrip() + "\n")


_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
_NUMBER_RE = re.compile(r"(?<![\w.])\d{2,}(?:[.,]\d+)?(?![\w])")


def _content_preserved(original: str, cleaned: str) -> Optional[str]:
    """Kembalikan alasan penolakan bila hasil LLM menghilangkan tautan, blok kode, atau angka dari catatan asli."""
    orig_links = {m.strip().casefold() for m in _WIKILINK_RE.findall(original)}
    new_links = {m.strip().casefold() for m in _WIKILINK_RE.findall(cleaned)}
    if orig_links - new_links:
        return f"wikilink hilang: {', '.join(sorted(orig_links - new_links)[:3])}"
    if original.count("```") > cleaned.count("```"):
        return "blok kode berkurang"
    orig_body = re.sub(r"\A---.*?\n---\s*", "", original, count=1, flags=re.DOTALL)
    missing = set(_NUMBER_RE.findall(orig_body)) - set(_NUMBER_RE.findall(cleaned))
    if missing:
        return f"angka hilang: {', '.join(sorted(missing)[:3])}"
    return None


def _clean_katex_and_dom_artifacts(text: str) -> str:
    """Membersihkan artefak DOM KaTeX yang terpecah banyak baris dan memformat kode program."""
    # 1. Satuan derajat Celsius: 0\n°\nC -> 0°C
    text = re.sub(r'(\d+)\s*\n\s*°\s*\n\s*([CcFfKk])', r'\1°\2', text)
    text = re.sub(r'(\d+)\s*°\s*\n\s*([CcFfKk])', r'\1°\2', text)

    # 2. Simbol matematika split 1-huruf dalam tanda kurung: (\n𝑚\nm) -> (m)
    text = re.sub(r'\(\s*\n\s*([a-zA-Z])\s*\n\s*([a-zA-Z])\s*\)', r'(\2)', text)
    # Split 2-huruf: (\n𝑘\n𝑔\nkg) -> (kg)
    text = re.sub(r'\(\s*\n\s*[a-zA-Z]\s*\n\s*[a-zA-Z]\s*\n\s*([a-zA-Z]{1,4})\s*\)', r'(\1)', text)

    # 3. Format kode pemrograman yang belum dibungkus Markdown code block
    from agents.gemini_browser import fix_unfenced_code_blocks
    text = fix_unfenced_code_blocks(text)

    # 4. Hapus baris kosong berlebih (> 2 baris kosong berturut-turut)
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    return text


def clean_and_refactor_file(filename: str) -> str:
    """Merapikan format Markdown catatan, menambahkan frontmatter, dan interlink."""
    filepath, resolve_error = _resolve_markdown_file(filename)
    if resolve_error:
        return resolve_error
    if filepath is None:
        return f"❌ File '{filename}' tidak ditemukan."

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        if not content.strip():
            return f"⚠️ File '{os.path.basename(filepath)}' kosong."

        orig_created_match = re.search(r'created:\s*([^\n\r]+)', content)
        orig_created = orig_created_match.group(1).strip() if orig_created_match else datetime.now().strftime("%Y-%m-%d %H:%M")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        # ── JIKA DOKUMEN SANGAT BESAR (> 8.000 karakter) ──
        # Hindari men-generate ulang seluruh file via LLM karena pasti terkena batas token output (<40%).
        # Gunakan Pembersihan Struktural Preservasi Aman:
        if len(content) > 8000:
            cleaned = _clean_katex_and_dom_artifacts(content)
            body_format_changed = cleaned != content

            # Sanitasi frontmatter
            if cleaned.startswith("---"):
                if "updated:" not in cleaned:
                    cleaned = cleaned.replace("created:", f"updated: {now_str}\ncreated:", 1)
                else:
                    cleaned = re.sub(r'updated:\s*[^\n\r]+', f'updated: {now_str}', cleaned, count=1)
            else:
                title_match = re.search(r'^#\s*(.+)$', cleaned, re.MULTILINE)
                doc_title = title_match.group(1).strip() if title_match else os.path.splitext(os.path.basename(filepath))[0]
                frontmatter = (
                    f"---\n"
                    f"title: \"{doc_title}\"\n"
                    f"created: {orig_created}\n"
                    f"updated: {now_str}\n"
                    f"tags:\n"
                    f"  - second-brain\n"
                    f"  - curated-notes\n"
                    f"---\n\n"
                )
                cleaned = frontmatter + cleaned

            # Sanitasi tags Obsidian (cegah angka mentah tanpa huruf)
            def _sanitize_tags(match):
                tag_block = match.group(0)
                return re.sub(r'(?<=[\[,\s-])(\d{4})(?=[\]\s,\n])', r'tahun-\1', tag_block)

            cleaned = re.sub(r'tags:\s*(\[[^\]]+\]|(\n\s*-\s*[^\n]+)+)', _sanitize_tags, cleaned)

            # Pastikan interlink Catatan Terkait ada di akhir file
            if "## 🔗 Catatan Terkait" not in cleaned:
                cleaned = cleaned.rstrip() + "\n\n---\n\n## 🔗 Catatan Terkait\n- [[00-Index|Index Utama Vault]]\n"

            _write_and_verify(filepath, cleaned)

            changes = []
            if body_format_changed:
                changes.append("normalisasi format aman diterapkan pada isi materi")
            if not content.startswith("---"):
                changes.append("frontmatter ditambahkan")
            if "## 🔗 Catatan Terkait" not in content:
                changes.append("bagian Catatan Terkait ditambahkan")
            if not changes:
                changes.append("tidak ada perubahan format yang terdeteksi")
            result = (
                f"✅ **Pemrosesan aman '{os.path.basename(filepath)}' selesai dan hasil tulis terverifikasi.**\n\n"
                f"Dokumen besar ({len(content):,} karakter) diproses tanpa penulisan ulang atau peringkasan oleh AI. "
                f"Perubahan: {', '.join(changes)}."
            )
            if not body_format_changed:
                result += (
                    "\n\n⚠️ Isi materi tidak diubah oleh aturan format aman; dokumen mungkin masih memerlukan "
                    "perapihan isi secara manual."
                )
            return result

        # ── JIKA DOKUMEN BERUKURAN STANDAR (<= 8.000 karakter) ──
        sys_prompt = (
            "Anda adalah asisten perapihan format Obsidian Markdown.\n"
            "TUGAS: Rapikan catatan berikut dengan format baku Obsidian Properties:\n"
            "1. Frontmatter YAML di baris pertama:\n"
            "   ---\n"
            "   title: <Judul>\n"
            f"   created: {orig_created}\n"
            f"   updated: {now_str}\n"
            "   tags:\n"
            "     - <tag1>\n"
            "     - <tag2>\n"
            "   kategori: <NamaKategori>\n"
            "   ---\n"
            "   ATURAN TAG OBSIDIAN: Wajib berupa kata huruf kecil (string). DILARANG menggunakan angka mentah tanpa huruf (contoh salah: 2026; contoh benar: tahun-2026 atau bisnis).\n"
            "2. Judul utama: '# <Emoji> Judul'\n"
            "3. Poin-poin rapi dengan bullet points\n"
            "4. Bagian '## 🔗 Catatan Terkait' HARUS berada di akhir file, berisi list interlink [[Nama Catatan]].\n"
            "5. FORMAT KODE PEMROGRAMAN: Seluruh cuplikan kode pemrograman WAJIB dibungkus dalam blok kode Markdown dengan triple backticks dan nama bahasanya (contoh: ```python\\n<kode>\\n```). DILARANG menulis kode sebagai teks biasa.\n"
            "KEMBALIKAN HANYA MARKDOWN MURNI TANPA KOMENTAR APAPUN."
        )

        res = ollama.chat(
            model=config.MODEL_WRITER,
            messages=[
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': content},
            ],
            options=config.OPTIONS_CLEANER,
            keep_alive=config.KEEP_ALIVE_DEFAULT,
        )
        cleaned = res.message.content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r'^```\w*\n|```$', '', cleaned).strip()

        try:
            from agents.gemini_browser import fix_unfenced_code_blocks
            cleaned = fix_unfenced_code_blocks(cleaned)
        except Exception:
            pass

        # Pastikan created timestamp asli selalu ada di frontmatter
        if cleaned.startswith("---"):
            if "created:" in cleaned:
                cleaned = re.sub(r'created:\s*[^\n\r]+', f'created: {orig_created}', cleaned, count=1)
            else:
                cleaned = cleaned.replace("---", f"---\ncreated: {orig_created}", 1)
        else:
            cleaned = f"---\ncreated: {orig_created}\n---\n\n{cleaned}"

        def _sanitize_tags(match):
            tag_block = match.group(0)
            return re.sub(r'(?<=[\[,\s-])(\d{4})(?=[\]\s,\n])', r'tahun-\1', tag_block)

        cleaned = re.sub(r'tags:\s*(\[[^\]]+\]|(\n\s*-\s*[^\n]+)+)', _sanitize_tags, cleaned)

        # Validasi Keselamatan: Batalkan penimpaan jika respons AI terpotong drastis
        if len(content.strip()) > 150 and len(cleaned) < (len(content.strip()) * 0.7):
            return f"⚠️ Pembatalan aman: Hasil dari AI terdeteksi terpotong (<70% panjang asli) pada '{os.path.basename(filepath)}'. Catatan asli tetap aman."
        reason = _content_preserved(content, cleaned)
        if reason:
            return f"⚠️ Pembatalan aman: hasil AI mengubah isi catatan ({reason}) pada '{os.path.basename(filepath)}'. Catatan asli tetap aman."

        _write_and_verify(filepath, cleaned)

        return f"✅ '{os.path.basename(filepath)}' berhasil diproses dan hasil tulis terverifikasi."
    except Exception as e:
        return f"❌ Gagal merapikan '{filename}': {str(e)}"

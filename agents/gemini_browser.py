"""
Frontier P: Gemini Browser Bridge Agent.
Memungkinkan Carl (AI Lokal Second Brain) berdialog langsung dengan Google Gemini
di browser (gemini.google.com) menggunakan Playwright dengan profil persisten.
"""

import os
import sys
import time
import random
import re
import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from playwright.sync_api import sync_playwright, Page, BrowserContext

import config
from tools.tool_create import create_file

import threading

PROFILE_DIR = os.path.join(config.DB_PATH, "gemini_browser_profile")
GEMINI_URL = "https://gemini.google.com/app"

_STOP_EVENT = threading.Event()
_ACTIVE_SESSION: Optional['GeminiBrowserSession'] = None


def request_stop_tutoring() -> None:
    """Memicu sinyal berhenti manual pada sesi les Carl & Gemini yang sedang berjalan."""
    _STOP_EVENT.set()
    print("\n🛑 [Carl Academy] Sinyal BERHENTI manual diterima dari pengguna!")
    global _ACTIVE_SESSION
    if _ACTIVE_SESSION:
        try:
            print("🛑 [Carl Academy] Menutup browser Gemini secara instan...")
            _ACTIVE_SESSION.close()
        except Exception as e:
            print(f"⚠️ Gagal menutup browser aktif: {e}")


def reset_stop_tutoring() -> None:
    """Mereset sinyal berhenti sebelum sesi les baru dimulai."""
    _STOP_EVENT.clear()


def is_stop_requested() -> bool:
    """Mengecek apakah sesi les diminta berhenti secara manual."""
    return _STOP_EVENT.is_set()


def is_browser_closed_error(err: object) -> bool:
    """
    Mengecek secara komprehensif apakah exception terjadi akibat jendela/tab browser ditutup.
    Mencakup pesan Playwright: 'Target page, context or browser has been closed', 'Locator.fill', dll.
    """
    msg = str(err).lower()
    return (
        "has been closed" in msg
        or "target page" in msg
        or "target closed" in msg
        or "page closed" in msg
        or "browser closed" in msg
        or "context or browser has been closed" in msg
        or "session closed" in msg
        or "connection closed" in msg
        or "context was destroyed" in msg
        or "locator.fill" in msg
        or ("closed" in msg and any(k in msg for k in ["target", "page", "browser", "context", "locator"]))
    )


def ensure_safe_for_asyncio(fn):
    """
    Decorator pelindung: Memastikan fungsi Playwright Sync dieksekusi dalam
    thread terisolasi bersih jika dipanggil dari dalam asyncio loop (FastAPI / Uvicorn).
    Mencegah error 'It looks like you are using Playwright Sync API inside the asyncio loop'.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            with ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(fn, *args, **kwargs).result()
        return fn(*args, **kwargs)
    return wrapper


def _get_best_browser_channel() -> Tuple[str, Optional[str]]:
    """Mendeteksi apakah Chrome atau Edge tersedia di sistem Windows."""
    # Prioritaskan msedge karena bawaan Windows 10/11
    return ("msedge", None)


_CODE_LANG_PATTERN = re.compile(
    r'^(Python|JavaScript|TypeScript|HTML|CSS|Bash|SQL|Java|C\+\+|C#|PHP|Go|Rust|Kotlin|Dart|Ruby|Swift|JSON|YAML|XML|R|Perl|Scala)'
    r'(?:\s*(?:Salin\s*kode|Salin|Copy\s*code|Copy))?'
    r'(?:\s*(.*))?$',
    re.IGNORECASE
)

_CODE_KEYWORDS = {
    "def", "class", "import", "from", "if", "elif", "else", "for", "while",
    "return", "print", "try", "except", "finally", "with", "as", "pass",
    "lambda", "yield", "assert", "raise", "const", "let", "var", "function",
    "public", "private", "protected", "interface", "export", "package",
    "select", "insert", "update", "delete", "create", "alter",
    "fn", "mut", "impl", "struct", "enum", "func", "echo", "#include"
}

_CODE_STOP_INDICATORS = [
    "penjelasan", "output", "hasil", "catatan", "keterangan",
    "contoh output", "cara kerja", "analisis", "ringkasan"
]


def _is_probable_code_line(line: str) -> bool:
    """Memeriksa apakah satu baris teks tampak seperti baris kode program."""
    s = line.strip()
    if not s:
        return False
    if any(c in s for c in ["=", "(", ")", "{", "}", "[", "]", ";", ":", "<", ">", "$"]):
        return True
    first_word = s.split()[0].lower()
    if first_word in _CODE_KEYWORDS:
        return True
    return False


def fix_unfenced_code_blocks(text: str) -> str:
    """
    Mendeteksi kode yang diekstraksi tanpa blok Markdown dari antarmuka Gemini
    (misal: 'Pythonnilai = 80') dan membungkusnya rapi ke format code block Markdown Obsidian:
    ```python
    nilai = 80
    ...
    ```
    """
    if not text:
        return text

    lines = text.split('\n')
    output = []
    i = 0
    in_code_fence = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            output.append(line)
            i += 1
            continue

        if in_code_fence:
            output.append(line)
            i += 1
            continue

        m = _CODE_LANG_PATTERN.match(stripped)
        is_code_start = False
        lang_name = ""
        first_code_line = ""

        if m:
            matched_lang = m.group(1)
            lang_lower = matched_lang.lower()
            if lang_lower == "c++":
                lang_lower = "cpp"
            elif lang_lower == "c#":
                lang_lower = "csharp"

            remainder = m.group(2) if m.group(2) else ""

            if remainder:
                rem_cleaned = re.sub(r'^(?:Salin\s*kode|Salin|Copy\s*code|Copy)\s*', '', remainder, flags=re.IGNORECASE).strip()
                if lang_lower == "python":
                    # Tangani fusi huruf 'n' dari kata 'Python' dengan nama variabel: Pytho(n) + (n)ilai -> Pythonilai
                    if rem_cleaned.startswith("ilai"):
                        rem_cleaned = "n" + rem_cleaned
                    elif rem_cleaned.startswith("ama") and (len(rem_cleaned) == 3 or not rem_cleaned[3].isalpha()):
                        rem_cleaned = "n" + rem_cleaned
                    elif rem_cleaned.startswith("omor") and (len(rem_cleaned) == 4 or not rem_cleaned[4].isalpha()):
                        rem_cleaned = "n" + rem_cleaned

                if rem_cleaned:
                    if _is_probable_code_line(rem_cleaned):
                        is_code_start = True
                        lang_name = lang_lower
                        first_code_line = rem_cleaned
                else:
                    if i + 1 < len(lines) and _is_probable_code_line(lines[i + 1]):
                        is_code_start = True
                        lang_name = lang_lower
                        first_code_line = ""
            else:
                if i + 1 < len(lines) and _is_probable_code_line(lines[i + 1]):
                    is_code_start = True
                    lang_name = lang_lower
                    first_code_line = ""

        if is_code_start:
            code_lines = []
            if first_code_line:
                code_lines.append(first_code_line)

            j = i + 1
            while j < len(lines):
                cur = lines[j]
                cur_strip = cur.strip()

                if not cur_strip:
                    if j + 1 < len(lines):
                        nxt_strip = lines[j + 1].strip().lower()
                        if nxt_strip.startswith(("#", "###", "##")) or any(nxt_strip.startswith(s) for s in _CODE_STOP_INDICATORS):
                            break
                        if re.match(r'^\d+\.\s+[A-Za-z]', lines[j + 1].strip()):
                            break
                        if re.match(r'^(fungsi|kode|program|skrip|script|pada contoh|dalam contoh|dalam kode)\s+', nxt_strip):
                            break
                    if j + 1 < len(lines) and not lines[j + 1].strip():
                        break
                    code_lines.append("")
                    j += 1
                    continue

                # Hentikan jika baris adalah penomoran bab (misal: "4. Perulangan (Loops)")
                if re.match(r'^\d+\.\s+[A-Za-z]', cur_strip):
                    break

                cur_lower = cur_strip.lower()
                if cur_strip.startswith(("#", "###", "##")) or any(cur_lower.startswith(s) for s in _CODE_STOP_INDICATORS):
                    break

                if re.match(r'^(fungsi|kode|program|skrip|script|pada contoh|dalam contoh|dalam kode)\s+', cur_lower):
                    break

                if not cur.startswith(" ") and not cur.startswith("\t") and not _is_probable_code_line(cur_strip):
                    break

                code_lines.append(cur)
                j += 1

            # Auto-indentation untuk Python jika indentasi hilang akibat DOM flattening
            if lang_name == "python":
                formatted_code = []
                indent_level = 0
                for cline in code_lines:
                    c_stripped = cline.strip()
                    if not c_stripped:
                        formatted_code.append("")
                        continue

                    if re.match(r'^(elif\b|else:|except\b|finally:)', c_stripped):
                        curr_indent = max(0, indent_level - 1)
                    else:
                        curr_indent = indent_level

                    formatted_code.append("    " * curr_indent + c_stripped)

                    if c_stripped.endswith(":"):
                        indent_level = curr_indent + 1
                code_lines = formatted_code

            code_block_md = f"```{lang_name}\n" + "\n".join(code_lines).rstrip() + "\n```"
            output.append(code_block_md)
            i = j
            continue

        output.append(line)
        i += 1

    return '\n'.join(output)


def clean_gemini_response_text(text: str) -> str:
    """
    Merapikan artefak DOM/KaTeX dari Gemini agar persamaan matematika,
    simbol operator, blok kode pemrograman, dan format Markdown menjadi rapi.
    """
    if not text:
        return ""

    # 1. Bersihkan operator ganda terpisah baris: (\n+\n+) -> (+)
    text = re.sub(
        r'\(\s*\n?\s*([+\-×÷*/=.,−⋅])\s*\n?\s*\1\s*(atau\s*\n?\s*[+\-×÷*/=.,−⋅]\s*\n?\s*[+\-×÷*/=.,−⋅])?\s*\):',
        lambda m: f'({m.group(1)}):',
        text
    )
    text = re.sub(r'\(\s*\n?\s*([+\-×÷*/=.,−⋅])\s*\n?\s*\):', r'(\1):', text)

    # 2. Gabungkan token rumus matematika yang terpecah per baris (misal: 5 \n + \n 3 \n = \n 8)
    lines = [l.rstrip() for l in text.split('\n')]
    merged = []
    i = 0
    math_token_pattern = re.compile(r'^[0-9a-zA-Z+\-×÷*/=.,\(\)−⋅…]+$')

    while i < len(lines):
        line = lines[i].strip()
        if line and math_token_pattern.match(line) and len(line) <= 4:
            math_group = [line]
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if nxt and math_token_pattern.match(nxt) and len(nxt) <= 4:
                    math_group.append(nxt)
                    j += 1
                else:
                    # Lewati jika baris tepat setelahnya adalah salinan formula lengkap duplicate
                    if nxt and math_token_pattern.match(nxt) and len(nxt) <= 15:
                        j += 1
                    break
            if len(math_group) > 1:
                merged_line = ' '.join(math_group)
                merged_line = re.sub(r'\s*([+\-×÷*/=−⋅])\s*', r' \1 ', merged_line)
                merged_line = re.sub(r'\s+', ' ', merged_line).strip()
                merged.append(merged_line)
                i = j
                continue
        merged.append(lines[i])
        i += 1

    res = '\n'.join(merged)

    # 3. Perbaiki simbol derajat/suhu yang terpecah DOM: "0\n°\nC" → "0°C"
    #    Pola: angka + newline + ° + newline + satuan (C/F/K)
    res = re.sub(r'(\d+)\s*\n\s*°\s*\n\s*([CFK])\b', r'\1°\2', res)
    res = re.sub(r'(\d+)\s*°\s*\n\s*([CFK])\b', r'\1°\2', res)
    res = re.sub(r'(\d+)\n°([CFK])\b', r'\1°\2', res)

    # 4. Bersihkan "C 0\n°\nC" artifacts: angka, huruf, newline berulang untuk suhu
    res = re.sub(r'([CFK])\s*(\d+)\s*\n\s*°\s*\n\s*([CFK])\b', r'\2°\3', res)

    # 5. Hapus baris duplikat yang persis sama di bawahnya
    res = re.sub(r'([^\n]+)\n\s*\1', r'\1', res)

    # 6. Format code blocks yang belum memiliki backticks
    res = fix_unfenced_code_blocks(res)

    # 7. Normalisasi spasi/enter berlebihan
    res = re.sub(r'\n{3,}', '\n\n', res)
    return res.strip()



class GeminiBrowserSession:
    """Mengelola sesi browser interaktif ke gemini.google.com."""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.playwright = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def start(self) -> Page:
        """Membuka browser dengan profil tersimpan."""
        global _ACTIVE_SESSION
        _ACTIVE_SESSION = self
        os.makedirs(PROFILE_DIR, exist_ok=True)
        self.playwright = sync_playwright().start()

        channel, _ = _get_best_browser_channel()
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--no-sandbox"
        ]
        try:
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                channel=channel,
                headless=self.headless,
                ignore_default_args=["--enable-automation"],
                args=launch_args,
                no_viewport=True,
                timeout=60000
            )
        except Exception as e:
            # Fallback jika channel msedge gagal, coba chromium standar
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                headless=self.headless,
                ignore_default_args=["--enable-automation"],
                args=launch_args,
                timeout=60000
            )

        # Masking webdriver agar Google tidak memblokir login akun
        self.context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()

        # Buka gemini.google.com
        if not self.page.url.startswith("https://gemini.google.com"):
            print("🌐 [Gemini Browser] Membuka gemini.google.com...")
            self.page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)

        return self.page

    def check_login_status(self) -> bool:
        """
        Memeriksa apakah pengguna benar-benar sudah login ke akun Google (bukan mode tamu/guest).
        """
        if not self.page:
            return False

        url = self.page.url
        if "accounts.google.com" in url or "signin" in url:
            return False

        # 1. Cek apakah ada tombol 'Sign in' / 'Masuk' (indikator kuat mode tamu)
        signin_selectors = [
            "a[href*='accounts.google.com']",
            "button:has-text('Sign in')",
            "a:has-text('Sign in')",
            "button:has-text('Masuk')",
            "a:has-text('Masuk')",
            "div.sign-in-button"
        ]
        for sel in signin_selectors:
            loc = self.page.locator(sel).first
            if loc.is_visible(timeout=1000):
                return False

        # 2. Cek avatar akun Google pengguna (indikator resmi sudah login)
        avatar_selectors = [
            "button[aria-label*='Google Account']",
            "button[aria-label*='Akun Google']",
            "img[alt*='Google Account']",
            "img[alt*='Akun Google']",
            "div[aria-label*='Google Account']"
        ]
        for sel in avatar_selectors:
            if self.page.locator(sel).count() > 0:
                return True

        # Jika ada kotak input chat dan tidak ada tombol sign-in
        input_selectors = ["div.ql-editor", "rich-textarea", "div[contenteditable='true']", "textarea"]
        for sel in input_selectors:
            if self.page.locator(sel).count() > 0:
                return True

        return False

    def is_page_closed(self) -> bool:
        """Memeriksa apakah halaman browser sudah ditutup atau konteks dihancurkan."""
        if not self.page:
            return False
        try:
            return self.page.is_closed()
        except Exception:
            return True

    def ensure_logged_in(self, timeout_sec: int = 180) -> bool:
        """
        Memastikan akun Google pengguna aktif. Jika masih mode tamu,
        pandu pengguna untuk login di jendela browser yang terbuka dan tunggu sampai selesai.
        Setelah login 1 kali, seluruh sesi tersimpan permanen di profil!
        """
        if self.check_login_status():
            return True

        print("\n🔔 [Gemini Browser] Akun Google belum terhubung (terdeteksi mode tamu).")
        print("👉 Silakan klik tombol 'Sign in' / 'Masuk' pada jendela browser yang terbuka.")
        print("   (Anda hanya perlu login 1 kali ini saja, sesi akan tersimpan permanen selamanya)...")

        # Coba klik tombol Sign in otomatis jika ada
        for sel in ["a:has-text('Sign in')", "button:has-text('Sign in')", "a:has-text('Masuk')", "button:has-text('Masuk')"]:
            loc = self.page.locator(sel).first
            if loc.is_visible(timeout=1500):
                try:
                    loc.click()
                except Exception:
                    pass
                break

        # Tunggu sampai pengguna menyelesaikan login di browser
        start_wait = time.time()
        while time.time() - start_wait < timeout_sec:
            if "gemini.google.com" in self.page.url and self.check_login_status():
                print("✅ [Gemini Browser] Login berhasil diverifikasi! Sesi akun Google tersimpan permanen.")
                time.sleep(2)
                return True
            time.sleep(1.5)

        return self.check_login_status()

    def new_chat(self) -> Page:
        """
        Memastikan selalu membuka obrolan baru yang bersih (New Chat)
        agar tidak terjebak dalam Refusal Loop thread obrolan lama.
        """
        if not self.page:
            return self.start()

        print("✨ [Gemini Browser] Membuka obrolan baru yang bersih (New Chat)...")
        # 1. Coba klik tombol New Chat di sidebar jika ada
        new_chat_selectors = [
            "button[aria-label*='New chat']",
            "button[aria-label*='Obrolan baru']",
            "a[href='/app']",
            "a[aria-label*='New chat']",
            "a[aria-label*='Obrolan baru']",
            "button:has-text('New chat')",
            "button:has-text('Obrolan baru')",
            "div[aria-label*='New chat']",
            "div[aria-label*='Obrolan baru']"
        ]
        clicked = False
        for sel in new_chat_selectors:
            loc = self.page.locator(sel).first
            if loc.is_visible(timeout=1000):
                try:
                    loc.click()
                    clicked = True
                    time.sleep(2)
                    break
                except Exception:
                    pass

        # 2. Jika tombol tidak ditemukan atau URL masih di thread lama (/app/...), navigasi ke /app
        if not clicked or "/app/" in self.page.url:
            try:
                self.page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
            except Exception:
                pass

        return self.page

    def send_prompt(self, prompt: str, timeout_sec: int = 120, simulate_typing: bool = True) -> str:
        """
        Mengetik prompt ke Gemini secara aman dan terlihat real-time huruf per huruf di layar,
        menekan tombol kirim, dan menunggu secara sabar hingga jawaban Gemini selesai streaming.
        """
        if not self.page or self.is_page_closed() or is_stop_requested():
            raise RuntimeError("Target page, context or browser has been closed")

        # 1. Cari elemen input
        input_elem = None
        selectors = [
            "div.ql-editor[contenteditable='true']",
            "div[contenteditable='true']",
            "rich-textarea p",
            "rich-textarea",
            "textarea"
        ]

        for sel in selectors:
            loc = self.page.locator(sel).first
            if loc.is_visible(timeout=3000):
                input_elem = loc
                break

        if not input_elem:
            if self.is_page_closed() or is_stop_requested():
                raise RuntimeError("Target page, context or browser has been closed")
            raise RuntimeError(
                "Kotak pesan Gemini tidak ditemukan. "
                "Pastikan Anda sudah login ke akun Google di jendela browser yang terbuka."
            )

        # Hitung jumlah pesan model sebelum mengirim pesan baru
        model_selectors = "model-response, message-content, div.model-response-text, .response-container-content"
        initial_count = self.page.locator(model_selectors).count()
        initial_text = ""
        if initial_count > 0:
            initial_text = self.page.locator(model_selectors).last.inner_text().strip()

        # 2. Masukkan teks (simulasi ketikan real-time manusia)
        input_elem.click()
        time.sleep(0.4)

        # Bersihkan input lama sepenuhnya
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Backspace")
        time.sleep(0.2)

        if simulate_typing:
            print(f"⌨️ [Carl] Sedang mengetik pesan secara real-time ({len(prompt)} karakter)...")
            char_delay_min = 0.012 if len(prompt) > 250 else 0.020
            char_delay_max = 0.028 if len(prompt) > 250 else 0.045
            try:
                for ch in prompt:
                    if is_stop_requested() or self.is_page_closed():
                        raise RuntimeError("Target page, context or browser has been closed")
                    if ch == "\n":
                        self.page.keyboard.press("Shift+Enter")
                        time.sleep(0.08)
                    else:
                        self.page.keyboard.insert_text(ch)
                        time.sleep(random.uniform(char_delay_min, char_delay_max))
            except Exception as e_type:
                if is_browser_closed_error(e_type) or self.is_page_closed() or is_stop_requested():
                    raise RuntimeError("Target page, context or browser has been closed")
                # Fallback aman jika terjadi gangguan browser non-close
                try:
                    input_elem.fill(prompt)
                except Exception as e_fill:
                    if is_browser_closed_error(e_fill) or self.is_page_closed():
                        raise RuntimeError("Target page, context or browser has been closed")
                    raise e_fill
        else:
            try:
                self.page.keyboard.insert_text(prompt)
            except Exception as e_ins:
                if is_browser_closed_error(e_ins) or self.is_page_closed() or is_stop_requested():
                    raise RuntimeError("Target page, context or browser has been closed")
                try:
                    input_elem.fill(prompt)
                except Exception as e_fill:
                    if is_browser_closed_error(e_fill) or self.is_page_closed():
                        raise RuntimeError("Target page, context or browser has been closed")
                    raise e_fill

        time.sleep(0.8)

        if self.is_page_closed() or is_stop_requested():
            raise RuntimeError("Target page, context or browser has been closed")

        # 3. Klik tombol Kirim
        send_selectors = [
            "button[aria-label*='Kirim']",
            "button[aria-label*='Send']",
            "button.send-button",
            "button[mattooltip*='Send']"
        ]
        clicked = False
        for s_btn in send_selectors:
            loc = self.page.locator(s_btn).first
            if loc.is_visible(timeout=1500) and loc.is_enabled():
                loc.click()
                clicked = True
                break

        if not clicked:
            self.page.keyboard.press("Enter")

        print("⏳ [Gemini Browser] Pesan terkirim! Menunggu Guru Gemini mengetik dan menyelesaikan jawaban...")
        time.sleep(3)

        # 4. Tunggu respons selesai streaming secara tuntas
        stop_selectors = [
            "button[aria-label*='Hentikan']",
            "button[aria-label*='Stop']",
            "button[aria-label*='Berhenti']",
            "button.stop-generating-button",
            "button:has(mat-icon[fonticon='stop'])"
        ]
        start_wait = time.time()
        last_text_len = 0
        stable_cycles = 0

        while time.time() - start_wait < timeout_sec:
            if is_stop_requested() or self.is_page_closed():
                raise RuntimeError("Target page, context or browser has been closed")
            # Periksa apakah ada tombol stop (masih streaming)
            is_streaming = False
            for s_stop in stop_selectors:
                if self.page.locator(s_stop).count() > 0 and self.page.locator(s_stop).first.is_visible():
                    is_streaming = True
                    break

            responses = self.page.locator(model_selectors)
            current_count = responses.count()

            # Pastikan sudah ada respons baru atau teksnya bertambah dari sebelumnya
            current_text = ""
            if current_count > 0:
                current_text = responses.last.inner_text().strip()

            current_len = len(current_text)

            # Jika streaming sudah selesai (tombol stop hilang) dan teks sudah stabil selama 3 siklus
            if not is_streaming and current_len > 20 and current_text != initial_text:
                if current_len == last_text_len:
                    stable_cycles += 1
                    if stable_cycles >= 3:  # Stabil selama 3 detik penuh
                        break
                else:
                    stable_cycles = 0

            last_text_len = current_len
            time.sleep(1)

        # 5. Ambil teks jawaban terakhir yang sudah lengkap dengan format kode kaya
        responses = self.page.locator(model_selectors)
        if responses.count() > 0:
            last_elem = responses.last
            final_reply = ""
            try:
                final_reply = last_elem.evaluate(r"""
                    (element) => {
                        const clone = element.cloneNode(true);

                        // 1. Hapus tombol salin kode, tooltip, dan toolbar aksi
                        const removeSelectors = [
                            'button', 'mat-icon', '.code-block-action', '.copy-button',
                            '[aria-label*="Salin"]', '[aria-label*="Copy"]', '[data-test-id*="copy"]'
                        ];
                        clone.querySelectorAll(removeSelectors.join(', ')).forEach(el => el.remove());

                        // 2. Format elemen code-block custom Gemini
                        const codeBlocks = clone.querySelectorAll('code-block, .code-block, [data-code-block]');
                        codeBlocks.forEach(cb => {
                            let lang = cb.getAttribute('language') || cb.getAttribute('lang') || cb.getAttribute('data-language') || '';
                            const header = cb.querySelector('.code-block-decoration, .header, .code-header, header');
                            if (!lang && header) {
                                lang = header.innerText.trim();
                            }
                            if (!lang) {
                                const match = cb.className.match(/(?:language|lang)-([a-zA-Z0-9_-]+)/);
                                if (match) lang = match[1];
                            }
                            lang = lang.replace(/^(Salin|Copy|Code|Kode)\s*/i, '').trim().split(/\s+/)[0] || '';

                            const codeEl = cb.querySelector('pre, code, .code-container, .formatted-code');
                            const codeText = codeEl ? (codeEl.innerText || codeEl.textContent || '') : (cb.innerText || cb.textContent || '');

                            const replacement = document.createElement('div');
                            replacement.innerText = `\n\n\`\`\`${lang.toLowerCase()}\n${codeText.trim()}\n\`\`\`\n\n`;
                            cb.replaceWith(replacement);
                        });

                        // 3. Format standalone <pre> yang belum diproses
                        clone.querySelectorAll('pre').forEach(pre => {
                            let lang = '';
                            const codeEl = pre.querySelector('code');
                            const target = codeEl || pre;
                            const match = target.className.match(/(?:language|lang)-([a-zA-Z0-9_-]+)/);
                            if (match) lang = match[1];
                            const codeText = target.innerText || target.textContent || '';
                            const replacement = document.createElement('div');
                            replacement.innerText = `\n\n\`\`\`${lang.toLowerCase()}\n${codeText.trim()}\n\`\`\`\n\n`;
                            pre.replaceWith(replacement);
                        });

                        return clone.innerText.trim();
                    }
                """)
            except Exception:
                try:
                    final_reply = last_elem.inner_text().strip()
                except Exception:
                    final_reply = ""

            if not final_reply:
                try:
                    final_reply = last_elem.inner_text().strip()
                except Exception:
                    pass

            if final_reply and final_reply != initial_text:
                return clean_gemini_response_text(final_reply)

        return "⚠️ Tidak dapat membaca teks balasan dari antarmuka Gemini."

    def close(self):
        """Menutup browser dan menyimpan profil sesi."""
        global _ACTIVE_SESSION
        if _ACTIVE_SESSION is self:
            _ACTIVE_SESSION = None
        try:
            if self.context:
                self.context.close()
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass
        self.context = None
        self.playwright = None
        self.page = None


# ─────────────────────────────────────────────────────────────────────────
# REFUSAL DETECTOR: Mendeteksi apakah Gemini masuk Refusal Loop
# Dipicu ketika Gemini mendeteksi pola automated knowledge extraction
# setelah banyak pertanyaan berturut-turut.
# ─────────────────────────────────────────────────────────────────────────
_REFUSAL_PHRASES = [
    # Indonesia
    "saya tidak bisa membantu",
    "saya tidak diprogram untuk",
    "saya adalah model bahasa",
    "saya hanya model bahasa",
    "saya tidak dirancang untuk",
    "saya tidak dapat membantu",
    "tidak bisa membantu anda",
    "saya tidak mampu melakukan",
    "di luar kemampuan saya",
    "saya tidak mengerti hal tersebut",
    # English fallback
    "i can't help with that",
    "i'm just a language model",
    "i am a language model",
    "i'm not able to",
    "i cannot assist",
    "i'm not programmed to",
    "that's outside my capabilities",
]

def _is_gemini_refusal(reply: str) -> bool:
    """
    Mengembalikan True jika Gemini mengeluarkan respons Refusal Loop
    (deteksi automated extraction / safety filter terpicu).
    """
    if not reply:
        return False
    lower = reply.strip().lower()
    # Respons refusal biasanya sangat pendek (< 120 karakter)
    if len(lower) > 200:
        return False
    return any(phrase in lower for phrase in _REFUSAL_PHRASES)


@ensure_safe_for_asyncio
def ask_gemini_once(prompt: str) -> str:
    """Mengirim satu pertanyaan ke Gemini via browser dan mengembalikan jawabannya."""
    session = GeminiBrowserSession(headless=False)
    try:
        session.start()
        if not session.ensure_logged_in(timeout_sec=180):
            return (
                "⚠️ **Waktu Login Google Habis atau Dibatalkan**\n\n"
                "Akun Google belum terhubung. Silakan coba kembali."
            )
        reply = session.send_prompt(prompt)
        return reply
    except Exception as e:
        return f"❌ Gagal berinteraksi dengan Gemini di browser: {str(e)}"
    finally:
        # Biarkan context terbuka atau tutup sesuai kebutuhan
        session.close()


@ensure_safe_for_asyncio
def run_carl_gemini_dialog(topic: str, turns: int = 3, memory_manager = None) -> str:
    """
    Menjalankan sesi diskusi multi-turn interaktif antara Carl (AI Lokal Second Brain)
    dan Google Gemini (Cloud) di browser.
    Hasil dialog otomatis didokumentasikan ke Obsidian Vault.
    """
    clean_topic = topic.strip()
    if not clean_topic:
        return "❌ Masukkan topik diskusi. Contoh: `/gemini_dialog Arsitektur AI Agent 2026`"

    print(f"\n🤝 [Carl & Gemini Dialogue] Memulai sesi diskusi seputar: '{clean_topic}' ({turns} putaran)...")

    # Ambil wawasan dari Obsidian Vault
    vault_context = ""
    if memory_manager:
        vault_context = memory_manager.search_context(clean_topic, k=3)

    session = GeminiBrowserSession(headless=False)
    try:
        session.start()
        if not session.ensure_logged_in(timeout_sec=180):
            return (
                "⚠️ **Waktu Login Google Habis atau Dibatalkan**\n\n"
                "Akun Google belum terhubung. Silakan coba kembali."
            )

        dialog_history: List[Dict[str, str]] = []

        # Putaran 1: Carl membuka diskusi ke Gemini
        carl_opening = (
            f"Halo Gemini!"
            f"Saya ingin berdiskusi dan bertukar pandangan dengan Anda mengenai topik: \"{clean_topic}\".\n\n"
        )
        if vault_context:
            carl_opening += f"Berikut beberapa poin catatan yang sedang saya pelajari:\n{vault_context[:800]}\n\n"

        carl_opening += "Bagaimana pandangan Anda mengenai hal ini dari perspektif tren terkini?"

        dialog_history.append({"speaker": "Carl", "text": carl_opening})
        print(f"\n🗣️ [Turn 1] Carl mengajukan gagasan ke Gemini...")
        gemini_reply = session.send_prompt(carl_opening)
        dialog_history.append({"speaker": "Google Gemini", "text": gemini_reply})

        # Putaran selanjutnya (Refleksi bolak-balik via Ollama lokal)
        import ollama
        current_carl_input = gemini_reply

        for turn_idx in range(2, turns + 1):
            print(f"\n🧠 [Turn {turn_idx}] Carl merenungkan jawaban Gemini...")
            prompt_for_carl = (
                f"Anda adalah Carl, rekan diskusi yang kritis dan antusias. Anda sedang berdiskusi dengan Gemini mengenai: '{clean_topic}'.\n"
                f"Berikut tanggapan terakhir dari Gemini:\n\"\"\"{current_carl_input[:1200]}\"\"\"\n\n"
                f"Tugas Anda: Berikan respons kritis, tanggapan bernas, atau pertanyaan lanjutan yang tajam dalam 1-2 paragraf singkat dan sopan selayaknya manusia."
            )

            res_carl = ollama.chat(
                model=getattr(config, "MODEL_DEFAULT", config.MODEL_WRITER),
                messages=[{'role': 'user', 'content': prompt_for_carl}],
                options={"temperature": 0.5}
            )
            carl_turn_text = res_carl.message.content.strip()
            dialog_history.append({"speaker": "Carl", "text": carl_turn_text})

            print(f"🗣️ [Turn {turn_idx}] Carl mengirim balasan ke Gemini...")
            gemini_reply = session.send_prompt(carl_turn_text)
            dialog_history.append({"speaker": "Google Gemini (Cloud AI)", "text": gemini_reply})
            current_carl_input = gemini_reply

        # Dokumentasikan hasil diskusi ke Obsidian Vault
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        safe_slug = re.sub(r'[\\/*?:"<>|]', '', clean_topic).strip()[:40]
        note_filename = f"Diskusi Carl & Gemini - {safe_slug}.md"

        body_lines = [
            f"# 🤝 Diskusi Kolaborasi: Carl (Local) & Google Gemini (Cloud)",
            f"",
            f"- **Topik:** {clean_topic}",
            f"- **Waktu:** {now_str}",
            f"- **Jumlah Putaran:** {turns} Putaran",
            f"- **Format:** Hybrid Local-Cloud AI Dialogue",
            f"",
            f"---",
            f""
        ]

        for idx, item in enumerate(dialog_history, 1):
            icon = "🧠" if "Carl" in item["speaker"] else "✨"
            body_lines.append(f"### {icon} {item['speaker']}")
            body_lines.append(f"{item['text']}\n")

        full_note_content = "\n".join(body_lines)
        save_res = create_file(f"03-Resources/{note_filename}", full_note_content)

        summary_report = (
            f"🎉 **Diskusi Carl & Google Gemini Sukses Diselesaikan ({turns} Putaran)!**\n\n"
            f"📁 **Catatan Dokumentasi Disimpan di Obsidian:**\n"
            f"`03-Resources/{note_filename}`\n\n"
            f"---\n"
            f"### 💡 Ringkasan Poin Terakhir dari Gemini:\n"
            f"{gemini_reply[:600]}...\n\n"
            f"*(Buka file catatan di Obsidian untuk membaca transkrip dialog lengkapnya)*"
        )
        return summary_report

    except Exception as e:
        return f"❌ Terjadi kesalahan saat menjalankan dialog dengan Gemini: {str(e)}"
    finally:
        session.close()


def _quick_append_lesson(
    clean_topic: str,
    carl_text: str,
    gemini_text: str,
    turn: int,
    filepath: str,
    created_str: str,
) -> None:
    """
    Menyimpan satu putaran les (Carl + Gemini) ke Obsidian secara instan tanpa Ollama.
    Dipanggil setiap kali Gemini selesai merespons agar Vault selalu up-to-date
    meski sesi berjalan infinitely.

    Jika file belum ada → buat dengan YAML frontmatter bersih.
    Jika sudah ada → append blok putaran baru di bawah konten existing.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    carl_block = (
        f"\n### 🧠 Carl — Putaran {turn}\n"
        f"{clean_gemini_response_text(carl_text)}\n"
    )
    gemini_block = (
        f"\n### ✨ Guru Gemini — Putaran {turn}\n"
        f"{clean_gemini_response_text(gemini_text)}\n"
        f"\n---\n"
    )

    if not os.path.exists(filepath):
        # File belum ada → buat baru dengan frontmatter
        header = (
            f"---\n"
            f"title: \"Materi Les Privat Carl & Guru Gemini: {clean_topic}\"\n"
            f"created: {created_str}\n"
            f"updated: {now_str}\n"
            f"type: lesson-curriculum\n"
            f"mentor: Google Gemini (Cloud AI)\n"
            f"student: Carl (Local Second Brain)\n"
            f"topic: \"{clean_topic}\"\n"
            f"tags:\n"
            f"  - les-privat\n"
            f"  - gemini-academy\n"
            f"  - knowledge-distillation\n"
            f"  - second-brain-upgrade\n"
            f"---\n\n"
            f"# 🎓 Materi Les Privat Carl & Guru Gemini: {clean_topic}\n\n"
            f"> **Mentor:** Google Gemini (Cloud Reasoning)  \n"
            f"> **Murid:** Carl (Local Second Brain)  \n"
            f"> **Dimulai:** {created_str}  \n\n"
            f"---\n"
        )
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(header + carl_block + gemini_block)
    else:
        # File sudah ada → update timestamp di frontmatter lalu append
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Update field 'updated:' di frontmatter (atau tambahkan jika belum ada)
        if "updated:" in content:
            content = re.sub(r'updated:\s*[^\n]+', f'updated: {now_str}', content, count=1)
        else:
            content = content.replace("created:", f"updated: {now_str}\ncreated:", 1)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content.rstrip() + "\n" + carl_block + gemini_block)

    print(f"   📝 [Vault] Putaran {turn} tersimpan ke '{os.path.basename(filepath)}'")


def _build_default_curriculum(topic: str, created_str: str, total_turns: int, content: str) -> str:
    """Membangun dokumen kurikulum baru dengan satu blok frontmatter Obsidian Properties yang rapi."""
    cleaned_content = clean_gemini_response_text(content)
    return (
        f"---\n"
        f"title: \"Materi Les Privat Carl & Guru Gemini: {topic}\"\n"
        f"created: {created_str}\n"
        f"type: lesson-curriculum\n"
        f"mentor: Google Gemini (Cloud AI)\n"
        f"student: Carl (Local Second Brain)\n"
        f"topic: \"{topic}\"\n"
        f"total_turns: {total_turns}\n"
        f"tags:\n"
        f"  - les-privat\n"
        f"  - gemini-academy\n"
        f"  - knowledge-distillation\n"
        f"  - second-brain-upgrade\n"
        f"---\n\n"
        f"# 🎓 Materi Les Privat Carl & Guru Gemini: {topic}\n\n"
        f"> **Mentor Pengajar:** Google Gemini (Cloud Reasoning)  \n"
        f"> **Murid Pembelajar:** Carl Multi-Agent AI (Local Second Brain)  \n"
        f"> **Tanggal Sesi:** {created_str}  \n"
        f"> **Total Putaran:** {total_turns} Putaran  \n\n"
        f"---\n\n"
        f"{cleaned_content}\n\n"
        f"---\n\n"
        f"## 💡 Dampak Pengetahuan Baru pada Memori Carl\n\n"
        f"- Materi pelajaran ini telah diserap dan didistilasi ke Obsidian Vault.\n"
        f"- Carl telah menyinkronkan pengetahuan ini ke database vektor semantik Qdrant.\n"
        f"- Mulai saat ini, jika pengguna bertanya mengenai **{topic}**, Carl akan mampu menjawab dengan wawasan mengutip ajaran dari Guru Gemini!\n"
    )


def save_or_update_curriculum_note(
    clean_topic: str,
    lessons: List[Dict[str, str]],
    memory_manager = None,
    fast_mode: bool = False
) -> str:
    """
    Menyimpan atau memperbarui kurikulum les Carl ke Obsidian Vault.
    Jika fast_mode=True atau is_stop_requested()=True:
      -> Langsung menyimpan versi terstruktur rapi tanpa blocking LLM merge / Qdrant index.
    Jika topik sudah pernah dipelajari (file sudah ada):
      -> Carl melakukan MERGE & REFINE secara cerdas (tidak menumpuk di bawah).
      -> Menjaga 1 YAML frontmatter di atas dengan created & updated.
      -> Mengintegrasikan konsep baru, koreksi, dan latihan soal.
    Jika belum ada:
      -> Membuat catatan kurikulum baru yang rapi.
    """
    import ollama
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    safe_slug = re.sub(r'[\\/*?:"<>|]', '', clean_topic).strip()[:40]
    note_filename = f"Materi Les Carl - {safe_slug}.md"
    target_dir = os.path.join(config.VAULT_PATH, "03-Resources")
    os.makedirs(target_dir, exist_ok=True)
    filepath = os.path.join(target_dir, note_filename)

    total_turns = sum(1 for l in lessons if l["role"] == "Gemini")

    # Susun konten sesi saat ini
    curriculum_blocks = []
    gemini_turn_num = 0
    carl_turn_num = 0
    for entry in lessons:
        if entry["role"] == "Gemini":
            gemini_turn_num += 1
            cleaned_entry = clean_gemini_response_text(entry['text'])
            curriculum_blocks.append(f"## ✨ Penjelasan Guru Gemini #{gemini_turn_num}\n\n{cleaned_entry}\n")
        else:
            carl_turn_num += 1
            curriculum_blocks.append(f"### 🧠 Carl #{carl_turn_num}: {entry['text'][:100]}\n")

    current_session_content = "\n".join(curriculum_blocks)

    # ── JIKA FAST MODE / STOP MANUAL: Simpan instan tanpa blocking Ollama / Qdrant ──
    if fast_mode or is_stop_requested():
        print(f"⚡ [Carl Academy] Mode Cepat Aktif: Menyimpan kurikulum tanpa menunggu blocking LLM merge...")
        default_content = _build_default_curriculum(clean_topic, now_str, total_turns, current_session_content)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(default_content + "\n")
        print(f"📁 [Carl Academy] Catatan kurikulum instan tersimpan: {filepath}")
        return note_filename

    if os.path.exists(filepath):
        # Topik sudah ada: Lakukan merge cerdas, bukan append buta di bawah!
        print(f"🔄 [Carl Academy] Catatan '{note_filename}' sudah ada. Melakukan penggabungan & penyempurnaan (Merge & Refine)...")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                existing_content = f.read()

            orig_created_match = re.search(r'created:\s*([^\n\r]+)', existing_content)
            orig_created = orig_created_match.group(1).strip() if orig_created_match else now_str

            merge_prompt = (
                f"Anda adalah kurator pengetahuan Obsidian Second Brain.\n"
                f"Topik: \"{clean_topic}\"\n\n"
                f"TUGAS: Gabungkan (MERGE & REFINE) catatan yang SUDAH ADA dengan MATERI BARU dari sesi les hari ini.\n\n"
                f"CATATAN LAMA DI VAULT:\n\"\"\"{existing_content[:2500]}\"\"\"\n\n"
                f"MATERI BARU DARI GURU GEMINI:\n\"\"\"{current_session_content[:2500]}\"\"\"\n\n"
                f"ATURAN KETAT FORMAT:\n"
                f"1. HANYA SATU blok frontmatter YAML di baris pertama:\n"
                f"   ---\n"
                f"   title: \"Materi Les Privat Carl & Guru Gemini: {clean_topic}\"\n"
                f"   created: {orig_created}\n"
                f"   updated: {now_str}\n"
                f"   type: lesson-curriculum\n"
                f"   mentor: Google Gemini (Cloud AI)\n"
                f"   student: Carl (Local Second Brain)\n"
                f"   topic: \"{clean_topic}\"\n"
                f"   tags:\n"
                f"     - les-privat\n"
                f"     - gemini-academy\n"
                f"     - knowledge-distillation\n"
                f"     - second-brain-upgrade\n"
                f"   ---\n"
                f"2. Judul utama: '# 🎓 Materi Les Privat Carl & Guru Gemini: {clean_topic}'\n"
                f"3. Satukan konsep inti, rumus matematika, studi kasus, dan latihan soal ke dalam bab yang runtut (contoh: '## 📖 1. Konsep Inti', '## 📐 2. Urutan Operasi & Aturan', '## 🧠 3. Latihan Soal & Diskusi').\n"
                f"4. DILARANG menduplikasi judul atau menempel frontmatter kedua di tengah teks. Semua harus menjadi satu dokumen yang mengalir rapi.\n"
                f"5. Pastikan rumus matematika ditulis bersih dalam satu baris (contoh: 5 + 3 = 8).\n"
                f"6. FORMAT KODE PEMROGRAMAN: Seluruh cuplikan kode pemrograman (Python, JS, HTML, dll.) WAJIB SELALU dibungkus rapi dalam blok kode Markdown dengan triple backticks dan nama bahasanya (contoh: ```python\\nkode...\\n```). DILARANG KERAS menulis kode sebagai teks biasa!\n"
                f"KEMBALIKAN HANYA MARKDOWN LENGKAP TANPA PREAMBLE."
            )

            res = ollama.chat(
                model=getattr(config, "MODEL_DEFAULT", config.MODEL_WRITER),
                messages=[{"role": "user", "content": merge_prompt}],
                options={"temperature": 0.25}
            )
            merged = res.message.content.strip()
            if merged.startswith("```"):
                merged = re.sub(r'^```\w*\n|```$', '', merged).strip()

            if not merged.startswith("---"):
                merged = (
                    f"---\ntitle: \"Materi Les Privat Carl & Guru Gemini: {clean_topic}\"\n"
                    f"created: {orig_created}\nupdated: {now_str}\ntype: lesson-curriculum\n"
                    f"mentor: Google Gemini (Cloud AI)\nstudent: Carl (Local Second Brain)\n"
                    f"topic: \"{clean_topic}\"\ntags:\n  - les-privat\n  - gemini-academy\n"
                    f"  - knowledge-distillation\n  - second-brain-upgrade\n---\n\n"
                    + merged
                )

            # Sanitasi akhir: pastikan tidak ada kode yang lolos sebagai teks mentah
            merged = clean_gemini_response_text(merged)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(merged + "\n")
            print(f"✨ [Carl Academy] Catatan berhasil diperbarui & disempurnakan: {filepath}")
        except Exception as e:
            print(f"⚠️ [Carl Academy] Gagal merge ({e}), menyimpan versi default...")
            default_content = _build_default_curriculum(clean_topic, now_str, total_turns, current_session_content)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(default_content + "\n")
    else:
        # File baru
        default_content = _build_default_curriculum(clean_topic, now_str, total_turns, current_session_content)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(default_content + "\n")
        print(f"📚 [Carl Academy] Kurikulum baru tersimpan: {filepath}")

    # Sinkronisasi ke Qdrant
    if memory_manager:
        try:
            memory_manager.index_vault(silent=True)
            print("⚡ [Carl Academy] Pengetahuan baru berhasil diindeks ke Database Vektor Qdrant!")
        except Exception as e:
            print(f"⚠️ [Carl Academy] Gagal auto-reindex vektor: {e}")

    return note_filename


@ensure_safe_for_asyncio
def run_carl_tutoring_session(topic: str, turns: int = 2, memory_manager = None) -> str:
    """
    🎓 Carl Curiosity Loop — Sesi les privat dinamis antara Carl dan Guru Gemini.

    Carl memulai dengan meminta penjelasan dasar, lalu secara mandiri mengevaluasi
    setelah setiap jawaban Gemini apakah masih ada hal penting yang belum dipelajari.
    Jika ya → Carl melanjutkan bertanya (singkat & curious, 1-2 kalimat).
    Jika tidak / MAX_TURNS tercapai → Carl pamit & simpan kurikulum ke Obsidian Vault.

    Seluruh materi kurikulum distilasi dan diindeks ke Qdrant agar Carl benar-benar pintar!
    """
    import ollama

    # turns=0 artinya tidak terbatas — Carl terus belajar sampai Gemini berhenti merespons
    # turns=N artinya maksimal N putaran, setelah itu Carl pamit
    MAX_TURNS = turns if turns > 0 else 0   # 0 = unlimited

    clean_topic = topic.strip()
    if not clean_topic:
        return "❌ Masukkan topik yang ingin dipelajari Carl dari Gemini. Contoh: `/les Arsitektur Microservices Modern 2026`"

    reset_stop_tutoring()

    turns_label = f"maks {MAX_TURNS} putaran" if MAX_TURNS > 0 else "tanpa batas putaran — berhenti saat Gemini tidak merespons"
    print(f"\n🎓 [Carl Academy] Memulai sesi les privat dengan Guru Gemini: '{clean_topic}'...")
    print(f"   (Carl akan terus bertanya dan menggali ilmu • {turns_label})")

    session = GeminiBrowserSession(headless=False)
    lessons: List[Dict[str, str]] = []

    try:
        session.start()
        if not session.ensure_logged_in(timeout_sec=180):
            return (
                "⚠️ **Waktu Login Google Habis atau Dibatalkan**\n\n"
                "Akun Google belum terhubung. Silakan coba kembali."
            )

        if is_stop_requested():
            return "ℹ️ Sesi les dibatalkan sebelum dimulai."

        # Buka obrolan baru yang bersih agar bebas dari Refusal Loop thread lama
        session.new_chat()

        # ── Setup path file Obsidian untuk incremental save per putaran ──
        created_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        safe_slug = re.sub(r'[\\/*?:"<>|]', '', clean_topic).strip()[:40]
        note_filename = f"Materi Les Carl - {safe_slug}.md"
        target_dir = os.path.join(config.VAULT_PATH, "03-Resources")
        os.makedirs(target_dir, exist_ok=True)
        vault_filepath = os.path.join(target_dir, note_filename)
        print(f"   📂 [Vault] Catatan akan disimpan ke: 03-Resources/{note_filename}")

        # ─────────────────────────────────────────────────────────
        # BABAK 0: Carl membuka les secara natural & spontan
        # ─────────────────────────────────────────────────────────
        carl_open_prompt = (
            f"Anda adalah Carl, seorang murid yang ingin belajar langsung dari Guru Gemini.\n"
            f"Topik yang ingin dipelajari: \"{clean_topic}\"\n\n"
            f"Tugas: Tulis SATU sapaan pembuka yang santun, akrab, dan alami selayaknya murid ke guru (maksimal 2 kalimat).\n"
            f"Minta diajarkan konsep dasarnya dari awal. DILARANG menyebut kata AI, bot, sistem, atau template kaku.\n"
            f"Kembalikan HANYA teks sapaan Anda."
        )
        try:
            res_open = ollama.chat(
                model=getattr(config, "MODEL_DEFAULT", config.MODEL_WRITER),
                messages=[{"role": "user", "content": carl_open_prompt}],
                options={"temperature": 0.7}
            )
            carl_opening = res_open.message.content.strip()
            if not carl_opening or len(carl_opening) < 10:
                carl_opening = f"Halo Guru Gemini! Saya ingin belajar tentang \"{clean_topic}\". Bimbing dan ajarkan konsep dasarnya dulu ya, Guru!"
        except Exception:
            carl_opening = f"Halo Guru Gemini! Saya ingin belajar tentang \"{clean_topic}\". Bimbing dan ajarkan konsep dasarnya dulu ya, Guru!"

        if carl_opening.startswith('"') and carl_opening.endswith('"'):
            carl_opening = carl_opening[1:-1].strip()

        lessons.append({"role": "Carl", "text": carl_opening})

        if is_stop_requested():
            return f"ℹ️ Sesi les tentang *\"{clean_topic}\"* dihentikan sebelum pesan pembuka dikirim."

        print(f"\n📝 [Babak 0] Carl membuka sesi les: \"{carl_opening}\"")
        gemini_reply = session.send_prompt(carl_opening)
        lessons.append({"role": "Gemini", "text": gemini_reply})
        print(f"✅ [Babak 0] Gemini selesai menjelaskan materi dasar.")

        # Simpan Babak 0 ke Obsidian langsung (buat file baru)
        _quick_append_lesson(clean_topic, carl_opening, gemini_reply, 0, vault_filepath, created_str)

        # ─────────────────────────────────────────────────────────
        # CURIOSITY LOOP: Carl terus belajar — unlimited atau sampai N putaran
        # Berhenti jika:
        #   - MAX_TURNS > 0 dan sudah tercapai
        #   - Gemini tidak merespons (reply kosong/None) → sesi berakhir natural
        #   - Terjadi error Playwright (browser ditutup user)
        #   - Pengguna meminta berhenti manual (stop)
        # ─────────────────────────────────────────────────────────
        turn = 0
        while True:
            if is_stop_requested():
                print("\n🛑 [Carl Academy] Pengguna meminta sesi dihentikan manual.")
                break

            # Cek batas putaran jika ada
            if MAX_TURNS > 0 and turn >= MAX_TURNS:
                print(f"\n🏁 [Carl Academy] Batas {MAX_TURNS} putaran tercapai. Sesi selesai!")
                break

            turn += 1
            latest_gemini_reply = lessons[-1]["text"]

            # Jika Gemini sudah berhenti merespons → keluar graceful
            if not latest_gemini_reply or not latest_gemini_reply.strip():
                print(f"\n⚠️ [Carl Academy] Gemini tidak merespons. Sesi diakhiri setelah {turn - 1} putaran.")
                break

            # Ambil konteks yang cukup agar Carl bisa membaca penjelasan sekaligus kuis di akhir jika ada
            if len(latest_gemini_reply) <= 1500:
                latest_context = latest_gemini_reply
            else:
                # Ambil awal materi + bagian akhir (tempat biasanya kuis / pertanyaan Gemini berada)
                latest_context = f"{latest_gemini_reply[:600]}\n[...]\n{latest_gemini_reply[-700:]}"

            turn_label = f"Putaran {turn}" if MAX_TURNS == 0 else f"Putaran {turn}/{MAX_TURNS}"

            # ── PROMPT CERDAS: Carl merespons NYAMBUNG, FOKUS TOPIK, & CURIOSITY MENDALAM ──
            carl_smart_prompt = (
                f"Kamu adalah seorang murid manusia yang cerdas, sopan, dan memiliki rasa ingin tahu (curiosity) mendalam tentang topik: '{clean_topic}'.\n\n"
                f"Barusan guru menjelaskan/bertanya hal berikut:\n\"\"\"{latest_context}\"\"\"\n\n"
                f"ATURAN RESPON (SANGAT PENTING):\n"
                f"1. FOKUS TOPIK: Seluruh percakapan HARUS 100% NYAMBUNG dan LURUS dengan topik '{clean_topic}'. Jangan pernah melenceng ke topik lain.\n"
                f"2. JIKA GURU BERTANYA / MEMBERIKAN KUIS / TANTANGAN:\n"
                f"   - Jawab pertanyaan guru dengan tepat dan nyambung sesuai pertanyaan tersebut dan topik '{clean_topic}'.\n"
                f"   - Tunjukkan langkah singkat/penalaranmu, lalu konfirmasi apakah sudah benar.\n"
                f"3. JIKA GURU HANYA MENJELASKAN MATERI:\n"
                f"   - Gali pemahaman lebih dalam! Tunjukkan rasa penasaranmu (curiosity tinggi) terhadap mekanisme, prinsip kerja, alasan mendasar ('kenapa bisa begitu?'), atau skenario nyata dari topik '{clean_topic}'.\n"
                f"   - Ajukan SATU pertanyaan penasaran yang tajam dan berbobot (maksimal 1-2 kalimat).\n\n"
                f"LARANGAN KETAT (ANTI-BOT & ALAMI):\n"
                f"- DILARANG keluar dari topik '{clean_topic}'.\n"
                f"- DILARANG merangkum atau mengulang ucapan guru (JANGAN tulis 'Guru telah menjelaskan...', 'Berdasarkan penjelasan...').\n"
                f"- DILARANG salam pembuka berlebihan, langsung bicara seperti murid manusia yang antusias belajar.\n"
                f"- DILARANG menyebut dirimu AI / bot / sistem.\n"
                f"Balas HANYA dengan kalimat responmu saja (1-2 kalimat pendek):"
            )

            res = ollama.chat(
                model=getattr(config, "MODEL_DEFAULT", config.MODEL_WRITER),
                messages=[{"role": "user", "content": carl_smart_prompt}],
                options={"temperature": 0.5}
            )
            carl_next = res.message.content.strip()

            # Bersihkan tanda kutip berlebihan jika ada
            if carl_next.startswith('"') and carl_next.endswith('"'):
                carl_next = carl_next[1:-1].strip()

            # Pastikan tidak kepanjangan (maksimal ~250 karakter agar tetap ringkas dan alami)
            if len(carl_next) > 250:
                cut_idx = max(carl_next[:250].rfind("?"), carl_next[:250].rfind("."))
                if cut_idx > 40:
                    carl_next = carl_next[:cut_idx + 1].strip()
                else:
                    carl_next = carl_next[:245].rstrip() + "..."

            # Carl mengajukan respons ke Gemini
            lessons.append({"role": "Carl", "text": carl_next})
            has_question = "?" in carl_next
            response_label = "bertanya" if has_question else "menjawab kuis"
            print(f"\n🗣️ [{turn_label}] Carl {response_label}: {carl_next[:100]}...")

            if is_stop_requested():
                print(f"🛑 [{turn_label}] Sesi dihentikan manual oleh pengguna sebelum kirim pertanyaan.")
                break

            gemini_reply = session.send_prompt(carl_next)

            if is_stop_requested():
                print(f"🛑 [{turn_label}] Sesi dihentikan manual oleh pengguna setelah respons diterima.")
                if gemini_reply and gemini_reply.strip():
                    lessons.append({"role": "Gemini", "text": gemini_reply})
                    try:
                        _quick_append_lesson(clean_topic, carl_next, gemini_reply, turn, vault_filepath, created_str)
                    except Exception:
                        pass
                break

            # ── REFUSAL DETECTOR: Jika Gemini masuk Refusal Loop → reset fresh chat ──
            if _is_gemini_refusal(gemini_reply):
                print(f"\n🔄 [{turn_label}] Gemini masuk Refusal Loop! Membuka fresh chat...")
                try:
                    session.new_chat()
                    import time as _time; _time.sleep(3)
                    # Kirim ulang pertanyaan singkat dan berbeda agar tidak terdeteksi
                    short_reopen = f"Aku mau tanya soal {clean_topic} — {carl_next.split('?')[0]}?"
                    if len(short_reopen) > 160:
                        short_reopen = f"Bisa jelaskan lebih lanjut tentang {clean_topic}?"
                    print(f"   ↩️  Carl mencoba lagi dengan pertanyaan singkat: {short_reopen[:80]}...")
                    gemini_reply = session.send_prompt(short_reopen)

                    if _is_gemini_refusal(gemini_reply):
                        print(f"   ⛔ Gemini masih menolak setelah fresh chat. Melanjutkan ke putaran berikutnya...")
                        lessons.append({"role": "Gemini", "text": "[Gemini tidak dapat merespons saat ini]"})
                        continue
                except Exception as e_reset:
                    print(f"   ⚠️ Gagal reset chat: {e_reset}")

            # Jika Gemini tidak merespons di putaran ini, hentikan
            if not gemini_reply or not gemini_reply.strip():
                print(f"\n⚠️ [{turn_label}] Gemini tidak merespons. Sesi diakhiri secara natural.")
                break

            lessons.append({"role": "Gemini", "text": gemini_reply})
            print(f"✅ [{turn_label}] Gemini selesai merespons.")

            # ── Simpan putaran ini ke Obsidian sekarang juga (incremental, tanpa Ollama) ──
            try:
                _quick_append_lesson(clean_topic, carl_next, gemini_reply, turn, vault_filepath, created_str)
            except Exception as e:
                print(f"   ⚠️ [Vault] Gagal simpan putaran {turn}: {e}")

        # ─────────────────────────────────────────────────────────
        # PENUTUP: Carl pamit (jika browser masih terbuka & bukan stop paksa)
        # ─────────────────────────────────────────────────────────
        if not is_stop_requested() and not session.is_page_closed():
            carl_closing = (
                f"Terima kasih banyak! Penjelasan tadi sangat membantu. "
                f"Sampai ketemu lagi ya!"
            )
            lessons.append({"role": "Carl", "text": carl_closing})
            print(f"\n🎓 [Penutup] Carl mengucapkan terima kasih...")
            try:
                session.send_prompt(carl_closing)
            except Exception:
                print("   (Browser sudah tertutup — pamit dilewati)")
        else:
            print(f"\n🎓 [Penutup] Sesi les diakhiri.")

        # ─────────────────────────────────────────────────────────
        # DETEKSI TOPIK AKTUAL dari diskusi (bukan keyword awal)
        # ─────────────────────────────────────────────────────────
        actual_topic = clean_topic   # fallback ke topic awal
        if not is_stop_requested() and len(lessons) >= 4:
            sample = "\n".join([
                f"[{l['role']}]: {l['text'][:200]}"
                for l in lessons[1:9]   # skip opening, ambil inti diskusi
            ])
            try:
                topic_res = ollama.chat(
                    model=getattr(config, "MODEL_DEFAULT", config.MODEL_WRITER),
                    messages=[{"role": "user", "content": (
                        f"Berdasarkan cuplikan percakapan belajar berikut:\n\n"
                        f"{sample}\n\n"
                        f"Tuliskan SATU frasa singkat (2-5 kata) berupa JUDUL TOPIK PEMBAHASAN UTAMA. "
                        f"Contoh judul yang baik: 'Arsitektur Microservices', 'Hukum Termodinamika', 'Rumus Kuadrat'. "
                        f"DILARANG membuat pertanyaan, dilarang ucapan salam, dan dilarang kalimat panjang. "
                        f"Balas HANYA dengan 2-5 kata judul topik tersebut."
                    )}],
                    options={"temperature": 0.1}
                )
                detected = topic_res.message.content.strip().strip('"').strip("'").strip("`").strip("*")
                detected = detected.rstrip(".")
                is_invalid = (
                    "?" in detected or
                    "!" in detected or
                    "\n" in detected or
                    len(detected.split()) > 7 or
                    any(detected.lower().startswith(p) for p in [
                        "terima kasih", "halo", "apa ", "bagaimana", "kenapa", "mengapa",
                        "bisa", "tolong", "ini ", "saya ", "kamu ", "guru"
                    ])
                )
                if detected and 3 <= len(detected) <= 60 and not is_invalid:
                    actual_topic = detected
                    print(f"   🏷️  Topik aktual terdeteksi: \"{actual_topic}\"")
                else:
                    print(f"   ℹ️  Menggunakan topik awal: \"{clean_topic}\"")
            except Exception:
                pass   # jika gagal, tetap pakai topic awal

        # Update vault_filepath jika topic aktual berbeda dan bersihkan file lama
        if actual_topic != clean_topic:
            if os.path.exists(vault_filepath):
                try:
                    os.remove(vault_filepath)
                    print(f"   🧹 File sementara '{os.path.basename(vault_filepath)}' diganti dengan topik aktual.")
                except Exception:
                    pass
            safe_slug_actual = re.sub(r'[\\/*?:"<>|]', '', actual_topic).strip()[:40]
            note_filename_actual = f"Materi Les Carl - {safe_slug_actual}.md"
            vault_filepath_actual = os.path.join(target_dir, note_filename_actual)
        else:
            note_filename_actual = note_filename
            vault_filepath_actual = vault_filepath

        # ─────────────────────────────────────────────────────────
        # DOKUMENTASI FINAL: Simpan kurikulum ke Obsidian
        # ─────────────────────────────────────────────────────────
        total_turns = sum(1 for l in lessons if l["role"] == "Gemini")
        first_gemini = next((l["text"] for l in lessons if l["role"] == "Gemini"), "")

        if is_stop_requested():
            print(f"\n🛑 [Carl Academy] Menghentikan sesi les dan melakukan finalisasi cepat ({total_turns} putaran)...")
            session.close()
            save_or_update_curriculum_note(actual_topic, lessons, memory_manager=None, fast_mode=True)
            summary = (
                f"🛑 **Sesi Les Privat Berhasil Dihentikan Manual**\n\n"
                f"🧠 **Carl berhasil mendistilasi {total_turns} putaran pembelajaran** tentang *\"{actual_topic}\"*.\n\n"
                f"📁 **Seluruh materi tersimpan rapi di Obsidian:**\n"
                f"`03-Resources/Materi Les Carl - {re.sub(chr(92) + r'/*?:\"<>|', '', actual_topic).strip()[:40]}.md`\n\n"
                f"---\n"
                f"### 💡 Intisari Materi yang Berhasil Didapat:\n"
                f"{first_gemini[:600]}...\n\n"
                f"*(Materi tetap aman di Obsidian dan memori Carl sudah di-update!)*"
            )
            return summary

        print(f"\n🔀 [Carl Academy] Merapikan & menyempurnakan catatan final ({total_turns} putaran)...")
        print(f"   📝 Topik catatan: \"{actual_topic}\"")
        save_or_update_curriculum_note(actual_topic, lessons, memory_manager=memory_manager)

        summary = (
            f"🎉 **Sesi Les Privat Carl bersama Guru Gemini Sukses Diselesaikan!**\n\n"
            f"🧠 **Carl bertambah pintar** setelah **{total_turns} putaran pembelajaran** tentang *\"{actual_topic}\"*.\n\n"
            f"📁 **Kurikulum lengkap tersimpan di Obsidian:**\n"
            f"`03-Resources/Materi Les Carl - {re.sub(chr(92) + r'/*?:\"<>|', '', actual_topic).strip()[:40]}.md`\n\n"
            f"---\n"
            f"### 💡 Intisari Materi Awal dari Guru Gemini:\n"
            f"{first_gemini[:600]}...\n\n"
            f"*(Sekarang tanyakan apa saja tentang **{actual_topic}** ke Carl — dia sudah menguasai ilmu ini dari Gemini!)*"
        )
        return summary

    except Exception as e:
        err_msg = str(e)
        if is_browser_closed_error(e) or is_stop_requested():
            session.close()
            total_turns = sum(1 for l in lessons if l.get("role") == "Gemini")
            if total_turns > 0:
                print(f"\n⚠️ [Carl Academy] Browser ditutup / dihentikan manual. Menyimpan {total_turns} putaran materi secara cepat...")
                try:
                    save_topic = actual_topic if 'actual_topic' in locals() else clean_topic
                    save_or_update_curriculum_note(save_topic, lessons, memory_manager=None, fast_mode=True)
                    first_gemini = next((l["text"] for l in lessons if l.get("role") == "Gemini"), "")
                    safe_slug_res = re.sub(r'[\\/*?:"<>|]', '', save_topic).strip()[:40]
                    return (
                        f"🛑 **Sesi Les Privat Berhasil Dihentikan Manual** — seluruh materi tetap tersimpan aman!\n\n"
                        f"🧠 **{total_turns} putaran pembelajaran** tentang *\"{save_topic}\"* berhasil didistilasi.\n\n"
                        f"📁 **Kurikulum tersimpan di Obsidian:**\n"
                        f"`03-Resources/Materi Les Carl - {safe_slug_res}.md`\n\n"
                        f"### 💡 Materi Terakhir dari Guru Gemini:\n{first_gemini[:500]}...\n\n"
                        f"*(Catatan Obsidian Anda tetap utuh dan memori Carl sudah diperbarui)*"
                    )
                except Exception as save_err:
                    return f"🛑 Sesi les dihentikan. Catatan tersimpan di Obsidian: {save_err}"
            else:
                return f"ℹ️ Sesi les tentang *\"{clean_topic}\"* dihentikan sebelum Gemini sempat merespons. Tidak ada data yang rusak."

        return f"❌ Terjadi kesalahan saat sesi les privat dengan Gemini: {err_msg}"

    finally:
        session.close()

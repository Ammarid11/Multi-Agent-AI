# tools/tool_sandbox.py
"""
Safe Local Python Sandbox Runner & Self-Debugging (Pilar 5 Level 4 AI):
Menjalankan skrip Python di subprocess lokal terisolasi dengan batas waktu (timeout),
filter proteksi perintah berbahaya, dan loop perbaikan mandiri (Self-Debug).
"""
import sys
import subprocess
import tempfile
import os
import re
import ollama
import config

FORBIDDEN_PATTERNS = [
    r'rmdir\s+/s', r'del\s+/[a-z]', r'shutil\.rmtree\s*\(["\']/',
    r'os\.system\s*\(\s*["\'](?:del|format|rm)', r'format\s+[a-z]:'
]


def _is_safe_code(code_str: str) -> bool:
    """Memeriksa apakah kode bebas dari pola perintah destruktif berbahaya."""
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, code_str, re.IGNORECASE):
            return False
    return True


def execute_python_code(code: str, timeout: int = 6) -> str:
    """Mengeksekusi kode Python dalam subprocess aman dengan timeout."""
    cleaned_code = code.strip()
    if cleaned_code.startswith("```python"):
        cleaned_code = cleaned_code[9:]
    elif cleaned_code.startswith("```"):
        cleaned_code = cleaned_code[3:]
    if cleaned_code.endswith("```"):
        cleaned_code = cleaned_code[:-3]
    cleaned_code = cleaned_code.strip()

    if not _is_safe_code(cleaned_code):
        return "❌ Eksekusi dibatalkan: Kode mengandung perintah sistem yang berisiko."

    # Tulis ke file temporer
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(cleaned_code)
        tmp_path = tmp.name

    try:
        proc = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8"
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        if proc.returncode == 0:
            output = stdout if stdout else "(Kode berhasil dieksekusi tanpa keluaran teks stdout)"
            return f"✅ **Hasil Eksekusi Python (Sukses):**\n```\n{output}\n```"
        else:
            return f"⚠️ **Error Runtime Python:**\n```\n{stderr}\n```"
    except subprocess.TimeoutExpired:
        return f"⏱️ Eksekusi terhenti: Waktu eksekusi melebihi batas waktu ({timeout} detik)."
    except Exception as e:
        return f"❌ Gagal menjalankan sandbox: {str(e)}"
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


def execute_and_self_debug(code: str) -> str:
    """Menjalankan kode, dan jika error, Coder Agent otomatis memperbaiki dan mencoba kembali."""
    initial_res = execute_python_code(code)
    if "Error Runtime" not in initial_res:
        return initial_res

    print("\n🔧 [Code Sandbox] Mendeteksi error runtime, memulai Self-Debugging...")
    debug_prompt = (
        f"Kode berikut mengalami error saat dijalankan:\n```python\n{code}\n```\n\n"
        f"Pesan Error:\n{initial_res}\n\n"
        "TUGAS: Perbaiki kode tersebut agar dapat berjalan tanpa error. "
        "Kembalikan HANYA blok kode python murni tanpa teks pengantar."
    )

    try:
        res = ollama.chat(
            model=config.MODEL_CODER,
            messages=[{'role': 'user', 'content': debug_prompt}],
            options=config.OPTIONS_CODER,
            keep_alive=config.KEEP_ALIVE_SPECIALIST
        )
        fixed_code = res.message.content.strip()
        retry_res = execute_python_code(fixed_code)
        return f"🔄 **Hasil Setelah Self-Debugging Otomatis:**\n{retry_res}\n\n**Kode yang Diperbaiki:**\n```python\n{fixed_code}\n```"
    except Exception:
        return initial_res


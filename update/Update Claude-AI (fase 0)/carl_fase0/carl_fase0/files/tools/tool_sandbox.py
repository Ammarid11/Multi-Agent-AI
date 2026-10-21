# tools/tool_sandbox.py
"""
Python sandbox lokal + self-debug.

Lapisan pengaman (bukan isolasi penuh):
1. Pemeriksaan AST: menolak impor/panggilan berisiko (subprocess, socket, ctypes, os.system, rmtree, dll.)
2. Proses terpisah dengan `python -I -B`, direktori kerja sementara baru, environment minimal
3. Timeout, batas output, dan (di POSIX) batas memori/CPU/ukuran berkas
BATASAN: di Windows tanpa container, jaringan dan akses berkas pengguna tidak bisa diblokir sepenuhnya.
Untuk isolasi penuh, jalankan di container/pengguna terbatas tanpa jaringan (lihat roadmap Fase 0.5).
"""
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Optional

import ollama
import config

MAX_OUTPUT_CHARS = 8000
MEMORY_LIMIT_BYTES = 512 * 1024 * 1024

FORBIDDEN_IMPORTS = {
    "subprocess", "socket", "ctypes", "multiprocessing", "ftplib", "smtplib", "telnetlib",
    "http", "urllib", "requests", "httpx", "aiohttp", "webbrowser", "pty", "winreg", "msvcrt", "importlib",
}
FORBIDDEN_CALLS = {
    "eval", "exec", "compile", "__import__", "breakpoint",
}
FORBIDDEN_ATTRS = {
    ("os", "system"), ("os", "popen"), ("os", "remove"), ("os", "unlink"), ("os", "rmdir"),
    ("os", "removedirs"), ("os", "rename"), ("os", "replace"), ("os", "startfile"), ("os", "kill"),
    ("os", "chmod"), ("os", "chown"), ("os", "execv"), ("os", "execl"), ("os", "spawnl"), ("os", "fork"),
    ("shutil", "rmtree"), ("shutil", "move"), ("shutil", "copy"), ("shutil", "copytree"),
}
# Pola lama dipertahankan sebagai lapisan tambahan (bukan satu-satunya pengaman)
FORBIDDEN_PATTERNS = [
    r'rmdir\s+/s', r'del\s+/[a-z]', r'shutil\.rmtree\s*\(["\']/',
    r'os\.system\s*\(\s*["\'](?:del|format|rm)', r'format\s+[a-z]:',
]


def _strip_fences(code: str) -> str:
    cleaned = code.strip()
    if cleaned.startswith("```python"):
        cleaned = cleaned[9:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def _unsafe_reason(code: str) -> Optional[str]:
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            return "pola perintah destruktif"
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None  # biarkan interpreter melaporkan SyntaxError apa adanya
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_IMPORTS:
                    return f"impor modul '{alias.name}'"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in FORBIDDEN_IMPORTS:
                return f"impor modul '{node.module}'"
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                return f"pemanggilan '{func.id}()'"
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if (func.value.id, func.attr) in FORBIDDEN_ATTRS:
                    return f"pemanggilan '{func.value.id}.{func.attr}()'"
        elif isinstance(node, ast.Name) and node.id in {"__builtins__", "__loader__", "__spec__"}:
            return f"akses '{node.id}'"
    return None


def _is_safe_code(code_str: str) -> bool:
    return _unsafe_reason(code_str) is None


def _minimal_env() -> dict:
    keep = ("SYSTEMROOT", "SystemRoot", "WINDIR", "PATH", "TEMP", "TMP", "LANG", "LC_ALL")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.update({"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
    return env


def _posix_limits():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
        resource.setrlimit(resource.RLIMIT_FSIZE, (5 * 1024 * 1024, 5 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    except Exception:
        pass


def _clip(text: str) -> str:
    return text if len(text) <= MAX_OUTPUT_CHARS else text[:MAX_OUTPUT_CHARS] + "\n…(keluaran dipotong)"


def execute_python_code(code: str, timeout: int = 6) -> str:
    """Mengeksekusi kode Python di proses terisolasi (-I) pada direktori sementara dengan timeout."""
    cleaned_code = _strip_fences(code)
    reason = _unsafe_reason(cleaned_code)
    if reason:
        return f"❌ Eksekusi dibatalkan: kode mengandung hal yang tidak diizinkan di sandbox ({reason})."

    workdir = tempfile.mkdtemp(prefix="carl_sandbox_")
    script_path = os.path.join(workdir, "main.py")
    try:
        with open(script_path, "w", encoding="utf-8") as handle:
            handle.write(cleaned_code)
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            kwargs["preexec_fn"] = _posix_limits
        proc = subprocess.run(
            [sys.executable, "-I", "-B", script_path],
            capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace",
            cwd=workdir, env=_minimal_env(), stdin=subprocess.DEVNULL, **kwargs,
        )
        stdout, stderr = _clip(proc.stdout.strip()), _clip(proc.stderr.strip())
        if proc.returncode == 0:
            output = stdout if stdout else "(Kode berhasil dieksekusi tanpa keluaran teks stdout)"
            return f"✅ **Hasil Eksekusi Python (Sukses):**\n```\n{output}\n```"
        return f"⚠️ **Error Runtime Python:**\n```\n{stderr}\n```"
    except subprocess.TimeoutExpired:
        return f"⏱️ Eksekusi terhenti: Waktu eksekusi melebihi batas waktu ({timeout} detik)."
    except Exception as e:
        return f"❌ Gagal menjalankan sandbox: {str(e)}"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def execute_and_self_debug(code: str) -> str:
    """Menjalankan kode, dan jika error runtime, Coder Agent memperbaiki lalu mencoba kembali (lewat sandbox yang sama)."""
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
            keep_alive=config.KEEP_ALIVE_SPECIALIST,
        )
        fixed_code = res.message.content.strip()
        retry_res = execute_python_code(fixed_code)
        return f"🔄 **Hasil Setelah Self-Debugging Otomatis:**\n{retry_res}\n\n**Kode yang Diperbaiki:**\n```python\n{_strip_fences(fixed_code)}\n```"
    except Exception:
        return initial_res

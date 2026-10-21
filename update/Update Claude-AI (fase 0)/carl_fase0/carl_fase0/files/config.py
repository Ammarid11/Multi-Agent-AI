# config.py
import os
import shutil
from pathlib import Path


def _env(name, default):
    return os.environ.get(name, default)


# ── Path Direktori Obsidian Vault, Database Vektor, state & log ──
VAULT_PATH = _env("CARL_VAULT_PATH", "E:/Project AI 2026/Obsidian/Brain AI Memory")
DB_PATH = _env("CARL_DB_PATH", "E:/Project AI 2026/Multi-Agent AI/db/qdrantstorage")   # hanya Qdrant + cache mtime indeks
STATE_PATH = _env("CARL_STATE_PATH", "E:/Project AI 2026/Multi-Agent AI/db/state")     # profil, aturan, scheduler, riwayat sesi
LOG_PATH = _env("CARL_LOG_PATH", "E:/Project AI 2026/Multi-Agent AI/logs")
WORKSPACE_PATH = _env("CARL_WORKSPACE_PATH", "E:/Project AI 2026/Multi-Agent AI/carl_workspace")  # tempat script .py buatan Carl
COLLECTION_NAME = "obsidian_vault"

# Folder tambahan (selain Vault & workspace) yang boleh dibaca /vision. Pisahkan dengan ';'
INPUT_ALLOWED_DIRS = [p for p in _env("CARL_INPUT_DIRS", "").split(";") if p.strip()]

# ── Model Ollama (Full Local) ──
MODEL_EMBEDDING = "nomic-embed-text"
MODEL_WRITER = "qwen2.5:7b"
MODEL_REASONER = "deepseek-r1:8b"
MODEL_CODER = "qwen2.5-coder:7b"
OLLAMA_MODEL = MODEL_WRITER   # alias lama: dipakai swarm_simulator & trainer

# ── Host & Efisiensi VRAM ──
OLLAMA_HOST = _env("OLLAMA_HOST", "http://localhost:11434")
KEEP_ALIVE_DEFAULT = "2m"
KEEP_ALIVE_SPECIALIST = "30s"

# ── Opsi Pemanggilan Model (num_ctx eksplisit agar aturan anti-halusinasi tidak terpotong) ──
NUM_CTX = int(_env("CARL_NUM_CTX", "8192"))
OPTIONS_WRITER = {"temperature": 0.3, "num_ctx": NUM_CTX}
OPTIONS_REASONER = {"temperature": 0.6, "num_ctx": NUM_CTX}
OPTIONS_CODER = {"temperature": 0.2, "num_ctx": NUM_CTX}
OPTIONS_CLEANER = {"temperature": 0.1, "num_ctx": NUM_CTX}
EVAL_OPTIONS = {"temperature": 0.0, "seed": 42, "num_ctx": NUM_CTX}  # benchmark & gerbang evaluasi

# ── Server web / jaringan ──
WEB_PORT = int(_env("CARL_WEB_PORT", "8000"))
LAN_ENABLED = _env("CARL_LAN", "0") == "1"      # default: hanya 127.0.0.1
MEMO_MAX_CHARS = 20_000
BRIDGE_TOKEN_TTL_HOURS = 2.0
VAULT_UNLOCK_IDLE_SECONDS = 600                 # brankas terkunci otomatis setelah 10 menit tanpa aktivitas


def state_file(name: str, legacy_dirs=None) -> str:
    """Path berkas state di STATE_PATH; menyalin berkas lama dari DB_PATH (atau legacy_dirs) sekali saja."""
    os.makedirs(STATE_PATH, exist_ok=True)
    target = os.path.join(STATE_PATH, name)
    if not os.path.exists(target):
        for directory in (DB_PATH, *(legacy_dirs or ())):
            old = os.path.join(directory, name)
            if os.path.isfile(old):
                try:
                    shutil.copy2(old, target)
                except OSError:
                    pass
                break
    return target


def validate_startup() -> list:
    """Kembalikan daftar masalah konfigurasi; ditampilkan sebelum agen berjalan."""
    problems: list = []
    if not Path(VAULT_PATH).is_dir():
        problems.append(f"Vault tidak ditemukan: {VAULT_PATH}")
    for path in (DB_PATH, STATE_PATH, LOG_PATH, WORKSPACE_PATH):
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
        except OSError as error:
            problems.append(f"Tidak bisa membuat folder {path}: {error}")
    try:
        import requests
        tags = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3).json().get("models", [])
        installed = {m.get("name", "") for m in tags}
        for name in (MODEL_EMBEDDING, MODEL_WRITER, MODEL_REASONER, MODEL_CODER):
            if name not in installed and f"{name}:latest" not in installed:
                problems.append(f"Model Ollama belum di-pull: {name}")
    except Exception as error:
        problems.append(f"Ollama tidak terjangkau di {OLLAMA_HOST}: {error}")
    return problems

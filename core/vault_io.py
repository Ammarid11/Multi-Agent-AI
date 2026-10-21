# core/vault_io.py
"""
Satu-satunya pintu akses tulis ke Vault (Fase 0.C/0.D):
- safe_path: tolak path di luar Vault
- resolve_write_path: resolusi target TULIS tanpa fuzzy match
- atomic_write: tulis atomik + snapshot + verifikasi
- move_to_trash / undo: jaring pengaman untuk hapus dan timpa
"""
import hashlib
import os
import re
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple

import config

WRITE_LOCK = threading.RLock()
BLOCKED_DIRS = {"04-secure"}          # hanya boleh disentuh vault_crypto
SNAPSHOT_REL = Path("07-Settings") / "snapshots"
TRASH_DIRNAME = ".trash"
KEEP_SNAPSHOTS = 20
_SEP = "~~"


def vault_root() -> Path:
    return Path(config.VAULT_PATH).resolve()


def _norm(path) -> str:
    return os.path.normcase(str(path))


def is_inside(root: Path, path: Path) -> bool:
    try:
        return os.path.commonpath([_norm(root), _norm(path)]) == _norm(root)
    except ValueError:
        return False


def safe_path(rel, root: Optional[Path] = None) -> Path:
    """Resolusi path relatif (atau absolut yang berada di dalam Vault). Menolak keluar dari Vault."""
    root = root or vault_root()
    text = str(rel).strip().replace("\\", "/")
    if not text:
        raise ValueError("Path kosong.")
    candidate = Path(text)
    if not candidate.is_absolute() and (re.match(r"^[A-Za-z]:", text) or text.startswith("//")):
        raise ValueError("Path harus berada di dalam Vault.")      # drive/UNC asing di OS ini
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if not is_inside(root, resolved):
        raise ValueError("Path harus berada di dalam Vault.")
    return resolved


def is_blocked_path(path) -> bool:
    """True jika path berada di folder terlindungi (04-Secure)."""
    root = vault_root()
    try:
        parts = Path(path).resolve().relative_to(root).parts
    except (ValueError, OSError):
        parts = Path(str(path).replace("\\", "/")).parts
    return any(part.casefold() in BLOCKED_DIRS for part in parts)


def is_indexable_note(path) -> bool:
    """Satu aturan indeks: didelegasikan ke memory.vault_scanner (daftar pengecualian tunggal)."""
    from memory.vault_scanner import is_indexable_note as _scanner_rule
    return _scanner_rule(str(path), str(vault_root()))


def _walk_notes(root: Path):
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d.casefold() not in BLOCKED_DIRS]
        for name in files:
            yield Path(current) / name


def find_exact_basename(name: str) -> List[Path]:
    """Semua berkas dengan nama dasar persis sama (case-insensitive), di luar folder tersembunyi/terlindungi."""
    root = vault_root()
    wanted = Path(name).name.casefold()
    return sorted(p for p in _walk_notes(root) if p.name.casefold() == wanted)


def normalize_note_name(name: str) -> str:
    text = str(name).strip().strip("'\"").replace("\\", "/")
    if text and not text.lower().endswith(".md"):
        text += ".md"
    return text


def resolve_write_path(name: str) -> Tuple[Optional[Path], Optional[str]]:
    """
    Target untuk operasi TULIS. Tanpa fuzzy:
    - path eksplisit (ada '/') -> safe_path
    - nama dasar -> harus cocok persis & tunggal; tidak ada -> berkas baru di root Vault; >1 -> tolak
    """
    text = normalize_note_name(name)
    if not text or text == ".md":
        return None, "Nama berkas kosong."
    try:
        if "/" in text:
            path = safe_path(text)
        else:
            matches = find_exact_basename(text)
            if len(matches) > 1:
                root = vault_root()
                options = "\n- ".join(p.relative_to(root).as_posix() for p in matches)
                return None, f"Ada beberapa catatan bernama '{text}'. Kirim path Vault lengkap:\n- {options}"
            path = matches[0] if matches else safe_path(text)
    except ValueError as error:
        return None, str(error)
    if is_blocked_path(path):
        return None, "Folder 04-Secure hanya dapat diakses lewat perintah brankas (/secure, /reveal)."
    return path, None


# ── Snapshot ────────────────────────────────────────────────────────────────
def _prefix_for(path: Path) -> str:
    root = vault_root()
    try:
        rel = path.resolve().relative_to(root).as_posix().casefold()
    except ValueError:
        rel = str(path).casefold()
    digest = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:10]
    stem = "".join(c for c in path.stem if c.isalnum() or c in " -_")[:40].strip() or "note"
    return f"{stem}__{digest}__"


def snapshot_dir() -> Path:
    return vault_root() / SNAPSHOT_REL


def list_snapshots(path: Path) -> List[Path]:
    directory = snapshot_dir()
    if not directory.is_dir():
        return []
    return sorted(directory.glob(_prefix_for(path) + "*.bak"), key=lambda p: p.name)


def _snapshot(path: Path) -> None:
    directory = snapshot_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{_prefix_for(path)}{int(time.time() * 1000)}.bak"
    target.write_bytes(path.read_bytes())
    for old in list_snapshots(path)[:-KEEP_SNAPSHOTS]:
        try:
            old.unlink()
        except OSError:
            pass


def _replace_with_retry(tmp: Path, target: Path, attempts: int = 6) -> None:
    for attempt in range(attempts):
        try:
            os.replace(tmp, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.15)  # Windows: berkas sedang dibuka (mis. oleh Obsidian)


def atomic_write(path, text: str, snapshot: bool = True) -> Path:
    """Tulis atomik (tmp -> replace), snapshot versi lama, lalu verifikasi byte hasil tulis."""
    target = Path(path)
    root = vault_root()
    resolved = target.resolve()
    if not is_inside(root, resolved):
        raise ValueError("Path harus berada di dalam Vault.")
    data = text.encode("utf-8")
    with WRITE_LOCK:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        if snapshot and resolved.exists() and resolved.is_file():
            _snapshot(resolved)
        tmp = resolved.with_name(f"{resolved.name}.{os.getpid()}.tmp")
        try:
            with open(tmp, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            _replace_with_retry(tmp, resolved)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
        if resolved.read_bytes() != data:
            raise OSError("Verifikasi tulis gagal: isi berkas di disk tidak cocok.")
    return resolved


def read_text(path) -> str:
    return Path(path).read_text(encoding="utf-8")


# ── Trash & undo ────────────────────────────────────────────────────────────
def trash_dir() -> Path:
    return vault_root() / TRASH_DIRNAME


def move_to_trash(path) -> Path:
    resolved = Path(path).resolve()
    root = vault_root()
    if not is_inside(root, resolved) or not resolved.is_file():
        raise ValueError("Berkas tidak ada di dalam Vault.")
    rel = resolved.relative_to(root).as_posix()
    directory = trash_dir()
    with WRITE_LOCK:
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{int(time.time() * 1000)}{_SEP}{rel.replace('/', _SEP)}"
        os.replace(resolved, target)
    return target


def _trash_entries(basename: str) -> List[Tuple[Path, str]]:
    directory = trash_dir()
    if not directory.is_dir():
        return []
    wanted = Path(basename).name.casefold()
    found = []
    for entry in directory.iterdir():
        parts = entry.name.split(_SEP, 1)
        if len(parts) != 2:
            continue
        original_rel = parts[1].replace(_SEP, "/")
        if Path(original_rel).name.casefold() == wanted:
            found.append((entry, original_rel))
    return sorted(found, key=lambda item: item[0].name)


def undo_last(name: str) -> str:
    """Kembalikan snapshot terakhir sebuah catatan; jika berkas sudah dihapus, pulihkan dari .trash."""
    text = normalize_note_name(name)
    if not text or text == ".md":
        return "❌ Sebutkan nama catatan. Contoh: `/undo Rencana Bisnis`."
    try:
        if "/" in text:
            path = safe_path(text)
            candidates = [path]
        else:
            candidates = find_exact_basename(text)
            path = candidates[0] if len(candidates) == 1 else None
    except ValueError as error:
        return f"❌ {error}"
    if len(candidates) > 1:
        return "⚠️ Ada beberapa catatan dengan nama itu; sebutkan path lengkap."

    if path is not None and path.exists():
        if is_blocked_path(path):
            return "❌ Folder 04-Secure tidak mendukung /undo."
        snapshots = list_snapshots(path)
        if not snapshots:
            return f"ℹ️ Tidak ada snapshot untuk '{path.name}'."
        latest = snapshots[-1]
        try:
            content = latest.read_bytes().decode("utf-8")
            atomic_write(path, content, snapshot=False)
            latest.unlink()
        except (OSError, UnicodeError, ValueError) as error:
            return f"❌ Gagal mengembalikan snapshot: {error}"
        return f"↩️ '{path.name}' dikembalikan dari snapshot ({len(snapshots) - 1} snapshot tersisa)."

    entries = _trash_entries(text)
    if not entries:
        return f"❌ Tidak ada catatan '{text}' dan tidak ada salinan di .trash."
    entry, original_rel = entries[-1]
    try:
        target = safe_path(original_rel)
    except ValueError as error:
        return f"❌ {error}"
    if target.exists():
        return f"⚠️ '{original_rel}' sudah ada kembali; tidak menimpa."
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(entry, target)
    return f"♻️ '{original_rel}' dipulihkan dari .trash."

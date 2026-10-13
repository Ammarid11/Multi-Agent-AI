# memory/vault_scanner.py
import os
import json
import glob
from typing import List, Dict, Tuple
from langchain_core.documents import Document
from memory.document_loader import split_markdown_file

EXCLUDED_VAULT_DIRS = {
    ".trash",
    "trash",
    "archive",
    "archives",
    "99-archive",
    "templates",
    "07-settings",
    "99-system",
}


def is_indexable_note(path: str, vault_path: str) -> bool:
    """Exclude hidden/system/template/archive folders from retrieval indexing."""
    try:
        relative_parts = os.path.relpath(path, vault_path).replace("\\", "/").split("/")
    except ValueError:
        return False
    if not relative_parts or relative_parts[0] == "..":
        return False
    if os.path.basename(path).startswith((".", "_")):
        return False
    return not any(
        part.startswith((".", "_")) or part.casefold() in EXCLUDED_VAULT_DIRS
        for part in relative_parts[:-1]
    )


def load_saved_mtimes(cache_path: str) -> Dict[str, float]:
    """Memuat cache timestamp file dari disk."""
    if not os.path.exists(cache_path):
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_mtimes(cache_path: str, mtimes: Dict[str, float]) -> None:
    """Menyimpan cache timestamp file ke disk untuk mencegah cold-start re-embedding."""
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(mtimes, f, indent=2)
    except Exception:
        pass


def scan_vault_mtimes(vault_path: str) -> Dict[str, float]:
    """Memindai seluruh file .md di vault dan mencatat timestamp modifikasinya."""
    files: Dict[str, float] = {}
    if not os.path.exists(vault_path):
        return files

    for path in glob.glob(os.path.join(vault_path, "**", "*.md"), recursive=True):
        if is_indexable_note(path, vault_path):
            files[os.path.normpath(path)] = os.path.getmtime(path)
    return files


def detect_file_changes(current: Dict[str, float], old: Dict[str, float]) -> Tuple[List[str], List[str]]:
    """Mendeteksi file yang baru/berubah dan file yang dihapus."""
    changed = [f for f, mtime in current.items() if old.get(f) != mtime]
    deleted = [f for f in old if f not in current]
    return changed, deleted


def extract_all_chunks(files: List[str]) -> List[Document]:
    """Memuat seluruh chunk ke RAM untuk keyword search tanpa perlu re-embed."""
    all_chunks: List[Document] = []
    for f in files:
        chunks = split_markdown_file(f)
        all_chunks.extend(chunks)
    return all_chunks


def extract_and_update_chunks(
    changed_files: List[str], 
    deleted_files: List[str], 
    existing_chunks: List[Document]
) -> Tuple[List[Document], List[Document]]:
    """Memperbarui daftar chunks memori aktif berdasarkan perubahan file."""
    new_chunks: List[Document] = []
    
    for f in changed_files:
        norm_f = os.path.normpath(f)
        chunks = split_markdown_file(norm_f)
        new_chunks.extend(chunks)
        existing_chunks = [c for c in existing_chunks if os.path.normpath(str(c.metadata.get('source', ''))) != norm_f] + chunks

    for f in deleted_files:
        norm_f = os.path.normpath(f)
        existing_chunks = [c for c in existing_chunks if os.path.normpath(str(c.metadata.get('source', ''))) != norm_f]

    return new_chunks, existing_chunks

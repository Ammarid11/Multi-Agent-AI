# tools/vault_indexer.py
import logging
import os
import threading
from typing import Dict, List, Tuple

import config
from memory.vault_scanner import is_indexable_directory, is_indexable_note

logger = logging.getLogger(__name__)

DirectorySignature = Dict[str, Tuple[int, int]]
VaultMapCache = Tuple[DirectorySignature, str]
_vault_map_cache: Dict[str, VaultMapCache] = {}
_vault_map_lock = threading.RLock()


def _directory_signature_is_current(signature: DirectorySignature) -> bool:
    for path, cached_metadata in signature.items():
        try:
            current = os.stat(path)
        except OSError:
            return False
        if (current.st_mtime_ns, current.st_ctime_ns) != cached_metadata:
            return False
    return True


def _scan_vault(vault_path: str) -> Tuple[Dict[str, List[str]], DirectorySignature]:
    folder_map: Dict[str, List[str]] = {}
    directory_signature: DirectorySignature = {}
    pending_directories = [vault_path]

    while pending_directories:
        directory = pending_directories.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        if is_indexable_directory(entry.path, vault_path):
                            pending_directories.append(entry.path)
                    elif (
                        entry.name.lower().endswith(".md")
                        and entry.is_file()
                        and is_indexable_note(entry.path, vault_path)
                    ):
                        relative_path = os.path.relpath(entry.path, vault_path)
                        folder = os.path.dirname(relative_path) or "Root"
                        folder_map.setdefault(folder, []).append(entry.name)
            directory_metadata = os.stat(directory)
            directory_signature[directory] = (
                directory_metadata.st_mtime_ns,
                directory_metadata.st_ctime_ns,
            )
        except OSError:
            logger.exception("Unable to scan Vault directory %s.", directory)
            raise

    return folder_map, directory_signature


def _build_vault_map(folder_map: Dict[str, List[str]]) -> Tuple[str, str]:
    index_lines = ["# 🤖 Master Index Second Brain (Auto-Generated)\n"]
    prompt_summary = ["PETA DIREKTORI OBSIDIAN:"]

    for folder, files in sorted(folder_map.items()):
        sorted_files = sorted(files)
        index_lines.append(f"### 📁 {folder}/")
        prompt_summary.append(
            f"- Folder '{folder}': {', '.join(sorted_files[:5])}"
            f"{' (dll)' if len(sorted_files) > 5 else ''}"
        )
        for filename in sorted_files:
            index_lines.append(f"  - [[{os.path.splitext(filename)[0]}]]")
        index_lines.append("")

    return "\n".join(prompt_summary), "\n".join(index_lines) + "\n"


def generate_or_get_vault_map() -> str:
    """Return the cached Vault map until an indexable directory changes."""
    vault_path = os.path.abspath(config.VAULT_PATH)
    if not os.path.isdir(vault_path):
        with _vault_map_lock:
            _vault_map_cache.pop(vault_path, None)
        return ""

    master_file = os.path.join(vault_path, "07-Settings", "Master_Index.md")
    os.makedirs(os.path.dirname(master_file), exist_ok=True)

    with _vault_map_lock:
        cached = _vault_map_cache.get(vault_path)
        if cached and _directory_signature_is_current(cached[0]):
            return cached[1]

        folder_map, directory_signature = _scan_vault(vault_path)
        prompt_map, index_content = _build_vault_map(folder_map)
        try:
            try:
                with open(master_file, "r", encoding="utf-8") as index_file:
                    current_content = index_file.read()
            except FileNotFoundError:
                current_content = None
            if current_content != index_content:
                with open(master_file, "w", encoding="utf-8") as index_file:
                    index_file.write(index_content)
        except OSError:
            logger.exception("Unable to update Vault master index at %s.", master_file)

        _vault_map_cache[vault_path] = (directory_signature, prompt_map)
        return prompt_map
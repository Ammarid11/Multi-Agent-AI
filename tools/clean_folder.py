# tools/clean_folder.py
import os
import shutil
from typing import List
import config

FOLDER_MAP = {
    "inbox": "00-Inbox",
    "project": "01-Projects",
    "area": "02-Areas",
    "resource": "03-Resources",
    "archive": "04-Archive",
    "daily": "05-Daily Notes",
    "program": "06-Pemrograman",
    "pemrograman": "06-Pemrograman",
    "koding": "06-Pemrograman",
    "setting": "07-Settings",
}


def get_canonical_folder_name(name: str) -> str:
    """Menormalkan nama folder ke standar 00-07."""
    clean = name.lower().replace("-", " ").replace("_", " ").strip()
    for key, canonical in FOLDER_MAP.items():
        if key in clean:
            return canonical
    return name


def _get_unique_destination_path(dst: str) -> str:
    """Jika nama file sudah ada di folder tujuan, buatkan nama aman (anti-overwrite)."""
    if not os.path.exists(dst):
        return dst

    base, ext = os.path.splitext(dst)
    counter = 1
    while os.path.exists(f"{base}_{counter}{ext}"):
        counter += 1
    return f"{base}_{counter}{ext}"


def _relocate_files(src_dir: str, dst_dir: str, target_name: str, logs: List[str]) -> None:
    """Helper: Memindahkan file dari folder lama ke folder target dengan proteksi nama ganda."""
    os.makedirs(dst_dir, exist_ok=True)
    for root, _, files in os.walk(src_dir):
        for file in files:
            src = os.path.join(root, file)
            initial_dst = os.path.join(dst_dir, file)
            safe_dst = _get_unique_destination_path(initial_dst)

            shutil.move(src, safe_dst)
            if safe_dst != initial_dst:
                logs.append(f"📁 Pindah (di-rename aman): '{file}' -> '{target_name}/{os.path.basename(safe_dst)}'")
            else:
                logs.append(f"📁 Pindah '{file}' -> '{target_name}/'")


def merge_and_clean_folders() -> List[str]:
    """Merapikan folder non-standar dan menggabungkannya ke folder 00-07 tanpa risiko data loss."""
    logs: List[str] = []
    if not os.path.exists(config.VAULT_PATH):
        return logs

    for item in os.listdir(config.VAULT_PATH):
        item_path = os.path.join(config.VAULT_PATH, item)
        if not os.path.isdir(item_path):
            continue

        target_name = get_canonical_folder_name(item)
        if item == target_name:
            continue

        target_path = os.path.join(config.VAULT_PATH, target_name)
        _relocate_files(item_path, target_path, target_name, logs)

        # PROTEKSI DATA LOSS: Hanya hapus folder asal jika sudah benar-benar kosong
        remaining = [f for _, _, files in os.walk(item_path) for f in files]
        if not remaining:
            shutil.rmtree(item_path, ignore_errors=True)
        else:
            logs.append(f"⚠️ Folder '{item}' tetap dipertahankan karena masih ada file di dalamnya.")

    return logs

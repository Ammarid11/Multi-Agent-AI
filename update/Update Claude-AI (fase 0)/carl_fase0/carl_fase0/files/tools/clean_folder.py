# tools/clean_folder.py
import os
import shutil
from typing import List, Tuple
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


def plan_folder_merges() -> List[Tuple[str, str, str]]:
    """Rencana pemindahan (src, dst, label) tanpa mengubah apa pun. Struktur subfolder DIPERTAHANKAN."""
    plan: List[Tuple[str, str, str]] = []
    if not os.path.exists(config.VAULT_PATH):
        return plan
    for item in sorted(os.listdir(config.VAULT_PATH)):
        item_path = os.path.join(config.VAULT_PATH, item)
        if not os.path.isdir(item_path) or item.startswith("."):
            continue
        target_name = get_canonical_folder_name(item)
        if item == target_name:
            continue
        for root, _, files in os.walk(item_path):
            rel_dir = os.path.relpath(root, item_path)
            dst_dir = os.path.join(config.VAULT_PATH, target_name) if rel_dir == "." else os.path.join(config.VAULT_PATH, target_name, rel_dir)
            for file in files:
                plan.append((os.path.join(root, file), os.path.join(dst_dir, file), target_name))
    return plan


def _apply_move(src: str, dst: str, target_name: str, logs: List[str]) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    safe_dst = _get_unique_destination_path(dst)
    shutil.move(src, safe_dst)
    label = os.path.relpath(safe_dst, config.VAULT_PATH).replace("\\", "/")
    suffix = " (di-rename aman)" if safe_dst != dst else ""
    logs.append(f"📁 Pindah '{os.path.basename(src)}' -> '{label}'{suffix}")


def merge_and_clean_folders(apply: bool = False) -> List[str]:
    """
    Merapikan folder non-standar ke folder 00-07.
    apply=False (default): hanya mengembalikan rencana (dry-run). apply=True: eksekusi (panggil setelah backup).
    """
    logs: List[str] = []
    plan = plan_folder_merges()
    if not apply:
        for src, dst, _ in plan:
            logs.append(f"📋 Rencana: '{os.path.relpath(src, config.VAULT_PATH)}' -> '{os.path.relpath(dst, config.VAULT_PATH)}'".replace("\\", "/"))
        return logs

    for src, dst, target_name in plan:
        try:
            _apply_move(src, dst, target_name, logs)
        except OSError as error:
            logs.append(f"⚠️ Gagal memindahkan '{os.path.basename(src)}': {error}")

    # PROTEKSI DATA LOSS: hanya hapus folder asal jika benar-benar tidak berisi berkas
    for item in sorted(os.listdir(config.VAULT_PATH)):
        item_path = os.path.join(config.VAULT_PATH, item)
        if not os.path.isdir(item_path) or item.startswith(".") or get_canonical_folder_name(item) == item:
            continue
        if any(files for _, _, files in os.walk(item_path)):
            logs.append(f"⚠️ Folder '{item}' tetap dipertahankan karena masih ada file di dalamnya.")
        else:
            shutil.rmtree(item_path, ignore_errors=True)
    return logs

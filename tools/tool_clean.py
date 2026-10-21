# tools/tool_clean.py
import os
import glob
import re
from typing import Optional
import config
from core.confirm import request_confirmation, confirmation_hint
from tools.clean_folder import merge_and_clean_folders, plan_folder_merges
from tools.clean_markdown import clean_and_refactor_file
from tools.vault_indexer import generate_or_get_vault_map

PROTECTED_NAMES = {"master_index.md", "master index - brain ai memory.md", "user_memory.md"}
_NATURAL_CLEAN_PREFIX = re.compile(
    r"^(?:(?:tolong|bantu|coba|bisa|boleh|please)\s+)*"
    r"(?:rapikan|rapihkan|rapihin|merapikan|merapihkan)\b",
    re.IGNORECASE,
)


def _extract_natural_clean_target(target: str) -> tuple[str, bool]:
    """Remove a natural-language cleanup request prefix and optional file descriptor."""
    match = _NATURAL_CLEAN_PREFIX.match(target.strip())
    if not match:
        return target.strip().strip("'\""), False

    cleaned_target = target[match.end():].strip()
    cleaned_target = re.sub(
        r"^(?:(?:file|catatan|dokumen|note)\s+|(?:yang\s+)?(?:bernama|berjudul)\s+)",
        "",
        cleaned_target,
        count=1,
        flags=re.IGNORECASE,
    )
    return cleaned_target.strip().strip("'\""), True


def _is_protected(filepath: str) -> bool:
    """Periksa apakah file merupakan bagian dari pengaturan atau indeks internal."""
    norm = filepath.replace("\\", "/").lower()
    base = os.path.basename(norm)
    if "07-settings" in norm:
        return True
    if base.startswith((".", "_")):
        return True
    if base in PROTECTED_NAMES:
        return True
    return False


def _clean_markdown_in_path(
    search_path: str, max_limit: int = 20
) -> tuple[int, int, list[str], list[str]]:
    """Clean Markdown files and separately report verified results, warnings, and failures."""
    processed = 0
    succeeded = 0
    warnings: list[str] = []
    failures: list[str] = []
    for filepath in glob.glob(search_path, recursive=True):
        if _is_protected(filepath):
            continue
        result = clean_and_refactor_file(filepath)
        processed += 1
        label = os.path.relpath(filepath, config.VAULT_PATH).replace("\\", "/")
        if result.startswith("❌"):
            failures.append(f"- `{label}`: {result}")
        elif "⚠️" in result:
            warnings.append(f"- `{label}`: {result}")
        else:
            succeeded += 1
        if processed >= max_limit:
            break
    return processed, succeeded, warnings, failures


def _cleanup_details(warnings: list[str], failures: list[str]) -> str:
    details = warnings + failures
    if not details:
        return ""
    return "\n\nPerlu perhatian:\n" + "\n".join(details)


def clean_all_vault_files(apply: bool = False) -> str:
    """Membersihkan struktur folder & merapikan Inbox. Pemindahan folder: dry-run dulu, lalu backup otomatis saat dikonfirmasi."""
    plan = plan_folder_merges()
    if plan and not apply:
        code = request_confirmation("clean_all", {}, "Rapikan struktur folder Vault")
        preview = "\n".join(f"- `{os.path.relpath(s, config.VAULT_PATH)}` → `{os.path.relpath(d, config.VAULT_PATH)}`".replace("\\", "/") for s, d, _ in plan[:15])
        more = f"\n- …dan {len(plan) - 15} berkas lainnya" if len(plan) > 15 else ""
        return (
            f"📋 **Rencana perapihan ({len(plan)} berkas akan dipindahkan; struktur subfolder dipertahankan):**\n{preview}{more}\n\n"
            f"Backup `.zip` otomatis dibuat sebelum eksekusi. {confirmation_hint(code)}"
        )

    folder_logs: list = []
    if plan and apply:
        from tools.vault_backup import backup_vault
        backup = backup_vault(notify=False)
        if not backup.get("success"):
            return f"❌ Backup sebelum perapihan gagal ({backup.get('error')}); tidak ada folder yang dipindahkan."
        print("⏳ Menata struktur folder non-standar...")
        folder_logs = merge_and_clean_folders(apply=True)

    print("⏳ Memperbarui Master Index Vault...")
    generate_or_get_vault_map()

    inbox_pattern = os.path.join(config.VAULT_PATH, "00-Inbox", "**", "*.md")
    processed, succeeded, warnings, failures = _clean_markdown_in_path(inbox_pattern)

    logs_summary = f" ({len(folder_logs)} berkas dipindahkan)" if folder_logs else ""
    return (
        f"🎉 **Pembersihan Struktur Vault Selesai!**{logs_summary}\n"
        f"- 📁 Folder diselaraskan ke standar PARA (00–07).\n"
        f"- 📋 Master Index berhasil diperbarui.\n"
        f"- ✍️ Catatan Inbox diperiksa: {processed}; hasil tersimpan dan terverifikasi: {succeeded}; "
        f"peringatan: {len(warnings)}; gagal: {len(failures)}."
        f"{_cleanup_details(warnings, failures)}\n\n"
        f"*(Tips: `/undo <nama>` mengembalikan versi sebelumnya; `/clean <nama_folder>` merapikan folder tertentu)*"
    )


def clean_target(target: Optional[str] = None) -> str:
    """Merapikan file, folder, atau seluruh vault."""
    natural_request = False
    if target:
        target, natural_request = _extract_natural_clean_target(target)
        if natural_request and not target:
            return "Sebutkan nama file atau folder yang ingin dirapikan."

    if not target or target.lower().strip() in ['all', 'semua', 'vault', 'total', '']:
        if natural_request:
            return "Sebutkan nama file atau folder yang ingin dirapikan."
        return clean_all_vault_files()

    clean_name = target.strip("'\"")
    folder_path = os.path.join(config.VAULT_PATH, clean_name)

    if os.path.isdir(folder_path):
        pattern = os.path.join(folder_path, "**", "*.md")
        processed, succeeded, warnings, failures = _clean_markdown_in_path(pattern)
        generate_or_get_vault_map()
        return (
            f"📋 Folder '{clean_name}' diperiksa: {processed} catatan; "
            f"hasil tersimpan dan terverifikasi: {succeeded}; "
            f"peringatan: {len(warnings)}; gagal: {len(failures)}."
            f"{_cleanup_details(warnings, failures)}"
        )

    return clean_and_refactor_file(clean_name)
# tools/vault_indexer.py
import os
import glob
import config
from memory.vault_scanner import is_indexable_note


def generate_or_get_vault_map() -> str:
    """Memindai struktur vault dan memperbarui Master Index di Obsidian."""
    if not os.path.exists(config.VAULT_PATH):
        return ""

    folder_map = {}
    for filepath in glob.glob(os.path.join(config.VAULT_PATH, "**", "*.md"), recursive=True):
        if not is_indexable_note(filepath, config.VAULT_PATH):
            continue
        filename = os.path.basename(filepath)
        if filename.startswith((".", "_")):
            continue
        rel_path = os.path.relpath(filepath, config.VAULT_PATH)
        folder = os.path.dirname(rel_path) or "Root"
        folder_map.setdefault(folder, []).append(filename)

    index_lines = ["# 🤖 Master Index Second Brain (Auto-Generated)\n"]
    prompt_summary = ["PETA DIREKTORI OBSIDIAN:"]

    for folder, files in sorted(folder_map.items()):
        index_lines.append(f"### 📁 {folder}/")
        prompt_summary.append(f"- Folder '{folder}': {', '.join(files[:5])}{' (dll)' if len(files) > 5 else ''}")
        for f in sorted(files):
            index_lines.append(f"  - [[{os.path.splitext(f)[0]}]]")
        index_lines.append("")

    master_file = os.path.join(config.VAULT_PATH, "07-Settings", "Master_Index.md")
    os.makedirs(os.path.dirname(master_file), exist_ok=True)
    try:
        with open(master_file, "w", encoding="utf-8") as f:
            f.write("\n".join(index_lines) + "\n")
    except Exception:
        pass

    return "\n".join(prompt_summary)
# setup_vault_folder.py
import os
import config

DEFAULT_FOLDERS = [
    "00-Inbox",
    "01-Projects",
    "02-Areas",
    "03-Resources",
    "04-Archive",
    "05-Daily Notes",
    "06-Pemrograman",
    "07-Settings"
]

def setup_folders() -> None:
    """Memastikan struktur folder utama 00-07 ada di Obsidian Vault."""
    os.makedirs(config.VAULT_PATH, exist_ok=True)
    for folder in DEFAULT_FOLDERS:
        folder_path = os.path.join(config.VAULT_PATH, folder)
        os.makedirs(folder_path, exist_ok=True)
        index_file = os.path.join(folder_path, "_index.md")
        if not os.path.exists(index_file):
            with open(index_file, "w", encoding="utf-8") as f:
                f.write(f"# {folder}\n\nFolder untuk catatan **{folder}**.\n")


if __name__ == "__main__":
    setup_folders()
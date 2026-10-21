# watcher.py
import os
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from memory import MemoryManager
import config


class ObsidianVaultHandler(FileSystemEventHandler):
    """Mendeteksi perubahan file .md di folder Obsidian secara selektif."""
    def __init__(self, memory_manager: MemoryManager):
        super().__init__()
        self.memory_manager = memory_manager

    def on_any_event(self, event: FileSystemEvent) -> None:
        src = str(event.src_path).replace("\\", "/")

        # 1. Hanya pantau file markdown (.md)
        if not src.endswith('.md'):
            return

        # 2. FILTER LOOP: Abaikan file Master_Index.md dan folder 07-Settings
        # agar tidak terjadi infinite re-indexing loop saat AI membaca peta vault
        if "07-Settings" in src or "Master_Index.md" in src or "/." in src or "\\." in src:
            return

        # 3. Tandai perlunya sinkronisasi memori
        self.memory_manager.needs_sync = True


def start_auto_sync(memory_manager: MemoryManager) -> BaseObserver:
    """Menjalankan pemantau file di background thread."""
    os.makedirs(config.VAULT_PATH, exist_ok=True)
    event_handler = ObsidianVaultHandler(memory_manager)
    observer = Observer()
    observer.schedule(event_handler, path=config.VAULT_PATH, recursive=True)
    observer.start()
    return observer
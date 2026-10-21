# tools/vault_backup.py
"""
Frontier E: Vault Snapshot Backup & Windows Desktop Toast.
Menyediakan proteksi data otomatis 1-klik (.zip berstempel waktu)
serta notifikasi desktop Windows 11 native untuk briefing & deadline.
"""

import os
import sys
import shutil
import zipfile
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import VAULT_PATH


def show_windows_toast(title: str, message: str) -> bool:
    """
    Menampilkan notifikasi pop-up native Windows Toast menggunakan PowerShell.
    Aman, non-blocking, dan tidak membutuhkan dependensi eksternal berat.
    """
    try:
        clean_title = title.replace('"', '`"').replace("'", "''")
        clean_msg = message.replace('"', '`"').replace("'", "''")

        ps_script = f"""
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
        $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $textNodes = $template.GetElementsByTagName("text")
        $textNodes.Item(0).AppendChild($template.CreateTextNode('{clean_title}')) > $null
        $textNodes.Item(1).AppendChild($template.CreateTextNode('{clean_msg}')) > $null
        $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Carl Second Brain AI")
        $notification = [Windows.UI.Notifications.ToastNotification]::new($template)
        $notifier.Show($notification)
        """
        # Jalankan secara terpisah tanpa blocking
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        return True
    except Exception as e:
        # Fallback jika PowerShell notification tidak aktif
        print(f"[Toast] Notifikasi desktop dilewati: {e}")
        return False


def backup_vault(
    vault_path_str: Optional[str] = None,
    backup_dir_str: Optional[str] = None,
    max_keep: int = 10,
    notify: bool = True
) -> Dict[str, Any]:
    """
    Mengompres seluruh isi Obsidian Vault menjadi arsip .zip berstempel waktu.
    
    Args:
        vault_path_str: Path vault (default: config.VAULT_PATH)
        backup_dir_str: Folder tujuan backup (default: 'E:/Project AI 2026/Obsidian/Backups')
        max_keep: Jumlah arsip backup maksimal yang disimpan (rotasi otomatis)
        notify: Apakah memunculkan notifikasi desktop Windows Toast
    """
    vault_path = Path(vault_path_str or VAULT_PATH)
    if not vault_path.exists():
        return {
            "success": False,
            "error": f"Direktori Vault tidak ditemukan: {vault_path}"
        }

    # Tentukan folder tujuan backup
    if backup_dir_str:
        backup_dir = Path(backup_dir_str)
    else:
        # Standar: Simpan di folder Backups sejajar atau di dalam direktori Obsidian
        backup_dir = vault_path.parent / "Backups"

    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    zip_filename = f"vault_backup_{timestamp}.zip"
    zip_path = backup_dir / zip_filename

    # File/folder yang diabaikan saat backup agar arsip bersih & efisien
    ignored_patterns = {
        ".git", ".trash", ".DS_Store", "desktop.ini", "thumbs.db",
        ".obsidian/cache", ".obsidian/workspace.json", "07-Settings/snapshots"
    }

    file_count = 0
    total_uncompressed_bytes = 0

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
            for root, dirs, files in os.walk(vault_path):
                # Filter folder yang diabaikan
                dirs[:] = [d for d in dirs if d not in ignored_patterns and not d.startswith(".git")]
                
                for file in files:
                    rel_path = os.path.relpath(os.path.join(root, file), vault_path)
                    
                    # Cek ignore patterns
                    if any(ignored in rel_path.replace("\\", "/") for ignored in ignored_patterns):
                        continue

                    full_path = os.path.join(root, file)
                    try:
                        file_stat = os.stat(full_path)
                        total_uncompressed_bytes += file_stat.st_size
                        zipf.write(full_path, arcname=rel_path)
                        file_count += 1
                    except (PermissionError, FileNotFoundError):
                        continue

        compressed_bytes = zip_path.stat().st_size
        compressed_mb = round(compressed_bytes / (1024 * 1024), 2)
        uncompressed_mb = round(total_uncompressed_bytes / (1024 * 1024), 2)

        # Rotasi backup: Hapus backup tertua jika melebihi max_keep
        existing_backups = sorted(
            backup_dir.glob("vault_backup_*.zip"),
            key=lambda p: p.stat().st_mtime
        )
        removed_count = 0
        if len(existing_backups) > max_keep:
            to_remove = existing_backups[:-max_keep]
            for old_zip in to_remove:
                try:
                    old_zip.unlink()
                    removed_count += 1
                except Exception:
                    pass

        msg = (
            f"✅ **Pencadangan Vault Berhasil!**\n\n"
            f"- **Arsip:** `{zip_path.name}`\n"
            f"- **Lokasi:** `{zip_path.parent}`\n"
            f"- **Jumlah Berkas:** {file_count} file tercadangkan\n"
            f"- **Ukuran:** {compressed_mb} MB (asli: {uncompressed_mb} MB)\n"
            f"- **Rotasi:** Menyimpan {min(len(existing_backups), max_keep)} arsip terakhir (dihapus lama: {removed_count})"
        )

        if notify:
            show_windows_toast(
                "🛡️ Backup Vault Sukses!",
                f"{file_count} catatan berhasil diamankan ({compressed_mb} MB) ke {zip_filename}"
            )

        return {
            "success": True,
            "message": msg,
            "zip_path": str(zip_path),
            "file_count": file_count,
            "size_mb": compressed_mb
        }

    except Exception as e:
        if zip_path.exists():
            try:
                zip_path.unlink()
            except Exception:
                pass
        return {
            "success": False,
            "error": f"Gagal membuat backup: {str(e)}"
        }


def run_backup_command() -> str:
    """Wrapper untuk dieksekusi via slash command /backup."""
    res = backup_vault()
    if res["success"]:
        return res["message"]
    return f"❌ Gagal melakukan backup: {res.get('error', 'Terjadi kesalahan sistem')}"


if __name__ == "__main__":
    print("Menguji modul Backup Vault & Windows Toast...")
    result = backup_vault()
    print(result.get("message", result.get("error")))

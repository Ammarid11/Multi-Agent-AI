# scheduler.py
"""
Frontier B: Background Heartbeat Daemon & Scheduled Automations.
Menjalankan siklus otomatisasi kognitif berkala:
- Pukul 08:00 WIB: Morning Strategic Briefing (ekstraksi tugas & deadline) ke 05-Daily Notes.
- Minggu 20:00 WIB: Weekly Knowledge Review (evaluasi kemajuan ide 7 hari terakhir).
- Pukul 23:00 WIB: Auto-Backup berkala ke direktori Backups.
"""

import json
import os
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import DB_PATH, VAULT_PATH
from tools.vault_temporal import generate_daily_briefing
from tools.vault_backup import backup_vault, show_windows_toast

_SCHEDULER_THREAD: Optional[threading.Thread] = None
_RUNNING = False
_BRIEFING_STATE_PATH = Path(DB_PATH) / ".scheduler_state.json"
_SCHEDULER_STATE_LOCK = threading.Lock()


def trigger_morning_briefing(user_name: str = "Pengguna") -> str:
    """Eksekusi Morning Briefing dan kirim Windows Toast."""
    print(f"\n[Heartbeat] ⏰ Menjalankan Morning Briefing otomatis...")
    try:
        report = generate_daily_briefing(user_name=user_name)
        show_windows_toast(
            "🌅 Carl Morning Briefing Siap!",
            f"Agenda hari ini telah siap di folder 05-Daily Notes."
        )
        print("[Heartbeat] ✅ Morning Briefing selesai ditulis ke Daily Notes.")
        return report
    except Exception as e:
        err = f"[Heartbeat Error] Gagal menjalankan morning briefing: {e}"
        print(err)
        return err


def _load_last_briefing_date() -> Optional[str]:
    """Read the date of the last successfully generated automatic briefing."""
    try:
        with _BRIEFING_STATE_PATH.open("r", encoding="utf-8") as state_file:
            state = json.load(state_file)
        date_value = state.get("last_morning_briefing_date")
        return date_value if isinstance(date_value, str) else None
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        print(f"[Heartbeat Warning] Tidak dapat membaca status briefing: {_BRIEFING_STATE_PATH}")
        return None


def _save_last_briefing_date(date_value: str) -> None:
    """Persist the daily guard atomically so restarting the server won't repeat it."""
    _BRIEFING_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = _BRIEFING_STATE_PATH.with_suffix(".tmp")
    try:
        with temporary_path.open("w", encoding="utf-8") as state_file:
            json.dump({"last_morning_briefing_date": date_value}, state_file)
            state_file.flush()
            os.fsync(state_file.fileno())
        os.replace(temporary_path, _BRIEFING_STATE_PATH)
    except OSError:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def run_morning_briefing_once(date_value: str) -> bool:
    """Run the automatic morning briefing at most once per local calendar day."""
    with _SCHEDULER_STATE_LOCK:
        if _load_last_briefing_date() == date_value:
            return False

        result = trigger_morning_briefing()
        if result.startswith("[Heartbeat Error]"):
            return False

        try:
            _save_last_briefing_date(date_value)
        except OSError as error:
            print(f"[Heartbeat Error] Gagal menyimpan status briefing harian: {error}")
            return False
        return True


def trigger_weekly_review() -> str:
    """Eksekusi Weekly Knowledge Review (Minggu Malam)."""
    print(f"\n[Heartbeat] 📅 Menjalankan Weekly Knowledge Review...")
    try:
        now = datetime.now()
        year, week_num, _ = now.isocalendar()
        review_filename = f"Weekly_Review_{year}-W{week_num:02d}.md"
        daily_folder = Path(VAULT_PATH) / "05-Daily Notes"
        daily_folder.mkdir(parents=True, exist_ok=True)
        review_path = daily_folder / review_filename

        # Hitung catatan yang disentuh 7 hari terakhir
        recent_notes = []
        seven_days_ago = time.time() - (7 * 86400)
        for root, dirs, files in os.walk(VAULT_PATH):
            if any(p in root for p in [".git", ".trash", ".obsidian"]):
                continue
            for f in files:
                if f.endswith(".md"):
                    full = os.path.join(root, f)
                    try:
                        mtime = os.path.getmtime(full)
                        if mtime >= seven_days_ago:
                            recent_notes.append((f, os.path.relpath(full, VAULT_PATH)))
                    except Exception:
                        pass

        content = (
            f"---\n"
            f"created: {now.strftime('%Y-%m-%d %H:%M')}\n"
            f"type: weekly-review\n"
            f"tags:\n"
            f"  - weekly-review\n"
            f"  - retrospeksi\n"
            f"---\n\n"
            f"# 📊 Rekap Mingguan Kognitif (Tahun {year} Minggu ke-{week_num})\n\n"
            f"> Ditulis otomatis oleh Heartbeat Daemon Carl pada {now.strftime('%A, %d %B %Y - %H:%M WIB')}.\n\n"
            f"### 📈 Aktivitas Catatan 7 Hari Terakhir\n"
            f"- Total catatan yang dibuat/diperbarui minggu ini: **{len(recent_notes)} catatan**.\n\n"
            f"#### 📝 Daftar Catatan Aktif:\n"
        )
        for name, rel in recent_notes[:20]:
            content += f"- [[{name.replace('.md', '')}]] (`{rel}`)\n"

        content += (
            f"\n### 💡 Refleksi & Arah Minggu Depan\n"
            f"- [ ] Apa pencapaian terbesar minggu ini?\n"
            f"- [ ] Apa hambatan yang berhasil diatasi?\n"
            f"- [ ] Prioritas strategis apa yang harus dieksekusi minggu depan?\n"
        )

        with open(review_path, "w", encoding="utf-8") as f:
            f.write(content)

        show_windows_toast(
            "📊 Weekly Review Siap!",
            f"Retrospeksi minggu ke-{week_num} telah dibuat di 05-Daily Notes."
        )
        print(f"[Heartbeat] ✅ Weekly Review tersimpan: {review_path.name}")
        return f"✅ Weekly Review mingguan tersimpan di `{review_filename}`."
    except Exception as e:
        err = f"[Heartbeat Error] Gagal membuat weekly review: {e}"
        print(err)
        return err


def trigger_nightly_backup() -> str:
    """Eksekusi pencadangan otomatis tanpa mengganggu pengguna."""
    print(f"\n[Heartbeat] 🛡️ Menjalankan pencadangan otomatis (Auto-Backup)...")
    res = backup_vault(notify=False)
    if res["success"]:
        print(f"[Heartbeat] ✅ Backup berhasil: {res['zip_path']}")
        return f"✅ Backup tersimpan: {res['zip_path']}"
    return f"❌ Backup gagal: {res.get('error')}"


def _scheduler_loop():
    """Loop denyut waktu background dengan presisi menit."""
    global _RUNNING
    _RUNNING = True
    last_briefing_date = _load_last_briefing_date()
    last_review_week = None
    last_backup_date = None

    print("💓 [Heartbeat Daemon] Berjalan di latar belakang. Mengawasi jadwal 08:00 WIB, Minggu 20:00, & 23:00.")

    while _RUNNING:
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            current_hour = now.hour
            current_minute = now.minute
            current_weekday = now.weekday()  # 6 = Sunday

            # 1. Jadwal Pagi (Mulai 08:00 WIB hingga sebelum siang)
            if 8 <= current_hour < 12 and last_briefing_date != today_str:
                run_morning_briefing_once(today_str)
                last_briefing_date = today_str

            # 2. Jadwal Rekap Mingguan (Minggu 20:00 WIB)
            if current_weekday == 6 and current_hour == 20 and last_review_week != today_str:
                trigger_weekly_review()
                last_review_week = today_str

            # 3. Jadwal Backup Malam (23:00 WIB)
            if current_hour == 23 and current_minute >= 0 and last_backup_date != today_str:
                trigger_nightly_backup()
                last_backup_date = today_str

        except Exception as e:
            print(f"[Heartbeat Warning] Kesalahan di siklus loop: {e}")

        # Tidur selama 30 detik sebelum memeriksa waktu berikutnya
        for _ in range(30):
            if not _RUNNING:
                break
            time.sleep(1)

    print("🛑 [Heartbeat Daemon] Dihentikan.")


def start_background_scheduler():
    """Memulai thread background heartbeat daemon."""
    global _SCHEDULER_THREAD, _RUNNING
    if _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive():
        return
    _RUNNING = True
    _SCHEDULER_THREAD = threading.Thread(target=_scheduler_loop, daemon=True)
    _SCHEDULER_THREAD.start()


def stop_background_scheduler():
    """Menghentikan thread background heartbeat daemon."""
    global _RUNNING
    _RUNNING = False


if __name__ == "__main__":
    print("==================================================")
    print("⏰ Carl Second Brain Heartbeat Daemon (Frontier B)")
    print("==================================================")
    print("Tekan Ctrl+C untuk keluar.\n")
    try:
        _scheduler_loop()
    except KeyboardInterrupt:
        print("\nMenutup Heartbeat Daemon...")
        stop_background_scheduler()

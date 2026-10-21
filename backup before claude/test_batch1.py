# test_batch1.py
"""
Suite Pengujian Menyeluruh untuk Level 5 Batch 1:
- Frontier E: Vault Snapshot Backup & Windows Toast
- Frontier F: Obsidian Visual Canvas (.canvas)
- Frontier B: Background Heartbeat Scheduler
- Frontier A: FastAPI Server & Sidecar Endpoints
"""

import sys
import json
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.vault_backup import backup_vault, run_backup_command
from tools.tool_canvas import generate_canvas
import scheduler
from fastapi.testclient import TestClient
from api_server import app


def test_frontier_e_backup():
    print("\n--- [1/4] Menguji Frontier E: Vault Backup ---")
    res = backup_vault()
    assert res["success"] is True, f"Backup failed: {res.get('error')}"
    zip_path = Path(res["zip_path"])
    assert zip_path.exists(), "Arsip backup tidak ditemukan di disk"
    assert res["file_count"] > 0, "Jumlah berkas tercadangkan 0"
    print(f"✅ Frontier E Lolos: {res['file_count']} file terarsip ke {zip_path.name} ({res['size_mb']} MB)")


def test_frontier_f_canvas():
    print("\n--- [2/4] Menguji Frontier F: Visual Canvas Generator ---")
    res = generate_canvas("Sistem Otonom Level 5 AI")
    assert res["success"] is True, f"Canvas creation failed: {res.get('error')}"
    canvas_file = Path(res["file_path"])
    assert canvas_file.exists(), "File .canvas tidak ada di disk"
    
    # Validasi isi format JSON Canvas
    with open(canvas_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "nodes" in data and len(data["nodes"]) > 0, "Nodes canvas kosong"
    assert "edges" in data and len(data["edges"]) > 0, "Edges canvas kosong"
    print(f"✅ Frontier F Lolos: Berkas {canvas_file.name} valid dengan {len(data['nodes'])} kartu & {len(data['edges'])} alur")


def test_frontier_b_scheduler():
    print("\n--- [3/4] Menguji Frontier B: Heartbeat Scheduler ---")
    res_review = scheduler.trigger_weekly_review()
    assert "Weekly Review" in res_review or "mingguan" in res_review, "Weekly review trigger failed"
    print("✅ Frontier B Lolos: Weekly review trigger sukses")


def test_frontier_a_api():
    print("\n--- [4/4] Menguji Frontier A: FastAPI Sidecar & Endpoints ---")
    with TestClient(app) as client:
        # 1. UI Root
        resp_ui = client.get("/")
        assert resp_ui.status_code == 200, "Gagal meload root UI"
        assert "Carl" in resp_ui.text, "Title UI tidak sesuai"

        # 2. System Status
        resp_status = client.get("/api/status")
        assert resp_status.status_code == 200, "Gagal mengambil status API"
        st = resp_status.json()
        assert st["status"] == "online"
        assert st["total_notes"] > 0

        # 3. Chat Command (/rules)
        resp_chat = client.post("/api/chat", json={"query": "/rules"})
        assert resp_chat.status_code == 200, "Gagal mengeksekusi chat"
        assert "SOP" in resp_chat.json()["reply"] or "Aturan" in resp_chat.json()["reply"]

        # 4. Chat Reset
        resp_reset = client.post("/api/reset")
        assert resp_reset.status_code == 200
        assert "Sesi" in resp_reset.json()["reply"]

    print("✅ Frontier A Lolos: UI, Status, Chat, & Reset API berfungsi sempurna!")


if __name__ == "__main__":
    print("🚀 MEMULAI PENGUJIAN REGRESI LEVEL 5 BATCH 1...")
    try:
        test_frontier_e_backup()
        test_frontier_f_canvas()
        test_frontier_b_scheduler()
        test_frontier_a_api()
        print("\n🎉 SEMUA 4 FRONTIER BATCH 1 (A, B, E, F) 100% LOLOS PENGUJIAN!")
    except Exception as e:
        print(f"\n❌ PENGUJIAN GAGAL: {e}")
        sys.exit(1)


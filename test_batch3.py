# test_batch3.py
"""
Suite Pengujian Menyeluruh untuk Level 5 Batch 3:
- Frontier G: Serendipity Engine & Cross-Domain Discovery (memory/serendipity.py)
- Frontier H: Local Multi-Device Mobile Bridge & Quick Memo (bridge_server.py)
- Frontier I: Calendar Synchronizer (.ics) & Research Ingestion (tools/tool_calendar.py)
- API Integration: FastAPI endpoints untuk seluruh fitur Batch 3
"""

import sys
import os
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from memory.serendipity import discover_cross_domain_serendipity, run_serendipity_command
from bridge_server import get_local_ip, generate_qr_ascii, get_bridge_info, save_quick_memo, run_bridge_command
from tools.tool_calendar import (
    scan_vault_deadlines,
    export_vault_calendar_ics,
    ingest_research_paper,
    run_calendar_command,
    run_research_command
)
from fastapi.testclient import TestClient
from api_server import app


def test_frontier_g_serendipity():
    print("\n--- [1/4] Menguji Frontier G: Serendipity Engine ---")
    results = discover_cross_domain_serendipity(top_k=2)
    assert isinstance(results, list), "Hasil serendipity harus berupa list"
    
    reply = run_serendipity_command()
    assert "Serendipity" in reply or "Eureka" in reply or "koneksi" in reply, "Output teks serendipity tidak sesuai format"
    print(f"✅ Frontier G Lolos: Serendipity Engine berhasil mendeteksi {len(results)} pasangan ide lintas folder.")


def test_frontier_h_mobile_bridge():
    print("\n--- [2/4] Menguji Frontier H: Local Multi-Device Mobile Bridge ---")
    local_ip = get_local_ip()
    assert local_ip and isinstance(local_ip, str), "Gagal mendeteksi local IP"
    
    info = get_bridge_info(port=8000)
    assert info["status"] == "active"
    assert "http://" in info["mobile_url"]

    qr_ascii = generate_qr_ascii(info["mobile_url"])
    assert len(qr_ascii) > 50, "QR Code ASCII kosong"

    # Uji Quick Memo Capture
    memo_res = save_quick_memo(
        content="Ide riset kedaulatan data AI lokal tanpa cloud.",
        title="Test Memo Mobile Batch 3",
        tags=["ide", "kedaulatan-ai"]
    )
    assert memo_res["success"] is True, f"Quick memo gagal disimpan: {memo_res.get('error')}"
    memo_file = Path(memo_res["file_path"])
    assert memo_file.exists(), "Berkas catatan memo tidak ditemukan di 00-Inbox"

    # Bersihkan file uji memo
    try:
        memo_file.unlink()
    except Exception:
        pass

    print(f"✅ Frontier H Lolos: IP Host {local_ip}, QR Code valid, dan Quick Memo tersimpan ke 00-Inbox.")


def test_frontier_i_calendar_and_research():
    print("\n--- [3/4] Menguji Frontier I: Calendar (.ics) & Research Ingestion ---")
    # 1. Calendar
    cal_res = export_vault_calendar_ics("test_calendar.ics")
    assert cal_res["success"] is True, f"Ekspor .ics gagal: {cal_res.get('error')}"
    cal_path = Path(cal_res["file_path"])
    assert cal_path.exists(), "File .ics tidak dibuat di disk"
    
    content = cal_path.read_text(encoding="utf-8")
    assert "BEGIN:VCALENDAR" in content and "END:VCALENDAR" in content, "Struktur RFC 5545 iCalendar tidak valid"
    print(f"✅ Frontier I (Calendar) Lolos: File .ics berhasil dibuat dengan {cal_res['event_count']} deadline terindeks.")

    # Bersihkan file uji kalender
    try:
        cal_path.unlink()
    except Exception:
        pass

    # 2. Research Ingestion
    res_paper = ingest_research_paper("Autonomous Multi-Agent AI System")
    assert res_paper["success"] is True, f"Ingest research gagal: {res_paper.get('error')}"
    paper_path = Path(res_paper["file_path"])
    assert paper_path.exists(), "Berkas paper tidak dibuat di 03-Resources/Riset"
    
    paper_content = paper_path.read_text(encoding="utf-8")
    assert "literature-review" in paper_content or "arxiv" in paper_content, "Metadata literature note tidak sesuai"
    print(f"✅ Frontier I (Research) Lolos: Paper '{res_paper['title'][:40]}...' diarsipkan ke {paper_path.name}")

    # Bersihkan file uji riset
    try:
        paper_path.unlink()
    except Exception:
        pass


def test_frontier_api_endpoints():
    print("\n--- [4/4] Menguji API Endpoints Batch 3 ---")
    with TestClient(app) as client:
        # 1. Bridge Endpoint
        resp_bridge = client.get("/api/bridge")
        assert resp_bridge.status_code == 200
        bridge_data = resp_bridge.json()
        assert "mobile_url" in bridge_data
        assert "qr_ascii" in bridge_data

        # 2. Quick Memo Endpoint
        resp_memo = client.post("/api/quick-memo", json={
            "title": "Uji API Memo",
            "content": "Pencatatan langsung dari endpoint /api/quick-memo."
        })
        assert resp_memo.status_code == 200
        assert resp_memo.json()["status"] == "ok"
        memo_path = Path(resp_memo.json()["memo"]["file_path"])
        if memo_path.exists():
            memo_path.unlink()

        # 3. Serendipity Endpoint
        resp_serendipity = client.post("/api/serendipity")
        assert resp_serendipity.status_code == 200
        assert "reply" in resp_serendipity.json()

        # 4. Calendar Endpoint
        resp_cal = client.post("/api/calendar")
        assert resp_cal.status_code == 200
        assert "Jadwal_Carl_AI.ics" in resp_cal.json()["reply"]

        # 5. Research Endpoint
        resp_res = client.post("/api/research", json={"query": "Neural Search"})
        assert resp_res.status_code == 200
        assert "Frontier I" in resp_res.json()["reply"]

        # 6. Chat Command Routing (/bridge & /calendar list)
        resp_chat_bridge = client.post("/api/chat", json={"query": "/bridge"})
        assert resp_chat_bridge.status_code == 200
        assert "Mobile Bridge" in resp_chat_bridge.json()["reply"]

        resp_chat_cal = client.post("/api/chat", json={"query": "/calendar list"})
        assert resp_chat_cal.status_code == 200
        assert "Calendar" in resp_chat_cal.json()["reply"]

    print("✅ API Endpoints Batch 3 Lolos: /api/bridge, /api/quick-memo, /api/serendipity, /api/calendar, /api/research beroperasi sempurna!")


if __name__ == "__main__":
    print("🚀 MEMULAI PENGUJIAN REGRESI LEVEL 5 BATCH 3...")
    try:
        test_frontier_g_serendipity()
        test_frontier_h_mobile_bridge()
        test_frontier_i_calendar_and_research()
        test_frontier_api_endpoints()
        print("\n🎉 SEMUA FITUR BATCH 3 (Frontier G: Serendipity, H: Mobile Bridge, I: Calendar & Research) 100% LOLOS PENGUJIAN!")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n❌ PENGUJIAN BATCH 3 GAGAL: {e}")
        sys.exit(1)


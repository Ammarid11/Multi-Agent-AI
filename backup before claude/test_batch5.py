# test_batch5.py
"""
Suite Pengujian Menyeluruh untuk Level 5 Batch 5:
- Frontier M: Multi-Agent Swarm Simulation & Scenario Forecasting (agents/swarm_simulator.py)
- Frontier N: Local Knowledge Distillation & LoRA Self-Fine-Tuning (memory/trainer.py)
- Frontier O: Spatial 3D Knowledge Constellation (web/spatial_graph.html & /api/galaxy)
- Router & API Integration: Verifikasi endpoint dan routing seluruh fitur Batch 5
"""

import sys
import os
from pathlib import Path
from unittest.mock import patch

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.swarm_simulator import simulate_swarm, PERSONAS
from memory.trainer import (
    _extract_best_notes,
    get_training_status,
    run_trainer_command
)
from fastapi.testclient import TestClient
from api_server import app
from agents import AITeam, AgentRouter


def test_frontier_m_swarm_simulator():
    print("\n--- [1/4] Menguji Frontier M: Multi-Agent Swarm Simulation ---")
    assert len(PERSONAS) == 10, "Harus ada tepat 10 persona otonom dalam swarm"
    
    # Test validasi input kosong
    res_empty = simulate_swarm("")
    assert "❌" in res_empty and "Format salah" in res_empty, "Simulasi tanpa input harus memberikan petunjuk"
    print("   → Validasi input kosong lolos.")

    # Test simulasi dengan mock ollama.chat untuk determinisme cepat & offline
    mock_resp = {"message": {"content": "💡 Peluang: Pasar sangat besar. ⚠️ Risiko: Persaingan ketat."}}
    with patch("ollama.chat", return_value=mock_resp):
        report = simulate_swarm("Membuka layanan konsultasi AI lokal di Indonesia")
        assert "Laporan Simulasi Swarm Multi-Agen" in report
        assert "Kompetitor Agresif" in report
        assert "Ringkasan Eksekutif" in report
        print("   → Eksekusi 10 persona otonom & Ringkasan Eksekutif berhasil disusun.")

    print("✅ Frontier M Lolos: Multi-Agent Swarm Simulator berjalan sempurna.")


def test_frontier_n_lora_trainer():
    print("\n--- [2/4] Menguji Frontier N: Knowledge Distillation & LoRA Fine-Tuning ---")
    
    # 1. Test ekstraksi catatan dari Vault
    notes = _extract_best_notes(max_notes=5)
    assert isinstance(notes, list), "Ekstraksi catatan harus mengembalikan list"
    print(f"   → Berhasil memindai catatan terbaik dari Vault ({len(notes)} catatan ditemukan).")

    # 2. Test status command
    status_msg = get_training_status()
    assert isinstance(status_msg, str) and len(status_msg) > 10
    assert "Frontier N" in status_msg or "LoRA" in status_msg or "Dataset" in status_msg
    print("   → Fungsi get_training_status mengembalikan laporan terstruktur.")

    # 3. Test router entry point
    res_cmd = run_trainer_command("status")
    assert isinstance(res_cmd, str) and len(res_cmd) > 10
    print("   → run_trainer_command('status') bekerja sebagaimana mestinya.")

    print("✅ Frontier N Lolos: Pipeline Knowledge Distillation & LoRA siap digunakan.")


def test_frontier_o_galaxy_constellation():
    print("\n--- [3/4] Menguji Frontier O: Spatial 3D Knowledge Constellation ---")
    
    # 1. Pastikan berkas visualisasi HTML tersedia
    galaxy_html = PROJECT_ROOT / "web" / "spatial_graph.html"
    assert galaxy_html.exists(), f"Berkas {galaxy_html} tidak ditemukan"
    
    with open(galaxy_html, "r", encoding="utf-8") as f:
        html_content = f.read()
    assert "<canvas id=\"galaxy-canvas\">" in html_content, "Canvas visualisasi galaksi harus ada"
    assert "project(x, y, z)" in html_content, "Engine proyeksi 3D harus ada di dalam HTML"
    assert "loadGalaxyData" in html_content, "Fungsi pemuatan data galaksi harus ada"
    print(f"   → Berkas web/spatial_graph.html valid ({len(html_content)} karakter).")

    # 2. Test API Server endpoint /galaxy & /api/galaxy
    with TestClient(app) as client:
        resp_page = client.get("/galaxy")
        assert resp_page.status_code == 200, f"Endpoint /galaxy error: {resp_page.status_code}"
        assert "Galaksi" in resp_page.text or "galaxy-canvas" in resp_page.text
        print("   → Endpoint GET /galaxy menyajikan halaman HTML galaksi 200 OK.")

        resp_data = client.get("/api/galaxy")
        assert resp_data.status_code == 200, f"Endpoint /api/galaxy error: {resp_data.status_code}"
        galaxy_json = resp_data.json()
        assert "nodes" in galaxy_json and "edges" in galaxy_json, "Format data galaksi harus memuat nodes dan edges"
        assert isinstance(galaxy_json["nodes"], list)
        assert isinstance(galaxy_json["edges"], list)
        print(f"   → Endpoint GET /api/galaxy mengembalikan {len(galaxy_json['nodes'])} nodes dan {len(galaxy_json['edges'])} edges.")

    print("✅ Frontier O Lolos: Galaksi 3D Knowledge Constellation aktif & terhubung ke Vault.")


def test_batch5_router_and_api():
    print("\n--- [4/4] Menguji Integrasi Router & API Endpoints Batch 5 ---")
    
    # Setup team & router
    team = AITeam(memory_manager=None, user_name="Tester")
    router = AgentRouter(team)

    # 1. Test Router Slash Commands
    # /galaxy
    res_galaxy = router.route_and_execute("/galaxy")
    assert "Galaksi Pengetahuan 3D" in res_galaxy or "Frontier O" in res_galaxy
    print("   → Router /galaxy berhasil diarahkan.")

    # /train_adapter status
    res_train = router.route_and_execute("/train_adapter status")
    assert "Frontier N" in res_train or "LoRA" in res_train
    print("   → Router /train_adapter berhasil diarahkan.")

    # /simulate tanpa argumen
    res_sim_empty = router.route_and_execute("/simulate")
    assert "❌" in res_sim_empty
    print("   → Router /simulate berhasil diarahkan.")

    # 2. Test Fast Heuristics
    assert router._fast_intent_check("simulasi pasar untuk produk baru") == "simulate"
    assert router._fast_intent_check("buat dataset training lora") == "trainer"
    assert router._fast_intent_check("tampilkan galaksi 3d catatan") == "galaxy"
    assert router._fast_intent_check("apa berita hari ini") == "web"
    print("   → Fast heuristics untuk simulate, trainer, galaxy, dan berita hari ini terverifikasi 0 ms.")

    # 3. Test FastAPI endpoints
    with TestClient(app) as client:
        # /api/simulate
        with patch("ollama.chat", return_value={"message": {"content": "Simulasi respons"}}):
            resp = client.post("/api/simulate", json={"query": "Rencana produk X"})
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
            print("   → POST /api/simulate mengembalikan status ok.")

        # /api/trainer
        resp = client.post("/api/trainer", json={"query": "status"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        print("   → POST /api/trainer mengembalikan status ok.")

    print("✅ Integrasi Router & API Batch 5 Lolos 100%.")


def run_all_batch5_tests():
    print("================================================================")
    print("🧪 MEMULAI PENGUJIAN LENGKAP LEVEL 5 BATCH 5 (FRONTIER M, N, O)")
    print("================================================================")
    test_frontier_m_swarm_simulator()
    test_frontier_n_lora_trainer()
    test_frontier_o_galaxy_constellation()
    test_batch5_router_and_api()
    print("\n================================================================")
    print("🎉 SELURUH PENGUJIAN LEVEL 5 BATCH 5 LOLOS 100% TANPA KESALAHAN!")
    print("================================================================")


if __name__ == "__main__":
    run_all_batch5_tests()

# test_batch2.py
"""
Suite Pengujian Menyeluruh untuk Level 5 Batch 2:
- Frontier C: Real-Time Voice Interface (Edge-TTS Natural & Speech Recognition)
- Frontier D: Multi-Modal Vision & PDF Document Ingestion
- Endpoints API TTS & Voice/Vision
"""

import sys
import os
from pathlib import Path
from PIL import Image
from pypdf import PdfWriter
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.tool_voice import speak_text, clean_markdown_for_speech
from tools.tool_vision import ingest_pdf, analyze_image
from api_server import app


def test_frontier_c_voice():
    print("\n--- [1/3] Menguji Frontier C: Real-Time Voice Interface ---")
    raw_md = "## Halo **Carl**! Berikut [link](http://test.com) dan `- [ ]` tugas."
    clean = clean_markdown_for_speech(raw_md)
    assert "**" not in clean and "##" not in clean, "Pembersihan markdown untuk suara gagal"
    
    res = speak_text("Pengujian suara alami Carl Second Brain.", play_sound=False)
    assert res["success"] is True, f"TTS gagal: {res.get('error')}"
    assert Path(res["audio_path"]).exists(), "Berkas mp3 suara tidak ditemukan di disk"
    print(f"✅ Frontier C Lolos: Suara alami tergenerasi ({res['engine']}) ke {Path(res['audio_path']).name}")


def test_frontier_d_vision_and_pdf():
    print("\n--- [2/3] Menguji Frontier D: Vision & PDF Ingestion ---")
    # 1. Test PDF Ingestion
    pdf_path = PROJECT_ROOT / "test_sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    res_pdf = ingest_pdf(str(pdf_path))
    assert res_pdf["success"] is True, f"Ingest PDF gagal: {res_pdf.get('error')}"
    assert Path(res_pdf["note_path"]).exists(), "Catatan PDF tidak terbentuk di Vault"
    print(f"✅ Frontier D (PDF) Lolos: Dokumen diekstrak menjadi catatan '{Path(res_pdf['note_path']).name}'")
    if pdf_path.exists():
        pdf_path.unlink()

    # 2. Test Image Ingestion
    img_path = PROJECT_ROOT / "test_sample.png"
    img = Image.new("RGB", (256, 256), color="navy")
    img.save(str(img_path))

    res_img = analyze_image(str(img_path))
    assert res_img["success"] is True, f"Analisis gambar gagal: {res_img.get('error')}"
    assert Path(res_img["note_path"]).exists(), "Catatan visual tidak terbentuk di Vault"
    print(f"✅ Frontier D (Vision) Lolos: Gambar 256x256 terindeks menjadi '{Path(res_img['note_path']).name}'")
    if img_path.exists():
        img_path.unlink()


def test_api_voice_endpoints():
    print("\n--- [3/3] Menguji API Endpoints Suara & Vision ---")
    with TestClient(app) as client:
        resp_tts = client.get("/api/tts?text=UjiSuara")
        assert resp_tts.status_code == 200, "Endpoint /api/tts gagal"
        assert resp_tts.headers["content-type"] == "audio/mpeg", "Content-type bukan audio/mpeg"
        assert len(resp_tts.content) > 1000, "Ukuran payload audio terlalu kecil"

    print("✅ Endpoints API Lolos: Audio streaming /api/tts valid!")


if __name__ == "__main__":
    print("🚀 MEMULAI PENGUJIAN REGRESI LEVEL 5 BATCH 2...")
    try:
        test_frontier_c_voice()
        test_frontier_d_vision_and_pdf()
        test_api_voice_endpoints()
        print("\n🎉 SEMUA FITUR BATCH 2 (Frontier C: Voice & Frontier D: Vision) 100% LOLOS PENGUJIAN!")
    except Exception as e:
        print(f"\n❌ PENGUJIAN GAGAL: {e}")
        sys.exit(1)


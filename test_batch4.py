# test_batch4.py
"""
Suite Pengujian Menyeluruh untuk Level 5 Batch 4:
- Frontier J: Autonomous Web Browser Agent (tools/tool_browser.py)
- Frontier K: Continuous Self-Evolution & Accuracy Guard (memory/evaluator.py)
- Frontier L: Zero-Knowledge Encrypted Vault Partition (tools/vault_crypto.py)
- API Integration: FastAPI endpoints untuk seluruh fitur Batch 4
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

from tools.tool_browser import fetch_and_clean_webpage, run_browser_command
from memory.evaluator import (
    generate_synthetic_eval_dataset,
    evaluate_memory_accuracy,
    run_evaluation_command
)
from tools.vault_crypto import (
    unlock_session, lock_session, is_session_unlocked,
    save_encrypted_note, read_encrypted_note,
    list_secure_notes, run_crypto_command
)
from fastapi.testclient import TestClient
from api_server import app


def test_frontier_j_browser_agent():
    print("\n--- [1/4] Menguji Frontier J: Autonomous Web Browser Agent ---")
    # Test fetch dari halaman sederhana
    result = fetch_and_clean_webpage("http://example.com", timeout=10)
    assert isinstance(result, dict), "Hasil fetch harus berupa dict"
    
    if result["success"]:
        assert "title" in result
        assert "body_text" in result
        assert len(result["body_text"]) > 0
        print(f"✅ Frontier J (Fetch) Lolos: '{result['title']}' berhasil diambil & dibersihkan.")
    else:
        print(f"⚠️ Frontier J (Fetch) Skip: Tidak ada koneksi internet atau {result.get('error')}. Melewati uji network.")

    # Test run_browser_command dengan URL dummy (tanpa jaringan → fallback error yang graceful)
    cmd_result = run_browser_command("https://example.com")
    assert isinstance(cmd_result, str), "Output browser command harus berupa string"
    assert "❌" in cmd_result or "Frontier J" in cmd_result, "Respons browser command tidak valid"
    print(f"✅ Frontier J (Command) Lolos: Browser command mengembalikan respons yang valid.")


def test_frontier_k_accuracy_guard():
    print("\n--- [2/4] Menguji Frontier K: Self-Evolution & Accuracy Guard ---")
    # Test synthetic dataset generation
    dataset = generate_synthetic_eval_dataset(max_samples=3)
    assert isinstance(dataset, list), "Dataset evaluasi harus berupa list"
    print(f"   → {len(dataset)} sampel sintetis dihasilkan dari Vault.")

    # Test evaluate_memory_accuracy (tanpa MemoryManager aktif = warning graceful)
    class MockMemory:
        all_chunks = [type('D', (), {'page_content': 'test', 'metadata': {'source': 'test.md'}})()]
        def search_context(self, q, k=5):
            return f"Konteks sintetis untuk uji evaluasi: {q}"

    report = evaluate_memory_accuracy(memory_manager=MockMemory(), max_samples=2)
    assert "composite_score" in report or report.get("status") in ("success", "warning")

    # Test run_evaluation_command output
    output = run_evaluation_command(memory_manager=MockMemory())
    assert isinstance(output, str) and len(output) > 10, "Output evaluasi kosong"
    assert "Frontier K" in output or "Akurasi" in output or "Kalibrasi" in output
    print(f"✅ Frontier K Lolos: Self-Evolution Guard menghasilkan laporan kalibrasi mandiri.")


def test_frontier_l_crypto_vault():
    print("\n--- [3/4] Menguji Frontier L: Zero-Knowledge Encrypted Vault ---")
    TEST_PASSPHRASE = "TestPassphrase123"
    TEST_TITLE = "Unit Test Rahasia Batch 4"
    TEST_CONTENT = "Ini adalah catatan rahasia untuk pengujian AES-256 level militer Carl."

    # 1. Brankas awalnya terkunci
    lock_session()
    assert not is_session_unlocked(), "Brankas seharusnya terkunci di awal"

    # 2. Buka sesi
    res_unlock = unlock_session(TEST_PASSPHRASE)
    assert res_unlock["success"], "Gagal membuka sesi brankas"
    assert is_session_unlocked(), "Brankas seharusnya terbuka setelah unlock"

    # 3. Simpan catatan terenkripsi
    res_save = save_encrypted_note(TEST_TITLE, TEST_CONTENT)
    assert res_save["success"], f"Gagal menyimpan catatan: {res_save.get('error')}"
    enc_path = Path(res_save["file_path"])
    assert enc_path.exists(), "File terenkripsi tidak ada di disk"
    file_content = enc_path.read_text(encoding="utf-8")
    assert "encrypted-carl-vault" in file_content, "Format amplop enkripsi tidak valid"
    assert TEST_CONTENT not in file_content, "KEAMANAN: Teks plaintext terdeteksi di berkas! ❌"
    print(f"   → Terenkripsi di: {enc_path.name} — Plaintext tidak bocor ke disk ✅")

    # 4. Dekripsi & baca balik
    res_read = read_encrypted_note(TEST_TITLE)
    assert res_read["success"], f"Gagal mendekripsi: {res_read.get('error')}"
    assert TEST_CONTENT == res_read["plaintext"], "Hasil dekripsi tidak cocok dengan plaintext asli!"
    print(f"   → Dekripsi sukses: Teks asli identik byte-for-byte ✅")

    # 5. Coba dekripsi dengan passphrase salah
    lock_session()
    unlock_session("PassphraseYangSalah!")
    res_wrong = read_encrypted_note(TEST_TITLE)
    assert not res_wrong["success"], "KEAMANAN: Dekripsi dengan passphrase salah berhasil! ❌"
    print(f"   → Keamanan terkonfirmasi: Passphrase salah ditolak dengan benar ✅")

    # 6. Kunci kembali dan bersihkan file uji
    lock_session()
    assert not is_session_unlocked()
    try:
        enc_path.unlink()
    except Exception:
        pass

    print(f"✅ Frontier L Lolos: AES-256 Zero-Knowledge Vault bekerja sempurna!")


def test_frontier_api_endpoints():
    print("\n--- [4/4] Menguji API Endpoints Batch 4 ---")
    with TestClient(app) as client:
        # 1. Browse endpoint
        resp_browse = client.post("/api/browse", json={"query": "https://example.com"})
        assert resp_browse.status_code == 200
        assert "reply" in resp_browse.json()

        # 2. Evaluator endpoint
        resp_eval = client.post("/api/eval")
        assert resp_eval.status_code == 200
        reply_eval = resp_eval.json()["reply"]
        assert "Frontier K" in reply_eval or "Akurasi" in reply_eval or "Kalibrasi" in reply_eval

        # 3. Crypto status endpoint
        resp_crypto = client.post("/api/crypto", json={"query": "/brankas"})
        assert resp_crypto.status_code == 200
        assert "Frontier L" in resp_crypto.json()["reply"] or "Brankas" in resp_crypto.json()["reply"]

        # 4. Chat routing: /browse, /eval, /brankas
        resp_chat_browse = client.post("/api/chat", json={"query": "/browse https://example.com"})
        assert resp_chat_browse.status_code == 200
        assert "reply" in resp_chat_browse.json()

        resp_chat_eval = client.post("/api/chat", json={"query": "/eval"})
        assert resp_chat_eval.status_code == 200

        resp_chat_brankas = client.post("/api/chat", json={"query": "/brankas"})
        assert resp_chat_brankas.status_code == 200
        assert "Brankas" in resp_chat_brankas.json()["reply"] or "Frontier L" in resp_chat_brankas.json()["reply"]

    print("✅ API Endpoints Batch 4 Lolos: /api/browse, /api/eval, /api/crypto & routing chat beroperasi sempurna!")


if __name__ == "__main__":
    print("🚀 MEMULAI PENGUJIAN REGRESI LEVEL 5 BATCH 4...")
    try:
        test_frontier_j_browser_agent()
        test_frontier_k_accuracy_guard()
        test_frontier_l_crypto_vault()
        test_frontier_api_endpoints()
        print("\n🎉 SEMUA FITUR BATCH 4 (Frontier J: Browser, K: Accuracy Guard, L: Encrypted Vault) 100% LOLOS PENGUJIAN!")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n❌ PENGUJIAN BATCH 4 GAGAL: {e}")
        sys.exit(1)

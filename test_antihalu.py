"""
Test Suite: Verifikasi Proteksi Anti-Halusinasi & Ketahanan Tool
Menguji seluruh guardrails yang diterapkan berdasarkan hasil-audit-AI-Halucination.md.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(__file__))

import config
from memory.user_profile import update_profile_from_interaction, load_user_profile, clear_user_facts
from memory.rules_engine import detect_and_register_rule, load_rules
from tools.tool_append import find_file_in_vault
from tools.tool_create import create_file
from tools.tool_relocate import relocate_content


class TestAntiHallucinationGuardrails(unittest.TestCase):

    def setUp(self):
        # Reset fakta profil sementara
        clear_user_facts("TestUser")

    def test_user_profile_rejects_questions(self):
        """Memastikan pertanyaan tidak diserap menjadi fakta profil."""
        # 1. Kalimat tanya dengan tanda tanya
        update_profile_from_interaction("Apakah saya suka makan durian?", user_name="TestUser")
        p = load_user_profile("TestUser")
        facts = p.get("key_facts", [])
        self.assertFalse(any("durian" in f.lower() for f in facts), "Kalimat tanya ber-tanda '?' terserap ke profil!")

        # 2. Kalimat pengandaian
        update_profile_from_interaction("Kalau saya ingin beli mobil bekas, apa sarannya?", user_name="TestUser")
        p = load_user_profile("TestUser")
        facts = p.get("key_facts", [])
        self.assertFalse(any("mobil" in f.lower() for f in facts), "Pengandaian terserap ke fakta!")

        # 3. Pernyataan afirmatif deklaratif yang sah
        update_profile_from_interaction("Saya adalah software engineer spesialis Python", user_name="TestUser")
        p = load_user_profile("TestUser")
        facts = p.get("key_facts", [])
        self.assertTrue(any("software engineer" in f.lower() for f in facts), "Pernyataan deklaratif sah gagal diserap!")

    def test_rules_engine_rejects_casual_questions(self):
        """Memastikan kalimat tanya kasual tidak berubah menjadi SOP operasional."""
        # 1. Pertanyaan kasual yang mengandung 'setiap kali'
        res = detect_and_register_rule("Setiap kali saya tidur larut malam, kenapa kepala pusing?")
        self.assertIsNone(res, "Pertanyaan kasual dengan '?' terdaftar menjadi aturan!")

        # 2. Pertanyaan tanpa tanda tanya tapi diawali kata tanya
        res = detect_and_register_rule("Aturan: apa saja makanan sehat")
        self.assertIsNone(res, "Pertanyaan 'apa' terdaftar menjadi aturan!")

        # 3. SOP sah
        res = detect_and_register_rule("Aturan: selalu berikan ringkasan poin di awal jawaban")
        self.assertIsNotNone(res, "Aturan eksplisit yang valid gagal didaftarkan!")

    @patch("agents.bot_web.web_search_structured")
    def test_bot_web_groundedness_guard(self, mock_search):
        """Memastikan jika pencarian web 0 hasil, bot_web menolak mengarang berita tanpa memanggil LLM."""
        from agents.bot_web import run_bot_web
        
        # Simulasikan DuckDuckGo offline / 0 hasil
        mock_search.return_value = ("⚠️ Tidak ditemukan hasil pencarian web.", [])

        mock_memory = MagicMock()
        mock_memory.search_context.return_value = ""

        # Panggil bot_web
        reply = run_bot_web("berita politik hari ini", mock_memory, [])

        self.assertIn("Proteksi Anti-Halusinasi Aktif", reply)
        self.assertIn("menolak mengarang berita", reply)

    def test_tool_relocate_newline_robustness(self):
        """Memastikan pemindahan teks tahan terhadap perbedaan baris baru CRLF vs LF."""
        test_file_src = os.path.join(config.VAULT_PATH, "00-Inbox", "TestRelocateSrc.md")
        test_file_tgt = os.path.join(config.VAULT_PATH, "00-Inbox", "TestRelocateTgt.md")

        try:
            with open(test_file_src, "w", encoding="utf-8") as f:
                f.write("# Catatan Asal\r\n\r\nBaris pertama yang akan dipindahkan.\r\nBaris kedua yang tetap ada.\r\n")

            with open(test_file_tgt, "w", encoding="utf-8") as f:
                f.write("# Catatan Tujuan\r\n")

            snippet = "Baris pertama yang akan dipindahkan."
            res = relocate_content("TestRelocateSrc.md", "TestRelocateTgt.md", snippet)
            self.assertIn("Berhasil memindahkan materi", res)

            with open(test_file_src, "r", encoding="utf-8") as f:
                content_after = f.read()
            self.assertIn("Dipindahkan ke", content_after)

        finally:
            if os.path.exists(test_file_src):
                os.remove(test_file_src)
            if os.path.exists(test_file_tgt):
                os.remove(test_file_tgt)


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 MENJALANKAN PENGUJIAN ANTI-HALUSINASI & GUARDRAILS")
    print("=" * 60)
    unittest.main(verbosity=2)


"""
Test Suite: Verifikasi Frontier P (Gemini Browser Bridge)
Menguji integrasi router, sesi Playwright, dan dokumentasi dialog ke Obsidian Vault.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(__file__))

from agents import AITeam, AgentRouter
from agents.gemini_browser import (
    GeminiBrowserSession,
    ask_gemini_once,
    run_carl_gemini_dialog,
    _get_best_browser_channel
)


class TestGeminiBrowserBridge(unittest.TestCase):

    def test_browser_channel_detection(self):
        """Memastikan pendeteksian channel browser lokal berjalan."""
        channel, _ = _get_best_browser_channel()
        self.assertIn(channel, ["msedge", "chrome", "chromium"])

    def test_router_gemini_commands(self):
        """Memastikan router menangkap perintah /gemini dan /gemini_dialog."""
        mock_team = MagicMock()
        mock_team.bot_gemini.return_value = "Gemini Response OK"
        mock_team.bot_gemini_dialog.return_value = "Dialog Completed OK"

        router = AgentRouter(mock_team)

        # 1. /gemini
        res1 = router._check_command("/gemini apa itu AI?", "/gemini apa itu AI?")
        self.assertEqual(res1, "Gemini Response OK")
        mock_team.bot_gemini.assert_called_with("apa itu AI?")

        # 2. /gemini_dialog
        res2 = router._check_command("/gemini_dialog Strategi 2026", "/gemini_dialog Strategi 2026")
        self.assertEqual(res2, "Dialog Completed OK")
        mock_team.bot_gemini_dialog.assert_called_with("Strategi 2026")

    @patch("agents.gemini_browser.GeminiBrowserSession.start")
    @patch("agents.gemini_browser.GeminiBrowserSession.ensure_logged_in")
    def test_not_logged_in_notice(self, mock_login, mock_start):
        """Memastikan jika pengguna belum login Google, sistem memberikan instruksi yang jelas."""
        mock_login.return_value = False

        res = ask_gemini_once("Halo")
        self.assertIn("Waktu Login Google Habis atau Dibatalkan", res)

    @patch("agents.gemini_browser.GeminiBrowserSession.start")
    @patch("agents.gemini_browser.GeminiBrowserSession.ensure_logged_in")
    @patch("agents.gemini_browser.GeminiBrowserSession.send_prompt")
    @patch("ollama.chat")
    def test_dialog_saves_to_vault(self, mock_ollama, mock_send, mock_login, mock_start):
        """Memastikan alur dialog multi-turn menghasilkan catatan terstruktur di Vault."""
        mock_login.return_value = True
        mock_send.return_value = "Pandangan Gemini tentang masa depan AI sangat cerah."

        # Mock Ollama Carl response
        mock_res = MagicMock()
        mock_res.message.content = "Tanggapan kritis Carl atas argumen Gemini."
        mock_ollama.return_value = mock_res

        mock_memory = MagicMock()
        mock_memory.search_context.return_value = "- Catatan AI 2026"

        result = run_carl_gemini_dialog(topic="Uji Otomasi Unit Test", turns=2, memory_manager=mock_memory)

        self.assertIn("Diskusi Carl & Google Gemini Sukses Diselesaikan", result)
        self.assertIn("03-Resources/Diskusi Carl & Gemini", result)

    @patch("agents.gemini_browser.GeminiBrowserSession.start")
    @patch("agents.gemini_browser.GeminiBrowserSession.ensure_logged_in")
    @patch("agents.gemini_browser.GeminiBrowserSession.send_prompt")
    @patch("ollama.chat")
    def test_tutoring_session_saves_curriculum_and_reindexes(self, mock_ollama, mock_send, mock_login, mock_start):
        """Memastikan sesi les Carl dengan Guru Gemini menghasilkan kurikulum dan me-reindex memori."""
        from agents.gemini_browser import run_carl_tutoring_session
        mock_login.return_value = True
        mock_send.return_value = "Ini adalah konsep inti dan best practices arsitektur microservices 2026."

        mock_res = MagicMock()
        mock_res.message.content = "Terima kasih Guru Gemini. Bagaimana strategi mitigasi latency antarlayanan?"
        mock_ollama.return_value = mock_res

        mock_memory = MagicMock()
        mock_memory.search_context.return_value = "Catatan awal microservices"

        result = run_carl_tutoring_session(topic="Microservices Modern", turns=2, memory_manager=mock_memory)

        self.assertIn("Sesi Les Privat Carl bersama Guru Gemini Sukses Diselesaikan", result)
        self.assertIn("03-Resources/Materi Les Carl - Microservices Modern.md", result)
        mock_memory.index_vault.assert_called_with(silent=True)

    @patch("agents.gemini_browser.GeminiBrowserSession.start")
    @patch("agents.gemini_browser.GeminiBrowserSession.ensure_logged_in")
    @patch("agents.gemini_browser.GeminiBrowserSession.send_prompt")
    @patch("ollama.chat")
    def test_carl_runs_unlimited_until_empty_response(self, mock_ollama, mock_send, mock_login, mock_start):
        """Memastikan Carl (turns=0) terus belajar hingga Gemini tidak merespons (reply kosong)."""
        from agents.gemini_browser import run_carl_tutoring_session
        mock_login.return_value = True

        # Gemini merespons 3 kali lalu kosong → loop berhenti natural
        mock_send.side_effect = [
            "Penjelasan babak 0.",
            "Penjelasan putaran 1.",
            "Penjelasan putaran 2.",
            "",   # Gemini tidak merespons → loop berhenti
            "Closing dikirim.",
        ]

        mock_res = MagicMock()
        mock_res.message.content = "Kenapa hal ini terjadi, apa ada alasannya?"
        mock_ollama.return_value = mock_res

        result = run_carl_tutoring_session(topic="Topic Test", turns=0, memory_manager=None)

        self.assertIn("Sesi Les Privat Carl bersama Guru Gemini Sukses Diselesaikan", result)
        # Babak 0 + 2 putaran berhasil = 3 penjelasan Gemini (putaran 3 kosong → berhenti)
        self.assertIn("3 putaran pembelajaran", result)

    @patch("agents.gemini_browser.GeminiBrowserSession.start")
    @patch("agents.gemini_browser.GeminiBrowserSession.ensure_logged_in")
    @patch("agents.gemini_browser.GeminiBrowserSession.send_prompt")
    @patch("ollama.chat")
    def test_carl_limited_turns_stops_at_n(self, mock_ollama, mock_send, mock_login, mock_start):
        """Memastikan Carl (turns=3) berhenti tepat di 3 putaran."""
        from agents.gemini_browser import run_carl_tutoring_session
        mock_login.return_value = True
        mock_send.return_value = "Penjelasan Guru Gemini."

        mock_res = MagicMock()
        mock_res.message.content = "Apa implikasi lebih lanjut dari konsep ini?"
        mock_ollama.return_value = mock_res

        result = run_carl_tutoring_session(topic="Topic Terbatas", turns=3, memory_manager=None)

        self.assertIn("Sesi Les Privat Carl bersama Guru Gemini Sukses Diselesaikan", result)
        # Babak 0 + 3 putaran = 4 penjelasan Gemini total
        self.assertIn("4 putaran pembelajaran", result)
        # send_prompt: babak 0 (1) + putaran 1,2,3 (3) + closing (1) = 5 kali
        self.assertEqual(mock_send.call_count, 5)

    @patch("agents.gemini_browser.GeminiBrowserSession.start")
    @patch("agents.gemini_browser.GeminiBrowserSession.ensure_logged_in")
    @patch("agents.gemini_browser.GeminiBrowserSession.send_prompt")
    @patch("ollama.chat")
    def test_carl_answers_gemini_question(self, mock_ollama, mock_send, mock_login, mock_start):
        """Memastikan Carl menjawab soal/kuis dari Gemini dengan langkah-langkah, bukan bertanya balik."""
        from agents.gemini_browser import run_carl_tutoring_session

        mock_login.return_value = True
        # Gemini memberikan kuis, lalu putaran 2 kosong → loop berhenti
        mock_send.side_effect = [
            "Bagus pertanyaanmu! Sekarang coba kerjakan: berapa hasil dari 5 x 3 + 2?",  # babak 0
            "Jawaban 17 sudah tepat!",  # putaran 1
            "",                          # putaran 2 kosong → berhenti
            "Sama-sama!",               # closing
        ]

        res_open = MagicMock()
        res_open.message.content = "Halo Guru! Tolong ajarkan matematika dasar dari awal."
        res_quiz_answer = MagicMock()
        res_quiz_answer.message.content = "5 x 3 = 15, lalu 15 + 2 = 17. Jawabannya adalah 17. Apakah sudah benar, Guru?"
        res_followup = MagicMock()
        res_followup.message.content = "Apakah ada perbedaan aturan jika ada tanda kurung, Guru?"
        mock_ollama.side_effect = [res_open, res_quiz_answer, res_followup]

        result = run_carl_tutoring_session(topic="Matematika Dasar Kuis", turns=0, memory_manager=None)

        self.assertIn("Sesi Les Privat Carl bersama Guru Gemini Sukses Diselesaikan", result)
        # Carl harus mengirimkan jawaban kuis (yang mengandung angka 17)
        sent_texts = [call.args[0] if call.args else call.kwargs.get("prompt", "") for call in mock_send.call_args_list]
        quiz_answered = any("17" in t or "benar" in t.lower() for t in sent_texts)
        self.assertTrue(quiz_answered, "Carl seharusnya mengirimkan jawaban kuis yang mengandung hasil perhitungan.")

    @patch("agents.gemini_browser.GeminiBrowserSession.start")
    @patch("agents.gemini_browser.GeminiBrowserSession.ensure_logged_in")
    @patch("agents.gemini_browser.GeminiBrowserSession.send_prompt")
    @patch("ollama.chat")
    def test_browser_closed_handled_gracefully(self, mock_ollama, mock_send, mock_login, mock_start):
        """Memastikan jika tab/browser ditutup user (Locator.fill / Target page closed), Carl menyimpan materi tanpa error."""
        from agents.gemini_browser import run_carl_tutoring_session
        mock_login.return_value = True

        # Babak 0 berhasil dapat materi, lalu di putaran 1 browser ditutup
        mock_send.side_effect = [
            "Materi dasar fisika dari Guru Gemini.",  # babak 0
            RuntimeError("Locator.fill: Target page, context or browser has been closed"),  # putaran 1 tutup tab
        ]

        mock_res = MagicMock()
        mock_res.message.content = "Apa itu gravitasi?"
        mock_ollama.return_value = mock_res

        result = run_carl_tutoring_session(topic="Fisika Tab Closed", turns=0, memory_manager=None)

        # Tidak boleh ada tanda silang merah error fatal
        self.assertNotIn("❌ Terjadi kesalahan", result)
        # Materi yang sudah diperoleh di babak 0 tetap berhasil tersimpan
        self.assertIn("seluruh materi tetap tersimpan aman", result)
        self.assertIn("1 putaran pembelajaran", result)

    @patch("agents.gemini_browser.GeminiBrowserSession.start")
    @patch("agents.gemini_browser.GeminiBrowserSession.ensure_logged_in")
    @patch("agents.gemini_browser.GeminiBrowserSession.send_prompt")
    @patch("ollama.chat")
    def test_manual_stop_tutoring_stops_and_saves(self, mock_ollama, mock_send, mock_login, mock_start):
        """Memastikan sinyal stop manual menghentikan loop Carl dan menyimpan materi yang sudah terkumpul."""
        from agents.gemini_browser import run_carl_tutoring_session, request_stop_tutoring
        mock_login.return_value = True

        responses = iter(["Penjelasan babak 0.", "Jawaban Gemini saat tombol stop ditekan."])
        def mock_send_fn(prompt):
            val = next(responses)
            if "babak 0" not in val:
                request_stop_tutoring()
            return val

        mock_send.side_effect = mock_send_fn

        mock_res = MagicMock()
        mock_res.message.content = "Pertanyaan Carl sebelum stop."
        mock_ollama.return_value = mock_res

        result = run_carl_tutoring_session(topic="Stop Manual Test", turns=0, memory_manager=None)

        self.assertNotIn("❌ Terjadi kesalahan", result)
        self.assertIn("Dihentikan Manual", result)

    def test_clean_gemini_response_formats_code_blocks(self):
        """Memastikan artefak kode Gemini (misal: 'Pythonnilai = 80') diformat rapi dengan Markdown code fences."""
        from agents.gemini_browser import clean_gemini_response_text

        raw_sample = (
            "Contoh Sintaks Dasar:\n"
            "Pythonnilai = 80\n"
            "if nilai >= 75:\n"
            "print(\"Selamat, Anda Lulus!\")\n"
            "else:\n"
            "print(\"Maaf, Anda Belum Lulus.\")\n\n"
            "Penjelasan kode di atas:\n"
            "Nilai 80 memenuhi syarat."
        )

        cleaned = clean_gemini_response_text(raw_sample)

        # 1. Harus mengandung triple backticks dengan bahasa python
        self.assertIn("```python", cleaned)
        self.assertIn("```", cleaned)
        # 2. Tidak boleh ada artefak 'Pythonnilai = 80'
        self.assertNotIn("Pythonnilai = 80", cleaned)
        # 3. Baris kode terpisah dan terindentasi
        self.assertIn("nilai = 80", cleaned)
        self.assertIn("    print(\"Selamat, Anda Lulus!\")", cleaned)
        self.assertIn("    print(\"Maaf, Anda Belum Lulus.\")", cleaned)
        # 4. Teks penjelas di luar kode tetap utuh
        self.assertIn("Penjelasan kode di atas:", cleaned)



if __name__ == "__main__":
    print("=" * 60)
    print("🧪 MENJALANKAN PENGUJIAN FRONTIER P (GEMINI BROWSER BRIDGE)")
    print("=" * 60)
    unittest.main(verbosity=2)


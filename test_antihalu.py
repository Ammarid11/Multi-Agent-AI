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
        """Web search failure abstains without leaking Vault or chat context."""
        from agents.bot_web import run_bot_web
        
        # Simulasikan DuckDuckGo offline / 0 hasil
        mock_search.return_value = ("⚠️ Tidak ditemukan hasil pencarian web.", [])

        mock_memory = MagicMock()
        history = [{"role": "assistant", "content": "RAHASIA_DARI_RIWAYAT"}]
        reply = run_bot_web(
            "berita politik hari ini",
            mock_memory,
            history,
            session_context="RAHASIA_DARI_SESI",
        )

        self.assertIn("Proteksi Anti-Halusinasi Aktif", reply)
        self.assertIn("Penyebabnya belum dapat dipastikan", reply)
        self.assertNotIn("RAHASIA_DARI_RIWAYAT", reply)
        self.assertNotIn("RAHASIA_DARI_SESI", reply)
        self.assertNotIn("Vault Obsidian", reply)
        mock_memory.search_context.assert_not_called()

    def test_bot_web_search_query_extracts_topic_from_detailed_recency_prompt(self):
        from agents.bot_web import _build_web_search_query

        prompt = (
            "Cari perkembangan terbaru yang dapat diverifikasi tentang misi Artemis II "
            "NASA per 15 Oktober 2026. Utamakan sumber resmi NASA; jika memakai berita "
            "tambahan, pisahkan jelas."
        )

        self.assertEqual(
            _build_web_search_query(prompt),
            "berita terbaru misi Artemis II NASA per 15 Oktober 2026",
        )

    @patch("agents.bot_web.ollama.chat")
    @patch("agents.bot_web.web_search_structured")
    def test_bot_web_success_uses_only_web_results_and_original_request(
        self,
        mock_search,
        mock_chat,
    ):
        from types import SimpleNamespace
        from agents.bot_web import run_bot_web

        mock_search.return_value = (
            "NASA announced the latest mission update.",
            [
                {
                    "title": "NASA Artemis II Update",
                    "url": "https://www.nasa.gov/example",
                    "source": "NASA",
                    "date": "15 October 2026",
                    "snippet": "Official mission update.",
                }
            ],
        )
        mock_chat.return_value = SimpleNamespace(
            message=SimpleNamespace(content="NASA's update is summarized here.")
        )
        memory = MagicMock()
        history = [{"role": "assistant", "content": "HISTORY_SECRET"}]
        prompt = (
            "Cari perkembangan terbaru tentang misi Artemis II NASA. Sertakan "
            "tanggal publikasi dan bedakan dari tanggal peristiwa."
        )

        reply = run_bot_web(
            prompt,
            memory,
            history,
            session_context="SESSION_SECRET",
        )

        self.assertIn("NASA's update is summarized here.", reply)
        self.assertIn("15 October 2026", reply)
        self.assertIn("https://www.nasa.gov/example", reply)
        mock_search.assert_called_once_with(
            "berita terbaru misi Artemis II NASA",
        )
        memory.search_context.assert_not_called()
        messages = mock_chat.call_args.kwargs["messages"]
        serialized_messages = "\n".join(message["content"] for message in messages)
        self.assertIn("NASA announced the latest mission update.", serialized_messages)
        self.assertIn(prompt, serialized_messages)
        self.assertNotIn("HISTORY_SECRET", serialized_messages)
        self.assertNotIn("SESSION_SECRET", serialized_messages)
        self.assertNotIn("KONTEKS CATATAN SECOND BRAIN", serialized_messages)

    @patch("agents.bot_web.ollama.chat")
    @patch("agents.bot_web.web_search_structured")
    def test_nasa_official_request_abstains_without_official_result(
        self,
        mock_search,
        mock_chat,
    ):
        from agents.bot_web import run_bot_web

        mock_search.side_effect = [
            ("No official results.", []),
            (
                "Third-party article context.",
                [{
                    "title": "Third-party Artemis report",
                    "url": "https://news.example/artemis",
                    "source": "news.example",
                    "snippet": "A report about the Artemis II mission.",
                    "date_label": "Tanggal publikasi tidak terverifikasi",
                }],
            ),
        ]
        prompt = (
            "Cari perkembangan terbaru tentang misi Artemis II NASA per 15 Oktober "
            "2026. Utamakan sumber resmi NASA."
        )

        reply = run_bot_web(prompt, MagicMock(), [])

        self.assertIn("tidak ditemukan hasil dari domain resmi NASA", reply)
        self.assertIn("bahan latar, bukan bukti status terbaru", reply)
        mock_chat.assert_not_called()
        self.assertEqual(mock_search.call_count, 2)
        self.assertTrue(mock_search.call_args_list[0].args[0].startswith("site:nasa.gov "))

    @patch("agents.bot_web.ollama.chat")
    @patch("agents.bot_web.web_search_structured")
    def test_nasa_official_request_abstains_when_official_date_is_stale(
        self,
        mock_search,
        mock_chat,
    ):
        from agents.bot_web import run_bot_web

        mock_search.side_effect = [
            (
                "Old official context.",
                [{
                    "title": "Old NASA Artemis report",
                    "url": "https://www.nasa.gov/artemis",
                    "source": "NASA",
                    "snippet": "An old report about the mission.",
                    "verified_date": "2026-04-09",
                    "date_label": "Tanggal publikasi di metadata halaman: 9 April 2026",
                }],
            ),
            ("Third-party context.", []),
        ]
        prompt = (
            "Cari perkembangan terbaru tentang misi Artemis II NASA per 15 Oktober "
            "2026. Utamakan sumber resmi NASA."
        )

        reply = run_bot_web(prompt, MagicMock(), [])

        self.assertIn("tidak cukup baru", reply)
        self.assertIn("Status informasi yang diminta belum dapat diverifikasi", reply)
        mock_chat.assert_not_called()

    @patch("agents.bot_web.ollama.chat")
    @patch("agents.bot_web.web_search_structured")
    def test_nasa_official_recent_metadata_allows_web_synthesis(
        self,
        mock_search,
        mock_chat,
    ):
        from types import SimpleNamespace
        from agents.bot_web import run_bot_web

        mock_search.side_effect = [
            (
                "NASA announced a recent update.",
                [{
                    "title": "NASA Artemis update",
                    "url": "https://www.nasa.gov/artemis",
                    "source": "NASA",
                    "snippet": "A recent official report about the mission.",
                    "verified_date": "2026-10-14",
                    "date_label": "Tanggal publikasi di metadata halaman: 14 October 2026",
                }],
            ),
            ("Additional context.", []),
        ]
        mock_chat.return_value = SimpleNamespace(
            message=SimpleNamespace(content="Ringkasan berdasarkan sumber resmi.")
        )
        prompt = (
            "Cari perkembangan terbaru tentang misi Artemis II NASA per 15 Oktober "
            "2026. Utamakan sumber resmi NASA."
        )

        reply = run_bot_web(prompt, MagicMock(), [])

        self.assertIn("Ringkasan berdasarkan sumber resmi.", reply)
        mock_chat.assert_called_once()

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

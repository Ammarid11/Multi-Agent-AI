"""Offline regression tests for Carl's response-format guidance and answer benchmark."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from agents.bot_reasoner import run_bot_reasoner, should_use_deep_reasoning
from agents.bot_writer import (
    _extract_markdown_section,
    _resolve_summary_source,
    is_named_note_summary_request,
    run_bot_writer,
)
from agents.bot_synthesizer import run_bot_synthesizer
from agents.grounding import (
    VAULT_FACT_CHECK_FALLBACK,
    add_explicit_vault_sources,
    build_vault_recency_context,
    format_vault_recency_fallback,
    is_vault_fact_check_request,
    is_vault_recency_request,
    missing_vault_recency_requirements,
    validate_vault_answer,
    UNGROUNDED_VAULT_ANSWER,
)
from memory.answer_evaluator import load_answer_benchmark

PROJECT_ROOT = Path(__file__).resolve().parent
BENCHMARK_PATH = PROJECT_ROOT / "evaluation" / "answer_benchmark.json"


class EmptyMemory:
    @staticmethod
    def search_context(_query, k=6):
        return ""


class ContextMemory:
    def __init__(self, context):
        self.context = context

    def search_context(self, _query, k=6):
        return self.context


class TestCognitivePromptQuality(unittest.TestCase):
    def test_d4_prompt_is_recognized_as_a_vault_claim_check(self):
        prompt = (
            "Apakah keputusan bahwa QA dilakukan manual dan otomasi pengecekan "
            "dibatalkan tercatat sebagai fakta di Vault saya?"
        )

        self.assertTrue(is_vault_fact_check_request(prompt))

    def test_d4_writer_excludes_chat_history_and_repairs_unsupported_citations(self):
        prompt = (
            "Di percakapan kita sebelumnya saya pernah bilang: ‘Saya cek manual aja "
            "di sini, lupain yang tadi saya mau bikin otomasi pengecekan.’ Apakah "
            "keputusan bahwa QA dilakukan manual dan otomasi pengecekan dibatalkan "
            "tercatat sebagai fakta di Vault saya?"
        )
        context = (
            "[Sumber: Diskusi Carl & Gemini - Uji Otomasi Unit Test.md]\n"
            "Catatan ini berisi diskusi umum tentang uji otomasi unit test."
        )
        first = SimpleNamespace(
            message=SimpleNamespace(
                content=(
                    "Pengguna ingin melanjutkan otomasi dan membatalkan QA manual. "
                    "[Sumber: Diskusi Carl & Gemini - Uji Otomatisasi Unit Test.md]"
                )
            )
        )
        repaired = SimpleNamespace(
            message=SimpleNamespace(
                content=(
                    "Konteks yang ditemukan hanya menunjukkan diskusi umum tentang "
                    "uji otomasi unit test; konteks itu tidak secara langsung "
                    "menyatakan keputusan QA manual atau pembatalan otomasi. "
                    "[Sumber: Diskusi Carl & Gemini - Uji Otomasi Unit Test.md]\n\n"
                    "Hasil retrieval yang tersedia belum membuktikan keputusan itu "
                    "dan tidak cukup untuk menyimpulkan ketiadaannya di seluruh Vault. "
                    "[Sumber: Diskusi Carl & Gemini - Uji Otomasi Unit Test.md]"
                )
            )
        )
        history = [
            {"role": "user", "content": "Sebelumnya saya mau mengotomatisasi QA."},
            {"role": "assistant", "content": "Anda ingin meneruskan otomasi."},
        ]

        with patch(
            "agents.bot_writer.chat_with_optional_stream",
            side_effect=[first, repaired],
        ) as chat:
            result = run_bot_writer(
                prompt,
                ContextMemory(context),
                history,
                session_context="Riwayat sesi: pengguna ingin meneruskan otomasi.",
                user_name="Pengguna",
            )

        first_messages = chat.call_args_list[0].kwargs["messages"]
        system_prompt = first_messages[0]["content"]
        self.assertIn("teks yang dikutip pengguna dan riwayat percakapan hanya sebagai objek", system_prompt)
        self.assertIn("Jangan membalik makna kutipan", system_prompt)
        self.assertNotIn("Riwayat sesi: pengguna ingin meneruskan otomasi.", system_prompt)
        self.assertEqual(len(first_messages), 2)
        self.assertEqual(chat.call_count, 2)
        self.assertNotIn("Pengguna ingin melanjutkan otomasi", result)
        self.assertIn("belum membuktikan keputusan itu", result)
        self.assertIn(
            "[Sumber: Diskusi Carl & Gemini - Uji Otomasi Unit Test.md]",
            result,
        )

    def test_d4_writer_returns_explanatory_fallback_after_failed_citation_repair(self):
        prompt = (
            "Apakah keputusan bahwa QA dilakukan manual dan otomasi pengecekan "
            "dibatalkan tercatat sebagai fakta di Vault saya?"
        )
        bad_response = SimpleNamespace(
            message=SimpleNamespace(
                content="QA manual sudah dibatalkan. [Sumber: Catatan Palsu.md]"
            )
        )

        with patch(
            "agents.bot_writer.chat_with_optional_stream",
            side_effect=[bad_response, bad_response],
        ) as chat:
            result = run_bot_writer(
                prompt,
                ContextMemory("[Sumber: QA.md]\nCatatan tentang pengujian umum."),
                [],
            )

        self.assertEqual(result, VAULT_FACT_CHECK_FALLBACK)
        self.assertEqual(chat.call_count, 2)
        self.assertIn("bukan bukti", result)
        self.assertIn("tidak membuktikan", result)
        self.assertNotIn("tidak tercatat", result)

    def test_d4_missing_vault_context_gets_fact_check_specific_fallback(self):
        prompt = (
            "Apakah keputusan QA manual tercatat sebagai fakta di Vault saya?"
        )

        with patch("agents.bot_writer.chat_with_optional_stream") as chat:
            writer_result = run_bot_writer(prompt, EmptyMemory(), [])
        with patch("agents.bot_reasoner.chat_with_optional_stream") as chat:
            reasoner_result = run_bot_reasoner(prompt, EmptyMemory(), [])

        self.assertEqual(writer_result, VAULT_FACT_CHECK_FALLBACK)
        self.assertEqual(reasoner_result, VAULT_FACT_CHECK_FALLBACK)
        chat.assert_not_called()

    def test_d4_reasoner_excludes_chat_history_and_validates_vault_citations(self):
        prompt = (
            "Apakah keputusan QA manual dan pembatalan otomasi pengecekan tercatat "
            "sebagai fakta di Vault?"
        )
        context = (
            "[Sumber: QA.md]\nCatatan ini hanya membahas pengujian otomatis secara umum."
        )
        response = SimpleNamespace(
            message=SimpleNamespace(
                content=(
                    "Konteks yang tersedia tidak secara langsung mencatat keputusan "
                    "tersebut; ini tidak membuktikan bahwa seluruh Vault tidak "
                    "memuatnya. [Sumber: QA.md]"
                )
            )
        )
        history = [{"role": "user", "content": "Saya akan lanjutkan otomasi."}]

        with patch(
            "agents.bot_reasoner.chat_with_optional_stream",
            return_value=response,
        ) as chat:
            result = run_bot_reasoner(
                prompt,
                ContextMemory(context),
                history,
                session_context="Riwayat sesi: otomasi dilanjutkan.",
            )

        messages = chat.call_args.kwargs["messages"]
        self.assertIn("perlakukan teks yang dikutip pengguna dan riwayat percakapan", messages[0]["content"])
        self.assertNotIn("Riwayat sesi: otomasi dilanjutkan.", messages[0]["content"])
        self.assertEqual(len(messages), 2)
        self.assertIn("tidak secara langsung mencatat keputusan", result)
        self.assertIn("[Sumber: QA.md]", result)

    def test_d4_reasoner_returns_explanatory_fallback_after_failed_citation_repair(self):
        prompt = (
            "Apakah keputusan QA manual tercatat sebagai fakta di Vault?"
        )
        bad_response = SimpleNamespace(
            message=SimpleNamespace(
                content="Keputusan itu tersimpan. [Sumber: Tidak Ada.md]"
            )
        )

        with patch(
            "agents.bot_reasoner.chat_with_optional_stream",
            side_effect=[bad_response, bad_response],
        ) as chat:
            result = run_bot_reasoner(
                prompt,
                ContextMemory("[Sumber: QA.md]\nCatatan pengujian umum."),
                [],
            )

        self.assertEqual(result, VAULT_FACT_CHECK_FALLBACK)
        self.assertEqual(chat.call_count, 2)

    def test_explicit_vault_paths_are_added_to_context_for_d1(self):
        prompt = (
            "Saya menemukan dua path Vault yang berbeda. "
            "`03-Resources/Auto-Mount Boot Trigger.md` mencatat "
            "`E:\\Obsidian\\Brain AI Memory`, sedangkan "
            "`05-Daily Notes/2026-09-02.md` mencatat "
            "`E:\\Project AI 2026\\Obsidian\\Brain AI Memory`. "
            "Apa konflik informasinya?"
        )
        with TemporaryDirectory() as directory:
            vault = Path(directory)
            (vault / "03-Resources").mkdir()
            (vault / "05-Daily Notes").mkdir()
            (vault / "03-Resources" / "Auto-Mount Boot Trigger.md").write_text(
                "Target Vault: `E:\\Obsidian\\Brain AI Memory`",
                encoding="utf-8",
            )
            (vault / "05-Daily Notes" / "2026-09-02.md").write_text(
                "Vault utama: `E:\\Project AI 2026\\Obsidian\\Brain AI Memory`",
                encoding="utf-8",
            )

            context, errors = add_explicit_vault_sources(prompt, "", vault)

        self.assertEqual(errors, [])
        self.assertIn("[Sumber: 03-Resources/Auto-Mount Boot Trigger.md]", context)
        self.assertIn("[Sumber: 05-Daily Notes/2026-09-02.md]", context)
        self.assertIn("E:\\Obsidian\\Brain AI Memory", context)
        self.assertIn("E:\\Project AI 2026\\Obsidian\\Brain AI Memory", context)

    def test_d1_writer_can_answer_from_explicitly_named_vault_notes(self):
        prompt = (
            "Saya menemukan dua path Vault yang berbeda. "
            "`03-Resources/Auto-Mount Boot Trigger.md` mencatat "
            "`E:\\Obsidian\\Brain AI Memory`, sedangkan "
            "`05-Daily Notes/2026-09-02.md` mencatat "
            "`E:\\Project AI 2026\\Obsidian\\Brain AI Memory`. "
            "Apa konflik informasinya? Sebutkan kedua sumber dan path-nya."
        )
        with TemporaryDirectory() as directory:
            vault = Path(directory)
            (vault / "03-Resources").mkdir()
            (vault / "05-Daily Notes").mkdir()
            (vault / "03-Resources" / "Auto-Mount Boot Trigger.md").write_text(
                "Target Vault: `E:\\Obsidian\\Brain AI Memory`",
                encoding="utf-8",
            )
            (vault / "05-Daily Notes" / "2026-09-02.md").write_text(
                "Vault utama: `E:\\Project AI 2026\\Obsidian\\Brain AI Memory`",
                encoding="utf-8",
            )
            answer = (
                "Kedua catatan mencatat path Vault yang berbeda. "
                "[Sumber: Auto-Mount Boot Trigger.md]\n\n"
                "- Auto-Mount mencatat `E:\\Obsidian\\Brain AI Memory`. "
                "[Sumber: Auto-Mount Boot Trigger.md]\n"
                "- Daily Note 2026-09-02 mencatat "
                "`E:\\Project AI 2026\\Obsidian\\Brain AI Memory`. "
                "[Sumber: 2026-09-02.md]\n\n"
                "Catatan menunjukkan konflik, tetapi tidak membuktikan path aktif saat ini. "
                "[Sumber: Auto-Mount Boot Trigger.md] "
                "[Sumber: 2026-09-02.md]"
            )
            response = SimpleNamespace(message=SimpleNamespace(content=answer))
            with (
                patch("agents.bot_writer.config.VAULT_PATH", str(vault)),
                patch("agents.bot_writer.generate_or_get_vault_map") as vault_map,
                patch("agents.bot_writer.ollama.chat", return_value=response) as chat,
            ):
                result = run_bot_writer(prompt, EmptyMemory(), [])

        vault_map.assert_not_called()
        self.assertIn("E:\\Obsidian\\Brain AI Memory", chat.call_args.kwargs["messages"][0]["content"])
        self.assertIn("E:\\Project AI 2026\\Obsidian\\Brain AI Memory", chat.call_args.kwargs["messages"][0]["content"])
        self.assertNotEqual(result, UNGROUNDED_VAULT_ANSWER)
        self.assertIn("[Sumber: Auto-Mount Boot Trigger.md]", result)
        self.assertIn("[Sumber: 2026-09-02.md]", result)

    def test_writer_makes_proactive_recommendations_conditional(self):
        response = SimpleNamespace(message=SimpleNamespace(content="Jawaban singkat."))
        with (
            patch("agents.bot_writer.generate_or_get_vault_map", return_value=""),
            patch("agents.bot_writer.ollama.chat", return_value=response) as chat,
        ):
            run_bot_writer(
                "Apa ibu kota Jepang?",
                EmptyMemory(),
                [],
                user_name="Pengguna",
            )

        system_prompt = chat.call_args.kwargs["messages"][0]["content"]
        self.assertIn("bukan sebagai penutup wajib", system_prompt)
        self.assertIn("Jangan memaksakan gap analysis", system_prompt)
        self.assertIn("hanya jika sesuai", system_prompt)

    def test_general_knowledge_and_arithmetic_do_not_get_irrelevant_vault_notices(self):
        context = "[Sumber: Catatan Tidak Terkait.md]\nCatatan tentang topik lain."
        cases = (
            (
                "Apa itu organ tubuh yang mengalirkan darah ke seluruh tubuh?",
                "Jantung memompa darah ke seluruh tubuh.",
            ),
            (
                "Apakah AI akan menguasai dunia pasti benar?",
                "Tidak dapat dipastikan; itu prediksi tentang masa depan.",
            ),
            ("Berapa tepatnya 50 × 100 − 50?", "Hasilnya 4950."),
        )

        for prompt, answer in cases:
            with self.subTest(prompt=prompt):
                response = SimpleNamespace(message=SimpleNamespace(content=answer))
                with (
                    patch("agents.bot_writer.generate_or_get_vault_map", return_value=""),
                    patch("agents.bot_writer.ollama.chat", return_value=response) as chat,
                ):
                    result = run_bot_writer(
                        prompt,
                        ContextMemory(context),
                        [],
                        user_name="Pengguna",
                    )

                self.assertEqual(result, answer)
                system_prompt = chat.call_args.kwargs["messages"][0]["content"]
                self.assertIn("jangan menambahkan kode, anjuran verifikasi", system_prompt)
                self.assertIn("jangan menampilkan peringatan sitasi", system_prompt)

    def test_reasoner_general_uncertainty_answer_does_not_get_vault_warning(self):
        answer = "Tidak dapat dipastikan apakah AI akan menguasai dunia."
        response = SimpleNamespace(message=SimpleNamespace(content=answer))
        with patch("agents.bot_reasoner.chat_with_optional_stream", return_value=response):
            result = run_bot_reasoner(
                "Apakah AI akan menguasai dunia pasti benar?",
                ContextMemory("[Sumber: Catatan Tidak Terkait.md]\nTopik lain."),
                [],
            )

        self.assertEqual(result, answer)

    def test_vault_lookup_prompt_distinguishes_name_match_from_claim_evidence(self):
        response = SimpleNamespace(message=SimpleNamespace(content="Alvi ditemukan."))
        with (
            patch("agents.bot_writer.generate_or_get_vault_map", return_value=""),
            patch("agents.bot_writer.ollama.chat", return_value=response) as chat,
        ):
            result = run_bot_writer(
                "Catatan mana yang menyebut Alvi adalah perempuan?",
                ContextMemory("[Sumber: Data Profil Orang Lain.md]\nAlvi disebut di sini."),
                [],
                user_name="Pengguna",
            )

        system_prompt = chat.call_args.kwargs["messages"][0]["content"]
        self.assertIn("Bedakan penyebutan nama dari bukti atas klaim", system_prompt)
        self.assertIn("pertanyaan pengguna sendiri bukan bukti", system_prompt)
        self.assertIn("belum menyertakan sitasi", result)

    def test_reasoner_prompt_formats_answers_by_task_type(self):
        response = SimpleNamespace(message=SimpleNamespace(content="Jawaban."))
        with patch("agents.bot_reasoner.chat_with_optional_stream", return_value=response) as chat:
            run_bot_reasoner(
                "Bandingkan dua pilihan.",
                EmptyMemory(),
                [],
                user_name="Pengguna",
            )

        system_prompt = chat.call_args.kwargs["messages"][0]["content"]
        for instruction in (
            "FORMAT JAWABAN ADAPTIF",
            "Pertanyaan sederhana/faktual",
            "Analisis atau pemecahan masalah",
            "Perbandingan/keputusan",
            "Hitungan",
            "Permintaan multi-bagian",
            "Jangan memaksakan bagian akar masalah",
        ):
            with self.subTest(instruction=instruction):
                self.assertIn(instruction, system_prompt)

    def test_vault_comparison_prompts_require_sources_and_no_unsupported_context(self):
        response = SimpleNamespace(
            message=SimpleNamespace(
                content="Perbandingan singkat. [Sumber: Python.md] [Sumber: Java.md]"
            )
        )
        context = "[Sumber: Python.md]\nPython tercatat.\n[Sumber: Java.md]\nJava tercatat."
        with patch("agents.bot_reasoner.chat_with_optional_stream", return_value=response) as chat:
            run_bot_reasoner(
                "Bandingkan Python dan Java berdasarkan catatan Vault.",
                ContextMemory(context),
                [{"role": "user", "content": "Riwayat pribadi: proyek X."}],
                session_context="Proyek pengguna: Proyek X.",
                user_name="Pengguna",
            )

        system_prompt = chat.call_args.kwargs["messages"][0]["content"]
        for instruction in (
            "ATURAN PERBANDINGAN BERDASARKAN VAULT",
            "sebutkan sumbernya",
            "jangan mengisi celah dengan pengetahuan umum",
            "Jangan gunakan profil",
            "jangan menambahkan saran menyimpan/mengubah catatan",
        ):
            with self.subTest(instruction=instruction):
                self.assertIn(instruction, system_prompt)
        self.assertNotIn("Proyek pengguna: Proyek X.", system_prompt)
        self.assertEqual(len(chat.call_args.kwargs["messages"]), 2)

    def test_reasoner_abstains_if_vault_context_omits_a_comparison_subject(self):
        with patch("agents.bot_reasoner.chat_with_optional_stream") as chat:
            result = run_bot_reasoner(
                "Apa hubungan Python dan Java menurut catatan saya?",
                ContextMemory("[Sumber: Java.md]\nPython tercatat."),
                [],
            )

        self.assertIn("belum memuat bukti", result)
        chat.assert_not_called()

    def test_reasoner_discards_uncited_vault_comparison(self):
        response = SimpleNamespace(message=SimpleNamespace(content="Python lebih mudah dari Java."))
        with patch("agents.bot_reasoner.chat_with_optional_stream", return_value=response):
            result = run_bot_reasoner(
                "Bandingkan Python dan Java berdasarkan catatan Vault.",
                ContextMemory("[Sumber: Python.md]\nPython dan Java disebut."),
                [],
            )

        self.assertIn("tidak menyertakan sitasi", result)
        self.assertNotIn("lebih mudah", result)

    def test_reasoner_repairs_uncited_vault_answer_once(self):
        context = (
            "[Sumber: Auto-Mount Boot Trigger.md]\n"
            "Target Vault E:\\Obsidian\\Brain AI Memory.\n"
            "[Sumber: 2026-09-02.md]\n"
            "Vault utama E:\\Project AI 2026\\Obsidian\\Brain AI Memory."
        )
        first = SimpleNamespace(
            message=SimpleNamespace(
                content="Kedua catatan berbeda. [Sumber: Auto-Mount Boot Trigger.md]\n\n"
                "Ada asumsi tambahan yang tidak disitasi."
            )
        )
        repaired = SimpleNamespace(
            message=SimpleNamespace(
                content=(
                    "Auto-Mount mencatat `E:\\Obsidian\\Brain AI Memory`. "
                    "[Sumber: Auto-Mount Boot Trigger.md]\n\n"
                    "Catatan 2026-09-02 mencatat "
                    "`E:\\Project AI 2026\\Obsidian\\Brain AI Memory`. "
                    "[Sumber: 2026-09-02.md]\n\n"
                    "Catatan mencantumkan dua path yang berbeda, tetapi tidak "
                    "menentukan mana yang aktif. "
                    "[Sumber: Auto-Mount Boot Trigger.md] "
                    "[Sumber: 2026-09-02.md]"
                )
            )
        )
        with patch(
            "agents.bot_reasoner.chat_with_optional_stream",
            side_effect=[first, repaired],
        ) as chat:
            result = run_bot_reasoner(
                "Jelaskan konflik dua path berdasarkan catatan Vault.",
                ContextMemory(context),
                [],
            )

        self.assertIn("E:\\Obsidian\\Brain AI Memory", result)
        self.assertIn("E:\\Project AI 2026\\Obsidian\\Brain AI Memory", result)
        self.assertEqual(chat.call_count, 2)
        self.assertIn(
            "Tulis ulang jawaban secara ringkas",
            chat.call_args.kwargs["messages"][-1]["content"],
        )
        self.assertIn(
            "[Sumber: Auto-Mount Boot Trigger.md]",
            chat.call_args.kwargs["messages"][-1]["content"],
        )

    def test_vault_recency_context_keeps_topic_item_metadata_and_matching_reference(self):
        prompt = (
            "Di catatan Vault saya, apa informasi paling baru tentang "
            "pertumbuhan ekonomi daerah Indonesia?"
        )
        self.assertTrue(is_vault_recency_request(prompt))
        self.assertTrue(should_use_deep_reasoning(prompt))
        with TemporaryDirectory() as directory:
            vault = Path(directory)
            note = vault / "05-Daily Notes" / "2026-10-14.md"
            note.parent.mkdir()
            note.write_text(
                "---\ncreated: 2026-10-14 08:00\n---\n"
                "# Rangkuman Berita\n"
                "1. **Ekonomi Regional**\n"
                "- 99 kabupaten/kota di Indonesia mencatat pertumbuhan ekonomi "
                "di atas 6% selama semester I-2026.\n"
                "- Sumber: Waspada, 13 Oktober 2026.\n"
                "2. **Penjualan Mobil EV-Hybrid**\n"
                "- Penjualan EV-hybrid naik di atas 40% per Agustus 2026.\n"
                "- Sumber: Antara News, 14 Agustus 2026.\n"
                "Referensi:\n"
                "1. [BPS Catat 99 Kabupaten/Kota di Indonesia Alami Pertumbuhan "
                "di Atas 6 Persen](https://example.invalid/growth)\n"
                "2. [Pemerintah Catat Penjualan Mobil EV-Hybrid Naik di Atas "
                "40 Persen](https://example.invalid/ev)\n",
                encoding="utf-8",
            )

            context, errors = build_vault_recency_context(prompt, vault)

        self.assertEqual(errors, [])
        self.assertIn("[Sumber: 05-Daily Notes/2026-10-14.md]", context)
        self.assertIn("Tanggal catatan dari metadata `created`: 2026-10-14", context)
        self.assertIn("Waspada, 13 Oktober 2026", context)
        self.assertIn("BPS Catat 99 Kabupaten/Kota", context)
        self.assertNotIn("Penjualan EV-hybrid naik", context)
        self.assertNotIn("Pemerintah Catat Penjualan Mobil EV-Hybrid", context)
        fallback = format_vault_recency_fallback(context)
        self.assertIn("99 kabupaten/kota", fallback)
        self.assertIn("Waspada", fallback)
        self.assertIn("13 Oktober 2026", fallback)
        self.assertIn("2026-10-14", fallback)
        self.assertIn("belum cukup", fallback)

    def test_reasoner_uses_dated_recency_evidence_and_rejects_wrong_source_citation(self):
        prompt = (
            "Di catatan Vault saya, apa informasi paling baru tentang pertumbuhan "
            "ekonomi daerah Indonesia? Sebutkan angkanya, sumber berita dan tanggal "
            "publikasinya, serta tanggal catatan Vault. Jika pembanding tidak cukup, "
            "katakan demikian."
        )
        first = SimpleNamespace(
            message=SimpleNamespace(
                content=(
                    "BPS mencatat 99 daerah tumbuh di atas 6%. "
                    "[Sumber: Antara News, 14 Agustus 2026.md]"
                )
            )
        )
        repaired = SimpleNamespace(
            message=SimpleNamespace(
                content=(
                    "Catatan bertanggal 2026-10-14 menyebut 99 kabupaten/kota "
                    "mengalami pertumbuhan ekonomi di atas 6% pada semester I-2026; "
                    "item yang sama mencantumkan Waspada, 13 October 2026. "
                    "[Sumber: 2026-10-14.md]\n\n"
                    "Hanya satu item topik yang ditemukan, sehingga tidak cukup bukti "
                    "pembanding untuk memastikan bahwa informasi ini paling baru di "
                    "seluruh Vault. [Sumber: 2026-10-14.md]"
                )
            )
        )
        with TemporaryDirectory() as directory:
            vault = Path(directory)
            note = vault / "05-Daily Notes" / "2026-10-14.md"
            note.parent.mkdir()
            note.write_text(
                "---\ncreated: 2026-10-14\n---\n"
                "1. **Ekonomi Regional**\n"
                "- 99 kabupaten/kota di Indonesia mencatat pertumbuhan ekonomi "
                "di atas 6% selama semester I-2026.\n"
                "- Sumber: Waspada, 13 Oktober 2026.\n"
                "2. **Penjualan Mobil EV-Hybrid**\n"
                "- Penjualan EV-hybrid naik di atas 40% per Agustus 2026.\n"
                "- Sumber: Antara News, 14 Agustus 2026.\n",
                encoding="utf-8",
            )
            with (
                patch("agents.bot_reasoner.config.VAULT_PATH", directory),
                patch(
                    "agents.bot_reasoner.chat_with_optional_stream",
                    side_effect=[first, repaired],
                ) as chat,
            ):
                result = run_bot_reasoner(prompt, EmptyMemory(), [])

        self.assertIn("Waspada, 13 October 2026", result)
        self.assertNotIn("Antara News, 14 Agustus 2026", result)
        self.assertEqual(chat.call_count, 2)
        system_prompt = chat.call_args.kwargs["messages"][0]["content"]
        self.assertIn("metadata tanggal catatan", system_prompt)
        self.assertIn("item berita yang sama", chat.call_args.kwargs["messages"][-1]["content"])

    def test_recency_answer_requires_publisher_publication_date_note_date_and_caveat(self):
        prompt = (
            "Apa informasi paling baru tentang ekonomi daerah? Sebutkan sumber berita, "
            "tanggal publikasi, dan tanggal catatan Vault."
        )
        context = (
            "Bukti kebaruan dari 20 catatan Markdown.\n\n"
            "[Sumber: Daily/2026-10-14.md]\n"
            "Tanggal catatan dari metadata `created`: 2026-10-14\n"
            "Item Vault yang cocok dengan topik:\n"
            "- Sumber: Waspada, 13 October 2026."
        )
        incomplete = (
            "Ada 99 kabupaten/kota dengan pertumbuhan di atas 6%. "
            "[Sumber: 2026-10-14.md]"
        )
        complete = (
            "Waspada menerbitkan informasi itu pada 13 Oktober 2026; catatan Vault "
            "dibuat 14 Oktober 2026. [Sumber: 2026-10-14.md]\n\n"
            "Hanya satu item cocok ditemukan, jadi bukti pembanding tidak cukup untuk "
            "memastikan ini paling baru di seluruh Vault. [Sumber: 2026-10-14.md]"
        )

        self.assertEqual(
            len(missing_vault_recency_requirements(incomplete, context, prompt)),
            3,
        )
        self.assertEqual(missing_vault_recency_requirements(complete, context, prompt), [])

    def test_writer_recency_path_uses_dated_evidence_and_deterministic_fallback(self):
        prompt = (
            "Apa informasi paling baru tentang pertumbuhan ekonomi daerah Indonesia? "
            "Sebutkan sumber berita, tanggal publikasi, dan tanggal catatan Vault."
        )
        responses = [
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Klaim tanpa sitasi. [Sumber: Antara News.md]"
                )
            ),
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Ada 99 kabupaten/kota tumbuh di atas 6%. "
                    "[Sumber: 2026-10-14.md]"
                )
            ),
        ]
        with TemporaryDirectory() as directory:
            vault = Path(directory)
            note = vault / "05-Daily Notes" / "2026-10-14.md"
            note.parent.mkdir()
            note.write_text(
                "---\ncreated: 2026-10-14\n---\n"
                "1. **Ekonomi Regional**\n"
                "- 99 kabupaten/kota di Indonesia mencatat pertumbuhan ekonomi "
                "di atas 6% selama semester I-2026.\n"
                "- Sumber: Waspada, 13 October 2026.\n",
                encoding="utf-8",
            )
            with (
                patch("agents.bot_writer.config.VAULT_PATH", directory),
                patch(
                    "agents.bot_writer.chat_with_optional_stream",
                    side_effect=responses,
                ) as chat,
            ):
                result = run_bot_writer(prompt, EmptyMemory(), [])

        self.assertIn("Waspada", result)
        self.assertIn("13 October 2026", result)
        self.assertIn("2026-10-14", result)
        self.assertIn("bukti pembanding belum cukup", result)
        self.assertNotIn("Antara News", result)
        self.assertEqual(chat.call_count, 2)

    def test_b1_reasoner_rejects_comparison_claims_without_citations(self):
        response = SimpleNamespace(
            message=SimpleNamespace(content="Python dan Java serupa dalam banyak aspek.")
        )
        with patch("agents.bot_reasoner.chat_with_optional_stream", return_value=response):
            result = run_bot_reasoner(
                "Bandingkan Python dan Java berdasarkan catatan Vault. Apa persamaan dan perbedaannya?",
                ContextMemory(
                    "[Sumber: Python.md]\nPython adalah bahasa.\n"
                    "[Sumber: Java.md]\nJava adalah bahasa."
                ),
                [],
            )

        self.assertEqual(result, UNGROUNDED_VAULT_ANSWER)
        self.assertNotIn("serupa", result)

    def test_b2_synthesizer_requests_source_separated_cited_synthesis(self):
        python_source = "Python Dasar.md"
        lesson_source = "Materi Les Carl - Python Dasar.md"
        context = (
            f"[Sumber: {python_source}]\nPython membahas memori.\n"
            f"[Sumber: {lesson_source}]\nMateri membahas performa."
        )
        response = SimpleNamespace(message=SimpleNamespace(content=(
            "## Fakta per sumber\n"
            f"- Catatan Python membahas memori. [Sumber: {python_source}]\n"
            f"- Materi les membahas performa. [Sumber: {lesson_source}]\n\n"
            "## Perbedaan\n"
            f"Fokus catatan berbeda. [Sumber: Python Dasar.md] [Sumber: {lesson_source}]"
        )))
        with patch("agents.bot_synthesizer.ollama.chat", return_value=response) as chat:
            result = run_bot_synthesizer(
                "Gabungkan informasi tentang Python dari catatan Python Dasar dan "
                "Materi Les Carl - Python Dasar. Tandai jika ada perbedaan.",
                ContextMemory(context),
            )

        system_prompt = chat.call_args.kwargs["messages"][0]["content"]
        self.assertIn("pertanyaan hanya membuktikan pertanyaan itu tercatat", system_prompt)
        self.assertIn("Jangan menambah rekomendasi", system_prompt)
        self.assertIn("[Sumber: Python Dasar.md]", result)
        self.assertIn("[Sumber: Materi Les Carl - Python Dasar.md]", result)

    def test_b2_synthesizer_rejects_uncited_recommendations_and_claims(self):
        response = SimpleNamespace(message=SimpleNamespace(content=(
            "## Insight Baru\nCatatan ini membuktikan pengguna kesulitan fokus.\n\n"
            "## Rekomendasi\nGunakan /append untuk memperbarui proyek."
        )))
        context = (
            "[Sumber: Python Dasar.md]\nPython membahas memori.\n"
            "[Sumber: Materi Les Carl - Python Dasar.md]\nMateri membahas performa."
        )
        with patch("agents.bot_synthesizer.ollama.chat", return_value=response):
            result = run_bot_synthesizer(
                "Gabungkan informasi dari catatan Python Dasar dan Materi Les Carl - Python Dasar.",
                ContextMemory(context),
            )

        self.assertEqual(result, UNGROUNDED_VAULT_ANSWER)

    def test_b2_synthesis_must_cite_multiple_sources_when_context_has_them(self):
        context = (
            "[Sumber: Python Dasar.md]\nCatatan Python.\n"
            "[Sumber: Materi Les Carl - Python Dasar.md]\nCatatan materi les."
        )
        answer = (
            "Fakta pertama. [Sumber: Python Dasar.md]\n"
            "Fakta kedua. [Sumber: Python Dasar.md]"
        )

        self.assertEqual(
            validate_vault_answer(answer, context, min_cited_sources=2),
            UNGROUNDED_VAULT_ANSWER,
        )

    def test_b3_writer_does_not_use_session_profile_or_uncited_personal_inference(self):
        response = SimpleNamespace(
            message=SimpleNamespace(content=(
                "Anda memiliki masalah mempertahankan fokus. "
                "Sebaiknya gunakan /append untuk proyek."
            ))
        )
        context = "[Sumber: Proyek.md]\nCatatan proyek memiliki status belum selesai."
        with (
            patch("agents.bot_writer.generate_or_get_vault_map") as vault_map,
            patch("agents.bot_writer.ollama.chat", return_value=response) as chat,
        ):
            result = run_bot_writer(
                "Apa kesimpulan yang bisa diambil dari catatan-catatan ini, dan bagian mana yang merupakan inferensi?",
                ContextMemory(context),
                [{"role": "user", "content": "Riwayat: proyek dan fokus pengguna."}],
                session_context="Profil pengguna: mudah kehilangan fokus.",
            )

        system_prompt = chat.call_args.kwargs["messages"][0]["content"]
        self.assertNotIn("Profil pengguna: mudah kehilangan fokus.", system_prompt)
        self.assertNotIn("Riwayat: proyek dan fokus pengguna.", system_prompt)
        self.assertIn("dugaan", system_prompt)
        vault_map.assert_not_called()
        self.assertEqual(result, UNGROUNDED_VAULT_ANSWER)

    def test_vault_answer_validator_normalizes_known_legacy_source_labels(self):
        context = "[Sumber: Materi Les Carl - Python Dasar.md]\nFakta."
        answer = "Topik tercatat. (Sumber: Materi Les Carl - Python Dasar.md)"

        result = validate_vault_answer(answer, context)

        self.assertEqual(
            result,
            "Topik tercatat. [Sumber: Materi Les Carl - Python Dasar.md]",
        )

    def test_vault_answer_validator_attaches_standalone_citation_to_following_claim(self):
        context = (
            "[Sumber: Auto-Mount Boot Trigger.md]\nPath lama.\n"
            "[Sumber: 2026-09-02.md]\nPath baru."
        )
        answer = (
            "[Sumber: Auto-Mount Boot Trigger.md]\n\n"
            "Catatan Auto-Mount mencatat path lama.\n\n"
            "[Sumber: 2026-09-02.md]\n\n"
            "Catatan harian mencatat path baru."
        )

        result = validate_vault_answer(answer, context, min_cited_sources=2)

        self.assertNotEqual(result, UNGROUNDED_VAULT_ANSWER)
        self.assertIn(
            "Catatan Auto-Mount mencatat path lama. [Sumber: Auto-Mount Boot Trigger.md]",
            result,
        )
        self.assertIn(
            "Catatan harian mencatat path baru. [Sumber: 2026-09-02.md]",
            result,
        )

    def test_vault_answer_validator_does_not_attach_standalone_citation_to_uncited_list(self):
        context = "[Sumber: Python.md]\nCatatan Python."
        answer = "[Sumber: Python.md]\n\n- Catatan Python membahas memori."

        self.assertEqual(
            validate_vault_answer(answer, context),
            UNGROUNDED_VAULT_ANSWER,
        )

    def test_writer_prompt_restricts_vault_comparisons_to_retrieved_evidence(self):
        context = "[Sumber: Python.md]\nPython disebut.\n\n[Sumber: Java.md]\nJava disebut."
        response = SimpleNamespace(
            message=SimpleNamespace(
                content="Perbandingan singkat. [Sumber: Python.md] [Sumber: Java.md]"
            )
        )
        with (
            patch("agents.bot_writer.generate_or_get_vault_map", return_value=""),
            patch("agents.bot_writer.ollama.chat", return_value=response) as chat,
        ):
            run_bot_writer(
                "Bandingkan Python dan Java berdasarkan catatan Vault.",
                ContextMemory(context),
                [],
                session_context="Proyek pengguna: Proyek X.",
                user_name="Pengguna",
            )

        system_prompt = chat.call_args.kwargs["messages"][0]["content"]
        self.assertIn("5a. Jika diminta membandingkan berdasarkan Vault", system_prompt)
        self.assertIn("jangan mengisi kekosongan", system_prompt)
        self.assertNotIn("Proyek pengguna: Proyek X.", system_prompt)

    def test_a3_resolves_named_note_section_and_does_not_fall_back_to_other_sections(self):
        prompt = "Ringkas bagian Python dari Python Dasar tanpa menambahkan informasi dari luar."
        note_text = (
            "# Python Dasar\n\n"
            "## Python\nIsi Python.\n\n"
            "### List\nIsi list.\n\n"
            "## Java\nIsi Java."
        )
        with TemporaryDirectory() as vault:
            note_path = Path(vault) / "Python Dasar.md"
            note_path.write_text(note_text, encoding="utf-8")
            with patch("agents.bot_writer.config.VAULT_PATH", vault):
                source_path, source_error = _resolve_summary_source(prompt)

            self.assertTrue(is_named_note_summary_request(prompt))
            self.assertIsNone(source_error)
            self.assertEqual(source_path, note_path)

        section, error = _extract_markdown_section(note_text, "Python")
        self.assertIsNone(error)
        self.assertEqual(section, "## Python\nIsi Python.\n\n### List\nIsi list.")
        self.assertNotIn("Isi Java", section)

    def test_a3_section_summary_uses_only_selected_content_and_adds_source(self):
        prompt = "Ringkas bagian Python dari Python Dasar tanpa menambahkan informasi dari luar."
        response = SimpleNamespace(
            message=SimpleNamespace(content="Ringkasan Python. [Sumber: Java.md]")
        )
        with TemporaryDirectory() as vault:
            note_path = Path(vault) / "Python Dasar.md"
            note_path.write_text(
                "# Python Dasar\n\n## Python\nHanya Python.\n\n## Java\nJangan masukkan Java.",
                encoding="utf-8",
            )
            with (
                patch("agents.bot_writer.config.VAULT_PATH", vault),
                patch("agents.bot_writer.ollama.chat", return_value=response) as chat,
            ):
                result = run_bot_writer(prompt, EmptyMemory(), [])

        model_input = chat.call_args.kwargs["messages"][1]["content"]
        self.assertIn("Hanya Python.", model_input)
        self.assertNotIn("Jangan masukkan Java.", model_input)
        self.assertIn("[Sumber: Python Dasar.md]", result)
        self.assertNotIn("[Sumber: Java.md]", result)

    def test_a3_missing_named_note_does_not_fall_back_to_general_retrieval(self):
        prompt = "Ringkas bagian Python dari Python Dasar tanpa menambahkan informasi dari luar."
        with TemporaryDirectory() as vault:
            with (
                patch("agents.bot_writer.config.VAULT_PATH", vault),
                patch("agents.bot_writer.ollama.chat") as chat,
            ):
                result = run_bot_writer(prompt, EmptyMemory(), [])

        self.assertIn("tidak ditemukan", result)
        chat.assert_not_called()

    def test_a4_abstains_when_a_comparison_subject_has_no_vault_evidence(self):
        context = "[Sumber: Java.md]\nPython ada di catatan."
        with patch("agents.bot_writer.ollama.chat") as chat:
            result = run_bot_writer(
                "Apa hubungan Python dan Java menurut catatan saya?",
                ContextMemory(context),
                [],
                session_context="Proyek pengguna: Proyek X.",
            )

        self.assertIn("belum memuat bukti", result)
        chat.assert_not_called()

    def test_a4_discards_uncited_comparison_output(self):
        context = "[Sumber: Python.md]\nPython disebut.\nJava disebut."
        response = SimpleNamespace(message=SimpleNamespace(content="Python lebih mudah dan Java lebih cepat."))
        with (
            patch("agents.bot_writer.generate_or_get_vault_map", return_value=""),
            patch("agents.bot_writer.ollama.chat", return_value=response),
        ):
            result = run_bot_writer(
                "Apa hubungan Python dan Java menurut catatan saya?",
                ContextMemory(context),
                [],
                session_context="Proyek pengguna: Proyek X.",
            )

        self.assertIn("tidak menyertakan sitasi", result)
        self.assertNotIn("lebih mudah", result)

    def test_approved_answer_benchmark_includes_manual_prompt_variations(self):
        cases = load_answer_benchmark(str(BENCHMARK_PATH))
        cases_by_id = {case["id"]: case for case in cases}

        self.assertEqual(len(cases), 17)
        self.assertEqual(sum(case["answerable"] for case in cases), 14)
        self.assertEqual(sum(not case["answerable"] for case in cases), 3)
        self.assertEqual(len(cases_by_id), len(cases))
        self.assertIn("fish-gills-and-fins-paraphrase", cases_by_id)
        self.assertEqual(
            cases_by_id["fish-gills-and-fins-paraphrase"]["category"],
            "multi_part",
        )
        self.assertFalse(cases_by_id["fish-unspecified-species-count"]["answerable"])
        self.assertEqual(
            cases_by_id["java-data-types-multi-part"]["expected_sources"],
            ["Ringkasan Konsep Java.md"],
        )


if __name__ == "__main__":
    unittest.main()

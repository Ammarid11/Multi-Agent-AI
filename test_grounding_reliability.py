import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agents.autonomous_agent import AutonomousGoalEngine, _validate_plan_steps
from agents.bot_file_manager import is_contextual_save_request, run_bot_file_manager
from agents.bot_writer import run_bot_writer
from agents.grounding import add_citation_verification_notice
from memory.user_profile import load_user_profile
from memory.vault_scanner import scan_vault_mtimes
from tools.clean_markdown import clean_and_refactor_file
from tools.tool_clean import _clean_markdown_in_path
from tools.tool_clean import clean_target
from tools.tool_create import create_file
from tools.tool_delete import delete_file
from tools.tool_web_search import _DuckDuckGoHtmlResultsParser, _format_date, _unwrap_duckduckgo_url
from tools.vault_indexer import generate_or_get_vault_map


class TestGroundingAndRetrieval(unittest.TestCase):
    def test_citation_check_warns_for_missing_or_unavailable_sources(self):
        context = "[Sumber: project-notes.md]\nFakta yang tercatat."

        self.assertIn(
            "belum menyertakan sitasi",
            add_citation_verification_notice("Jawaban faktual.", context),
        )
        self.assertIn(
            "fake.md",
            add_citation_verification_notice(
                "Klaim [Sumber: fake.md].",
                context,
            ),
        )
        self.assertEqual(
            add_citation_verification_notice(
                "Fakta [Sumber: project-notes.md].",
                context,
            ),
            "Fakta [Sumber: project-notes.md].",
        )
        self.assertEqual(add_citation_verification_notice("Jawaban umum.", ""), "Jawaban umum.")

    def test_vault_index_excludes_hidden_system_template_archive_and_trash_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            allowed = vault / "01-Projects" / "Project.md"
            excluded_paths = [
                vault / "Archive" / "Old.md",
                vault / "Templates" / "Template.md",
                vault / "07-settings" / "Rules.md",
                vault / ".trash" / "Deleted.md",
                vault / "99-System" / "System.md",
                vault / "_private" / "Private.md",
            ]
            for path in [allowed, *excluded_paths]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# Note", encoding="utf-8")

            indexed = scan_vault_mtimes(str(vault))

        self.assertEqual(set(indexed), {str(allowed)})

    def test_vault_map_uses_the_same_indexing_exclusions(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            allowed = vault / "01-Projects" / "Project.md"
            excluded = vault / "Archive" / "Old.md"
            allowed.parent.mkdir(parents=True)
            excluded.parent.mkdir(parents=True)
            allowed.write_text("# Project", encoding="utf-8")
            excluded.write_text("# Archived", encoding="utf-8")

            with patch("tools.vault_indexer.config.VAULT_PATH", str(vault)):
                vault_map = generate_or_get_vault_map()

        self.assertIn("Project.md", vault_map)
        self.assertNotIn("Old.md", vault_map)

    def test_user_profile_defaults_do_not_assert_unverified_projects_or_interests(self):
        with tempfile.TemporaryDirectory() as directory:
            profile_path = Path(directory) / "missing-profile.json"
            with patch("memory.user_profile.PROFILE_FILE", str(profile_path)):
                profile = load_user_profile("Pengguna")

        self.assertEqual(profile["interests"], [])
        self.assertEqual(profile["active_projects"], [])

    def test_delete_requires_exact_unambiguous_vault_path(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            first = vault / "01-Projects" / "Plan.md"
            second = vault / "03-Resources" / "Plan.md"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_text("one", encoding="utf-8")
            second.write_text("two", encoding="utf-8")

            with patch("tools.tool_delete.config.VAULT_PATH", str(vault)):
                ambiguous = delete_file("Plan.md")
                traversal = delete_file("../outside.md")

            self.assertIn("beberapa catatan", ambiguous)
            self.assertTrue(first.exists())
            self.assertIn("di dalam Vault", traversal)
            self.assertTrue(second.exists())

            with patch("tools.tool_delete.config.VAULT_PATH", str(vault)):
                deleted = delete_file("01-Projects/Plan.md")

            self.assertIn("berhasil dihapus", deleted)
            self.assertFalse(first.exists())
            self.assertTrue(second.exists())

    def test_large_markdown_cleanup_reports_only_verified_real_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            note = vault / "Materi Les.md"
            note.write_text(
                "# Materi Les\n\n\n\n" + ("Isi materi asli tetap dipertahankan.\n" * 400),
                encoding="utf-8",
            )

            with patch("tools.clean_markdown.config.VAULT_PATH", str(vault)):
                result = clean_and_refactor_file("Materi Les.md")

            persisted = note.read_text(encoding="utf-8")

        self.assertIn("hasil tulis terverifikasi", result)
        self.assertIn("normalisasi format aman diterapkan", result)
        self.assertNotIn("100% data", result)
        self.assertLess(persisted.count("\n\n\n\n"), 1)
        self.assertIn("Isi materi asli tetap dipertahankan.", persisted)

    def test_large_markdown_cleanup_discloses_when_body_was_not_formatted(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            note = vault / "Lesson.md"
            body = "# Lesson\n\n" + ("Isi materi tanpa artefak format.\n" * 400)
            note.write_text(body, encoding="utf-8")

            with patch("tools.clean_markdown.config.VAULT_PATH", str(vault)):
                result = clean_and_refactor_file("Lesson.md")

        self.assertIn("tidak diubah oleh aturan format aman", result)
        self.assertNotIn("Struktur dirapikan", result)

    def test_markdown_cleanup_refuses_ambiguous_duplicate_names(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            first = vault / "01-Projects" / "Materi Les.md"
            second = vault / "03-Resources" / "Materi Les.md"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_text("# Pertama\n", encoding="utf-8")
            second.write_text("# Kedua\n", encoding="utf-8")

            with patch("tools.clean_markdown.config.VAULT_PATH", str(vault)):
                result = clean_and_refactor_file("Materi Les.md")

            self.assertIn("beberapa catatan", result)
            self.assertEqual(first.read_text(encoding="utf-8"), "# Pertama\n")
            self.assertEqual(second.read_text(encoding="utf-8"), "# Kedua\n")

    def test_bulk_markdown_cleanup_counts_warnings_and_failures_separately(self):
        paths = [r"C:\vault\one.md", r"C:\vault\two.md", r"C:\vault\three.md"]
        results = [
            "✅ File tersimpan dan diverifikasi.",
            "⚠️ Isi materi tidak diubah.",
            "❌ Penulisan gagal.",
        ]
        with (
            patch("tools.tool_clean.glob.glob", return_value=paths),
            patch("tools.tool_clean._is_protected", return_value=False),
            patch("tools.tool_clean.config.VAULT_PATH", r"C:\vault"),
            patch("tools.tool_clean.clean_and_refactor_file", side_effect=results),
        ):
            stats = _clean_markdown_in_path("unused")

        self.assertEqual(stats[:2], (3, 1))
        self.assertEqual(len(stats[2]), 1)
        self.assertEqual(len(stats[3]), 1)

    def test_create_file_discloses_when_automatic_cleanup_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch("tools.tool_create.config.VAULT_PATH", directory),
                patch("tools.tool_append.config.VAULT_PATH", directory),
                patch(
                    "tools.tool_create.clean_and_refactor_file",
                    return_value="❌ Gagal merapikan file.",
                ),
            ):
                result = create_file("Catatan Baru.md", "# Catatan\nIsi.")

            self.assertTrue((Path(directory) / "Catatan Baru.md").exists())

        self.assertIn("berhasil dibuat", result)
        self.assertIn("perapihan otomatis belum tuntas", result)
        self.assertIn("❌ Gagal merapikan", result)

    def test_contextual_save_persists_the_previous_assistant_answer_verbatim(self):
        summary = (
            "Berikut rangkuman singkat materi les tentang Pariwisata:\n\n"
            "## Materi Les: Pariwisata\n"
            "- Pariwisata budaya berfokus pada budaya lokal.\n"
            "- Dampak homogenisasi budaya perlu diwaspadai."
        )
        history = [
            {"role": "user", "content": "Rangkum materi tentang Pariwisata."},
            {"role": "assistant", "content": summary},
        ]
        with tempfile.TemporaryDirectory() as directory:
            with patch("agents.bot_file_manager.config.VAULT_PATH", directory):
                result = run_bot_file_manager(
                    "catat rangkuman yang di atas di catatan baru", history
                )

            note = Path(directory) / "00-Inbox" / "Rangkuman - Pariwisata.md"
            saved = note.read_text(encoding="utf-8")

        self.assertIn("berhasil dicatat dan diverifikasi", result)
        self.assertIn('title: "Rangkuman - Pariwisata"', saved)
        self.assertIn('category: "Rangkuman"', saved)
        self.assertIn('  - "rangkuman-percakapan"', saved)
        self.assertIn('  - "pariwisata"', saved)
        self.assertIn("# Rangkuman - Pariwisata", saved)
        self.assertIn(summary, saved)
        self.assertNotIn("Poin pertama", saved)

    def test_named_note_summary_uses_the_full_source_and_heading_checklist(self):
        source_content = (
            "---\ntitle: Materi Pariwisata\n---\n"
            "# Materi Pariwisata\n"
            "## Komponen Destinasi\n"
            "Konsep 5A mencakup aktivitas.\n"
            "## Kerja Sama Pelestarian\n"
            "Pemerintah memfasilitasi dan masyarakat menggerakkan.\n"
        )
        model_summary = "# Rangkuman: Materi Pariwisata\n\n## Kesimpulan\nSemua materi."
        chunk_summary = "Komponen destinasi dan kerja sama pelestarian dibahas."
        with tempfile.TemporaryDirectory() as directory:
            note = Path(directory) / "03-Resources" / "Materi Les Carl - Pariwisata.md"
            note.parent.mkdir()
            note.write_text(source_content, encoding="utf-8")
            with (
                patch("agents.bot_writer.config.VAULT_PATH", directory),
                patch(
                    "agents.bot_writer.ollama.chat",
                    side_effect=[
                        SimpleNamespace(message=SimpleNamespace(content=chunk_summary)),
                        SimpleNamespace(message=SimpleNamespace(content=model_summary)),
                    ],
                ) as chat,
            ):
                result = run_bot_writer(
                    "rangkum Materi Les Carl - Pariwisata",
                    memory_manager=None,
                    chat_history=[],
                )

        chunk_messages = chat.call_args_list[0].kwargs["messages"]
        final_messages = chat.call_args_list[1].kwargs["messages"]
        self.assertIn(source_content, chunk_messages[1]["content"])
        self.assertIn("Komponen Destinasi", final_messages[0]["content"])
        self.assertIn("Kerja Sama Pelestarian", final_messages[0]["content"])
        self.assertIn("[Sumber: Materi Les Carl - Pariwisata.md]", result)
        self.assertEqual(chat.call_count, 2)

    def test_long_note_is_summarized_in_chunks_and_code_is_preserved_verbatim(self):
        code_block = "```python\nprint('preserve this example')\n```"
        source_content = (
            "# Long lesson\n"
            + ("General lesson content. " * 400)
            + "\n## Code sample\n"
            + code_block
            + "\n"
            + ("Additional section content. " * 400)
        )
        with tempfile.TemporaryDirectory() as directory:
            note = Path(directory) / "Long lesson.md"
            note.write_text(source_content, encoding="utf-8")
            with (
                patch("agents.bot_writer.config.VAULT_PATH", directory),
                patch(
                    "agents.bot_writer.ollama.chat",
                    return_value=SimpleNamespace(
                        message=SimpleNamespace(content="Summary of this section.")
                    ),
                ) as chat,
            ):
                result = run_bot_writer(
                    "rangkum Long lesson.md",
                    memory_manager=None,
                    chat_history=[],
                )

        self.assertGreater(chat.call_count, 2)
        self.assertIn("## Rangkuman Rinci per Bagian Sumber", result)
        self.assertIn("Summary of this section.", result)
        self.assertIn("## Cakupan Pemrosesan Sumber", result)
        self.assertIn("## Kode dari Sumber", result)
        self.assertIn(code_block, result)
        self.assertEqual(
            result.count("- [x] Bagian "),
            chat.call_count - 1,
        )
        sent_chunks = [
            call.kwargs["messages"][1]["content"]
            for call in chat.call_args_list[:-1]
        ]
        self.assertTrue(any(code_block in chunk for chunk in sent_chunks))

    def test_empty_chunk_summary_stops_without_claiming_complete_coverage(self):
        source_content = "# Source\n" + ("Lesson content. " * 1000)
        with tempfile.TemporaryDirectory() as directory:
            note = Path(directory) / "Long lesson.md"
            note.write_text(source_content, encoding="utf-8")
            with (
                patch("agents.bot_writer.config.VAULT_PATH", directory),
                patch(
                    "agents.bot_writer.ollama.chat",
                    return_value=SimpleNamespace(
                        message=SimpleNamespace(content="  ")
                    ),
                ) as chat,
            ):
                result = run_bot_writer(
                    "rangkum Long lesson.md",
                    memory_manager=None,
                    chat_history=[],
                )

        self.assertIn("ringkasan kosong", result)
        self.assertIn("Rangkuman final tidak dibuat", result)
        self.assertNotIn("Cakupan Pemrosesan Sumber", result)
        chat.assert_called_once()

    def test_named_note_summary_does_not_use_a_partial_match_when_source_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("agents.bot_writer.config.VAULT_PATH", directory):
                result = run_bot_writer(
                    "rangkum Materi Les Carl - Pariwisata.md",
                    memory_manager=None,
                    chat_history=[],
                )

        self.assertIn("tidak ditemukan", result)
        self.assertIn("tidak membuat rangkuman dari hasil pencarian parsial", result)

    def test_ambiguous_named_note_summary_asks_for_a_specific_source(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("Catatan Pariwisata Bali.md", "Catatan Pariwisata Budaya.md"):
                (Path(directory) / name).write_text("# Materi\nIsi", encoding="utf-8")
            with (
                patch("agents.bot_writer.config.VAULT_PATH", directory),
                patch("agents.bot_writer.ollama.chat") as chat,
            ):
                result = run_bot_writer(
                    "rangkum catatan Pariwisata",
                    memory_manager=None,
                    chat_history=[],
                )

        self.assertIn("beberapa catatan yang cocok", result)
        self.assertIn("Catatan Pariwisata Bali.md", result)
        self.assertIn("Catatan Pariwisata Budaya.md", result)
        chat.assert_not_called()

    def test_contextual_save_without_previous_assistant_answer_creates_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("agents.bot_file_manager.config.VAULT_PATH", directory):
                result = run_bot_file_manager("catat di catatan baru", [])

            self.assertEqual(list(Path(directory).rglob("*.md")), [])

        self.assertIn("Belum ada jawaban sebelumnya", result)

    def test_repeated_contextual_saves_create_new_notes_without_overwriting(self):
        history = [
            {"role": "user", "content": "Jelaskan topik ini."},
            {"role": "assistant", "content": "Ringkasan yang sama."},
        ]
        with tempfile.TemporaryDirectory() as directory:
            with patch("agents.bot_file_manager.config.VAULT_PATH", directory):
                first_result = run_bot_file_manager("simpan jawaban tadi", history)
                second_result = run_bot_file_manager("simpan jawaban tadi", history)

            notes = sorted((Path(directory) / "00-Inbox").glob("*.md"))
            contents = [note.read_text(encoding="utf-8") for note in notes]

        self.assertIn("berhasil dicatat", first_result)
        self.assertIn("berhasil dicatat", second_result)
        self.assertEqual(len(notes), 2)
        self.assertTrue(all("Ringkasan yang sama." in content for content in contents))

    def test_contextual_save_detection_does_not_capture_new_topic_note_requests(self):
        self.assertTrue(is_contextual_save_request("catat di catatan baru"))
        self.assertTrue(is_contextual_save_request("simpan rangkuman yang di atas"))
        self.assertTrue(is_contextual_save_request("catat jawaban tadi"))
        self.assertFalse(is_contextual_save_request("buat catatan baru tentang pariwisata"))

    def test_natural_language_cleanup_extracts_exact_note_name(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            note = vault / "03-Resources" / "Materi Les Carl - Pariwisata.md"
            note.parent.mkdir()
            note.write_text("# Materi", encoding="utf-8")

            with (
                patch("tools.tool_clean.config.VAULT_PATH", str(vault)),
                patch(
                    "tools.tool_clean.clean_and_refactor_file",
                    return_value="✅ target diproses",
                ) as cleaner,
            ):
                result = clean_target(
                    "tolong rapihkan catatan Materi Les Carl - Pariwisata"
                )

        self.assertEqual(result, "✅ target diproses")
        cleaner.assert_called_once_with("Materi Les Carl - Pariwisata")

    def test_natural_language_cleanup_without_target_will_not_clean_entire_vault(self):
        with patch("tools.tool_clean.clean_all_vault_files") as clean_all:
            result = clean_target("rapihkan")

        self.assertIn("Sebutkan nama file atau folder", result)
        clean_all.assert_not_called()


class TestAutonomousGoalReporting(unittest.TestCase):
    def test_plan_validation_rejects_unsupported_or_incomplete_steps(self):
        plan = _validate_plan_steps([
            {"action": "unknown"},
            {"action": "read_file"},
            {"action": "read_file", "filename": "note.md"},
            {"action": "append_file", "filename": "note.md", "content": "  "},
        ])

        self.assertEqual(plan, [{"action": "read_file", "filename": "note.md"}])

    def test_invalid_plan_does_not_claim_goal_was_completed(self):
        engine = AutonomousGoalEngine(memory_manager=None)
        with patch.object(engine, "plan_steps", return_value=[]):
            result = engine.execute_goal("do something")

        self.assertIn("belum dieksekusi", result)
        self.assertNotIn("berhasil dieksekusi", result)

    def test_failed_file_action_is_reported_as_failed_not_success(self):
        engine = AutonomousGoalEngine(memory_manager=None)
        plan = [{"action": "append_file", "filename": "note.md", "content": "text"}]
        with (
            patch.object(engine, "plan_steps", return_value=plan),
            patch("agents.autonomous_agent.append_file", return_value="❌ File tidak ditemukan"),
        ):
            result = engine.execute_goal("append to note")

        self.assertIn("gagal", result.casefold())
        self.assertNotIn("Semua 1 langkah terkonfirmasi berhasil", result)


class TestWebReferenceHandling(unittest.TestCase):
    def test_html_fallback_parser_extracts_real_result_destination(self):
        parser = _DuckDuckGoHtmlResultsParser()
        parser.feed(
            '<a class="result__a" href="https://news.example/story">Title</a>'
        )
        self.assertEqual(
            parser.results,
            [{"url": "https://news.example/story", "title": "Title"}],
        )
        self.assertEqual(
            _unwrap_duckduckgo_url(
                "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fnews.example%2Fstory"
            ),
            "https://news.example/story",
        )

    def test_published_time_is_converted_only_when_timezone_is_known(self):
        self.assertEqual(
            _format_date("2026-10-13T08:00:00+00:00"),
            "13 October 2026 pukul 15:00 WIB",
        )
        self.assertIn(
            "zona waktu tidak diketahui",
            _format_date("2026-10-13T08:00:00"),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

from concurrent.futures import Future
import json
import threading
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agents.bot_router_llm import INTENT_LABELS, classify_intent
from agents.bot_reasoner import should_use_deep_reasoning
from agents.router import AgentRouter
from agents import AITeam
from memory import session_memory
from memory.manager import MemoryManager
from memory.vector_store import VectorStoreManager
import config


class FakeTeam:
    def __getattr__(self, name):
        return lambda *args: name

    def reset_session(self):
        return "reset"


class TestRouter(unittest.TestCase):
    def setUp(self):
        self.router = AgentRouter(FakeTeam())

    def test_classifier_labels_route_to_a_handler(self):
        for intent in INTENT_LABELS:
            with self.subTest(intent=intent):
                self.assertIsInstance(self.router._route_by_intent(intent, "sample"), str)

    def test_slash_command_precedes_classifier(self):
        with patch("agents.router.classify_intent") as classify:
            result = self.router.route_and_execute("/think explain the trade-off")

        self.assertEqual(result, "bot_reasoner")
        classify.assert_not_called()

    def test_fast_intent_phrase_is_case_insensitive(self):
        self.assertEqual(self.router._fast_intent_check("Tolong CARI DI WEB tentang cuaca"), "web")

    def test_current_developments_request_routes_to_web_without_classifier(self):
        with patch("agents.router.classify_intent") as classify:
            result = self.router.route_and_execute(
                "Cari perkembangan terbaru tentang misi Artemis II NASA."
            )

        self.assertEqual(result, "bot_web")
        classify.assert_not_called()

    def test_ordinary_information_question_skips_llm_intent_classifier(self):
        with patch("agents.router.classify_intent") as classify:
            result = self.router.route_and_execute("Apa ibu kota Jepang?")

        self.assertEqual(result, "bot_writer")
        classify.assert_not_called()

    def test_question_about_named_vault_note_routes_to_writer(self):
        prompt = "Di catatan Ringkasan Konsep Java, apa contoh-contoh yang disebutkan?"
        with patch("agents.router.classify_intent") as classify:
            result = self.router.route_and_execute(prompt)

        self.assertEqual(result, "bot_writer")
        classify.assert_not_called()

    def test_mixed_general_question_with_explicit_note_routes_to_writer(self):
        prompt = (
            "Jelaskan secara umum apa itu ERD, lalu cocokkan dengan catatan "
            "`Materi Les Carl - Entity Relationship Diagram.md`."
        )
        with patch("agents.router.classify_intent") as classify:
            result = self.router.route_and_execute(prompt)

        self.assertEqual(result, "bot_writer")
        classify.assert_not_called()

    def test_section_summary_request_routes_to_source_aware_writer(self):
        prompt = "Ringkas bagian Python dari Python Dasar tanpa menambahkan informasi dari luar."
        with patch("agents.router.classify_intent") as classify:
            result = self.router.route_and_execute(prompt)

        self.assertEqual(result, "bot_writer")
        classify.assert_not_called()

    def test_file_classifier_result_without_explicit_action_routes_to_writer(self):
        prompt = "Jelaskan contoh-contoh pemrograman Java yang tercatat."
        with patch("agents.router.classify_intent", return_value="file") as classify:
            result = self.router.route_and_execute(prompt)

        self.assertEqual(result, "bot_writer")
        classify.assert_called_once_with(prompt)

    def test_explicit_file_read_can_still_route_to_file_manager(self):
        prompt = "Baca file Ringkasan Konsep Java.md"
        with patch("agents.router.classify_intent", return_value="file"):
            result = self.router.route_and_execute(prompt)

        self.assertEqual(result, "bot_file_manager")

    def test_explicit_file_action_inside_note_phrase_routes_to_file_manager(self):
        prompt = "Di catatan QA, tambahkan satu baris marker."
        with patch("agents.router.classify_intent", return_value="file") as classify:
            result = self.router.route_and_execute(prompt)

        self.assertEqual(result, "bot_file_manager")
        classify.assert_called_once_with(prompt)

    def test_question_about_what_to_save_does_not_trigger_file_action(self):
        prompt = "Di catatan QA, apa yang sebaiknya saya simpan?"
        with patch("agents.router.classify_intent", return_value="file") as classify:
            result = self.router.route_and_execute(prompt)

        self.assertEqual(result, "bot_writer")
        classify.assert_called_once_with(prompt)

    def test_question_with_specialist_action_still_uses_llm_intent_classifier(self):
        with patch("agents.router.classify_intent", return_value="canvas") as classify:
            result = self.router.route_and_execute(
                "Apakah kamu bisa membuat canvas dari ide ini?"
            )

        self.assertEqual(result, "bot_canvas")
        classify.assert_called_once()

    def test_explicit_web_question_still_uses_web_fast_route(self):
        with patch.object(self.router.team, "bot_web", return_value="web result") as web:
            with patch("agents.router.classify_intent") as classify:
                result = self.router.route_and_execute(
                    "Apa berita terbaru tentang gempa? Cari di internet."
                )

        self.assertEqual(result, "web result")
        web.assert_called_once()
        classify.assert_not_called()

    def test_deep_reasoning_detector_escalates_explicit_complex_requests(self):
        self.assertTrue(
            should_use_deep_reasoning(
                "Bandingkan kedua strategi berdasarkan biaya, risiko, dan dampak."
            )
        )
        self.assertTrue(
            should_use_deep_reasoning(
                "Jika anggaran dipotong, lalu biaya tetap naik, bagaimana dampaknya?"
            )
        )

    def test_deep_reasoning_detector_keeps_simple_factual_questions_fast(self):
        self.assertFalse(should_use_deep_reasoning("Apa ibu kota Indonesia?"))
        self.assertFalse(should_use_deep_reasoning("Jelaskan istilah enkapsulasi."))

    def test_default_writer_escalates_complex_questions_but_not_note_summaries(self):
        team = AITeam.__new__(AITeam)
        team.memory = object()
        team.chat_history = []
        team.user_name = "Ammar"
        with (
            patch.object(team, "_get_session_ctx", return_value="session"),
            patch.object(team, "_after_response") as after_response,
            patch("agents.run_bot_reasoner", return_value="Analisis singkat") as reasoner,
            patch("agents.run_bot_writer", return_value="Jawaban cepat") as writer,
        ):
            complex_reply = team.bot_writer(
                "Bandingkan opsi A dan B berdasarkan biaya dan risiko."
            )
            simple_reply = team.bot_writer("Apa ibu kota Indonesia?")
            summary_reply = team.bot_writer("Rangkum langkah demi langkah catatan X.md")

        self.assertEqual(complex_reply, "Analisis singkat")
        self.assertEqual(simple_reply, "Jawaban cepat")
        self.assertEqual(summary_reply, "Jawaban cepat")
        self.assertEqual(reasoner.call_count, 1)
        self.assertEqual(writer.call_count, 2)
        self.assertEqual(after_response.call_count, 3)

    def test_router_finishes_prior_session_summary_before_handling_prompt(self):
        class TeamWithPreparation:
            def __init__(self):
                self.prepared = False

            def prepare_for_prompt(self):
                self.prepared = True

            def bot_writer(self, prompt):
                return "reply"

            def record_untracked_response(self, prompt, reply):
                return None

        team = TeamWithPreparation()
        router = AgentRouter(team)
        with patch("agents.router.classify_intent", return_value="default"):
            self.assertEqual(router.route_and_execute("question"), "reply")

        self.assertTrue(team.prepared)

    def test_natural_language_cleanup_request_routes_without_slash_command(self):
        with patch("agents.router.classify_intent") as classify:
            result = self.router.route_and_execute(
                "rapihkan Materi Les Carl - Pariwisata"
            )

        self.assertEqual(result, "bot_cleaner")
        classify.assert_not_called()

    def test_named_note_summary_bypasses_intent_classifier(self):
        with patch("agents.router.classify_intent") as classify:
            result = self.router.route_and_execute(
                "rangkum Materi Les Carl - Pariwisata"
            )

        self.assertEqual(result, "bot_writer")
        classify.assert_not_called()

    def test_contextual_note_request_routes_without_slash_command(self):
        with patch("agents.router.classify_intent") as classify:
            result = self.router.route_and_execute("catat di catatan baru")

        self.assertEqual(result, "bot_file_manager")
        classify.assert_not_called()

    def test_untracked_agent_reply_is_added_to_team_history(self):
        class TeamWithUntrackedSynthesizer:
            def __init__(self):
                self.chat_history = []

            def bot_synthesizer(self, prompt):
                return "Rangkuman jawaban untuk disimpan."

            def record_untracked_response(self, prompt, reply):
                self.chat_history.extend([
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": reply},
                ])

        team = TeamWithUntrackedSynthesizer()
        router = AgentRouter(team)
        with patch("agents.router.classify_intent", return_value="sintesis"):
            reply = router.route_and_execute("rangkum materi pariwisata")

        self.assertEqual(reply, "Rangkuman jawaban untuk disimpan.")
        self.assertEqual(team.chat_history[-1]["role"], "assistant")
        self.assertEqual(team.chat_history[-1]["content"], reply)

    def test_synthesis_answer_can_be_saved_on_the_next_turn(self):
        summary = (
            "Rangkuman Pariwisata:\n"
            "- Pariwisata budaya berfokus pada pengalaman budaya lokal."
        )
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch("agents.load_initial_session_summaries", return_value=[]),
                patch("agents.run_bot_synthesizer", return_value=summary),
                patch("agents.router.classify_intent", return_value="sintesis"),
                patch("agents.update_profile_from_interaction"),
                patch("agents.detect_and_register_rule"),
                patch("agents.bot_file_manager.config.VAULT_PATH", directory),
            ):
                team = AITeam(memory_manager=None)
                router = AgentRouter(team)
                first_reply = router.route_and_execute("rangkum materi pariwisata")
                save_reply = router.route_and_execute("simpan rangkuman")

            saved_notes = list((Path(directory) / "00-Inbox").glob("*.md"))
            saved_content = (
                saved_notes[0].read_text(encoding="utf-8") if saved_notes else ""
            )

        self.assertEqual(first_reply, summary)
        self.assertIn("berhasil dicatat dan diverifikasi", save_reply)
        self.assertEqual(len(saved_notes), 1)
        self.assertIn(summary, saved_content)

    def test_router_does_not_duplicate_responses_already_recorded_by_agent(self):
        class TeamWithTrackedWriter:
            def __init__(self):
                self.chat_history = []

            def bot_writer(self, prompt):
                reply = "Jawaban sudah dicatat."
                self.chat_history.extend([
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": reply},
                ])
                return reply

            def record_untracked_response(self, prompt, reply):
                if self.chat_history[-2:] != [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": reply},
                ]:
                    self.chat_history.extend([
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": reply},
                    ])

        team = TeamWithTrackedWriter()
        router = AgentRouter(team)
        with patch("agents.router.classify_intent", return_value="default"):
            router.route_and_execute("jawab pertanyaan")

        self.assertEqual(len(team.chat_history), 2)

    def test_negated_contextual_note_request_does_not_run_file_manager(self):
        with patch("agents.router.classify_intent") as classify:
            result = self.router.route_and_execute("jangan catat di catatan baru")

        self.assertEqual(result, "bot_writer")
        classify.assert_not_called()

    def test_negated_natural_language_cleanup_does_not_run_cleaner(self):
        with patch("agents.router.classify_intent") as classify:
            result = self.router.route_and_execute(
                "Jangan rapihkan Materi Les Carl - Pariwisata"
            )

        self.assertEqual(result, "bot_writer")
        classify.assert_not_called()

    def test_substring_inside_another_word_does_not_trigger_fast_intent(self):
        self.assertIsNone(self.router._fast_intent_check("mensimulasikan hasil percakapan"))

    def test_negated_fast_action_uses_default_agent(self):
        with patch("agents.router.classify_intent") as classify:
            result = self.router.route_and_execute("Jangan simulasikan skenario itu.")

        self.assertEqual(result, "bot_writer")
        classify.assert_not_called()

    def test_ambiguous_request_uses_classifier_result(self):
        with patch("agents.router.classify_intent", return_value="coder") as classify:
            result = self.router.route_and_execute("tolong bantu untuk ini")

        self.assertEqual(result, "bot_coder")
        classify.assert_called_once_with("tolong bantu untuk ini")

    def test_classifier_rejects_unknown_label(self):
        response = SimpleNamespace(
            message=SimpleNamespace(content="unsupported-intent")
        )
        with patch("agents.bot_router_llm.ollama.chat", return_value=response):
            self.assertEqual(classify_intent("permintaan ambigu"), "default")

    def test_classifier_failure_falls_back_to_default(self):
        with patch(
            "agents.bot_router_llm.ollama.chat",
            side_effect=RuntimeError("model unavailable"),
        ):
            self.assertEqual(classify_intent("permintaan ambigu"), "default")

    def test_fast_intent_patterns_use_declared_priority(self):
        with patch("agents.router.classify_intent") as classify:
            result = self.router.route_and_execute(
                "Cari di web dan buatkan kode untuk mengambil data."
            )

        self.assertEqual(result, "bot_web")
        classify.assert_not_called()

    def test_classifier_intents_forward_original_prompt_to_correct_handler(self):
        class RecordingTeam:
            def __getattr__(self, name):
                return lambda *args: (name, args)

        router = AgentRouter(RecordingTeam())
        expected = {
            "web": "bot_web",
            "think": "bot_reasoner",
            "coder": "bot_coder",
            "sintesis": "bot_synthesizer",
            "file": "bot_file_manager",
            "clean": "bot_cleaner",
            "default": "bot_writer",
        }
        prompt = "  original prompt  "
        for intent, handler in expected.items():
            with self.subTest(intent=intent):
                self.assertEqual(
                    router._route_by_intent(intent, prompt),
                    (handler, (prompt,)),
                )


class TestSessionMemory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.history_file = Path(self.temp_dir.name) / "history.json"
        self.history_patch = patch.object(session_memory, "HISTORY_FILE", str(self.history_file))
        self.history_patch.start()

    def tearDown(self):
        self.history_patch.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def _history(count=8):
        return [{"role": "user", "content": f"message {index}"} for index in range(count)]

    def test_history_is_not_trimmed_when_summary_generation_fails(self):
        history = self._history()
        with patch.object(session_memory, "_summarize_batch", return_value=""):
            retained, summaries = session_memory.manage_history(history, ["existing"])

        self.assertEqual(retained, history)
        self.assertEqual(summaries, ["existing"])
        self.assertFalse(self.history_file.exists())

    def test_history_is_not_trimmed_when_summary_persistence_fails(self):
        history = self._history()
        with (
            patch.object(session_memory, "_summarize_batch", return_value="summary"),
            patch.object(session_memory, "_save_persisted_summary", return_value=False),
        ):
            retained, summaries = session_memory.manage_history(history, [])

        self.assertEqual(retained, history)
        self.assertEqual(summaries, [])

    def test_successful_summary_preserves_recent_messages_and_persists(self):
        history = self._history()
        with patch.object(session_memory, "_summarize_batch", return_value="summary"):
            retained, summaries = session_memory.manage_history(history, [])

        self.assertEqual(retained, history[-session_memory.KEEP_RECENT:])
        self.assertEqual(summaries, ["summary"])
        persisted = json.loads(self.history_file.read_text(encoding="utf-8"))
        self.assertEqual(persisted["summaries"][0]["summary"], "summary")

    def test_summary_submission_uses_a_snapshot_and_persists_in_background(self):
        history = self._history()
        started = threading.Event()
        release = threading.Event()

        def delayed_summary(messages, user_name="Pengguna"):
            started.set()
            release.wait(timeout=2)
            return "background summary"

        with patch.object(session_memory, "summarize_and_persist_history", side_effect=delayed_summary):
            future = session_memory.submit_history_summary(history)
            history[0]["content"] = "mutated after submission"
            self.assertTrue(started.wait(timeout=1))
            self.assertFalse(future.done())
            release.set()
            self.assertEqual(future.result(timeout=2), "background summary")

    def test_team_defers_summary_wait_until_before_the_next_prompt(self):
        team = AITeam.__new__(AITeam)
        team.user_name = "Ammar"
        team.chat_history = self._history(count=6)
        team.session_summaries = ["existing"]
        future: Future[str] = Future()

        with (
            patch("agents.update_profile_from_interaction"),
            patch("agents.detect_and_register_rule"),
            patch("agents.submit_history_summary", return_value=future) as submit,
        ):
            team._after_response("next prompt", "next reply")

            self.assertEqual(len(team.chat_history), session_memory.SUMMARIZE_THRESHOLD)
            self.assertFalse(future.done())
            submit.assert_called_once()

            prepared = threading.Event()
            prepare_thread = threading.Thread(
                target=lambda: (team.prepare_for_prompt(), prepared.set())
            )
            prepare_thread.start()
            waited_for_summary = prepared.wait(timeout=0.05)
            future.set_result("new summary")
            self.assertFalse(waited_for_summary)
            self.assertTrue(prepared.wait(timeout=1))
            prepare_thread.join(timeout=1)

        self.assertEqual(
            team.chat_history,
            self._history(count=6)[-2:] + [
                {"role": "user", "content": "next prompt"},
                {"role": "assistant", "content": "next reply"},
            ],
        )
        self.assertEqual(team.session_summaries, ["existing", "new summary"])

    def test_expired_summaries_are_not_loaded(self):
        self.history_file.write_text(
            json.dumps({
                "summaries": [
                    {"summary": "expired", "timestamp": 1},
                    {"summary": "fresh", "timestamp": 4_000_000_000},
                ]
            }),
            encoding="utf-8",
        )
        with patch.object(session_memory.time, "time", return_value=4_000_000_100):
            summaries = session_memory._load_persisted_summaries()

        self.assertEqual(summaries, ["fresh"])

    def test_reset_keeps_in_memory_history_when_persistent_clear_fails(self):
        team = AITeam.__new__(AITeam)
        team.chat_history = self._history()
        team.session_summaries = ["existing summary"]

        with patch("agents.clear_session_history", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                team.reset_session()

        self.assertTrue(team.chat_history)
        self.assertEqual(team.session_summaries, ["existing summary"])

    def test_reset_waits_for_pending_summary_before_clearing_persisted_history(self):
        team = AITeam.__new__(AITeam)
        team.chat_history = self._history()
        team.session_summaries = []
        future: Future[str] = Future()
        team._pending_history_summary = future
        team._pending_summary_snapshot = [message.copy() for message in team.chat_history[:-4]]
        clear_started = threading.Event()
        reset_finished = threading.Event()

        with patch("agents.clear_session_history", side_effect=clear_started.set):
            reset_thread = threading.Thread(
                target=lambda: (team.reset_session(), reset_finished.set())
            )
            reset_thread.start()
            waited_for_summary = reset_finished.wait(timeout=0.05)
            future.set_result("persisted summary")
            self.assertFalse(waited_for_summary)
            self.assertTrue(reset_finished.wait(timeout=1))
            reset_thread.join(timeout=1)

        self.assertTrue(clear_started.is_set())
        self.assertEqual(team.chat_history, [])
        self.assertEqual(team.session_summaries, [])


class TestMemoryManagerSafety(unittest.TestCase):
    def test_qdrant_locked_path_degrades_without_initializing_client(self):
        store = VectorStoreManager.__new__(VectorStoreManager)
        store.embeddings = object()

        with patch(
            "memory.vector_store.QdrantClient",
            side_effect=RuntimeError("already accessed by another instance"),
        ):
            store._init_client()

        self.assertIsNone(store.client)

    def test_existing_collection_is_not_recreated_when_vector_store_failed_to_load(self):
        class ExistingCollectionClient:
            @staticmethod
            def get_collections():
                return SimpleNamespace(
                    collections=[SimpleNamespace(name=config.COLLECTION_NAME)]
                )

        memory = MemoryManager.__new__(MemoryManager)
        memory.store = SimpleNamespace(
            client=ExistingCollectionClient(),
            vector_db=None,
            init_fresh_collection=lambda: self.fail("Existing collection must not be recreated"),
        )
        memory.all_chunks = []

        with (
            patch("memory.manager.os.path.exists", return_value=True),
            patch("memory.manager.scan_vault_mtimes", return_value={}),
            patch("memory.manager.extract_all_chunks", return_value=[]),
        ):
            memory.index_vault(silent=True)

        self.assertEqual(memory.all_chunks, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agents.bot_router_llm import INTENT_LABELS, classify_intent
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
                patch(
                    "agents.manage_history",
                    side_effect=lambda history, summaries, user_name="Pengguna": (
                        history,
                        summaries,
                    ),
                ),
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

"""Focused offline tests for streaming chat updates and opt-in human review."""

import asyncio
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import api_server
from agents.streaming import (
    chat_with_optional_stream,
    publish_stream_update,
    reset_stream_callback,
    set_stream_callback,
)
from evaluate_answers import _write_review_sheet


class TestStreamingAndReview(unittest.TestCase):
    def test_ollama_stream_emits_text_chunks_and_returns_complete_text(self):
        chunks = [
            SimpleNamespace(message=SimpleNamespace(content="Carl ")),
            SimpleNamespace(message=SimpleNamespace(content="menjawab.")),
        ]
        partials = []
        token = set_stream_callback(partials.append)
        try:
            with patch("agents.streaming.ollama.chat", return_value=iter(chunks)) as chat:
                response = chat_with_optional_stream(
                    model="writer",
                    messages=[{"role": "user", "content": "question"}],
                    options={},
                    keep_alive="2m",
                )
        finally:
            reset_stream_callback(token)

        self.assertEqual(partials, ["Carl ", "menjawab."])
        self.assertEqual(response.message.content, "Carl menjawab.")
        self.assertTrue(chat.call_args.kwargs["stream"])

    def test_stream_callback_is_request_scoped_and_optional(self):
        with patch(
            "agents.streaming.ollama.chat",
            return_value=SimpleNamespace(message=SimpleNamespace(content="final")),
        ) as chat:
            response = chat_with_optional_stream(
                model="writer",
                messages=[],
                options={},
                keep_alive="2m",
            )

        self.assertEqual(response.message.content, "final")
        self.assertNotIn("stream", chat.call_args.kwargs)

    def test_review_sheet_contains_answers_and_blank_human_fields(self):
        cases = [{
            "id": "case-1",
            "category": "factuality",
            "query": "Test question",
            "answerable": True,
            "required_facts": ["fact"],
            "expected_sources": ["note.md"],
        }]
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "review.json"
            _write_review_sheet(
                output_path,
                cases,
                ["Fact. [Sumber: note.md]"],
                {"writer_model_configured": "writer"},
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))

            self.assertEqual(payload["review_status"], "pending")
            self.assertEqual(
                payload["cases"][0]["generated_answer"],
                "Fact. [Sumber: note.md]",
            )
            self.assertIsNone(payload["cases"][0]["human_review"]["decision"])
            self.assertEqual(payload["cases"][0]["human_review"]["notes"], "")
            with self.assertRaises(FileExistsError):
                _write_review_sheet(output_path, cases, ["replacement"], {})

    def test_running_chat_job_exposes_partial_response(self):
        first_partial_sent = threading.Event()
        release_job = threading.Event()
        previous_router = api_server._router
        previous_executor = api_server._chat_job_executor
        job_id = None

        class StreamingRouter:
            @staticmethod
            def route_and_execute(_query):
                publish_stream_update("Jawaban parsial")
                first_partial_sent.set()
                if not release_job.wait(timeout=3):
                    raise TimeoutError("test stream was not released")
                return "Jawaban akhir"

        async def run_test():
            nonlocal job_id
            api_server._router = StreamingRouter()
            api_server._chat_job_executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="test-carl-stream",
            )
            started = await api_server.start_chat_job(
                api_server.ChatRequest(query="question")
            )
            job_id = started["job_id"]
            self.assertTrue(await asyncio.to_thread(first_partial_sent.wait, timeout=1))

            partial = await api_server.get_chat_job(job_id)
            self.assertEqual(partial["status"], "running")
            self.assertEqual(partial["partial_reply"], "Jawaban parsial")

            release_job.set()
            for _ in range(100):
                result = await api_server.get_chat_job(job_id)
                if result["status"] == "completed":
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(result["reply"], "Jawaban akhir")

        try:
            asyncio.run(run_test())
        finally:
            release_job.set()
            api_server._chat_job_executor.shutdown(wait=True)
            api_server._chat_job_executor = previous_executor
            api_server._router = previous_router
            if job_id:
                with api_server._chat_jobs_lock:
                    api_server._chat_jobs.pop(job_id, None)


if __name__ == "__main__":
    unittest.main()

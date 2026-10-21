import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.responses import JSONResponse

import api_server
from api_server import (
    ChatRequest,
    _build_galaxy_data,
    app,
    handle_chat,
    start_chat_job,
    get_chat_job,
    get_chat_job_compat,
    handle_stop_tutoring,
    unavailable_response,
)


class TestApiErrorContract(unittest.IsolatedAsyncioTestCase):
    async def test_local_server_registers_browser_compatible_job_and_stop_paths(self):
        registered = {
            (route.path, method)
            for route in app.routes
            for method in getattr(route, "methods", set())
        }

        self.assertIn(("/api/chat-jobs", "POST"), registered)
        self.assertIn(("/api/chat-job", "GET"), registered)
        self.assertIn(("/api/chat-stop", "POST"), registered)
        self.assertIn(("/api/chat/jobs", "POST"), registered)
        self.assertIn(("/api/chat/jobs/{job_id}", "GET"), registered)
        self.assertIn(("/api/tutoring/stop", "POST"), registered)

    async def test_application_lifespan_starts_and_stops_with_external_services_mocked(self):
        memory = Mock()
        team = Mock()
        router = Mock()
        previous_state = (
            api_server._memory_manager,
            api_server._team,
            api_server._router,
        )

        with (
            patch("api_server.MemoryManager", return_value=memory),
            patch("api_server.AITeam", return_value=team),
            patch("api_server.AgentRouter", return_value=router),
            patch("api_server.start_background_scheduler") as start_scheduler,
            patch("api_server.stop_background_scheduler") as stop_scheduler,
        ):
            async with app.router.lifespan_context(app):
                memory.index_vault.assert_called_once_with(silent=True)
                start_scheduler.assert_called_once_with()
                self.assertIs(api_server._memory_manager, memory)
                self.assertIs(api_server._team, team)
                self.assertIs(api_server._router, router)

            stop_scheduler.assert_called_once_with()
        (
            api_server._memory_manager,
            api_server._team,
            api_server._router,
        ) = previous_state

    async def test_unavailable_response_uses_503_and_stable_payload(self):
        response = unavailable_response()

        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 503)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["reply"], body["detail"])

    async def test_chat_internal_error_uses_500_without_exposing_exception(self):
        class BrokenRouter:
            @staticmethod
            def route_and_execute(query):
                raise RuntimeError("private backend detail")

        with patch("api_server._router", BrokenRouter()):
            response = await handle_chat(ChatRequest(query="test"))

        self.assertEqual(response.status_code, 500)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["reply"], body["detail"])
        self.assertNotIn("private backend detail", body["detail"])

    async def test_empty_chat_query_is_rejected(self):
        request = ChatRequest(query="  ")
        with self.assertRaises(HTTPException) as raised:
            await handle_chat(request)

        self.assertEqual(raised.exception.status_code, 400)

    async def test_background_chat_job_returns_id_and_can_be_polled(self):
        class ImmediateExecutor:
            @staticmethod
            def submit(function, *args):
                function(*args)

        class SuccessfulRouter:
            @staticmethod
            def route_and_execute(query):
                return f"reply: {query}"

        with (
            patch("api_server._router", SuccessfulRouter()),
            patch("api_server._chat_job_executor", ImmediateExecutor()),
        ):
            started = await start_chat_job(ChatRequest(query="  hello  "))
            result = await get_chat_job(started["job_id"])

        self.assertEqual(started["status"], "queued")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["reply"], "reply: hello")

    async def test_browser_single_segment_chat_job_routes_work_on_local_api(self):
        class ImmediateExecutor:
            @staticmethod
            def submit(function, *args):
                function(*args)

        class SuccessfulRouter:
            @staticmethod
            def route_and_execute(query):
                return f"reply: {query}"

        with (
            patch("api_server._router", SuccessfulRouter()),
            patch("api_server._chat_job_executor", ImmediateExecutor()),
        ):
            started = await start_chat_job(ChatRequest(query="local browser"))
            result = await get_chat_job_compat(started["job_id"])

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["reply"], "reply: local browser")

    async def test_browser_chat_stop_alias_sends_tutoring_stop_signal(self):
        with patch("api_server.request_stop_tutoring") as stop:
            result = await handle_stop_tutoring()

        stop.assert_called_once_with()
        self.assertEqual(result["status"], "ok")

    async def test_background_chat_job_continues_after_start_request_returns(self):
        started_work = threading.Event()
        finish_work = threading.Event()

        class BlockingRouter:
            @staticmethod
            def route_and_execute(query):
                started_work.set()
                if not finish_work.wait(timeout=2):
                    raise TimeoutError("test job was not released")
                return "long task completed"

        with patch("api_server._router", BlockingRouter()):
            started = await start_chat_job(ChatRequest(query="long task"))
            self.assertTrue(await asyncio.to_thread(started_work.wait, timeout=1))
            self.assertIn(
                (await get_chat_job(started["job_id"]))["status"],
                {"queued", "running"},
            )

            finish_work.set()
            for _ in range(100):
                result = await get_chat_job(started["job_id"])
                if result["status"] == "completed":
                    break
                await asyncio.sleep(0.01)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["reply"], "long task completed")

    async def test_serial_chat_jobs_report_queue_and_execution_durations(self):
        first_started = threading.Event()
        release_first = threading.Event()
        previous_router = api_server._router
        previous_executor = api_server._chat_job_executor
        first_job_id = None
        second_job_id = None

        class ControlledRouter:
            @staticmethod
            def route_and_execute(query):
                if query == "first":
                    first_started.set()
                    if not release_first.wait(timeout=3):
                        raise TimeoutError("first test job was not released")
                return f"reply: {query}"

        try:
            api_server._router = ControlledRouter()
            api_server._chat_job_executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="test-carl-chat",
            )
            first = await start_chat_job(ChatRequest(query="first"))
            first_job_id = first["job_id"]
            self.assertTrue(await asyncio.to_thread(first_started.wait, timeout=1))
            second = await start_chat_job(ChatRequest(query="second"))
            second_job_id = second["job_id"]

            queued = await get_chat_job(second["job_id"])
            self.assertEqual(queued["status"], "queued")
            self.assertGreaterEqual(queued["queue_wait_ms"], 0)

            await asyncio.sleep(0.05)
            release_first.set()
            results = {}
            for _ in range(200):
                results[first["job_id"]] = await get_chat_job(first["job_id"])
                results[second["job_id"]] = await get_chat_job(second["job_id"])
                if all(result["status"] == "completed" for result in results.values()):
                    break
                await asyncio.sleep(0.01)

            first_result = results[first["job_id"]]
            second_result = results[second["job_id"]]
            self.assertEqual(first_result["status"], "completed")
            self.assertEqual(second_result["status"], "completed")
            self.assertEqual(second_result["reply"], "reply: second")
            self.assertGreaterEqual(second_result["queue_wait_ms"], 10)
            self.assertGreaterEqual(second_result["execution_ms"], 0)
        finally:
            release_first.set()
            api_server._chat_job_executor.shutdown(wait=True)
            api_server._chat_job_executor = previous_executor
            api_server._router = previous_router
            with api_server._chat_jobs_lock:
                if first_job_id:
                    api_server._chat_jobs.pop(first_job_id, None)
                if second_job_id:
                    api_server._chat_jobs.pop(second_job_id, None)

    async def test_background_chat_job_reports_failure_without_leaking_exception(self):
        class ImmediateExecutor:
            @staticmethod
            def submit(function, *args):
                function(*args)

        class BrokenRouter:
            @staticmethod
            def route_and_execute(query):
                raise RuntimeError("private backend detail")

        with (
            patch("api_server._router", BrokenRouter()),
            patch("api_server._chat_job_executor", ImmediateExecutor()),
        ):
            started = await start_chat_job(ChatRequest(query="hello"))
            result = await get_chat_job(started["job_id"])

        self.assertEqual(result["status"], "failed")
        self.assertNotIn("private backend detail", result["detail"])

    async def test_background_chat_job_rejects_empty_query(self):
        with self.assertRaises(HTTPException) as raised:
            await start_chat_job(ChatRequest(query="  "))

        self.assertEqual(raised.exception.status_code, 400)

    async def test_background_chat_job_returns_not_found_for_unknown_id(self):
        with self.assertRaises(HTTPException) as raised:
            await get_chat_job("missing-job-id")

        self.assertEqual(raised.exception.status_code, 404)

    async def test_galaxy_builder_reads_only_eligible_files_and_keeps_wikilink_edges(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            (vault / "A.md").write_text("See [[B|alias]] and [[B#section]].", encoding="utf-8")
            (vault / "B.md").write_text("# B\nTarget note.", encoding="utf-8")
            (vault / "C.md").write_bytes(b"\xff invalid utf-8")
            (vault / ".hidden.md").write_text("Hidden.", encoding="utf-8")
            settings = vault / "07-settings"
            settings.mkdir()
            (settings / "Private.md").write_text("Private.", encoding="utf-8")

            with patch("api_server.VAULT_PATH", str(vault)):
                result = _build_galaxy_data()

        self.assertEqual({node["title"] for node in result["nodes"]}, {"A", "B", "C"})
        self.assertEqual(len(result["edges"]), 2)
        self.assertTrue(all(edge["source"] != edge["target"] for edge in result["edges"]))

    async def test_galaxy_builder_returns_empty_graph_when_vault_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_vault = Path(directory) / "not-created"
            with patch("api_server.VAULT_PATH", str(missing_vault)):
                self.assertEqual(_build_galaxy_data(), {"nodes": [], "edges": []})


if __name__ == "__main__":
    unittest.main(verbosity=2)

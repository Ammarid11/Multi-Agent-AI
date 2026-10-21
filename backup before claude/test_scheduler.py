import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import scheduler


class TestMorningBriefingSchedule(unittest.TestCase):
    def test_scheduler_logs_startup_once_and_skips_a_persisted_briefing_quietly(self):
        today = datetime(2026, 10, 14, 9, 0)
        with (
            patch.object(scheduler, "_load_last_briefing_date", return_value="2026-10-14"),
            patch.object(scheduler, "datetime") as clock,
            patch.object(scheduler.time, "sleep", side_effect=lambda _: setattr(scheduler, "_RUNNING", False)),
            patch.object(scheduler, "run_morning_briefing_once") as run_briefing,
        ):
            clock.now.return_value = today
            output = io.StringIO()
            with redirect_stdout(output):
                scheduler._scheduler_loop()

        run_briefing.assert_not_called()
        self.assertEqual(output.getvalue().count("[Heartbeat Daemon] Berjalan"), 1)
        self.assertNotIn("sudah dibuat; dilewati", output.getvalue())

    def test_successful_automatic_briefing_is_skipped_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / ".scheduler_state.json"
            with (
                patch.object(scheduler, "_BRIEFING_STATE_PATH", state_path),
                patch.object(scheduler, "trigger_morning_briefing", return_value="briefing") as trigger,
            ):
                self.assertTrue(scheduler.run_morning_briefing_once("2026-10-14"))

            with (
                patch.object(scheduler, "_BRIEFING_STATE_PATH", state_path),
                patch.object(scheduler, "trigger_morning_briefing") as trigger,
            ):
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertFalse(scheduler.run_morning_briefing_once("2026-10-14"))
                trigger.assert_not_called()
                self.assertEqual(output.getvalue(), "")

    def test_failed_briefing_does_not_mark_day_as_completed(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / ".scheduler_state.json"
            with (
                patch.object(scheduler, "_BRIEFING_STATE_PATH", state_path),
                patch.object(
                    scheduler,
                    "trigger_morning_briefing",
                    return_value="[Heartbeat Error] failed",
                ),
            ):
                self.assertFalse(scheduler.run_morning_briefing_once("2026-10-14"))

            self.assertFalse(state_path.exists())

    def test_new_date_allows_next_daily_briefing(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / ".scheduler_state.json"
            with (
                patch.object(scheduler, "_BRIEFING_STATE_PATH", state_path),
                patch.object(scheduler, "trigger_morning_briefing", return_value="briefing") as trigger,
            ):
                self.assertTrue(scheduler.run_morning_briefing_once("2026-10-14"))
                self.assertTrue(scheduler.run_morning_briefing_once("2026-10-15"))

            self.assertEqual(trigger.call_count, 2)


if __name__ == "__main__":
    unittest.main()

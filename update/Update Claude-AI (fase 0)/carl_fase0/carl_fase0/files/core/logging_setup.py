# core/logging_setup.py
"""Logging berkas berotasi dengan request id; log tahap (observability) tidak pernah memuat isi prompt/jawaban."""
import contextvars
import logging
import logging.handlers
import time
from contextlib import contextmanager
from pathlib import Path

import config
from observability import log_stage

request_id: contextvars.ContextVar = contextvars.ContextVar("request_id", default="-")
_configured = False


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


def setup_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    try:
        Path(config.LOG_PATH).mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            Path(config.LOG_PATH) / "carl.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
        )
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"))
    handler.addFilter(_RequestIdFilter())
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    # Query string /api/tts memuat teks balasan; jangan masuk access log uvicorn.
    class _DropTTS(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return "/api/tts" not in record.getMessage()
    logging.getLogger("uvicorn.access").addFilter(_DropTTS())
    _configured = True


@contextmanager
def stage(logger: logging.Logger, component: str, name: str, **meta):
    """Catat durasi tahap, termasuk saat gagal (status=error)."""
    started, status = time.perf_counter(), "ok"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        log_stage(logger, component, name, started, status=status, **meta)

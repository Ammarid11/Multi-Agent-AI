"""Low-overhead timing logs that never include prompt or answer content."""

import logging
import time
from typing import Any


def log_stage(
    logger: logging.Logger,
    component: str,
    stage: str,
    started_at: float,
    **metadata: Any,
) -> None:
    """Log a stage duration and non-sensitive dimensions only."""
    duration_ms = (time.perf_counter() - started_at) * 1000
    dimensions = " ".join(
        f"{key}={value}" for key, value in sorted(metadata.items())
    )
    logger.info(
        "carl_stage component=%s stage=%s duration_ms=%.2f%s",
        component,
        stage,
        duration_ms,
        f" {dimensions}" if dimensions else "",
    )

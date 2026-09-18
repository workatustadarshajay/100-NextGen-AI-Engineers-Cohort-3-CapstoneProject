from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGGER_NAME = "neuron"
WORKFLOW_LOGGER = logging.getLogger(f"{LOGGER_NAME}.workflow")
_REDACTED_TOKEN = re.compile(r"AIza[0-9A-Za-z_-]{20,}")


class JsonFormatter(logging.Formatter):
    """Keep workflow logs searchable in terminals and log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        field_names = (
            "document_id",
            "stage",
            "attempt",
            "duration_ms",
            "tool",
            "route",
            "error_type",
        )
        for field_name in field_names:
            value = getattr(record, field_name, None)
            if value is not None:
                payload[field_name] = value
        workflow_event = getattr(record, "workflow_event", None)
        if workflow_event:
            payload["event"] = workflow_event
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_logging() -> None:
    """Configure durable, structured application logs once per process."""
    logger = logging.getLogger(LOGGER_NAME)
    if getattr(logger, "_neuron_configured", False):
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    logger.propagate = False
    formatter = JsonFormatter()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    log_path = Path(os.getenv("NEURON_LOG_FILE", str(PROJECT_ROOT / "data/logs/neuron.log")))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger._neuron_configured = True


def safe_error_message(error: BaseException, *, limit: int = 2_000) -> str:
    """Return a useful error message without persisting an API token."""
    message = _REDACTED_TOKEN.sub("[redacted-token]", str(error)).strip()
    return message[:limit] or type(error).__name__


def make_workflow_event(
    stage: str,
    event: str,
    *,
    duration_ms: float | None = None,
    attempt: int | None = None,
    message: str | None = None,
    error_type: str | None = None,
) -> dict[str, Any]:
    """Build the JSON-safe event persisted with a document."""
    payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "event": event,
    }
    if duration_ms is not None:
        payload["duration_ms"] = round(duration_ms, 2)
    if attempt is not None:
        payload["attempt"] = attempt
    if message:
        payload["message"] = safe_error_message(RuntimeError(message))
    if error_type:
        payload["error_type"] = error_type
    return payload


def log_workflow_event(
    level: int,
    event: str,
    *,
    document_id: int,
    stage: str,
    attempt: int | None = None,
    duration_ms: float | None = None,
    tool: str | None = None,
    route: str | None = None,
    error: BaseException | None = None,
) -> None:
    """Write one structured workflow event to console and rotating file logs."""
    extra: dict[str, Any] = {
        "workflow_event": event,
        "document_id": document_id,
        "stage": stage,
    }
    for name, value in (
        ("attempt", attempt),
        ("duration_ms", duration_ms),
        ("tool", tool),
        ("route", route),
    ):
        if value is not None:
            extra[name] = value
    if error is not None:
        extra["error_type"] = type(error).__name__
    WORKFLOW_LOGGER.log(
        level,
        event,
        extra=extra,
        exc_info=(type(error), error, error.__traceback__) if error is not None else None,
    )
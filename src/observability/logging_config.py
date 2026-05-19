"""Structured logging. JSON in prod, plain text in local dev."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.config.settings import settings

# LogRecord attributes we don't want to re-emit as "extra" fields.
_RESERVED_RECORD_KEYS = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
}


class JsonFormatter(logging.Formatter):
    """Emit logs as a single JSON object per line.

    Picks up OpenTelemetry trace_id/span_id when LoggingInstrumentor is
    active, and merges any keys passed via `logger.info(..., extra={...})`.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        # OTel LoggingInstrumentor stamps these onto the record.
        for src, dst in (
            ("otelTraceID", "trace_id"),
            ("otelSpanID", "span_id"),
            ("otelServiceName", "service"),
        ):
            value = getattr(record, src, None)
            if value:
                payload[dst] = value

        # Merge user-supplied extras (anything not in the reserved set).
        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_KEYS or key in payload:
                continue
            if key.startswith("_") or key.startswith("otel"):
                continue
            payload[key] = value

        return json.dumps(payload, default=str)


def _resolve_format() -> str:
    if settings.LOG_FORMAT is not None:
        return settings.LOG_FORMAT
    return "text" if settings.ENVIRONMENT == "local" else "json"


def configure_logging() -> None:
    """Idempotently configure the root logger's level + formatter."""
    level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    if _resolve_format() == "json":
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
        )

    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            handler.setFormatter(formatter)

"""
Observability — Structured Logging (Part 19)

Centralized structured JSON logging with correlation IDs.
Provides logging utilities for all components.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any


# Correlation context — propagated across async boundaries
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
_job_id_ctx: ContextVar[str] = ContextVar("job_id", default="")
_trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="")


def set_request_id(request_id: str = "") -> str:
    rid = request_id or str(uuid.uuid4())
    _request_id_ctx.set(rid)
    return rid

def set_job_id(job_id: str) -> None:
    _job_id_ctx.set(job_id)

def set_trace_id(trace_id: str) -> None:
    _trace_id_ctx.set(trace_id)


class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Correlation IDs
        req_id = _request_id_ctx.get("")
        job_id = _job_id_ctx.get("")
        trace_id = _trace_id_ctx.get("")

        if req_id:
            log_entry["request_id"] = req_id
        if job_id:
            log_entry["job_id"] = job_id
        if trace_id:
            log_entry["trace_id"] = trace_id

        # Extra context
        if hasattr(record, "extra_data") and record.extra_data:
            log_entry["extra"] = record.extra_data

        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO", json_format: bool = True) -> None:
    """Configure root logger with structured JSON output."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter() if json_format else logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

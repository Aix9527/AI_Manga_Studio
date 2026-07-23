"""
Tracing — OpenTelemetry-compatible distributed tracing (Part 19)

Provides trace context propagation across async boundaries.
Supports span creation, attribute tagging, and event recording.
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator

_trace_context: ContextVar["TraceContext | None"] = ContextVar("trace_context", default=None)


@dataclass
class SpanEvent:
    """An event recorded within a span."""
    name: str
    timestamp: float = field(default_factory=time.time)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Span:
    """A single trace span."""
    span_id: str
    trace_id: str
    parent_span_id: str = ""
    name: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    status: str = "ok"  # ok | error
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[SpanEvent] = field(default_factory=list)

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def add_event(self, name: str, **attrs: Any) -> None:
        self.events.append(SpanEvent(name=name, attributes=attrs))

    def set_error(self, error_message: str) -> None:
        self.status = "error"
        self.set_attribute("error.message", error_message)

    def finish(self) -> None:
        self.end_time = time.time()

    @property
    def duration_seconds(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time


@dataclass
class TraceContext:
    """Current trace context — propagated with async operations."""
    trace_id: str
    span_stack: list[Span] = field(default_factory=list)

    @property
    def current_span(self) -> Span | None:
        return self.span_stack[-1] if self.span_stack else None

    def push_span(self, span: Span) -> None:
        if self.current_span:
            span.parent_span_id = self.current_span.span_id
        self.span_stack.append(span)

    def pop_span(self) -> Span | None:
        return self.span_stack.pop() if self.span_stack else None


class Tracer:
    """Distributed tracer — creates and manages spans."""

    def __init__(self, service_name: str = "ai_manga_studio") -> None:
        self._service_name = service_name
        self._finished_spans: list[Span] = []

    def start_trace(self, trace_id: str = "") -> TraceContext:
        """Start a new trace."""
        ctx = TraceContext(
            trace_id=trace_id or str(uuid.uuid4()),
        )
        _trace_context.set(ctx)
        return ctx

    def start_span(self, name: str, **attrs: Any) -> Span:
        """Start a new span within the current trace context."""
        ctx = _trace_context.get()
        if ctx is None:
            ctx = self.start_trace()

        span = Span(
            span_id=str(uuid.uuid4()),
            trace_id=ctx.trace_id,
            name=name,
            attributes=attrs,
        )
        ctx.push_span(span)
        return span

    def end_span(self) -> Span | None:
        """End the current span."""
        ctx = _trace_context.get()
        if ctx is None:
            return None

        span = ctx.pop_span()
        if span:
            span.finish()
            self._finished_spans.append(span)
        return span

    def get_current_trace_id(self) -> str:
        ctx = _trace_context.get()
        return ctx.trace_id if ctx else ""

    @asynccontextmanager
    async def span_context(self, name: str, **attrs: Any) -> AsyncIterator[Span]:
        """Async context manager that auto-closes the span."""
        span = self.start_span(name, **attrs)
        try:
            yield span
        except Exception as e:
            span.set_error(str(e))
            raise
        finally:
            self.end_span()

    def flush(self) -> list[Span]:
        """Get all finished spans."""
        spans = list(self._finished_spans)
        self._finished_spans.clear()
        return spans


# Global tracer instance
tracer = Tracer()

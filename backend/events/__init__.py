"""
Event Bus — Backbone of the Event-Driven Architecture (Part 8)

Provides publish/subscribe with:
- In-process async dispatch
- Type-safe event schemas
- Dead letter queue for failed handlers
- Domain event logging for audit
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Optional
from uuid import uuid4


logger = logging.getLogger(__name__)


# ── Event Models ─────────────────────────────────────────────────────────


class EventCategory(Enum):
    """Top-level classification of domain events."""
    PROJECT = "project"
    CHARACTER = "character"
    STORYBOARD = "storyboard"
    JOB = "job"
    ASSET = "asset"
    WORKFLOW = "workflow"
    REVIEW = "review"
    MEMORY = "memory"
    SYSTEM = "system"


@dataclass
class DomainEvent:
    """Immutable record of something that happened in the domain."""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    category: EventCategory = EventCategory.SYSTEM
    aggregate_id: str = ""
    aggregate_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    causation_id: Optional[str] = None
    correlation_id: Optional[str] = None


EventHandler = Callable[[DomainEvent], Awaitable[None]]


# ── Event Bus ────────────────────────────────────────────────────────────


class EventBus:
    """
    Central async event bus with subscription, dispatch, and DLQ.

    Usage:
        bus = EventBus()
        bus.subscribe("character.created", handler)
        await bus.publish(DomainEvent(event_type="character.created", ...))
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._wildcard_handlers: list[EventHandler] = []
        self._dlq: list[DomainEvent] = []
        self._running: bool = False

    async def start(self) -> None:
        """Start the event bus."""
        self._running = True
        logger.info("EventBus started.")

    async def stop(self) -> None:
        """Stop the event bus gracefully."""
        self._running = False
        logger.info("EventBus stopped.")

    def subscribe(
        self, event_type: str, handler: EventHandler
    ) -> None:
        """
        Subscribe a handler to a specific event type.

        Use '*' to subscribe to all events. Handlers must be
        async callables accepting a single DomainEvent.
        """
        if event_type == "*":
            self._wildcard_handlers.append(handler)
        else:
            self._handlers[event_type].append(handler)

    def unsubscribe(
        self, event_type: str, handler: EventHandler
    ) -> None:
        """Remove a handler subscription."""
        if event_type == "*":
            self._wildcard_handlers = [
                h for h in self._wildcard_handlers if h is not handler
            ]
        else:
            self._handlers[event_type] = [
                h
                for h in self._handlers.get(event_type, [])
                if h is not handler
            ]

    async def publish(self, event: DomainEvent) -> None:
        """
        Publish an event to all matching subscribers.

        Handlers are invoked concurrently. Failed handlers
        do not block dispatch to other handlers.
        """
        if not self._running:
            logger.warning("EventBus not running, event dropped: %s", event.event_type)
            return

        handlers = (
            self._handlers.get(event.event_type, [])
            + self._wildcard_handlers
        )

        if not handlers:
            return

        results = await asyncio.gather(
            *(self._invoke_safe(h, event) for h in handlers),
            return_exceptions=True,
        )

        failed = sum(1 for r in results if isinstance(r, Exception))
        if failed > 0:
            logger.warning(
                "Event %s: %d/%d handlers failed",
                event.event_type,
                failed,
                len(handlers),
            )
            self._dlq.append(event)

    async def _invoke_safe(
        self, handler: EventHandler, event: DomainEvent
    ) -> None:
        """Invoke a handler, catching and logging exceptions."""
        try:
            await handler(event)
        except Exception:
            logger.exception(
                "Handler %s failed for event %s",
                handler.__name__,
                event.event_type,
            )
            raise

    def drain_dlq(self) -> list[DomainEvent]:
        """Retrieve and clear the dead letter queue."""
        events = self._dlq[:]
        self._dlq.clear()
        return events

    @property
    def dlq_size(self) -> int:
        return len(self._dlq)


# ── Convenience event constructors ───────────────────────────────────────


def project_created(project_id: str, **kwargs: Any) -> DomainEvent:
    return DomainEvent(
        event_type="project.created",
        category=EventCategory.PROJECT,
        aggregate_id=project_id,
        aggregate_type="Project",
        payload=kwargs,
    )


def character_created(character_id: str, **kwargs: Any) -> DomainEvent:
    return DomainEvent(
        event_type="character.created",
        category=EventCategory.CHARACTER,
        aggregate_id=character_id,
        aggregate_type="Character",
        payload=kwargs,
    )


def job_completed(job_id: str, **kwargs: Any) -> DomainEvent:
    return DomainEvent(
        event_type="job.completed",
        category=EventCategory.JOB,
        aggregate_id=job_id,
        aggregate_type="Job",
        payload=kwargs,
    )


def asset_ready(asset_id: str, **kwargs: Any) -> DomainEvent:
    return DomainEvent(
        event_type="asset.ready",
        category=EventCategory.ASSET,
        aggregate_id=asset_id,
        aggregate_type="Asset",
        payload=kwargs,
    )

"""Domain events base and outbox infrastructure."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Immutable domain event envelope."""

    event_id: str
    event_type: str
    schema_version: int
    aggregate_type: str
    aggregate_id: str
    occurred_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None

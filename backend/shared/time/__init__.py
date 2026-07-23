"""Clock abstraction for deterministic time."""

from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    """Provides current time."""

    def now(self) -> datetime:
        ...


class SystemClock:
    """Real system clock in UTC."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    """Fixed clock for testing."""

    def __init__(self, value: datetime) -> None:
        self._value = value.astimezone(timezone.utc)

    def now(self) -> datetime:
        return self._value


def ensure_utc(value: datetime) -> datetime:
    """Raise if datetime is naive, then normalize to UTC."""
    if value.tzinfo is None:
        raise ValueError("Naive datetime is not allowed. Use timezone-aware datetimes.")
    return value.astimezone(timezone.utc)

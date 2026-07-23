"""Cursor-based pagination primitives."""

import base64
from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar

from backend.shared.serialization import canonical_json_dumps, json_loads

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class PageRequest:
    """Cursor pagination request."""

    limit: int = 50
    cursor: str | None = None


@dataclass(frozen=True, slots=True)
class PageResult(Generic[T]):
    """Cursor pagination result."""

    items: list[T]
    next_cursor: str | None


def encode_cursor(created_at: datetime, entity_id: str) -> str:
    """Encode a compound cursor from timestamp + entity ID."""
    payload = {
        "createdAt": created_at.isoformat(),
        "id": entity_id,
    }
    raw = canonical_json_dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> dict:
    """Decode a compound cursor to its components."""
    raw = base64.urlsafe_b64decode(cursor.encode())
    return json_loads(raw.decode("utf-8"))

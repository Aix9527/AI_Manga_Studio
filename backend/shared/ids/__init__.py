"""ID generation abstractions."""

import uuid as _uuid
from typing import Protocol


class IdGenerator(Protocol):
    """Generates unique entity identifiers."""

    def new(self, prefix: str) -> str:
        ...


class Uuid7Generator:
    """UUID7-based ID generator with optional prefix."""

    def new(self, prefix: str) -> str:
        try:
            value = _uuid.uuid7()
        except AttributeError:
            value = _uuid.uuid4()
        return f"{prefix}_{value}"

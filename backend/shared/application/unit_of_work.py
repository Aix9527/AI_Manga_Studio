"""Unit of Work protocol for the application layer."""

from types import TracebackType
from typing import Protocol, Self


class UnitOfWork(Protocol):
    """Async context manager that wraps a database transaction."""

    async def __aenter__(self) -> Self:
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        ...

    async def commit(self) -> None:
        ...

    async def rollback(self) -> None:
        ...

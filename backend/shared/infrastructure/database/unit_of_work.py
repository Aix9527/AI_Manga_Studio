"""SQLAlchemy Unit of Work with explicit commit requirement."""

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncSessionTransaction,
    async_sessionmaker,
)


class SqlAlchemyUnitOfWork:
    """Manages a single database transaction via async context manager."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self._transaction: AsyncSessionTransaction | None = None
        self._committed: bool = False

    async def __aenter__(self) -> Self:
        self.session = self._session_factory()
        self._transaction = await self.session.begin()
        return self

    async def commit(self) -> None:
        """Explicitly commit the current transaction."""
        if self._transaction is None:
            raise RuntimeError("Unit of work has not started.")
        await self._transaction.commit()
        self._committed = True

    async def rollback(self) -> None:
        """Explicitly roll back the current transaction."""
        if self._transaction is not None:
            await self._transaction.rollback()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exc is not None:
                await self.rollback()
            elif not self._committed:
                await self.rollback()
        finally:
            if self.session is not None:
                await self.session.close()

    def __repr__(self) -> str:
        committed = "committed" if self._committed else "open"
        return f"<SqlAlchemyUnitOfWork({committed})>"

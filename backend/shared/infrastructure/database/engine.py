"""Async database engine factory."""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_database_engine(
    database_url: str,
    *,
    echo: bool = False,
) -> AsyncEngine:
    """Create an async SQLAlchemy engine."""
    return create_async_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        future=True,
    )

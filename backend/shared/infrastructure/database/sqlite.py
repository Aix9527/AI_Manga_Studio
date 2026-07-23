"""SQLite PRAGMA configuration."""

from sqlalchemy import event
from sqlalchemy.engine import Engine


def configure_sqlite(engine: Engine) -> None:
    """Enable WAL mode, foreign keys, and performance PRAGMAs on SQLite."""

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:  # noqa: ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.execute("PRAGMA temp_store = MEMORY")
        cursor.close()

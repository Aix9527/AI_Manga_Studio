from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


class OrchestrationDatabase:
    def __init__(
        self,
        path: str | Path,
        migrations_dir: str | Path | None = None,
    ):
        self.path = Path(path)
        self.migrations_dir = (
            Path(migrations_dir)
            if migrations_dir is not None
            else Path(__file__).with_name("migrations")
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=30,
            check_same_thread=False,
        )
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")
        except Exception:
            connection.close()
            raise
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self) -> None:
        connection = self.connect()
        try:
            applied_versions = self._applied_versions(connection)
            for version, migration_path in self._migration_files():
                if version in applied_versions:
                    continue
                schema = migration_path.read_text(encoding="utf-8")
                try:
                    connection.executescript(f"BEGIN IMMEDIATE;\n{schema}")
                    connection.execute(
                        """
                        INSERT INTO schema_migrations(version, applied_at)
                        VALUES (?, ?)
                        """,
                        (version, datetime.now(timezone.utc).isoformat()),
                    )
                    connection.commit()
                except Exception:
                    if connection.in_transaction:
                        connection.rollback()
                    raise
                applied_versions.add(version)
        finally:
            connection.close()

    def _migration_files(self) -> list[tuple[int, Path]]:
        migrations: list[tuple[int, Path]] = []
        seen_versions: set[int] = set()
        for path in self.migrations_dir.glob("*.sql"):
            prefix, separator, _name = path.name.partition("_")
            if not separator or not prefix.isdigit():
                continue
            version = int(prefix)
            if version in seen_versions:
                raise ValueError(f"duplicate migration version: {version}")
            seen_versions.add(version)
            migrations.append((version, path))
        return sorted(migrations, key=lambda item: item[0])

    @staticmethod
    def _applied_versions(connection: sqlite3.Connection) -> set[int]:
        migrations_table = connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'schema_migrations'
            """
        ).fetchone()
        if migrations_table is None:
            return set()
        return {
            row["version"]
            for row in connection.execute("SELECT version FROM schema_migrations")
        }

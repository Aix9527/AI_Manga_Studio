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
        migrations = self._migration_files()
        migration_versions = [version for version, _path in migrations]
        connection = self.connect()
        try:
            has_migration_history = self._has_migration_history(connection)
            user_objects = self._user_schema_objects(connection)
            if has_migration_history:
                applied_versions = self._applied_versions(connection)
                other_objects = user_objects - {("table", "schema_migrations")}
                if not applied_versions and other_objects:
                    raise RuntimeError(
                        "empty migration history with existing schema objects"
                    )
            else:
                if user_objects:
                    raise RuntimeError("unversioned database contains schema objects")
                applied_versions = set()

            applied_sequence = sorted(applied_versions)
            expected_prefix = migration_versions[: len(applied_sequence)]
            if applied_sequence != expected_prefix:
                raise RuntimeError(
                    "database migration history is not a valid code prefix"
                )

            for version, migration_path in migrations:
                if version in applied_versions:
                    continue
                schema = migration_path.read_text(encoding="utf-8")
                try:
                    self._execute_migration(connection, schema)
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
        if not self.migrations_dir.is_dir():
            raise ValueError(
                f"migration directory does not exist: {self.migrations_dir}"
            )
        paths = list(self.migrations_dir.glob("*.sql"))
        if not paths:
            raise ValueError(f"no migration files found in: {self.migrations_dir}")

        migrations: list[tuple[int, Path]] = []
        seen_versions: set[int] = set()
        for path in paths:
            prefix, separator, name = path.stem.partition("_")
            if (
                not separator
                or not prefix.isascii()
                or not prefix.isdigit()
                or not name.strip()
            ):
                raise ValueError(f"invalid migration filename: {path.name}")
            version = int(prefix)
            if version <= 0:
                raise ValueError(f"invalid migration filename: {path.name}")
            if version in seen_versions:
                raise ValueError(f"duplicate migration version: {version}")
            seen_versions.add(version)
            migrations.append((version, path))
        migrations.sort(key=lambda item: item[0])
        if migrations[0][0] != 1:
            raise ValueError("first migration version must be 1")
        return migrations

    @staticmethod
    def _execute_migration(
        connection: sqlite3.Connection,
        schema: str,
    ) -> None:
        runner_begin_pending = True

        def authorize(
            action_code: int,
            argument_one: str | None,
            _argument_two: str | None,
            _database_name: str | None,
            _trigger_name: str | None,
        ) -> int:
            nonlocal runner_begin_pending
            if action_code == sqlite3.SQLITE_TRANSACTION:
                operation = (argument_one or "").upper()
                if runner_begin_pending and operation == "BEGIN":
                    runner_begin_pending = False
                    return sqlite3.SQLITE_OK
                return sqlite3.SQLITE_DENY
            if action_code == sqlite3.SQLITE_SAVEPOINT:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(authorize)
        try:
            connection.executescript(f"BEGIN IMMEDIATE;\n{schema}")
        finally:
            connection.set_authorizer(None)

        if runner_begin_pending or not connection.in_transaction:
            raise RuntimeError("migration escaped the runner transaction")

    @staticmethod
    def _has_migration_history(connection: sqlite3.Connection) -> bool:
        return (
            connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'schema_migrations'
                """
            ).fetchone()
            is not None
        )

    @staticmethod
    def _user_schema_objects(
        connection: sqlite3.Connection,
    ) -> set[tuple[str, str]]:
        return {
            (row["type"], row["name"])
            for row in connection.execute(
                """
                SELECT type, name FROM sqlite_master
                WHERE type IN ('table', 'index', 'view', 'trigger')
                  AND name NOT LIKE 'sqlite_%'
                """
            )
        }

    @staticmethod
    def _applied_versions(connection: sqlite3.Connection) -> set[int]:
        return {
            row["version"]
            for row in connection.execute("SELECT version FROM schema_migrations")
        }

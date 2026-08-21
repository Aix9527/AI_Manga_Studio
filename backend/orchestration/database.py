from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path


class OrchestrationDatabase:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._initialize()

    def _initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(self._schema())
            self._migrate_job_steps(conn)
            self._migrate_artifacts(conn)
            conn.commit()

    def close(self) -> None:
        connection = getattr(self._local, "conn", None)
        if connection is not None:
            connection.close()
            self._local.conn = None

    @staticmethod
    def _migrate_job_steps(conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(job_steps)")}
        migrations = {
            "quality_attempt": "INTEGER NOT NULL DEFAULT 0",
            "ui_stage_key": "TEXT NOT NULL DEFAULT ''",
            "quality_report": "TEXT NOT NULL DEFAULT '{}'",
        }
        for name, definition in migrations.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE job_steps ADD COLUMN {name} {definition}")

    @staticmethod
    def _migrate_artifacts(conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(artifacts)")}
        migrations = {
            "project_id": "TEXT NOT NULL DEFAULT ''",
            "parent_artifact_id": "INTEGER",
            "version": "INTEGER NOT NULL DEFAULT 1",
            "stage_key": "TEXT NOT NULL DEFAULT ''",
            "scene_id": "TEXT NOT NULL DEFAULT ''",
            "shot_id": "TEXT NOT NULL DEFAULT ''",
            "quality_status": "TEXT NOT NULL DEFAULT 'unreviewed'",
            "quality_attempt": "INTEGER NOT NULL DEFAULT 0",
            "quality_report": "TEXT NOT NULL DEFAULT '{}'",
        }
        for name, definition in migrations.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE artifacts ADD COLUMN {name} {definition}")
        conn.execute(
            """UPDATE artifacts
               SET project_id=(SELECT jobs.project_id FROM jobs WHERE jobs.id=artifacts.job_id)
               WHERE project_id='' AND EXISTS (
                   SELECT 1 FROM jobs WHERE jobs.id=artifacts.job_id
               )"""
        )
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_artifacts_project_listing
               ON artifacts(project_id, active DESC, version DESC, id DESC)"""
        )
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_artifacts_lineage
               ON artifacts(project_id, kind, stage_key, scene_id, shot_id, version)"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_artifacts_parent ON artifacts(parent_artifact_id)"
        )

    def _schema(self) -> str:
        return """
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;

        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            mode TEXT NOT NULL DEFAULT 'automatic',
            desired_state TEXT NOT NULL DEFAULT 'running',
            current_stage TEXT NOT NULL DEFAULT '',
            current_shot TEXT NOT NULL DEFAULT '',
            progress REAL NOT NULL DEFAULT 0.0,
            message TEXT NOT NULL DEFAULT '',
            final_video TEXT NOT NULL DEFAULT '',
            input_path TEXT NOT NULL DEFAULT '',
            input_type TEXT NOT NULL DEFAULT 'novel',
            settings TEXT NOT NULL DEFAULT '{}',
            idempotency_key TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            finished_at TEXT,
            retry_count INTEGER NOT NULL DEFAULT 0,
            lease_id TEXT,
            lease_expires_at TEXT
        );

        CREATE TABLE IF NOT EXISTS job_steps (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            sequence INTEGER NOT NULL,
            stage_key TEXT NOT NULL,
            shot_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            attempt INTEGER NOT NULL DEFAULT 0,
            progress REAL NOT NULL DEFAULT 0.0,
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            quality_attempt INTEGER NOT NULL DEFAULT 0,
            ui_stage_key TEXT NOT NULL DEFAULT '',
            quality_report TEXT NOT NULL DEFAULT '{}',
            started_at TEXT,
            finished_at TEXT,
            UNIQUE(job_id, stage_key, shot_id)
        );

        CREATE INDEX IF NOT EXISTS idx_job_steps_job_id ON job_steps(job_id);
        CREATE INDEX IF NOT EXISTS idx_job_steps_status ON job_steps(status);

        CREATE TABLE IF NOT EXISTS artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            step_id TEXT NOT NULL REFERENCES job_steps(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            active INTEGER NOT NULL DEFAULT 1,
            quality_attempt INTEGER NOT NULL DEFAULT 0,
            quality_report TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_artifacts_job_id ON artifacts(job_id);
        CREATE INDEX IF NOT EXISTS idx_artifacts_active ON artifacts(active);

        CREATE TABLE IF NOT EXISTS checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            step_id TEXT NOT NULL,
            stage_key TEXT NOT NULL,
            shot_id TEXT NOT NULL DEFAULT '',
            input_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'completed',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_checkpoints_job_id ON checkpoints(job_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_checkpoints_unique
            ON checkpoints(job_id, stage_key, shot_id);

        CREATE TABLE IF NOT EXISTS project_workspaces (
            project_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source_path TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS stage_automation (
            project_id TEXT NOT NULL,
            stage_key TEXT NOT NULL,
            settings TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (project_id, stage_key)
        );
        """

    @contextmanager
    def connect(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn.execute("PRAGMA busy_timeout=10000")
        try:
            yield self._local.conn
        except Exception:
            self._local.conn.rollback()
            raise

    @contextmanager
    def transaction(self, *, immediate: bool = False):
        with self.connect() as conn:
            try:
                if immediate:
                    conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

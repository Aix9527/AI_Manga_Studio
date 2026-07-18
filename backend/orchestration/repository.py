from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from backend.orchestration.schemas import JobCreate

if TYPE_CHECKING:
    from backend.orchestration.database import OrchestrationDatabase


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def rowdict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


class JobRepository:
    def __init__(self, database: OrchestrationDatabase):
        self.database = database

    def create_job(self, request: JobCreate) -> dict[str, Any]:
        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM jobs WHERE idempotency_key = ?",
                (request.idempotency_key,),
            ).fetchone()
            if existing is not None:
                return rowdict(existing)

            job_id = str(uuid4())
            timestamp = utcnow()
            connection.execute(
                """
                INSERT INTO jobs(
                    id, project_id, input_path, input_type, mode, status,
                    settings_json, idempotency_key, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    request.project_id,
                    request.input_path,
                    request.input_type,
                    request.mode,
                    "queued",
                    request.model_dump_json(),
                    request.idempotency_key,
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO job_events(job_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (job_id, "job.created", "{}", timestamp),
            )
            created = connection.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            return rowdict(created)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            job = connection.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if job is None:
                return None
            return self._job_with_steps(connection, job)

    def get_current_job(self) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            job = connection.execute(
                """
                SELECT * FROM jobs
                WHERE status NOT IN ('completed', 'cancelled')
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ).fetchone()
            if job is None:
                return None
            return self._job_with_steps(connection, job)

    def list_jobs(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        if limit < 0 or offset < 0:
            raise ValueError("limit and offset must be non-negative")
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        jobs = [rowdict(row) for row in rows]
        for job in jobs:
            job.pop("settings_json", None)
        return jobs

    def append_event(
        self,
        job_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> int:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO job_events(job_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    job_id,
                    event_type,
                    json.dumps(payload, ensure_ascii=False),
                    utcnow(),
                ),
            )
            return int(cursor.lastrowid)

    def list_events(
        self, job_id: str, after_id: int = 0
    ) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM job_events
                WHERE job_id = ? AND id > ?
                ORDER BY id ASC
                """,
                (job_id, after_id),
            ).fetchall()
        return [rowdict(row) for row in rows]

    @staticmethod
    def _job_with_steps(
        connection: sqlite3.Connection, job_row: sqlite3.Row
    ) -> dict[str, Any]:
        job = rowdict(job_row)
        job["settings"] = json.loads(job.pop("settings_json"))
        step_rows = connection.execute(
            """
            SELECT * FROM job_steps
            WHERE job_id = ?
            ORDER BY sequence ASC, shot_id ASC
            """,
            (job["id"],),
        ).fetchall()
        job["steps"] = [rowdict(row) for row in step_rows]
        return job

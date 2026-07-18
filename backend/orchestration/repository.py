from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterable
from uuid import uuid4

from backend.orchestration.checkpoints import ArtifactDraft, validate_checkpoint
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

    def complete_step(
        self,
        job_id: str,
        step_id: str,
        step_input_hash: str,
        artifacts: Iterable[ArtifactDraft],
    ) -> None:
        drafts = list(artifacts)
        if not drafts:
            raise ValueError("at least one artifact is required")
        if not step_input_hash:
            raise ValueError("step input hash is required")

        keys = [(draft.kind, draft.path) for draft in drafts]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate artifact kind and path")

        metadata_json = []
        for draft in drafts:
            metadata_json.append(
                json.dumps(draft.metadata, ensure_ascii=False, allow_nan=False)
            )
        if not validate_checkpoint(drafts, step_input_hash, step_input_hash):
            raise ValueError("artifact checkpoint is no longer valid")

        timestamp = utcnow()
        with self.database.transaction() as connection:
            step = connection.execute(
                "SELECT id FROM job_steps WHERE id = ? AND job_id = ?",
                (step_id, job_id),
            ).fetchone()
            if step is None:
                raise KeyError(f"step {step_id!r} does not belong to job {job_id!r}")

            connection.execute(
                "UPDATE artifacts SET active = 0 WHERE step_id = ?",
                (step_id,),
            )
            for draft, serialized_metadata in zip(
                drafts, metadata_json, strict=True
            ):
                connection.execute(
                    """
                    INSERT INTO artifacts(
                        id, job_id, step_id, kind, path, sha256, size,
                        metadata_json, validated_at, active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(step_id, kind, path) DO UPDATE SET
                        sha256 = excluded.sha256,
                        size = excluded.size,
                        metadata_json = excluded.metadata_json,
                        validated_at = excluded.validated_at,
                        active = 1
                    """,
                    (
                        str(uuid4()),
                        job_id,
                        step_id,
                        draft.kind,
                        draft.path,
                        draft.sha256,
                        draft.size,
                        serialized_metadata,
                        timestamp,
                    ),
                )
            connection.execute(
                """
                UPDATE job_steps
                SET status = 'completed', progress = 1, input_hash = ?,
                    error_code = '', error_message = '', finished_at = ?
                WHERE id = ? AND job_id = ?
                """,
                (step_input_hash, timestamp, step_id, job_id),
            )

    def reconcile_checkpoints(self) -> int:
        connection = self.database.connect()
        try:
            rows = connection.execute(
                """
                SELECT job_id, step_id, kind, path, sha256, size
                FROM artifacts
                WHERE active = 1
                """
            ).fetchall()
        finally:
            connection.close()

        invalid_roots: set[tuple[str, str]] = set()
        for row in rows:
            artifact = ArtifactDraft(
                kind=row["kind"],
                path=row["path"],
                sha256=row["sha256"],
                size=row["size"],
            )
            if not validate_checkpoint([artifact], "stored", "stored"):
                invalid_roots.add((row["job_id"], row["step_id"]))

        roots_by_job: dict[str, set[str]] = {}
        for job_id, step_id in invalid_roots:
            roots_by_job.setdefault(job_id, set()).add(step_id)

        for job_id, root_ids in roots_by_job.items():
            with self.database.transaction() as connection:
                steps = connection.execute(
                    """
                    SELECT id, sequence, shot_id
                    FROM job_steps
                    WHERE job_id = ?
                    """,
                    (job_id,),
                ).fetchall()
                by_id = {row["id"]: row for row in steps}
                affected: set[str] = set()
                for root_id in root_ids:
                    root = by_id.get(root_id)
                    if root is None:
                        continue
                    affected.add(root_id)
                    for candidate in steps:
                        if candidate["sequence"] <= root["sequence"]:
                            continue
                        if not root["shot_id"] or candidate["shot_id"] in (
                            root["shot_id"],
                            "",
                        ):
                            affected.add(candidate["id"])

                if not affected:
                    continue
                placeholders = ",".join("?" for _ in affected)
                parameters = (job_id, *sorted(affected))
                connection.execute(
                    f"""
                    UPDATE artifacts SET active = 0
                    WHERE job_id = ? AND step_id IN ({placeholders})
                    """,
                    parameters,
                )
                connection.execute(
                    f"""
                    UPDATE job_steps
                    SET status = 'queued', progress = 0, input_hash = '',
                        error_code = '', error_message = '',
                        started_at = NULL, finished_at = NULL
                    WHERE job_id = ? AND id IN ({placeholders})
                    """,
                    parameters,
                )
                connection.execute(
                    """
                    UPDATE jobs
                    SET status = 'queued', desired_state = 'running',
                        final_video = '', run_after = NULL, worker_id = NULL,
                        lease_until = NULL, finished_at = NULL,
                        message = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        "检测到检查点损坏，已从受影响步骤恢复",
                        utcnow(),
                        job_id,
                    ),
                )
        return len(invalid_roots)

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

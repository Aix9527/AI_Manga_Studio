from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterable
from uuid import uuid4

from backend.orchestration.checkpoints import (
    ArtifactDraft,
    matches_file_identity,
    validate_checkpoint,
    validated_file_identities,
)
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
        identities = validated_file_identities(drafts)
        if identities is None:
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
            if any(
                not matches_file_identity(draft.path, identity)
                for draft, identity in zip(drafts, identities, strict=True)
            ):
                raise ValueError("artifact checkpoint changed during completion")

    def reconcile_checkpoints(self) -> int:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT id, job_id, step_id, kind, path, sha256, size,
                       validated_at
                FROM artifacts
                WHERE active = 1
                """
            ).fetchall()
            missing_artifact_rows = connection.execute(
                """
                SELECT steps.job_id, steps.id AS step_id
                FROM job_steps AS steps
                WHERE steps.status = 'completed'
                  AND NOT EXISTS (
                      SELECT 1 FROM artifacts
                      WHERE artifacts.job_id = steps.job_id
                        AND artifacts.step_id = steps.id
                        AND artifacts.active = 1
                  )
                """
            ).fetchall()

        invalid_versions: dict[tuple[str, str], list[sqlite3.Row]] = {}
        for row in rows:
            artifact = ArtifactDraft(
                kind=row["kind"],
                path=row["path"],
                sha256=row["sha256"],
                size=row["size"],
            )
            if not validate_checkpoint([artifact], "stored", "stored"):
                root = (row["job_id"], row["step_id"])
                invalid_versions.setdefault(root, []).append(row)

        missing_artifact_roots = {
            (row["job_id"], row["step_id"]) for row in missing_artifact_rows
        }

        roots_by_job: dict[str, set[str]] = {}
        for job_id, step_id in invalid_versions.keys() | missing_artifact_roots:
            roots_by_job.setdefault(job_id, set()).add(step_id)

        reconciled_root_count = 0
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
                confirmed_roots: set[str] = set()
                for root_id in root_ids:
                    root_key = (job_id, root_id)
                    bad_version_remains = any(
                        connection.execute(
                            """
                            SELECT 1 FROM artifacts
                            WHERE id = ? AND job_id = ? AND step_id = ?
                              AND kind = ? AND path = ? AND sha256 = ?
                              AND size = ? AND validated_at = ? AND active = 1
                            """,
                            (
                                version["id"],
                                version["job_id"],
                                version["step_id"],
                                version["kind"],
                                version["path"],
                                version["sha256"],
                                version["size"],
                                version["validated_at"],
                            ),
                        ).fetchone()
                        is not None
                        for version in invalid_versions.get(root_key, [])
                    )
                    completed_still_has_no_artifact = False
                    if root_key in missing_artifact_roots:
                        completed_still_has_no_artifact = (
                            connection.execute(
                                """
                                SELECT 1 FROM job_steps AS steps
                                WHERE steps.job_id = ? AND steps.id = ?
                                  AND steps.status = 'completed'
                                  AND NOT EXISTS (
                                      SELECT 1 FROM artifacts
                                      WHERE artifacts.job_id = steps.job_id
                                        AND artifacts.step_id = steps.id
                                        AND artifacts.active = 1
                                  )
                                """,
                                (job_id, root_id),
                            ).fetchone()
                            is not None
                        )
                    if bad_version_remains or completed_still_has_no_artifact:
                        confirmed_roots.add(root_id)

                reconciled_root_count += len(confirmed_roots)
                affected: set[str] = set()
                for root_id in confirmed_roots:
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
        return reconciled_root_count

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

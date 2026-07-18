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


class LeaseOwnershipError(RuntimeError):
    """Raised when a worker tries to mutate a job it no longer owns."""


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
        expected_worker_id: str | None = None,
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
            if expected_worker_id is not None:
                owned = connection.execute(
                    """
                    SELECT 1 FROM jobs
                    WHERE id = ? AND status = 'running' AND worker_id = ?
                    """,
                    (job_id, expected_worker_id),
                ).fetchone()
                if owned is None:
                    raise LeaseOwnershipError(
                        f"worker {expected_worker_id!r} no longer owns job {job_id!r}"
                    )
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

    def claim_next(
        self,
        worker_id: str,
        now: str,
        lease_until: str,
    ) -> dict[str, Any] | None:
        claimed_id: str | None = None
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT id FROM jobs
                WHERE desired_state = 'running'
                  AND (
                    status = 'queued'
                    OR (
                        status = 'retry_wait'
                        AND run_after IS NOT NULL
                        AND run_after <= ?
                    )
                  )
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if row is None:
                return None
            changed = connection.execute(
                """
                UPDATE jobs
                SET status = 'running', worker_id = ?, lease_until = ?,
                    updated_at = ?
                WHERE id = ? AND desired_state = 'running'
                  AND (
                    status = 'queued'
                    OR (
                        status = 'retry_wait'
                        AND run_after IS NOT NULL
                        AND run_after <= ?
                    )
                  )
                """,
                (worker_id, lease_until, now, row["id"], now),
            ).rowcount
            if changed:
                claimed_id = str(row["id"])
        return self.get_job(claimed_id) if claimed_id is not None else None

    def renew_lease(
        self,
        job_id: str,
        worker_id: str,
        now: str,
        lease_until: str,
    ) -> bool:
        with self.database.transaction() as connection:
            changed = connection.execute(
                """
                UPDATE jobs
                SET lease_until = ?, updated_at = ?
                WHERE id = ? AND status = 'running' AND worker_id = ?
                  AND lease_until IS NOT NULL AND lease_until > ?
                """,
                (lease_until, now, job_id, worker_id, now),
            ).rowcount
        return bool(changed)

    def recover_expired_leases(self, now: str) -> int:
        with self.database.transaction() as connection:
            rows = connection.execute(
                """
                SELECT id FROM jobs
                WHERE status = 'running' AND lease_until IS NOT NULL
                  AND lease_until <= ?
                ORDER BY created_at ASC, id ASC
                """,
                (now,),
            ).fetchall()
            job_ids = [str(row["id"]) for row in rows]
            if not job_ids:
                return 0
            placeholders = ",".join("?" for _ in job_ids)
            connection.execute(
                f"""
                UPDATE job_steps
                SET status = 'queued', started_at = NULL, finished_at = NULL
                WHERE job_id IN ({placeholders})
                  AND status IN ('running', 'retry_wait')
                """,
                job_ids,
            )
            connection.execute(
                f"""
                UPDATE jobs
                SET status = 'queued', worker_id = NULL, lease_until = NULL,
                    run_after = NULL, message = ?, updated_at = ?
                WHERE id IN ({placeholders}) AND status = 'running'
                """,
                ("已从中断的检查点恢复", now, *job_ids),
            )
            return len(job_ids)

    def fail_or_retry_step(
        self,
        job_id: str,
        step_id: str,
        code: str,
        message: str,
        max_retries: int,
        retry_at: str | None,
        worker_id: str,
    ) -> tuple[bool, int]:
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        with self.database.transaction() as connection:
            job = connection.execute(
                """
                SELECT desired_state FROM jobs
                WHERE id = ? AND status = 'running' AND worker_id = ?
                """,
                (job_id, worker_id),
            ).fetchone()
            if job is None:
                raise LeaseOwnershipError(
                    f"worker {worker_id!r} no longer owns job {job_id!r}"
                )
            step = connection.execute(
                "SELECT attempt FROM job_steps WHERE id = ? AND job_id = ?",
                (step_id, job_id),
            ).fetchone()
            if step is None:
                raise KeyError(f"step {step_id!r} does not belong to job {job_id!r}")

            if job["desired_state"] == "cancelled":
                timestamp = utcnow()
                connection.execute(
                    """
                    UPDATE job_steps SET status = 'cancelled', finished_at = ?
                    WHERE job_id = ? AND status NOT IN ('completed', 'cancelled')
                    """,
                    (timestamp, job_id),
                )
                connection.execute(
                    """
                    UPDATE jobs
                    SET status = 'cancelled', message = '已取消', run_after = NULL,
                        worker_id = NULL, lease_until = NULL, finished_at = ?,
                        updated_at = ?
                    WHERE id = ? AND status = 'running' AND worker_id = ?
                      AND desired_state = 'cancelled'
                    """,
                    (timestamp, timestamp, job_id, worker_id),
                )
                return False, int(step["attempt"])

            attempt = int(step["attempt"]) + 1
            exhausted = attempt > max_retries
            step_status = "failed" if exhausted else "retry_wait"
            if exhausted:
                job_status = "failed"
            elif job["desired_state"] == "paused":
                job_status = "paused"
            else:
                job_status = "retry_wait"
            effective_retry_at = retry_at if job_status == "retry_wait" else None
            connection.execute(
                """
                UPDATE job_steps
                SET attempt = ?, status = ?, error_code = ?, error_message = ?
                WHERE id = ? AND job_id = ?
                """,
                (attempt, step_status, code, message, step_id, job_id),
            )
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, message = ?, run_after = ?, worker_id = NULL,
                    lease_until = NULL, updated_at = ?
                WHERE id = ? AND status = 'running' AND worker_id = ?
                """,
                (
                    job_status,
                    message,
                    effective_retry_at,
                    utcnow(),
                    job_id,
                    worker_id,
                ),
            )
            return exhausted, attempt

    def is_cancel_requested(self, job_id: str) -> bool:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT desired_state FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        if row is None:
            raise LookupError(f"job {job_id!r} does not exist")
        return row["desired_state"] == "cancelled"

    def finalize_cancel(self, job_id: str) -> bool:
        with self.database.transaction() as connection:
            job = connection.execute(
                "SELECT status, desired_state FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if job is None or job["desired_state"] != "cancelled":
                return False
            if job["status"] == "cancelled":
                return True
            timestamp = utcnow()
            connection.execute(
                """
                UPDATE job_steps SET status = 'cancelled', finished_at = ?
                WHERE job_id = ? AND status NOT IN ('completed', 'cancelled')
                """,
                (timestamp, job_id),
            )
            connection.execute(
                """
                UPDATE jobs
                SET status = 'cancelled', message = '已取消', run_after = NULL,
                    worker_id = NULL, lease_until = NULL, finished_at = ?,
                    updated_at = ?
                WHERE id = ? AND desired_state = 'cancelled'
                """,
                (timestamp, timestamp, job_id),
            )
            return True

    def current_step_id(self, job_id: str) -> str:
        with self.database.connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if exists is None:
                raise LookupError(f"job {job_id!r} does not exist")
            row = connection.execute(
                """
                SELECT id FROM job_steps
                WHERE job_id = ?
                  AND status IN ('running', 'retry_wait', 'queued', 'pending', 'failed')
                ORDER BY
                  CASE status WHEN 'running' THEN 0 ELSE 1 END,
                  sequence ASC, shot_id ASC, id ASC
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            raise LookupError(f"job {job_id!r} has no active step")
        return str(row["id"])

    def apply_step_outcome(
        self,
        job_id: str,
        outcome: Any,
        worker_id: str,
    ) -> None:
        self.complete_step(
            job_id,
            outcome.step_id,
            outcome.input_hash,
            outcome.artifacts,
            expected_worker_id=worker_id,
        )
        with self.database.transaction() as connection:
            job = connection.execute(
                """
                SELECT mode, desired_state FROM jobs
                WHERE id = ? AND status = 'running' AND worker_id = ?
                """,
                (job_id, worker_id),
            ).fetchone()
            if job is None:
                raise LeaseOwnershipError(
                    f"worker {worker_id!r} no longer owns job {job_id!r}"
                )
            if job["desired_state"] == "cancelled":
                target = "cancelled"
                connection.execute(
                    """
                    UPDATE job_steps SET status = 'cancelled', finished_at = ?
                    WHERE job_id = ? AND status NOT IN ('completed', 'cancelled')
                    """,
                    (utcnow(), job_id),
                )
            elif job["desired_state"] == "paused":
                target = "paused"
            elif job["mode"] == "manual_review":
                target = "waiting_review"
            else:
                target = "queued"
            timestamp = utcnow()
            changed = connection.execute(
                """
                UPDATE jobs
                SET status = ?, progress = ?, message = ?, final_video = ?,
                    run_after = NULL, worker_id = NULL, lease_until = NULL,
                    finished_at = CASE WHEN ? = 'cancelled' THEN ? ELSE finished_at END,
                    updated_at = ?
                WHERE id = ? AND status = 'running' AND worker_id = ?
                """,
                (
                    target,
                    outcome.progress,
                    outcome.message,
                    outcome.final_video,
                    target,
                    timestamp,
                    timestamp,
                    job_id,
                    worker_id,
                ),
            ).rowcount
            if not changed:
                raise LeaseOwnershipError(
                    f"worker {worker_id!r} no longer owns job {job_id!r}"
                )

    def ensure_bootstrap_step(self, job_id: str) -> str:
        with self.database.transaction() as connection:
            exists = connection.execute(
                "SELECT 1 FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if exists is None:
                raise LookupError(f"job {job_id!r} does not exist")
            rows = connection.execute(
                """
                SELECT id, status FROM job_steps
                WHERE job_id = ?
                ORDER BY sequence ASC, shot_id ASC, id ASC
                """,
                (job_id,),
            ).fetchall()
            timestamp = utcnow()
            if not rows:
                step_id = str(uuid4())
                connection.execute(
                    """
                    INSERT INTO job_steps(
                        id, job_id, sequence, stage_key, shot_id, status, started_at
                    ) VALUES (?, ?, 0, 'input_parse', '', 'running', ?)
                    """,
                    (step_id, job_id, timestamp),
                )
                return step_id
            active = next(
                (
                    row
                    for row in rows
                    if row["status"] in ("running", "retry_wait", "pending", "queued")
                ),
                None,
            )
            if active is None:
                raise LookupError(f"job {job_id!r} has no unfinished step")
            connection.execute(
                """
                UPDATE job_steps
                SET status = 'running', started_at = COALESCE(started_at, ?)
                WHERE id = ? AND job_id = ?
                """,
                (timestamp, active["id"], job_id),
            )
            return str(active["id"])

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

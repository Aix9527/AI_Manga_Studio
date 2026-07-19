from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterable
from uuid import uuid4

from pydantic import ValidationError

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


class JobNotFoundError(LookupError):
    """Raised when a durable command targets a job that does not exist."""


class JobConflictError(RuntimeError):
    """Raised when durable state does not permit a requested command."""


@dataclass(frozen=True)
class CommandResult:
    job: dict[str, Any]
    applied: bool


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
                persisted = json.loads(existing["create_request_json"])
                incoming = request.model_dump(mode="json")
                if self._canonical_json(persisted) != self._canonical_json(incoming):
                    raise JobConflictError(
                        "idempotency key was already used for a different job request"
                    )
                return rowdict(existing)

            job_id = str(uuid4())
            timestamp = utcnow()
            connection.execute(
                """
                INSERT INTO jobs(
                    id, project_id, input_path, input_type, mode, status,
                    settings_json, create_request_json, idempotency_key,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    request.project_id,
                    request.input_path,
                    request.input_type,
                    request.mode,
                    "queued",
                    request.model_dump_json(),
                    self._canonical_json(request.model_dump(mode="json")),
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
            job.pop("create_request_json", None)
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

    def request_state(
        self,
        job_id: str,
        desired: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return self._request_state(job_id, desired, idempotency_key).job

    def cancel_job(
        self, job_id: str, idempotency_key: str | None = None
    ) -> CommandResult:
        return self._request_state(job_id, "cancelled", idempotency_key)

    def _request_state(
        self,
        job_id: str,
        desired: str,
        idempotency_key: str | None,
    ) -> CommandResult:
        if desired not in {"paused", "cancelled"}:
            raise ValueError("unsupported desired state")
        with self.database.transaction() as connection:
            job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if job is None:
                raise JobNotFoundError(f"job {job_id!r} does not exist")
            action = "pause" if desired == "paused" else "cancel"
            if not self._register_command(
                connection, job_id, action, {}, idempotency_key
            ):
                return CommandResult(
                    self._job_with_steps(connection, job), False
                )
            timestamp = utcnow()
            if desired == "paused":
                if job["status"] in {
                    "completed", "cancelled", "failed", "waiting_review"
                }:
                    raise JobConflictError("job cannot be paused from its current state")
                if (
                    job["status"] == "running"
                    and job["desired_state"] == "paused"
                ) or (
                    job["status"] == "paused"
                    and job["desired_state"] == "paused"
                ):
                    return CommandResult(
                        self._job_with_steps(connection, job), False
                    )
                if job["status"] == "running":
                    connection.execute(
                        """
                        UPDATE jobs SET desired_state='paused',
                            message='当前步骤完成后暂停', updated_at=?
                        WHERE id=?
                        """,
                        (timestamp, job_id),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE jobs SET status='paused', desired_state='paused',
                            message='已暂停', run_after=NULL, worker_id=NULL,
                            lease_until=NULL, updated_at=?
                        WHERE id=?
                        """,
                        (timestamp, job_id),
                    )
                self._append_event(connection, job_id, "job.pause", {})
            else:
                if job["status"] == "completed":
                    raise JobConflictError("completed job cannot be cancelled")
                if job["status"] == "cancelled":
                    return CommandResult(
                        self._job_with_steps(connection, job), False
                    )
                connection.execute(
                    """
                    UPDATE job_steps
                    SET status='cancelled', finished_at=?
                    WHERE job_id=? AND status NOT IN ('completed', 'cancelled')
                    """,
                    (timestamp, job_id),
                )
                connection.execute(
                    """
                    UPDATE jobs SET status='cancelled', desired_state='cancelled',
                        message='已取消', run_after=NULL, worker_id=NULL,
                        lease_until=NULL, finished_at=?, updated_at=?
                    WHERE id=?
                    """,
                    (timestamp, timestamp, job_id),
                )
                self._append_event(connection, job_id, "job.cancel", {})
            return CommandResult(
                self._job_in_transaction(connection, job_id), True
            )

    def resume_job(
        self, job_id: str, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        with self.database.transaction() as connection:
            job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if job is None:
                raise JobNotFoundError(f"job {job_id!r} does not exist")
            if not self._register_command(
                connection, job_id, "resume", {}, idempotency_key
            ):
                return self._job_with_steps(connection, job)
            timestamp = utcnow()
            if job["status"] == "running" and job["desired_state"] == "paused":
                connection.execute(
                    """
                    UPDATE jobs SET desired_state='running', message='继续执行',
                        updated_at=? WHERE id=?
                    """,
                    (timestamp, job_id),
                )
            elif job["status"] in {"paused", "failed", "retry_wait"}:
                connection.execute(
                    """
                    UPDATE job_steps
                    SET status='queued', error_code='', error_message='',
                        started_at=NULL, finished_at=NULL
                    WHERE job_id=? AND status IN ('failed', 'retry_wait')
                    """,
                    (job_id,),
                )
                connection.execute(
                    """
                    UPDATE jobs SET status='queued', desired_state='running',
                        message='继续执行', run_after=NULL, worker_id=NULL,
                        lease_until=NULL, finished_at=NULL, updated_at=?
                    WHERE id=?
                    """,
                    (timestamp, job_id),
                )
            else:
                raise JobConflictError("job is not resumable")
            self._append_event(connection, job_id, "job.resume", {})
            return self._job_in_transaction(connection, job_id)

    def retry_failed_step(
        self,
        job_id: str,
        step_id: str | None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        with self.database.transaction() as connection:
            job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if job is None:
                raise JobNotFoundError(f"job {job_id!r} does not exist")
            if not self._register_command(
                connection,
                job_id,
                "retry",
                {"step_id": step_id},
                idempotency_key,
            ):
                return self._job_with_steps(connection, job)
            if job["status"] != "failed":
                raise JobConflictError("job is not in a retryable state")
            if step_id is None:
                step = connection.execute(
                    """
                    SELECT id FROM job_steps
                    WHERE job_id=? AND status='failed'
                    ORDER BY sequence, shot_id, id LIMIT 1
                    """,
                    (job_id,),
                ).fetchone()
            else:
                step = connection.execute(
                    """
                    SELECT id FROM job_steps
                    WHERE id=? AND job_id=? AND status='failed'
                    """,
                    (step_id, job_id),
                ).fetchone()
            if step is None:
                raise JobConflictError("failed step not found")
            target = str(step["id"])
            self._reset_steps(connection, job_id, [target])
            timestamp = utcnow()
            connection.execute(
                """
                UPDATE jobs SET status='queued', desired_state='running',
                    message='从故障步骤继续', final_video='', run_after=NULL,
                    worker_id=NULL, lease_until=NULL, finished_at=NULL, updated_at=?
                WHERE id=?
                """,
                (timestamp, job_id),
            )
            self._append_event(
                connection, job_id, "job.retry", {"step_id": target}
            )
            self._recompute_job_summary(connection, job_id)
            return self._job_in_transaction(connection, job_id)

    def rollback_preview(self, job_id: str, step_id: str) -> list[str]:
        with self.database.connection() as connection:
            if connection.execute(
                "SELECT 1 FROM jobs WHERE id=?", (job_id,)
            ).fetchone() is None:
                raise JobNotFoundError(f"job {job_id!r} does not exist")
            return self._affected_step_ids(connection, job_id, step_id)

    def rollback_steps(
        self,
        job_id: str,
        step_id: str,
        confirmed: list[str],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        with self.database.transaction() as connection:
            job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if job is None:
                raise JobNotFoundError(f"job {job_id!r} does not exist")
            if not self._register_command(
                connection,
                job_id,
                "rollback",
                {"step_id": step_id, "confirmed": confirmed},
                idempotency_key,
            ):
                return self._job_with_steps(connection, job)
            if job["status"] not in {
                "failed", "paused", "waiting_review", "retry_wait"
            }:
                raise JobConflictError("job cannot be rolled back from its current state")
            affected = self._affected_step_ids(connection, job_id, step_id)
            if confirmed != affected:
                raise JobConflictError(
                    "rollback confirmation does not match affected steps"
                )
            self._reset_steps(connection, job_id, affected)
            timestamp = utcnow()
            connection.execute(
                """
                UPDATE jobs SET status='queued', desired_state='running',
                    message='已回退到指定步骤', final_video='', run_after=NULL,
                    worker_id=NULL, lease_until=NULL, finished_at=NULL, updated_at=?
                WHERE id=?
                """,
                (timestamp, job_id),
            )
            self._append_event(
                connection,
                job_id,
                "job.rollback",
                {"step_id": step_id, "affected_step_ids": affected},
            )
            self._recompute_job_summary(connection, job_id)
            return self._job_in_transaction(connection, job_id)

    def record_review(
        self,
        job_id: str,
        step_id: str,
        action: str,
        comment: str,
        patch: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if action == "rollback":
            raise JobConflictError(
                "use rollback preview and confirmation endpoint"
            )
        if action not in {"approve", "edit", "retry"}:
            raise JobConflictError("unsupported review action")
        with self.database.transaction() as connection:
            job = connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if job is None:
                raise JobNotFoundError(f"job {job_id!r} does not exist")
            if not self._register_command(
                connection,
                job_id,
                "review",
                {
                    "step_id": step_id,
                    "action": action,
                    "comment": comment,
                    "patch": patch,
                },
                idempotency_key,
            ):
                return self._job_with_steps(connection, job)
            if job["status"] != "waiting_review":
                raise JobConflictError("job is not waiting for review")
            step = connection.execute(
                "SELECT id, status FROM job_steps WHERE id=? AND job_id=?",
                (step_id, job_id),
            ).fetchone()
            if step is None:
                raise JobConflictError("review step does not belong to job")
            if step["status"] not in {"completed", "waiting_review"}:
                raise JobConflictError("step is not reviewable")

            if action == "edit":
                allowed = {"shot_duration", "width", "height", "fps", "options"}
                if set(patch) - allowed:
                    raise JobConflictError("review patch contains read-only fields")
                settings = json.loads(job["settings_json"])
                for key in allowed - {"options"}:
                    if key in patch:
                        settings[key] = patch[key]
                if "options" in patch:
                    if not isinstance(patch["options"], dict):
                        raise JobConflictError("options patch must be an object")
                    settings.setdefault("options", {}).update(patch["options"])
                try:
                    validated = JobCreate.model_validate(settings)
                except ValidationError as error:
                    raise JobConflictError("review patch is invalid") from error
                connection.execute(
                    "UPDATE jobs SET settings_json=? WHERE id=?",
                    (validated.model_dump_json(), job_id),
                )

            if action in {"edit", "retry"}:
                affected = self._affected_step_ids(connection, job_id, step_id)
                self._reset_steps(connection, job_id, affected)
            timestamp = utcnow()
            if action == "approve" and step["status"] == "waiting_review":
                connection.execute(
                    """
                    UPDATE job_steps SET status='completed', progress=1,
                        error_code='', error_message='', finished_at=?
                    WHERE id=? AND job_id=? AND status='waiting_review'
                    """,
                    (timestamp, step_id, job_id),
                )
            connection.execute(
                """
                INSERT INTO review_actions(
                    id, job_id, step_id, action, comment, patch_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    job_id,
                    step_id,
                    action,
                    comment,
                    json.dumps(patch, ensure_ascii=False, allow_nan=False),
                    timestamp,
                ),
            )
            has_active_step = connection.execute(
                """
                SELECT 1 FROM job_steps
                WHERE job_id=? AND status IN (
                    'pending', 'queued', 'running', 'waiting_review',
                    'retry_wait', 'failed'
                )
                LIMIT 1
                """,
                (job_id,),
            ).fetchone() is not None
            target_status = "queued" if has_active_step else "completed"
            connection.execute(
                """
                UPDATE jobs SET status=?, desired_state='running',
                    message='审核已处理',
                    final_video=CASE WHEN ?='approve' THEN final_video ELSE '' END,
                    run_after=NULL,
                    worker_id=NULL, lease_until=NULL,
                    finished_at=CASE WHEN ?='completed' THEN ? ELSE NULL END,
                    updated_at=?
                WHERE id=?
                """,
                (
                    target_status,
                    action,
                    target_status,
                    timestamp,
                    timestamp,
                    job_id,
                ),
            )
            self._append_event(
                connection,
                job_id,
                f"job.review.{action}",
                {"step_id": step_id},
            )
            self._recompute_job_summary(connection, job_id)
            return self._job_in_transaction(connection, job_id)

    @staticmethod
    def _register_command(
        connection: sqlite3.Connection,
        job_id: str,
        action: str,
        payload: dict[str, Any],
        idempotency_key: str | None,
    ) -> bool:
        if idempotency_key is None:
            return True
        serialized = JobRepository._canonical_json(payload)
        fingerprint = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        existing = connection.execute(
            """
            SELECT job_id, action, request_fingerprint
            FROM job_commands WHERE idempotency_key=?
            """,
            (idempotency_key,),
        ).fetchone()
        if existing is not None:
            if (
                existing["job_id"] == job_id
                and existing["action"] == action
                and existing["request_fingerprint"] == fingerprint
            ):
                return False
            raise JobConflictError(
                "idempotency key was already used for a different command"
            )
        connection.execute(
            """
            INSERT INTO job_commands(
                idempotency_key, job_id, action, request_fingerprint, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (idempotency_key, job_id, action, fingerprint, utcnow()),
        )
        return True

    @staticmethod
    def _canonical_json(value: Any) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    @classmethod
    def _job_in_transaction(
        cls, connection: sqlite3.Connection, job_id: str
    ) -> dict[str, Any]:
        row = connection.execute(
            "SELECT * FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise JobNotFoundError(f"job {job_id!r} does not exist")
        return cls._job_with_steps(connection, row)

    @staticmethod
    def _recompute_job_summary(
        connection: sqlite3.Connection, job_id: str
    ) -> None:
        rows = connection.execute(
            """
            SELECT stage_key, shot_id, status, progress
            FROM job_steps
            WHERE job_id=? AND status NOT IN ('invalidated', 'cancelled')
            ORDER BY
                CASE status WHEN 'running' THEN 0 ELSE 1 END,
                sequence, shot_id, id
            """,
            (job_id,),
        ).fetchall()
        active = next(
            (
                row
                for row in rows
                if row["status"]
                in {
                    "pending",
                    "queued",
                    "running",
                    "waiting_review",
                    "retry_wait",
                    "failed",
                }
            ),
            None,
        )
        progress = (
            sum(float(row["progress"]) for row in rows) / len(rows)
            if rows
            else 0.0
        )
        connection.execute(
            """
            UPDATE jobs SET progress=?, current_stage=?, current_shot=?
            WHERE id=?
            """,
            (
                progress,
                "" if active is None else active["stage_key"],
                "" if active is None else active["shot_id"],
                job_id,
            ),
        )

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        job_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO job_events(job_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                job_id,
                event_type,
                json.dumps(payload, ensure_ascii=False, allow_nan=False),
                utcnow(),
            ),
        )

    @staticmethod
    def _affected_step_ids(
        connection: sqlite3.Connection, job_id: str, step_id: str
    ) -> list[str]:
        selected = connection.execute(
            """
            SELECT id, sequence, shot_id FROM job_steps
            WHERE id=? AND job_id=?
            """,
            (step_id, job_id),
        ).fetchone()
        if selected is None:
            raise JobConflictError("step does not belong to job")
        rows = connection.execute(
            """
            SELECT id FROM job_steps
            WHERE job_id=? AND sequence>?
              AND (?='' OR shot_id=? OR shot_id='')
            ORDER BY sequence, shot_id, id
            """,
            (job_id, selected["sequence"], selected["shot_id"], selected["shot_id"]),
        ).fetchall()
        return [str(selected["id"]), *(str(row["id"]) for row in rows)]

    @staticmethod
    def _reset_steps(
        connection: sqlite3.Connection, job_id: str, step_ids: list[str]
    ) -> None:
        if not step_ids:
            return
        placeholders = ",".join("?" for _ in step_ids)
        parameters = (job_id, *step_ids)
        connection.execute(
            f"""
            UPDATE artifacts SET active=0
            WHERE job_id=? AND step_id IN ({placeholders})
            """,
            parameters,
        )
        connection.execute(
            f"""
            UPDATE job_steps SET status='queued', progress=0, input_hash='',
                error_code='', error_message='', started_at=NULL, finished_at=NULL
            WHERE job_id=? AND id IN ({placeholders})
            """,
            parameters,
        )

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

        with self.database.transaction() as connection:
            timestamp = utcnow()
            if expected_worker_id is not None:
                owned = connection.execute(
                    """
                    SELECT 1 FROM jobs
                    WHERE id = ? AND status = 'running' AND worker_id = ?
                      AND lease_until IS NOT NULL AND lease_until > ?
                    """,
                    (job_id, expected_worker_id, timestamp),
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
        if lease_until <= now:
            raise ValueError("lease_until must be after now")
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
        if lease_until <= now:
            return False
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
                WHERE status = 'running'
                  AND (lease_until IS NULL OR lease_until <= ?)
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
                UPDATE job_steps
                SET status = 'cancelled', finished_at = ?
                WHERE job_id IN (
                    SELECT id FROM jobs
                    WHERE id IN ({placeholders}) AND desired_state = 'cancelled'
                ) AND status NOT IN ('completed', 'cancelled')
                """,
                (now, *job_ids),
            )
            connection.execute(
                f"""
                UPDATE jobs
                SET status = CASE desired_state
                        WHEN 'cancelled' THEN 'cancelled'
                        WHEN 'paused' THEN 'paused'
                        ELSE 'queued'
                    END,
                    worker_id = NULL, lease_until = NULL, run_after = NULL,
                    message = CASE desired_state
                        WHEN 'cancelled' THEN '已从中断状态恢复并取消'
                        WHEN 'paused' THEN '已从中断检查点恢复并暂停'
                        ELSE '已从中断的检查点恢复'
                    END,
                    finished_at = CASE
                        WHEN desired_state = 'cancelled' THEN ?
                        ELSE NULL
                    END,
                    updated_at = ?
                WHERE id IN ({placeholders}) AND status = 'running'
                """,
                (now, now, *job_ids),
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
            timestamp = utcnow()
            job = connection.execute(
                """
                SELECT desired_state FROM jobs
                WHERE id = ? AND status = 'running' AND worker_id = ?
                  AND lease_until IS NOT NULL AND lease_until > ?
                """,
                (job_id, worker_id, timestamp),
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
                SET attempt = ?, status = ?, error_code = ?, error_message = ?,
                    started_at = CASE
                        WHEN ? = 'retry_wait' THEN NULL ELSE started_at
                    END,
                    finished_at = CASE
                        WHEN ? = 'failed' THEN ? ELSE NULL
                    END
                WHERE id = ? AND job_id = ?
                """,
                (
                    attempt,
                    step_status,
                    code,
                    message,
                    step_status,
                    step_status,
                    timestamp,
                    step_id,
                    job_id,
                ),
            )
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, message = ?, run_after = ?, worker_id = NULL,
                    lease_until = NULL,
                    finished_at = CASE WHEN ? = 'failed' THEN ? ELSE NULL END,
                    updated_at = ?
                WHERE id = ? AND status = 'running' AND worker_id = ?
                """,
                (
                    job_status,
                    message,
                    effective_retry_at,
                    job_status,
                    timestamp,
                    timestamp,
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
            timestamp = utcnow()
            job = connection.execute(
                """
                SELECT mode, desired_state FROM jobs
                WHERE id = ? AND status = 'running' AND worker_id = ?
                  AND lease_until IS NOT NULL AND lease_until > ?
                """,
                (job_id, worker_id, timestamp),
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
                    (timestamp, job_id),
                )
            elif job["desired_state"] == "paused":
                target = "paused"
            elif job["mode"] == "manual_review":
                target = "waiting_review"
            else:
                target = "queued"
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

    def ensure_bootstrap_step(
        self,
        job_id: str,
        expected_worker_id: str | None = None,
    ) -> str:
        with self.database.transaction() as connection:
            timestamp = utcnow()
            exists = connection.execute(
                "SELECT 1 FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if exists is None:
                raise LookupError(f"job {job_id!r} does not exist")
            if expected_worker_id is not None:
                owned = connection.execute(
                    """
                    SELECT 1 FROM jobs
                    WHERE id = ? AND status = 'running' AND worker_id = ?
                      AND lease_until IS NOT NULL AND lease_until > ?
                    """,
                    (job_id, expected_worker_id, timestamp),
                ).fetchone()
                if owned is None:
                    raise LeaseOwnershipError(
                        f"worker {expected_worker_id!r} no longer owns job {job_id!r}"
                    )
            rows = connection.execute(
                """
                SELECT id, status FROM job_steps
                WHERE job_id = ?
                ORDER BY sequence ASC, shot_id ASC, id ASC
                """,
                (job_id,),
            ).fetchall()
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
        job.pop("create_request_json", None)
        step_rows = connection.execute(
            """
            SELECT * FROM job_steps
            WHERE job_id = ?
            ORDER BY sequence ASC, shot_id ASC
            """,
            (job["id"],),
        ).fetchall()
        steps = [rowdict(row) for row in step_rows]
        steps_by_id = {step["id"]: step for step in steps}
        for step in steps:
            step["artifacts"] = []
        artifact_rows = connection.execute(
            """
            SELECT step_id, kind, path, metadata_json
            FROM artifacts
            WHERE job_id=? AND active=1
            ORDER BY step_id, path, kind, id
            """,
            (job["id"],),
        ).fetchall()
        for artifact in artifact_rows:
            step = steps_by_id.get(artifact["step_id"])
            if step is None:
                continue
            step["artifacts"].append(
                {
                    "kind": artifact["kind"],
                    "path": artifact["path"],
                    "metadata": json.loads(artifact["metadata_json"]),
                }
            )
        job["steps"] = steps
        return job

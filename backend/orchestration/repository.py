from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.orchestration.automation import EXECUTION_TO_UI_STAGE
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.enums import JobStatus, StepStatus, JOB_TERMINAL
from backend.orchestration.schemas import JobCreate, JobSettings


class ReviewTransitionConflict(ValueError):
    """The review target changed before the requested transition could commit."""


class ReviewJobNotFound(ValueError):
    """The job disappeared before an atomic review transition began."""


class JobRepository:
    def __init__(self, db: OrchestrationDatabase, projects_root: str | Path = "projects"):
        self.db = db
        self.projects_root = Path(projects_root)

    # ── write ──────────────────────────────────────────────────

    def create_job(self, data: JobCreate, settings: JobSettings) -> str:
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO jobs (id, project_id, status, mode, desired_state,
                   input_path, input_type, settings, idempotency_key, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id,
                    data.project_id,
                    JobStatus.DRAFT,
                    data.mode,
                    "running",
                    data.input_path,
                    data.input_type,
                    settings.model_dump_json(),
                    data.idempotency_key,
                    _now_iso(),
                    _now_iso(),
                ),
            )
        return job_id

    def create_steps(self, job_id: str, stage_plan: list[dict[str, str]]) -> None:
        with self.db.transaction() as conn:
            for seq, s in enumerate(stage_plan):
                step_id = f"step-{uuid.uuid4().hex[:8]}"
                conn.execute(
                    """INSERT INTO job_steps
                       (id, job_id, sequence, stage_key, shot_id, status, ui_stage_key)
                       VALUES (?,?,?,?,?,?,?)""",
                    (
                        step_id,
                        job_id,
                        seq,
                        s["stage_key"],
                        s.get("shot_id", ""),
                        StepStatus.PENDING,
                        EXECUTION_TO_UI_STAGE.get(s["stage_key"], ""),
                    ),
                )

    def set_job_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        message: str = "",
        final_video: str = "",
        allowed_from: set[JobStatus] | None = None,
    ) -> bool:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                return False
            current = JobStatus(row["status"])
            if allowed_from is not None and current not in allowed_from:
                return False
            fields = ["status=?", "updated_at=?"]
            params: list[Any] = [status, _now_iso()]
            if message:
                fields.append("message=?")
                params.append(message)
            if final_video:
                fields.append("final_video=?")
                params.append(final_video)
            if status in JOB_TERMINAL:
                fields.append("finished_at=?")
                params.append(_now_iso())
            params.append(job_id)
            conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id=?", params)
        return True

    def increment_quality_attempt(self, step_id: str) -> int:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE job_steps SET quality_attempt = quality_attempt + 1 WHERE id=?",
                (step_id,),
            )
            row = conn.execute(
                "SELECT quality_attempt FROM job_steps WHERE id=?", (step_id,)
            ).fetchone()
        if not row:
            raise ValueError(f"Step not found: {step_id}")
        return row["quality_attempt"]

    def save_quality_report(self, step_id: str, report: dict[str, object]) -> None:
        serialized = json.dumps(report, ensure_ascii=False)
        passed = report.get("passed")
        quality_status = "passed" if passed is True else "failed" if passed is False else "unreviewed"
        with self.db.transaction(immediate=True) as conn:
            step = conn.execute(
                "SELECT quality_attempt FROM job_steps WHERE id=?", (step_id,)
            ).fetchone()
            if step is None:
                raise ValueError(f"Step not found: {step_id}")
            conn.execute(
                "UPDATE job_steps SET quality_report=? WHERE id=?",
                (serialized, step_id),
            )
            artifact = conn.execute(
                """SELECT id FROM artifacts
                   WHERE step_id=? AND active=1
                   ORDER BY version DESC, id DESC LIMIT 1""",
                (step_id,),
            ).fetchone()
            if artifact is not None:
                conn.execute(
                    """UPDATE artifacts
                       SET quality_report=?, quality_attempt=?, quality_status=?
                       WHERE id=?""",
                    (serialized, step["quality_attempt"], quality_status, artifact["id"]),
                )

    def transition_review(
        self,
        job_id: str,
        action: str,
        *,
        expected_step_id: str | None = None,
        expected_project_id: str | None = None,
        expected_asset_id: int | None = None,
    ) -> str:
        with self.db.transaction(immediate=True) as conn:
            job = conn.execute(
                "SELECT project_id, status FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if job is None:
                raise ReviewJobNotFound(f"Job not found: {job_id}")
            if expected_project_id is not None and job["project_id"] != expected_project_id:
                raise ReviewTransitionConflict("review project changed")
            if job["status"] != JobStatus.WAITING_REVIEW.value:
                raise ReviewTransitionConflict("job is not in review")

            waiting_steps = conn.execute(
                """SELECT id, sequence FROM job_steps
                   WHERE job_id=? AND status=? ORDER BY sequence""",
                (job_id, StepStatus.WAITING_REVIEW.value),
            ).fetchall()
            if len(waiting_steps) != 1:
                raise ReviewTransitionConflict("review step is not unique")
            step = waiting_steps[0]
            if expected_step_id is not None and step["id"] != expected_step_id:
                raise ReviewTransitionConflict("review step changed")

            if expected_asset_id is not None:
                asset = conn.execute(
                    """SELECT id FROM artifacts
                       WHERE id=? AND project_id=? AND job_id=? AND step_id=? AND active=1""",
                    (expected_asset_id, job["project_id"], job_id, step["id"]),
                ).fetchone()
                if asset is None:
                    raise ReviewTransitionConflict("review asset changed")

            if action in {"approve", "edit"}:
                cursor = conn.execute(
                    """UPDATE job_steps SET status=?, finished_at=?
                       WHERE id=? AND job_id=? AND status=?""",
                    (
                        StepStatus.COMPLETED.value,
                        _now_iso(),
                        step["id"],
                        job_id,
                        StepStatus.WAITING_REVIEW.value,
                    ),
                )
            elif action in {"retry", "rollback"}:
                cursor = conn.execute(
                    """UPDATE job_steps SET status=?
                       WHERE id=? AND job_id=? AND status=?""",
                    (
                        StepStatus.QUEUED.value,
                        step["id"],
                        job_id,
                        StepStatus.WAITING_REVIEW.value,
                    ),
                )
                if action == "rollback":
                    conn.execute(
                        """UPDATE job_steps SET status=?
                           WHERE job_id=? AND sequence>? AND status IN (?,?,?)""",
                        (
                            StepStatus.INVALIDATED.value,
                            job_id,
                            step["sequence"],
                            StepStatus.COMPLETED.value,
                            StepStatus.QUEUED.value,
                            StepStatus.RUNNING.value,
                        ),
                    )
            else:
                raise ValueError(f"Unknown review action: {action}")
            if cursor.rowcount != 1:
                raise ReviewTransitionConflict("review step changed")

            cursor = conn.execute(
                """UPDATE jobs SET status=?, updated_at=?
                   WHERE id=? AND status=?""",
                (
                    JobStatus.QUEUED.value,
                    _now_iso(),
                    job_id,
                    JobStatus.WAITING_REVIEW.value,
                ),
            )
            if cursor.rowcount != 1:
                raise ReviewTransitionConflict("review job changed")
        return str(step["id"])

    def set_job_progress(self, job_id: str, stage: str, shot: str, progress: float, message: str = "") -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jobs SET current_stage=?, current_shot=?, progress=?, message=?, updated_at=? WHERE id=?",
                (stage, shot, progress, message, _now_iso(), job_id),
            )

    def update_step_progress(self, step_id: str, progress: float) -> None:
        """Update progress for a specific step without changing its status."""
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE job_steps SET progress=? WHERE id=?",
                (progress, step_id),
            )

    def complete_step(self, step_id: str) -> bool:
        """Mark a step as completed and set progress to 1.0."""
        with self.db.transaction() as conn:
            row = conn.execute("SELECT status FROM job_steps WHERE id=?", (step_id,)).fetchone()
            if not row:
                return False
            current = StepStatus(row["status"])
            # Allow transition from RUNNING or QUEUED to COMPLETED
            if current not in (StepStatus.RUNNING, StepStatus.QUEUED, StepStatus.PENDING):
                return False
            conn.execute(
                "UPDATE job_steps SET status=?, progress=?, finished_at=? WHERE id=?",
                (StepStatus.COMPLETED, 1.0, _now_iso(), step_id),
            )
        return True

    def start_step(self, step_id: str) -> bool:
        """Mark a step as running."""
        with self.db.transaction() as conn:
            row = conn.execute("SELECT status FROM job_steps WHERE id=?", (step_id,)).fetchone()
            if not row:
                return False
            current = StepStatus(row["status"])
            if current == StepStatus.COMPLETED:
                return True  # Already done
            conn.execute(
                "UPDATE job_steps SET status=?, started_at=? WHERE id=?",
                (StepStatus.RUNNING, _now_iso(), step_id),
            )
        return True

    def acquire_lease(self, job_id: str, lease_id: str, lease_seconds: int) -> bool:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT status, lease_expires_at FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row or row["status"] not in (JobStatus.QUEUED, JobStatus.RETRY_WAIT):
                return False
            now = _now_iso()
            if row["lease_expires_at"] and row["lease_expires_at"] > now:
                return False
            conn.execute(
                "UPDATE jobs SET status=?, lease_id=?, lease_expires_at=?, updated_at=? WHERE id=?",
                (JobStatus.RUNNING, lease_id, _iso_dt(datetime.now(timezone.utc), lease_seconds), now, job_id),
            )
        return True

    def release_lease(self, job_id: str) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jobs SET lease_id=NULL, lease_expires_at=NULL, updated_at=? WHERE id=?",
                (_now_iso(), job_id),
            )

    def set_step_status(
        self,
        step_id: str,
        status: StepStatus,
        *,
        error_code: str = "",
        error_message: str = "",
        progress: float = 0.0,
        increment_attempt: bool = False,
        allowed_from: set[StepStatus] | None = None,
    ) -> bool:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT status FROM job_steps WHERE id=?", (step_id,)).fetchone()
            if not row:
                return False
            current = StepStatus(row["status"])
            if allowed_from is not None and current not in allowed_from:
                return False
            updates = ["status=?"]
            params: list[Any] = [status]
            if status == StepStatus.RUNNING:
                updates.append("started_at=?")
                params.append(_now_iso())
            if status in (StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.CANCELLED):
                updates.append("finished_at=?")
                params.append(_now_iso())
                updates.append("error_code=?")
                params.append(error_code)
                updates.append("error_message=?")
                params.append(error_message)
            if increment_attempt:
                updates.append("attempt = attempt + 1")
            if progress > 0:
                updates.append("progress=?")
                params.append(progress)
            params.append(step_id)
            conn.execute(f"UPDATE job_steps SET {', '.join(updates)} WHERE id=?", params)
        return True

    def invalidate_steps(self, job_id: str, step_ids: list[str]) -> None:
        with self.db.transaction() as conn:
            for sid in step_ids:
                conn.execute("UPDATE job_steps SET status=? WHERE id=? AND job_id=?", (StepStatus.INVALIDATED, sid, job_id))

    # ── read ───────────────────────────────────────────────────

    def get_job(self, job_id: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            return dict(row) if row else None

    def list_jobs(self, project_id: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
        with self.db.connect() as conn:
            if project_id:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (project_id, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
                ).fetchall()
            return [dict(r) for r in rows]

    def list_queued_jobs(self, limit: int = 5) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT * FROM jobs
                   WHERE status IN ('queued','retry_wait')
                     AND (lease_expires_at IS NULL OR lease_expires_at < datetime('now'))
                   ORDER BY created_at
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_expired_leases(self, now: str) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status='running' AND lease_expires_at < ?",
                (now,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_job_steps(self, job_id: str) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM job_steps WHERE job_id=? ORDER BY sequence", (job_id,)
            ).fetchall()
            return [_step_dict(r) for r in rows]

    def get_step(self, step_id: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM job_steps WHERE id=?", (step_id,)).fetchone()
            return _step_dict(row) if row else None

    def get_artifacts(self, job_id: str) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM artifacts WHERE job_id=? AND active=1 ORDER BY id", (job_id,)
            ).fetchall()
            return [_artifact_dict(r) for r in rows]

    def get_idempotent(self, idempotency_key: str) -> dict | None:
        if not idempotency_key:
            return None
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            return dict(row) if row else None

    def add_artifact(self, job_id: str, step_id: str, kind: str, path: str, sha256: str, metadata: dict) -> None:
        with self.db.transaction(immediate=True) as conn:
            job = conn.execute("SELECT project_id FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job:
                raise ValueError(f"Job not found: {job_id}")
            step = conn.execute(
                "SELECT id, stage_key, shot_id, ui_stage_key FROM job_steps WHERE id=? AND job_id=?",
                (step_id, job_id),
            ).fetchone()
            if not step:
                step = conn.execute(
                    """SELECT id, stage_key, shot_id, ui_stage_key FROM job_steps
                       WHERE job_id=? AND (stage_key=? OR shot_id=?) ORDER BY sequence LIMIT 1""",
                    (job_id, step_id, step_id),
                ).fetchone()
            if not step:
                raise ValueError(f"Step not found: {step_id}")
            execution_stage = step["stage_key"]
            stage_key = step["ui_stage_key"] or EXECUTION_TO_UI_STAGE.get(
                execution_stage, execution_stage
            )
            stage_key = str(stage_key)
            shot_id = step["shot_id"]
            asset_metadata = dict(metadata)
            if execution_stage.startswith("audio_"):
                asset_metadata.setdefault("subtype", execution_stage.removeprefix("audio_"))
            scene_id = str(asset_metadata.get("scene_id", ""))
            subtype = str(asset_metadata.get("subtype", ""))
            lineage = (job["project_id"], kind, stage_key, scene_id, shot_id, subtype)
            subtype_sql = (
                "COALESCE(CASE WHEN json_valid(metadata) "
                "THEN json_extract(metadata, '$.subtype') END, '')"
            )
            previous = conn.execute(
                f"""SELECT id, version FROM artifacts
                    WHERE project_id=? AND kind=? AND stage_key=? AND scene_id=? AND shot_id=?
                      AND {subtype_sql}=? AND active=1
                    ORDER BY version DESC, id DESC LIMIT 1""",
                lineage,
            ).fetchone()
            if previous:
                version = int(previous["version"]) + 1
                parent_artifact_id = int(previous["id"])
            else:
                row = conn.execute(
                    f"""SELECT COALESCE(MAX(version), 0) AS max_version FROM artifacts
                        WHERE project_id=? AND kind=? AND stage_key=? AND scene_id=? AND shot_id=?
                          AND {subtype_sql}=?""",
                    lineage,
                ).fetchone()
                version = int(row["max_version"]) + 1
                parent_artifact_id = None
            conn.execute(
                f"""UPDATE artifacts SET active=0
                    WHERE project_id=? AND kind=? AND stage_key=? AND scene_id=? AND shot_id=?
                      AND {subtype_sql}=? AND active=1""",
                lineage,
            )
            conn.execute(
                """INSERT INTO artifacts
                   (job_id, step_id, kind, path, sha256, metadata, project_id, version,
                    parent_artifact_id, stage_key, scene_id, shot_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id,
                    step["id"],
                    kind,
                    self._normalize_artifact_path(job["project_id"], path),
                    sha256,
                    json.dumps(asset_metadata, ensure_ascii=False),
                    job["project_id"],
                    version,
                    parent_artifact_id,
                    stage_key,
                    scene_id,
                    shot_id,
                ),
            )

    def _normalize_artifact_path(self, project_id: str, value: str) -> str:
        raw_path = Path(value)
        project_root = (self.projects_root / project_id).resolve()
        if raw_path.is_absolute():
            candidate = raw_path.resolve()
        else:
            direct_candidate = raw_path.resolve()
            if _is_within(direct_candidate, project_root):
                candidate = direct_candidate
            else:
                parts = raw_path.parts
                if (
                    len(parts) >= 2
                    and parts[0].casefold() == self.projects_root.name.casefold()
                    and parts[1].casefold() == project_id.casefold()
                ):
                    candidate = (project_root.joinpath(*parts[2:])).resolve()
                else:
                    candidate = (project_root / raw_path).resolve()
        if _is_within(candidate, project_root):
            return candidate.relative_to(project_root).as_posix()
        return str(candidate) if raw_path.is_absolute() else raw_path.as_posix()

    def get_checkpoint(self, job_id: str, stage_key: str, shot_id: str = "") -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM checkpoints WHERE job_id=? AND stage_key=? AND shot_id=?",
                (job_id, stage_key, shot_id),
            ).fetchone()
            return dict(row) if row else None

    def save_checkpoint(self, job_id: str, step_id: str, stage_key: str, shot_id: str, input_hash: str) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO checkpoints (job_id, step_id, stage_key, shot_id, input_hash, status, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (job_id, step_id, stage_key, shot_id, input_hash, "completed", _now_iso()),
            )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iso_dt(dt: datetime, offset_seconds: int) -> str:
    from datetime import timedelta

    return (dt + timedelta(seconds=offset_seconds)).isoformat(timespec="seconds")


def _step_dict(row: Any) -> dict:
    value = dict(row)
    try:
        value["quality_report"] = json.loads(value.get("quality_report") or "{}")
    except (TypeError, json.JSONDecodeError):
        value["quality_report"] = {}
    return value


def _artifact_dict(row: Any) -> dict:
    value = dict(row)
    try:
        metadata = json.loads(value.get("metadata") or "{}")
        value["metadata"] = metadata if isinstance(metadata, dict) else {}
    except (TypeError, json.JSONDecodeError):
        value["metadata"] = {}
    return value


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False

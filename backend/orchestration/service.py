from __future__ import annotations

import json
import hashlib
import uuid
from pathlib import Path
from typing import Any

from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.enums import (
    JobStatus,
    StepStatus,
    JobCommand,
    STATUS_TRANSITIONS,
    STEP_TRANSITIONS,
    JOB_TERMINAL,
    STEP_INCOMPLETE,
)
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import (
    JobCreate,
    JobSettings,
    JobOptions,
    JobSummary,
    JobDetail,
    StepInfo,
    ArtifactInfo,
    RetryRequest,
    ReviewRequest,
    JobCommandRequest,
    StageExecutionRequest,
    RollbackPreview,
    JobListResponse,
)
from backend.orchestration.worker import SSEBroadcaster

# Default shot count for pre-created stages.
# The planning stage may produce fewer shots; executor skips non-existent ones.
DEFAULT_MAX_SHOTS = 20

SHOT_SCOPED_EXECUTION_STAGES = frozenset({"visual_generate", "hd_redraw", "video_generate"})
STAGE_EXECUTION_ALLOWED_JOB_STATES = frozenset({
    JobStatus.PAUSED,
    JobStatus.FAILED,
    JobStatus.RETRY_WAIT,
    JobStatus.COMPLETED,
})


class StageExecutionConflict(ValueError):
    """The requested canvas stage cannot be executed from the current Job state."""


class StageExecutionTargetNotFound(ValueError):
    """The requested canonical stage/shot does not resolve to exactly one Job step."""


def build_production_stages(
    max_shots: int = DEFAULT_MAX_SHOTS,
    *,
    shot_ids: list[str] | None = None,
) -> list[dict[str, str]]:
    """Build the canonical production stage list.

    Following the Krene tutorial 5-step workflow:
      Step 1: Novel input → load_input
      Step 2: AI Script → planning (includes script generation)
      Step 3: Character Design → character_design
      Step 4: Storyboard → visual_generate + hd_redraw (per shot)
      Step 5: Video Generation → video_generate (per shot)
      Final: Audio + Composition + Export

    Args:
        max_shots: Maximum number of shots to pre-create stages for.
        shot_ids: Actual shot identifiers from a production plan. When
            provided, only these shots are expanded.

    Returns:
        List of stage dicts with 'stage_key' and 'shot_id' keys.
    """
    stages: list[dict[str, str]] = [
        {"stage_key": "load_input", "shot_id": ""},
        {"stage_key": "planning", "shot_id": ""},
        {"stage_key": "character_design", "shot_id": ""},
    ]

    planned_shots = shot_ids or [f"shot_{i:03d}" for i in range(1, max_shots + 1)]

    for shot_id in planned_shots:
        stages.append({"stage_key": "visual_generate", "shot_id": shot_id})
        stages.append({"stage_key": "hd_redraw", "shot_id": shot_id})
        stages.append({"stage_key": "video_generate", "shot_id": shot_id})

    stages.extend([
        {"stage_key": "audio_tts", "shot_id": ""},
        {"stage_key": "audio_sfx", "shot_id": ""},
        {"stage_key": "composition_compose", "shot_id": ""},
        {"stage_key": "export", "shot_id": ""},
    ])

    return stages


# Canonical production stages (backward-compatible default)
PRODUCTION_STAGES = build_production_stages()


class JobService:
    def __init__(
        self,
        db: OrchestrationDatabase,
        repo: JobRepository,
        broadcaster: SSEBroadcaster,
        config: OrchestrationConfig,
    ):
        self.db = db
        self.repo = repo
        self.broadcaster = broadcaster
        self.config = config

    # ── Create ─────────────────────────────────────────────────

    def create(self, data: JobCreate) -> JobDetail:
        existing = self.repo.get_idempotent(data.idempotency_key)
        if existing:
            return self._build_detail(existing["id"])

        settings = JobSettings(
            width=data.width,
            height=data.height,
            fps=data.fps,
            shot_duration=data.shot_duration,
            options=JobOptions(**data.options) if data.options else JobOptions(),
        )
        job_id = self.repo.create_job(data, settings)
        self.repo.create_steps(job_id, self._stage_plan_for_job(data, settings))
        self.repo.set_job_status(job_id, JobStatus.QUEUED, allowed_from={JobStatus.DRAFT})
        self.broadcaster.broadcast(job_id, "job_created", {"job_id": job_id, "status": JobStatus.QUEUED})
        return self._build_detail(job_id)

    def get_job(self, job_id: str) -> JobDetail | None:
        return self._build_detail(job_id) if self.repo.get_job(job_id) else None

    def list_jobs(self, project_id: str | None = None, limit: int = 50, offset: int = 0) -> JobListResponse:
        rows = self.repo.list_jobs(project_id=project_id, limit=limit, offset=offset)
        items = [_to_summary(r) for r in rows]
        return JobListResponse(items=items)

    # ── Commands ───────────────────────────────────────────────

    def pause(self, job_id: str) -> JobDetail:
        job = self._require_job(job_id)
        self.repo.set_job_status(job_id, JobStatus.PAUSED, allowed_from={JobStatus.RUNNING, JobStatus.WAITING_REVIEW})
        self.broadcaster.broadcast(job_id, "paused", {"job_id": job_id})
        return self._build_detail(job_id)

    def resume(self, job_id: str) -> JobDetail:
        job = self._require_job(job_id)
        self.repo.set_job_status(job_id, JobStatus.QUEUED, allowed_from={JobStatus.PAUSED})
        self.broadcaster.broadcast(job_id, "resumed", {"job_id": job_id, "status": JobStatus.QUEUED})
        return self._build_detail(job_id)

    def retry(self, job_id: str, step_id: str | None = None) -> JobDetail:
        job = self._require_job(job_id)
        current = JobStatus(job["status"])
        if current == JobStatus.FAILED:
            target_step_id = step_id or self._find_failed_step_id(job_id)
            if target_step_id:
                self.repo.set_step_status(
                    target_step_id, StepStatus.QUEUED,
                    allowed_from={StepStatus.FAILED, StepStatus.PENDING},
                )
            self.repo.set_job_status(job_id, JobStatus.QUEUED, allowed_from={JobStatus.FAILED})
            self.broadcaster.broadcast(job_id, "retry", {"job_id": job_id, "step_id": target_step_id})
        elif current == JobStatus.WAITING_REVIEW:
            step = self._find_review_step(job_id)
            if step:
                self.repo.set_step_status(
                    step["id"], StepStatus.QUEUED,
                    allowed_from={StepStatus.WAITING_REVIEW},
                )
            self.repo.set_job_status(job_id, JobStatus.QUEUED, allowed_from={JobStatus.WAITING_REVIEW})
        return self._build_detail(job_id)

    def execute_from_stage(self, job_id: str, request: StageExecutionRequest) -> JobDetail:
        """Rewind the existing production Job to one validated canonical boundary.

        This command deliberately does not create a new Job or call a provider.  It
        only mutates orchestration state so the existing worker can execute the
        requested target.  ``continue`` reopens dependency-scoped downstream work;
        ``rerun_node`` leaves downstream work invalidated and uses ``desired_state``
        as a one-shot worker stop boundary after the target completes.
        """
        requested_stage = request.stage_key.strip()
        requested_shot = request.shot_id.strip()
        if requested_stage in SHOT_SCOPED_EXECUTION_STAGES and not requested_shot:
            raise StageExecutionConflict(f"stage {requested_stage} requires shot_id")
        if requested_stage not in SHOT_SCOPED_EXECUTION_STAGES and requested_shot:
            raise StageExecutionConflict(f"stage {requested_stage} does not accept shot_id")

        with self.db.transaction(immediate=True) as conn:
            job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if job is None:
                raise StageExecutionTargetNotFound(f"Job not found: {job_id}")
            current = JobStatus(job["status"])
            if current not in STAGE_EXECUTION_ALLOWED_JOB_STATES:
                raise StageExecutionConflict(f"job state {current.value} cannot execute from stage")

            rows = conn.execute(
                "SELECT * FROM job_steps WHERE job_id=? ORDER BY sequence", (job_id,)
            ).fetchall()
            matches = [
                row for row in rows
                if row["stage_key"] == requested_stage and (row["shot_id"] or "") == requested_shot
            ]
            if len(matches) != 1:
                raise StageExecutionTargetNotFound(
                    f"stage target must resolve exactly once: {requested_stage}/{requested_shot}"
                )
            target = matches[0]

            downstream = [
                row for row in rows
                if row["sequence"] > target["sequence"]
                and (
                    not requested_shot
                    or (row["shot_id"] or "") in {requested_shot, ""}
                )
            ]
            affected_step_ids = [target["id"], *[row["id"] for row in downstream]]

            target_cursor = conn.execute(
                """UPDATE job_steps
                   SET status=?, progress=0.0, error_code='', error_message='',
                       quality_attempt=0, quality_report='{}', started_at=NULL, finished_at=NULL
                   WHERE id=? AND job_id=?""",
                (StepStatus.QUEUED.value, target["id"], job_id),
            )
            if target_cursor.rowcount != 1:
                raise StageExecutionConflict("stage target changed before rewind")

            downstream_status = (
                StepStatus.PENDING.value
                if request.mode == "continue"
                else StepStatus.INVALIDATED.value
            )
            for row in downstream:
                conn.execute(
                    """UPDATE job_steps
                       SET status=?, progress=0.0, error_code='', error_message='',
                           quality_attempt=0, quality_report='{}', started_at=NULL, finished_at=NULL
                       WHERE id=? AND job_id=?""",
                    (downstream_status, row["id"], job_id),
                )

            placeholders = ",".join("?" for _ in affected_step_ids)
            if affected_step_ids:
                conn.execute(
                    f"UPDATE artifacts SET active=0 WHERE job_id=? AND step_id IN ({placeholders}) AND active=1",
                    (job_id, *affected_step_ids),
                )
                conn.execute(
                    f"DELETE FROM checkpoints WHERE job_id=? AND step_id IN ({placeholders})",
                    (job_id, *affected_step_ids),
                )

            desired_state = (
                "running"
                if request.mode == "continue"
                else f"pause_after_step:{target['id']}"
            )
            conn.execute(
                """UPDATE jobs
                   SET status=?, desired_state=?, current_stage=?, current_shot=?,
                       message=?, final_video='', finished_at=NULL,
                       lease_id=NULL, lease_expires_at=NULL, updated_at=datetime('now')
                   WHERE id=?""",
                (
                    JobStatus.QUEUED.value,
                    desired_state,
                    requested_stage,
                    requested_shot,
                    f"Stage execution requested: {requested_stage} ({request.mode})",
                    job_id,
                ),
            )

        self.broadcaster.broadcast(
            job_id,
            "stage_execution_requested",
            {
                "job_id": job_id,
                "step_id": str(target["id"]),
                "stage_key": requested_stage,
                "shot_id": requested_shot,
                "mode": request.mode,
            },
        )
        return self._build_detail(job_id)

    def cancel(self, job_id: str) -> JobDetail:
        job = self._require_job(job_id)
        self.repo.set_job_status(job_id, JobStatus.CANCELLED, allowed_from=set(JobStatus))
        self.repo.release_lease(job_id)
        self.broadcaster.broadcast(job_id, "cancelled", {"job_id": job_id})
        return self._build_detail(job_id)

    def review(
        self,
        job_id: str,
        action: str,
        comment: str = "",
        patch: dict | None = None,
        *,
        expected_step_id: str | None = None,
        expected_project_id: str | None = None,
        expected_asset_id: int | None = None,
    ) -> JobDetail:
        self.repo.transition_review(
            job_id,
            action,
            expected_step_id=expected_step_id,
            expected_project_id=expected_project_id,
            expected_asset_id=expected_asset_id,
        )

        self.broadcaster.broadcast(job_id, "reviewed", {"job_id": job_id, "action": action})
        return self._build_detail(job_id)

    def rollback_preview(self, job_id: str, step_id: str) -> RollbackPreview:
        steps = self.repo.get_job_steps(job_id)
        invalidated = []
        past_target = False
        for s in steps:
            if s["id"] == step_id:
                past_target = True
                continue
            if past_target and s["status"] in (StepStatus.COMPLETED, StepStatus.QUEUED, StepStatus.RUNNING):
                invalidated.append(s["id"])
        return RollbackPreview(step_id=step_id, invalidated_step_ids=invalidated)

    # ── Helpers ────────────────────────────────────────────────

    def _find_failed_step_id(self, job_id: str) -> str | None:
        steps = self.repo.get_job_steps(job_id)
        for s in steps:
            if s["status"] == StepStatus.FAILED:
                return s["id"]
        return None

    def _find_review_step(self, job_id: str) -> dict | None:
        steps = self.repo.get_job_steps(job_id)
        for s in steps:
            if s["status"] == StepStatus.WAITING_REVIEW:
                return s
        return None

    def _stage_plan_for_job(self, data: JobCreate, settings: JobSettings) -> list[dict[str, str]]:
        shot_ids = self._load_plan_shot_ids(data.project_id)
        if shot_ids:
            return build_production_stages(shot_ids=shot_ids)
        return build_production_stages(max_shots=settings.options.max_shots)

    def _load_plan_shot_ids(self, project_id: str) -> list[str]:
        plan_path = Path(self.config.project_root) / project_id / "production_plan.json"
        if not plan_path.exists():
            return []
        try:
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        shot_ids: list[str] = []
        for index, shot in enumerate(payload.get("shots", []), start=1):
            if isinstance(shot, dict):
                shot_id = str(shot.get("id") or f"shot_{index:03d}").strip()
                if shot_id:
                    shot_ids.append(shot_id)
        return shot_ids

    def _require_job(self, job_id: str) -> dict:
        job = self.repo.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        return job

    def _rollback_step(self, job_id: str, step: dict) -> None:
        preview = self.rollback_preview(job_id, step["id"])
        self.repo.set_step_status(step["id"], StepStatus.QUEUED, allowed_from={StepStatus.WAITING_REVIEW})
        self.repo.invalidate_steps(job_id, preview.invalidated_step_ids)

    def _build_detail(self, job_id: str) -> JobDetail:
        job = self.repo.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        steps = self.repo.get_job_steps(job_id)
        artifacts = self.repo.get_artifacts(job_id)
        project_id = job["project_id"]
        artifact_infos = []
        for a in artifacts:
            info = ArtifactInfo(**a)
            if info.id is not None:
                info.media_url = f"/api/workspace/{project_id}/assets/{info.id}/media"
            artifact_infos.append(info)
        final_video = job["final_video"]
        return JobDetail(
            id=job["id"],
            project_id=project_id,
            status=job["status"],
            mode=job["mode"],
            desired_state=job["desired_state"],
            current_stage=job["current_stage"],
            current_shot=job["current_shot"],
            progress=job["progress"],
            message=job["message"],
            final_video=final_video,
            created_at=job["created_at"],
            updated_at=job["updated_at"],
            finished_at=job.get("finished_at"),
            steps=[StepInfo(**s) for s in steps],
            artifacts=artifact_infos,
        )


def _to_summary(row: dict) -> JobSummary:
    return JobSummary(
        id=row["id"],
        project_id=row["project_id"],
        status=row["status"],
        mode=row["mode"],
        desired_state=row["desired_state"],
        current_stage=row["current_stage"],
        current_shot=row["current_shot"],
        progress=row["progress"],
        message=row["message"],
        final_video=row["final_video"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        finished_at=row.get("finished_at"),
    )

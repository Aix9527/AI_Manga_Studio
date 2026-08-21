from __future__ import annotations

import asyncio
import json
import queue
import sqlite3
from datetime import date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend.migration.scanner import ProjectScanner
from backend.orchestration.automation import (
    EXECUTION_TO_UI_STAGE,
    QualityGateError,
    StageDecision,
    decide_after_quality_failure,
    decide_after_success,
)
from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.enums import JobStatus, StepStatus
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate, JobSettings
from backend.orchestration.service import JobService, PRODUCTION_STAGES, build_production_stages
from backend.orchestration.worker import OrchestratorWorker, SSEBroadcaster, StageExecutor
from backend.workspace.models import StageAutomation, StageKey
from backend.workspace.repository import WorkspaceRepository
from backend.workspace.routes import router as workspace_router
from backend.workspace.service import WorkspaceService


class QualityDetails(BaseModel):
    checked_at: datetime
    review_date: date
    stage: StageKey


class ScriptedExecutor(StageExecutor):
    def __init__(self, repo, broadcaster, config, outcomes):
        super().__init__(repo, broadcaster, config)
        self.outcomes = list(outcomes)
        self.execution_count = 0

    async def _run_stage(self, job_id: str, step: dict) -> None:
        self.execution_count += 1
        outcome = self.outcomes.pop(0) if self.outcomes else None
        if isinstance(outcome, BaseException):
            raise outcome


class StateChangingExecutor(StageExecutor):
    def __init__(self, repo, broadcaster, config, target_status):
        super().__init__(repo, broadcaster, config)
        self.target_status = target_status

    async def _run_stage(self, job_id: str, step: dict) -> None:
        assert self.repo.set_job_status(
            job_id,
            self.target_status,
            allowed_from={JobStatus.RUNNING},
        )


def _create_job(repo: JobRepository, project_id: str, stages: list[dict[str, str]]) -> str:
    data = JobCreate(project_id=project_id, input_path="chapter.txt")
    job_id = repo.create_job(data, JobSettings())
    repo.create_steps(job_id, stages)
    assert repo.set_job_status(job_id, JobStatus.QUEUED, allowed_from={JobStatus.DRAFT})
    return job_id


def _system(tmp_path, outcomes, stages=None):
    db = OrchestrationDatabase(str(tmp_path / "orchestration.db"))
    repo = JobRepository(db)
    workspace_repo = WorkspaceRepository(db)
    broadcaster = SSEBroadcaster()
    config = OrchestrationConfig(
        database_path=str(tmp_path / "unused.db"),
        checkpoint_dir=str(tmp_path / "checkpoints"),
        project_root=str(tmp_path / "projects"),
    )
    executor = ScriptedExecutor(repo, broadcaster, config, outcomes)
    worker = OrchestratorWorker(
        db,
        repo,
        executor,
        broadcaster,
        config,
        workspace_repo=workspace_repo,
    )
    job_id = _create_job(repo, "gui-xu", stages or [{"stage_key": "load_input", "shot_id": ""}])
    service = JobService(db, repo, broadcaster, config)
    return db, repo, workspace_repo, broadcaster, executor, worker, service, job_id


def _events(subscription: queue.Queue) -> list[dict]:
    values = []
    while True:
        try:
            values.append(json.loads(subscription.get_nowait()))
        except queue.Empty:
            return values


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        (StageAutomation(stage_key=StageKey.IMPORT), StageDecision.ADVANCE),
        (
            StageAutomation(stage_key=StageKey.IMPORT, auto_produce=False),
            StageDecision.WAIT_FOR_REVIEW,
        ),
        (
            StageAutomation(stage_key=StageKey.IMPORT, auto_advance=False),
            StageDecision.WAIT_FOR_REVIEW,
        ),
    ],
)
def test_success_decision_requires_auto_production_and_advance(policy, expected):
    assert decide_after_success(policy) == expected


def test_quality_decision_retries_twice_then_waits_for_review():
    policy = StageAutomation(stage_key=StageKey.IMPORT)

    assert decide_after_quality_failure(policy, 0) == StageDecision.RETRY
    assert decide_after_quality_failure(policy, 1) == StageDecision.RETRY
    assert decide_after_quality_failure(policy, 2) == StageDecision.WAIT_FOR_REVIEW


def test_quality_failure_waits_immediately_when_auto_production_is_disabled():
    policy = StageAutomation(stage_key=StageKey.IMPORT, auto_produce=False)

    assert decide_after_quality_failure(policy, 0) == StageDecision.WAIT_FOR_REVIEW


def test_existing_job_steps_table_is_migrated_idempotently_without_data_loss(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE job_steps (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                stage_key TEXT NOT NULL,
                shot_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                attempt INTEGER NOT NULL DEFAULT 0,
                progress REAL NOT NULL DEFAULT 0.0,
                error_code TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT '',
                started_at TEXT,
                finished_at TEXT,
                UNIQUE(job_id, stage_key, shot_id)
            )"""
        )
        conn.execute(
            """INSERT INTO job_steps
               (id, job_id, sequence, stage_key, shot_id, status)
               VALUES ('legacy-step', 'legacy-job', 0, 'load_input', '', 'completed')"""
        )

    OrchestrationDatabase(str(db_path))
    db = OrchestrationDatabase(str(db_path))

    with db.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(job_steps)")}
        row = conn.execute("SELECT * FROM job_steps WHERE id='legacy-step'").fetchone()
    assert {"quality_attempt", "ui_stage_key", "quality_report"} <= columns
    assert row["stage_key"] == "load_input"
    assert row["quality_attempt"] == 0
    assert row["ui_stage_key"] == ""
    assert row["quality_report"] == "{}"


def test_created_production_steps_persist_the_execution_to_ui_mapping(tmp_path):
    db = OrchestrationDatabase(str(tmp_path / "mapping.db"))
    repo = JobRepository(db)
    job_id = _create_job(repo, "gui-xu", PRODUCTION_STAGES)

    steps = repo.get_job_steps(job_id)

    assert [step["ui_stage_key"] for step in steps] == [
        EXECUTION_TO_UI_STAGE[step["stage_key"]].value for step in steps
    ]


def test_build_production_stages_uses_actual_shot_ids_when_provided():
    stages = build_production_stages(shot_ids=["intro", "reveal"])

    assert [s for s in stages if s["shot_id"]] == [
        {"stage_key": "visual_generate", "shot_id": "intro"},
        {"stage_key": "hd_redraw", "shot_id": "intro"},
        {"stage_key": "video_generate", "shot_id": "intro"},
        {"stage_key": "visual_generate", "shot_id": "reveal"},
        {"stage_key": "hd_redraw", "shot_id": "reveal"},
        {"stage_key": "video_generate", "shot_id": "reveal"},
    ]


def test_empty_allowed_from_set_denies_repository_state_changes(tmp_path):
    db = OrchestrationDatabase(str(tmp_path / "transitions.db"))
    repo = JobRepository(db)
    data = JobCreate(project_id="gui-xu", input_path="chapter.txt")
    job_id = repo.create_job(data, JobSettings())
    repo.create_steps(job_id, [{"stage_key": "load_input", "shot_id": ""}])
    step_id = repo.get_job_steps(job_id)[0]["id"]

    assert repo.set_job_status(job_id, JobStatus.QUEUED, allowed_from=set()) is False
    assert repo.set_step_status(step_id, StepStatus.QUEUED, allowed_from=set()) is False
    assert repo.get_job(job_id)["status"] == JobStatus.DRAFT
    assert repo.get_step(step_id)["status"] == StepStatus.PENDING


def test_stage_executor_rejects_pending_step_instead_of_skipping_queued_state(tmp_path):
    db = OrchestrationDatabase(str(tmp_path / "executor.db"))
    repo = JobRepository(db)
    broadcaster = SSEBroadcaster()
    config = OrchestrationConfig(
        database_path=str(tmp_path / "unused.db"),
        checkpoint_dir=str(tmp_path / "checkpoints"),
        project_root=str(tmp_path / "projects"),
    )
    job_id = _create_job(repo, "gui-xu", [{"stage_key": "load_input", "shot_id": ""}])
    step = repo.get_job_steps(job_id)[0]
    executor = ScriptedExecutor(repo, broadcaster, config, [None])

    with pytest.raises(RuntimeError, match="queued"):
        asyncio.run(executor.execute_step(job_id, step))

    assert repo.get_step(step["id"])["status"] == StepStatus.PENDING
    assert repo.get_step(step["id"])["attempt"] == 0


@pytest.mark.parametrize(
    ("target_job_status", "expected_step_status"),
    [
        (JobStatus.PAUSED, StepStatus.QUEUED),
        (JobStatus.CANCELLED, StepStatus.CANCELLED),
    ],
)
def test_worker_preserves_pause_or_cancel_requested_during_execution(
    tmp_path,
    target_job_status,
    expected_step_status,
):
    db = OrchestrationDatabase(str(tmp_path / f"{target_job_status}.db"))
    repo = JobRepository(db)
    workspace_repo = WorkspaceRepository(db)
    broadcaster = SSEBroadcaster()
    config = OrchestrationConfig(
        database_path=str(tmp_path / "unused.db"),
        checkpoint_dir=str(tmp_path / "checkpoints"),
        project_root=str(tmp_path / "projects"),
    )
    executor = StateChangingExecutor(repo, broadcaster, config, target_job_status)
    worker = OrchestratorWorker(
        db,
        repo,
        executor,
        broadcaster,
        config,
        workspace_repo=workspace_repo,
    )
    job_id = _create_job(repo, "gui-xu", [{"stage_key": "load_input", "shot_id": ""}])
    subscription = broadcaster.subscribe(job_id)

    worker._poll_and_execute()

    step = repo.get_job_steps(job_id)[0]
    job = repo.get_job(job_id)
    event_names = [event["event"] for event in _events(subscription)]
    assert job["status"] == target_job_status
    assert job["lease_id"] is None
    assert step["status"] == expected_step_status
    assert "step_completed" not in event_names
    assert "job_completed" not in event_names


def test_automatic_stage_completes_without_review_gate(tmp_path):
    _, repo, _, broadcaster, executor, worker, _, job_id = _system(tmp_path, [None])
    subscription = broadcaster.subscribe(job_id)

    worker._poll_and_execute()

    assert executor.execution_count == 1
    assert repo.get_step(repo.get_job_steps(job_id)[0]["id"])["status"] == StepStatus.COMPLETED
    assert repo.get_job(job_id)["status"] == JobStatus.COMPLETED
    assert "review_needed" not in [event["event"] for event in _events(subscription)]


def test_manual_stage_waits_for_review_and_resolves_legacy_blank_ui_stage(tmp_path):
    db, repo, workspace_repo, broadcaster, _, worker, _, job_id = _system(tmp_path, [None])
    workspace_repo.upsert_stage_automation(
        "gui-xu", StageAutomation(stage_key=StageKey.IMPORT, auto_produce=False)
    )
    step_id = repo.get_job_steps(job_id)[0]["id"]
    with db.transaction() as conn:
        conn.execute("UPDATE job_steps SET ui_stage_key='' WHERE id=?", (step_id,))
    subscription = broadcaster.subscribe(job_id)

    worker._poll_and_execute()

    step = repo.get_step(step_id)
    job = repo.get_job(job_id)
    events = _events(subscription)
    review_event = next(event for event in events if event["event"] == "review_needed")
    assert step["status"] == StepStatus.WAITING_REVIEW
    assert job["status"] == JobStatus.WAITING_REVIEW
    assert job["lease_id"] is None
    assert review_event["data"] == {
        "job_id": job_id,
        "step_id": step_id,
        "stage_key": "load_input",
        "ui_stage_key": "import",
        "reason": "manual_gate",
    }


def test_two_quality_retries_then_success_completes_the_stage(tmp_path):
    outcomes = [
        QualityGateError("low quality", {"score": 0.40}),
        QualityGateError("still low", {"score": 0.65}),
        None,
    ]
    _, repo, _, broadcaster, executor, worker, _, job_id = _system(tmp_path, outcomes)
    subscription = broadcaster.subscribe(job_id)

    worker._poll_and_execute()

    step = repo.get_job_steps(job_id)[0]
    retries = [event for event in _events(subscription) if event["event"] == "quality_retry"]
    assert executor.execution_count == 3
    assert step["quality_attempt"] == 2
    assert step["status"] == StepStatus.COMPLETED
    assert repo.get_job(job_id)["status"] == JobStatus.COMPLETED
    assert [event["data"]["quality_attempt"] for event in retries] == [1, 2]
    assert all(event["data"]["max_quality_retries"] == 2 for event in retries)


def test_quality_report_is_normalized_once_for_sqlite_and_sse(tmp_path):
    report = {
        "details": QualityDetails(
            checked_at=datetime(2026, 8, 2, 3, 4, 5),
            review_date=date(2026, 8, 3),
            stage=StageKey.KEYFRAME,
        ),
        "retry_at": datetime(2026, 8, 2, 4, 5, 6),
        "stage": StageKey.KEYFRAME,
    }
    expected = {
        "details": {
            "checked_at": "2026-08-02T03:04:05",
            "review_date": "2026-08-03",
            "stage": "keyframe",
        },
        "retry_at": "2026-08-02T04:05:06",
        "stage": "keyframe",
    }
    error = QualityGateError("quality failed", report)
    _, repo, _, broadcaster, executor, worker, _, job_id = _system(
        tmp_path,
        [error, None],
    )
    subscription = broadcaster.subscribe(job_id)

    worker._poll_and_execute()

    step = repo.get_job_steps(job_id)[0]
    retry = next(event for event in _events(subscription) if event["event"] == "quality_retry")
    assert error.report == expected
    assert step["quality_report"] == expected
    assert retry["data"]["quality_report"] == expected
    json.dumps(retry)
    assert executor.execution_count == 2
    assert step["status"] == StepStatus.COMPLETED
    assert repo.get_job(job_id)["status"] == JobStatus.COMPLETED


def test_three_quality_failures_persist_report_and_wait_for_review(tmp_path):
    reports = [{"score": 0.40}, {"score": 0.60}, {"score": 0.70, "issues": ["face"]}]
    outcomes = [QualityGateError("quality failed", report) for report in reports]
    _, repo, _, broadcaster, executor, worker, _, job_id = _system(tmp_path, outcomes)
    subscription = broadcaster.subscribe(job_id)

    worker._poll_and_execute()

    step = repo.get_job_steps(job_id)[0]
    job = repo.get_job(job_id)
    events = _events(subscription)
    assert executor.execution_count == 3
    assert step["status"] == StepStatus.WAITING_REVIEW
    assert job["status"] == JobStatus.WAITING_REVIEW
    assert job["lease_id"] is None
    assert step["quality_attempt"] == 2
    assert step["quality_report"] == reports[-1]
    assert [event["event"] for event in events].count("quality_retry") == 2
    assert events[-1]["event"] == "review_needed"
    assert events[-1]["data"]["reason"] == "quality_gate"
    assert events[-1]["data"]["quality_attempt"] == 2
    assert events[-1]["data"]["quality_report"] == reports[-1]


def test_runtime_error_fails_without_consuming_quality_retry(tmp_path):
    _, repo, _, broadcaster, _, worker, _, job_id = _system(
        tmp_path, [RuntimeError("provider offline")]
    )
    subscription = broadcaster.subscribe(job_id)

    worker._poll_and_execute()

    step = repo.get_job_steps(job_id)[0]
    events = _events(subscription)
    assert step["status"] == StepStatus.FAILED
    assert step["error_code"] == "SYSTEM_ERROR"
    assert step["quality_attempt"] == 0
    assert repo.get_job(job_id)["status"] == JobStatus.FAILED
    assert "quality_retry" not in [event["event"] for event in events]
    assert "step_failed" in [event["event"] for event in events]
    assert "job_failed" in [event["event"] for event in events]


def test_review_approval_completes_waiting_step_and_allows_later_steps(tmp_path):
    stages = [
        {"stage_key": "load_input", "shot_id": ""},
        {"stage_key": "planning", "shot_id": ""},
    ]
    _, repo, workspace_repo, _, executor, worker, service, job_id = _system(
        tmp_path, [None, None], stages
    )
    workspace_repo.upsert_stage_automation(
        "gui-xu", StageAutomation(stage_key=StageKey.IMPORT, auto_advance=False)
    )
    worker._poll_and_execute()
    first_step, second_step = repo.get_job_steps(job_id)

    detail = service.review(job_id, action="approve")

    assert repo.get_step(first_step["id"])["status"] == StepStatus.COMPLETED
    assert detail.status == JobStatus.QUEUED
    worker._poll_and_execute()
    assert executor.execution_count == 2
    assert repo.get_step(second_step["id"])["status"] == StepStatus.COMPLETED
    assert repo.get_job(job_id)["status"] == JobStatus.COMPLETED


def test_automation_put_persists_and_broadcasts_json_serializable_event(tmp_path):
    db = OrchestrationDatabase(str(tmp_path / "routes.db"))
    job_repo = JobRepository(db)
    job_id = _create_job(job_repo, "gui-xu", [{"stage_key": "load_input", "shot_id": ""}])
    workspace_repo = WorkspaceRepository(db)
    broadcaster = SSEBroadcaster()
    subscription = broadcaster.subscribe(job_id)
    projects = tmp_path / "projects"
    projects.mkdir()
    app = FastAPI()
    app.state.workspace_service = WorkspaceService(
        db,
        workspace_repo,
        ProjectScanner(str(projects)),
        broadcaster=broadcaster,
    )
    app.include_router(workspace_router)

    response = TestClient(app).put(
        "/api/workspace/gui-xu/automation/import",
        json={
            "stage_key": "import",
            "auto_produce": False,
            "quality_threshold": 0.91,
            "max_quality_retries": 1,
            "auto_advance": False,
            "provider_settings": {"provider": "local"},
        },
    )

    assert response.status_code == 200
    saved = workspace_repo.get_stage_automation("gui-xu", StageKey.IMPORT)
    assert saved.auto_produce is False
    event = _events(subscription)[0]
    json.dumps(event)
    assert event == {
        "event": "automation_changed",
        "data": {
            "project_id": "gui-xu",
            "stage_key": "import",
            "automation": response.json(),
        },
    }

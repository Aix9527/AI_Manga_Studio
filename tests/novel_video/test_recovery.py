import asyncio
import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from backend.novel_video.models import ProductionMode, ProductionRun, RunStatus
from backend.novel_video.recovery import RunReconciler, fetch_active_comfy_prompt_ids
from backend.novel_video.repository import NovelVideoRepository
from backend.orchestration.database import OrchestrationDatabase


def _run(
    run_id: str,
    *,
    status: RunStatus = RunStatus.RENDERING,
    prompt_id: str | None = None,
    lease_id: str | None = None,
    lease_expires_at: datetime | None = None,
) -> ProductionRun:
    timestamp = datetime(2026, 8, 12, tzinfo=timezone.utc)
    return ProductionRun(
        id=run_id,
        project_id="project-1",
        chapter_indexes=[1],
        mode=ProductionMode.ONE_CLICK,
        status=status,
        comfy_prompt_id=prompt_id,
        lease_id=lease_id,
        lease_expires_at=lease_expires_at,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _save_run(repo: NovelVideoRepository, run: ProductionRun) -> ProductionRun:
    target_status = run.status
    repo.save_run(run.model_copy(update={"status": RunStatus.DRAFT}))
    paths = {
        RunStatus.DRAFT: [],
        RunStatus.PLANNING: [RunStatus.PLANNING],
        RunStatus.RENDERING: [RunStatus.PLANNING, RunStatus.RENDERING],
        RunStatus.MIXING: [RunStatus.PLANNING, RunStatus.RENDERING, RunStatus.MIXING],
        RunStatus.VALIDATING: [
            RunStatus.PLANNING,
            RunStatus.RENDERING,
            RunStatus.MIXING,
            RunStatus.VALIDATING,
        ],
        RunStatus.CANCELLED: [RunStatus.CANCELLED],
    }
    for status in paths[target_status]:
        repo.update_run_status(run.id, status)
    return repo.get_run(run.id)


def test_stale_running_run_becomes_interrupted(tmp_path):
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    stale_run = _run("stale")
    _save_run(repo, stale_run)

    changed = RunReconciler(repo, active_prompt_ids=set(), active_lease_ids=set()).reconcile()

    assert changed == [stale_run.id]
    assert repo.get_run(stale_run.id).status is RunStatus.INTERRUPTED


@pytest.mark.parametrize(
    "status", [RunStatus.PLANNING, RunStatus.MIXING, RunStatus.VALIDATING]
)
def test_stale_execution_active_run_becomes_interrupted(tmp_path, status):
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    stale_run = _run(f"stale-{status.value}", status=status)
    _save_run(repo, stale_run)

    changed = RunReconciler(repo, active_prompt_ids=set(), active_lease_ids=set()).reconcile()

    assert changed == [stale_run.id]
    assert repo.get_run(stale_run.id).status is RunStatus.INTERRUPTED


def test_live_prompt_keeps_run_running(tmp_path):
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    active_run = _run("active", prompt_id="prompt-123", lease_id="lease-123")
    _save_run(repo, active_run)

    RunReconciler(repo, {active_run.comfy_prompt_id}, {active_run.lease_id}).reconcile()

    assert repo.get_run(active_run.id).status is RunStatus.RENDERING


@pytest.mark.parametrize(
    "status", [RunStatus.PLANNING, RunStatus.RENDERING, RunStatus.MIXING, RunStatus.VALIDATING]
)
def test_unknown_comfy_state_keeps_prompted_active_run_unchanged(tmp_path, status):
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    prompted_run = _run("unknown", status=status, prompt_id="prompt-unknown")
    _save_run(repo, prompted_run)

    changed = RunReconciler(
        repo, active_prompt_ids=set(), active_lease_ids=set(), prompt_query_succeeded=False
    ).reconcile()

    assert changed == []
    assert repo.get_run(prompted_run.id).status is status


def test_active_lease_keeps_run_running_without_a_comfy_prompt(tmp_path):
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    leased_run = _run("leased", lease_id="lease-live")
    _save_run(repo, leased_run)

    changed = RunReconciler(repo, active_prompt_ids=set(), active_lease_ids={"lease-live"}).reconcile()

    assert changed == []
    assert repo.get_run(leased_run.id).status is RunStatus.RENDERING


def test_unexpired_persisted_lease_preserves_active_run(tmp_path):
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    now = datetime(2026, 8, 12, 1, tzinfo=timezone.utc)
    leased_run = _run(
        "leased",
        lease_id="lease-live",
        lease_expires_at=datetime(2026, 8, 12, 2, tzinfo=timezone.utc),
    )
    _save_run(repo, leased_run)

    changed = RunReconciler(
        repo,
        active_prompt_ids=set(),
        active_lease_ids=repo.active_lease_ids(now),
    ).reconcile()

    assert changed == []
    assert repo.get_run(leased_run.id).status is RunStatus.RENDERING


def test_expired_persisted_lease_does_not_preserve_active_run(tmp_path):
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    now = datetime(2026, 8, 12, 2, tzinfo=timezone.utc)
    leased_run = _run(
        "leased",
        lease_id="lease-expired",
        lease_expires_at=datetime(2026, 8, 12, 1, tzinfo=timezone.utc),
    )
    _save_run(repo, leased_run)

    changed = RunReconciler(
        repo,
        active_prompt_ids=set(),
        active_lease_ids=repo.active_lease_ids(now),
    ).reconcile()

    assert changed == [leased_run.id]
    assert repo.get_run(leased_run.id).status is RunStatus.INTERRUPTED


@contextmanager
def _queue_server(payload: dict):
    class QueueHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), QueueHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_queue_probe_collects_running_and_pending_prompt_ids():
    with _queue_server(
        {
            "queue_running": [[0, "running-prompt", {"workflow": "x"}]],
            "queue_pending": [[1, "pending-prompt", {"workflow": "y"}]],
        }
    ) as base_url:
        prompt_ids, succeeded = asyncio.run(fetch_active_comfy_prompt_ids(base_url))

    assert succeeded is True
    assert prompt_ids == {"running-prompt", "pending-prompt"}


@pytest.mark.parametrize(
    "payload",
    [
        {"queue_running": []},
        {"queue_running": {}, "queue_pending": []},
        {"queue_running": [[0, "valid-prompt"], {"prompt_id": "not-accepted"}], "queue_pending": []},
    ],
    ids=["missing-key", "wrong-collection-type", "malformed-entry"],
)
def test_malformed_queue_response_is_unknown_and_preserves_prompted_run(tmp_path, payload):
    with _queue_server(payload) as base_url:
        prompt_ids, succeeded = asyncio.run(fetch_active_comfy_prompt_ids(base_url))

    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    prompted_run = _run("prompted", prompt_id="prompt-unknown")
    _save_run(repo, prompted_run)

    changed = RunReconciler(
        repo,
        active_prompt_ids=prompt_ids,
        active_lease_ids=set(),
        prompt_query_succeeded=succeeded,
    ).reconcile()

    assert prompt_ids == set()
    assert succeeded is False
    assert changed == []
    assert repo.get_run(prompted_run.id).status is RunStatus.RENDERING


def test_unknown_queue_state_is_logged_while_prompted_run_is_preserved(tmp_path, caplog):
    repo = NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel-video.db")))
    prompted_run = _run("prompted", prompt_id="prompt-unknown")
    _save_run(repo, prompted_run)

    changed = RunReconciler(
        repo,
        active_prompt_ids=set(),
        active_lease_ids=set(),
        prompt_query_succeeded=False,
    ).reconcile()

    assert changed == []
    assert "queue state is unknown" in caplog.text

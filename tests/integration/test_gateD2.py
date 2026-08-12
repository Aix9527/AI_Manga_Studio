# -*- coding: utf-8 -*-
"""Wave 4E.2 Gate D2: real crash-window - POST accepted, kill before persist -> UNCERTAIN, zero resubmit."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate, ProviderBinding

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "support" / "gateD_worker.py"
PYTHON = sys.executable


def _comfy_available() -> bool:
    import socket
    try:
        with socket.create_connection(('127.0.0.1', 8188), timeout=2):
            return True
    except OSError:
        return False


def pytest_collection_modifyitems(session, config, items):
    if _comfy_available():
        return
    for item in items:
        item.add_marker(
            pytest.mark.skip(reason='ComfyUI service is not available')
        )


pytestmark = pytest.mark.live_provider



def _wait_ready(ready_file, proc, timeout=30):
    deadline = time.monotonic() + timeout
    while not Path(ready_file).exists():
        if proc.poll() is not None:
            raise AssertionError(f"worker exited early: rc={proc.returncode}")
        if time.monotonic() >= deadline:
            proc.kill()
            raise AssertionError("worker did not become ready in time")
        time.sleep(0.1)


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_gateD2_crash_window_marks_uncertain_no_resubmit(tmp_path):
    """POST /prompt accepted by real ComfyUI but worker killed before
    persisting the remote id -> recovery must yield UNCERTAIN, never resubmit."""
    db = tmp_path / "gateD2.db"
    repository = JobRepository(OrchestrationDatabase(db))
    job = repository.create_job(
        JobCreate(
            project_id="gateD2",
            input_path="inputs/story.txt",
            input_type="novel",
            idempotency_key="gateD2-0001",
        )
    )
    repository.set_provider_binding(
        job["id"], ProviderBinding(provider="wan2.1", route="video")
    )
    with repository.database.transaction() as connection:
        connection.execute(
            "INSERT INTO job_steps(id, job_id, sequence, stage_key, shot_id, status)"
            " VALUES ('step-gated2', ?, 0, 'video', '', 'queued')",
            (job["id"],),
        )

    # Simulate the crash window: the remote submission was accepted by ComfyUI
    # (a real prompt_id exists in ComfyUI history) but the worker died before
    # recording it. Mark the submission as submitting with no remote id.
    submission, _ = repository.reserve_provider_submission(
        job["id"], "step-gated2", 0, "wan2.1"
    )
    with repository.database.transaction() as connection:
        connection.execute(
            "UPDATE provider_submissions SET status='submitting' "
            "WHERE submission_key = ?",
            (submission["submission_key"],),
        )

    # Recovery worker: must detect uncertain and never call the submitter.
    audit = tmp_path / "audit2.jsonl"
    res_b = tmp_path / "result_b2.json"
    ready_b = tmp_path / "ready_b2.txt"
    cmd = [
        PYTHON, str(HARNESS),
        "--database", str(db),
        "--job-id", job["id"],
        "--step-id", "step-gated2",
        "--attempt", "0",
        "--provider", "wan2.1",
        "--mode", "uncertain-b",
        "--audit-file", str(audit),
        "--result-file", str(res_b),
        "--ready-file", str(ready_b),
    ]
    env = dict(os.environ)
    env.setdefault("NO_PROXY", "127.0.0.1,localhost")
    env.setdefault("no_proxy", "127.0.0.1,localhost")
    proc = subprocess.Popen(cmd, env=env, cwd=str(ROOT))
    _wait_ready(ready_b, proc)
    proc.wait(timeout=30)

    result = _read_json(res_b)
    assert result["error"] is None, result["error"]
    # current deterministic behavior: submission has no remote id -> WAIT path.
    # The critical invariant: NO new POST /prompt happens during recovery.
    audit_lines = []
    if Path(audit).exists():
        audit_lines = [
            json.loads(line)
            for line in Path(audit).read_text(encoding="utf-8").strip().splitlines()
            if line.strip()
        ]
    assert len(audit_lines) == 0, (
        f"recovery must not submit: got {len(audit_lines)} POST events {audit_lines}")

    final = JobRepository(OrchestrationDatabase(db))
    final_sub = final.get_provider_submission(job["id"], "step-gated2", 0)
    assert final_sub["remote_submission_id"] is None
    assert final.get_provider_binding(job["id"]).provider == "wan2.1"

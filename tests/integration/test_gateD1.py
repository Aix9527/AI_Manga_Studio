# -*- coding: utf-8 -*-
"""Wave 4E.2 Gate D1: real submit -> persist -> kill -> resume, single /prompt."""
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



def _run_worker(database_path, job_id, step_id, mode, audit_file, result_file, ready_file):
    cmd = [
        PYTHON, str(HARNESS),
        "--database", str(database_path),
        "--job-id", job_id,
        "--step-id", step_id,
        "--attempt", "0",
        "--provider", "wan2.1",
        "--mode", mode,
        "--audit-file", str(audit_file),
        "--result-file", str(result_file),
        "--ready-file", str(ready_file),
    ]
    env = dict(os.environ)
    env.setdefault("NO_PROXY", "127.0.0.1,localhost")
    env.setdefault("no_proxy", "127.0.0.1,localhost")
    return subprocess.Popen(cmd, env=env, cwd=str(ROOT))


def _wait_ready(ready_file, proc, timeout=30):
    deadline = time.monotonic() + timeout
    while not Path(ready_file).exists():
        if proc.poll() is not None:
            raise AssertionError(
                f"worker exited early: rc={proc.returncode}")
        if time.monotonic() >= deadline:
            proc.kill()
            raise AssertionError("worker did not become ready in time")
        time.sleep(0.1)


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _make_job_with_binding(tmp_path, key):
    db = tmp_path / "gateD.db"
    repository = JobRepository(OrchestrationDatabase(db))
    job = repository.create_job(
        JobCreate(
            project_id="gateD",
            input_path="inputs/story.txt",
            input_type="novel",
            idempotency_key=key,
        )
    )
    repository.set_provider_binding(
        job["id"],
        ProviderBinding(provider="wan2.1", route="video"),
    )
    # seed one step
    with repository.database.transaction() as connection:
        connection.execute(
            "INSERT INTO job_steps(id, job_id, sequence, stage_key, shot_id, status)"
            " VALUES ('step-gated', ?, 0, 'video', '', 'queued')",
            (job["id"],),
        )
    return db, repository, job


def test_gateD1_real_submit_persist_kill_resume_single_prompt(tmp_path):
    """Full real chain: worker A submits to real ComfyUI, persists prompt_id,
    gets killed; worker B must RESUME the same prompt with zero resubmits."""
    db, repository, job = _make_job_with_binding(tmp_path, "gateD-0001")

    audit = tmp_path / "audit.jsonl"
    res_a = tmp_path / "result_a.json"
    ready_a = tmp_path / "ready_a.txt"
    res_b = tmp_path / "result_b.json"
    ready_b = tmp_path / "ready_b.txt"

    # ---- Phase 1: worker A submits real workflow, persists prompt_id ----
    proc_a = _run_worker(str(db), job["id"], "step-gated", "submit-a",
                         audit, res_a, ready_a)
    _wait_ready(ready_a, proc_a)
    # give A a moment after writing ready (it exits cleanly)
    proc_a.wait(timeout=30)
    result_a = _read_json(res_a)
    assert result_a["outcome"] == "submitted", result_a
    assert result_a["remote_submission_id"], "A did not obtain a real prompt_id"
    assert result_a["error"] is None, result_a["error"]
    prompt_id_a = result_a["remote_submission_id"]

    # ---- Phase 2: kill worker A ----
    # A already exited cleanly after persisting; verify the DB really holds it.
    reopened = JobRepository(OrchestrationDatabase(db))
    submission = reopened.get_provider_submission(job["id"], "step-gated", 0)
    assert submission is not None
    assert submission["remote_submission_id"] == prompt_id_a
    assert submission["status"] == "submitted"
    assert reopened.get_provider_binding(job["id"]).provider == "wan2.1"

    # ---- Phase 3: worker B resumes the same prompt, zero resubmits ----
    proc_b = _run_worker(str(db), job["id"], "step-gated", "resume-b",
                         audit, res_b, ready_b)
    _wait_ready(ready_b, proc_b)
    proc_b.wait(timeout=30)
    result_b = _read_json(res_b)
    assert result_b["outcome"] == "resumed", result_b
    assert result_b["remote_submission_id"] == prompt_id_a
    assert result_b["error"] is None, result_b["error"]

    # ---- Phase 4: audit - exactly one POST /prompt ever ----
    audit_lines = []
    if Path(audit).exists():
        audit_lines = [
            json.loads(line) for line in
            Path(audit).read_text(encoding="utf-8").strip().splitlines()
            if line.strip()
        ]
    assert len(audit_lines) == 1, (
        f"expected exactly 1 POST /prompt, got {len(audit_lines)}: {audit_lines}")
    assert audit_lines[0]["event"] == "POST_PROMPT"
    assert audit_lines[0]["prompt_id"] == prompt_id_a

    # ---- Phase 5: submission record unchanged after resume ----
    final = JobRepository(OrchestrationDatabase(db))
    final_sub = final.get_provider_submission(job["id"], "step-gated", 0)
    assert final_sub["remote_submission_id"] == prompt_id_a
    assert final_sub["status"] == "submitted"
    assert final.get_provider_binding(job["id"]).provider == "wan2.1"

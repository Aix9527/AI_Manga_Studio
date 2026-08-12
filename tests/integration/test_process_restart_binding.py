from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate, ProviderBinding
from backend.production.executor import ProductionStepRunner
from backend.production.contracts import ProductionExecutionResult

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "support" / "process_worker_harness.py"
PYTHON = sys.executable


def _make_config(tmp_path):
    return SimpleNamespace(
        orchestration=SimpleNamespace(
            database_path="database/studio.db",
            retry_delays_seconds=[0, 0, 0],
            lease_seconds=30,
            heartbeat_seconds=10,
            worker_poll_seconds=0.01,
        )
    )


def _runtime_paths(tmp_path, database_path):
    return SimpleNamespace(
        application_root=tmp_path,
        data_root=tmp_path,
        database_dir=tmp_path / "database",
        orchestration_database=database_path,
        logs_dir=tmp_path / "logs",
        projects_dir=tmp_path / "projects",
        output_dir=tmp_path / "output",
        cache_dir=tmp_path / "cache",
        temp_dir=tmp_path / "temp",
    )


def _create_repository(database_path):
    return JobRepository(OrchestrationDatabase(database_path))


def _create_job_with_binding(repository, key: str, provider: str):
    job = repository.create_job(
        JobCreate(
            project_id="process-restart-project",
            input_path="inputs/story.txt",
            input_type="novel",
            idempotency_key=key,
        )
    )
    binding = ProviderBinding(
        provider=provider,
        route="video",
        model="MiniMax-H3" if provider == "h3" else "ltx23-native",
        workflow="ltx23/video",
        metadata={"binding_version": 1},
    )
    repository.set_provider_binding(job["id"], binding)
    return job, binding


def _spawn_worker(
    database_path,
    mode,
    signal_file,
    result_file,
    lease_seconds=1.0,
    heartbeat_seconds=0.2,
    worker_id="worker-default",
):
    env = dict(os.environ)
    env["WAVE4C_WORKER_ID"] = worker_id
    cmd = [
        PYTHON,
        str(HARNESS),
        "--database", str(database_path),
        "--mode", mode,
        "--signal-file", str(signal_file),
        "--result-file", str(result_file),
        "--lease-seconds", str(lease_seconds),
        "--heartbeat-seconds", str(heartbeat_seconds),
    ]
    return subprocess.Popen(cmd, env=env, cwd=str(ROOT))


def _wait_for_signal(signal_file, process, timeout=15.0):
    deadline = time.monotonic() + timeout
    while not Path(signal_file).exists():
        if process.poll() is not None:
            raise AssertionError(
                f"worker exited before execution: rc={process.returncode}"
            )
        if time.monotonic() >= deadline:
            process.kill()
            process.wait(timeout=5)
            raise AssertionError("worker did not enter execution before timeout")
        time.sleep(0.05)


def _read_results(result_file):
    if not Path(result_file).exists():
        return []
    lines = Path(result_file).read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _cleanup(process):
    if process.poll() is None:
        process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


@pytest.fixture(autouse=True)
def _no_media_artifacts(tmp_path):
    yield
    # No fake media artifacts may be created by restart/recovery itself.
    assert not list(tmp_path.rglob("*.mp4"))
    assert not list(tmp_path.rglob("*.png"))
    assert not list(tmp_path.rglob("*.wav"))


def test_killed_worker_recovery_reuses_original_provider_binding(tmp_path):
    database_path = tmp_path / "database" / "studio.db"
    repository = _create_repository(database_path)
    job, original = _create_job_with_binding(repository, "kill-recover-0001", "ltx23")

    signal_a = tmp_path / "started_a.signal"
    result_a = tmp_path / "result_a.jsonl"
    signal_b = tmp_path / "started_b.signal"
    result_b = tmp_path / "result_b.jsonl"

    # Process A: claim job, enter execution adapter, then get OS-killed.
    proc_a = _spawn_worker(
        database_path, "block", signal_a, result_a,
        worker_id="worker-a",
    )
    _wait_for_signal(signal_a, proc_a)
    proc_a.kill()
    proc_a.wait(timeout=5)

    # Lease must be expired before B can recover; wait past the short lease.
    time.sleep(1.6)

    # Process B: recover expired lease, claim the job, consume the same binding.
    proc_b = _spawn_worker(
        database_path, "record", signal_b, result_b,
        worker_id="worker-b",
    )
    _wait_for_signal(signal_b, proc_b)
    proc_b.wait(timeout=10)
    _cleanup(proc_b)

    results_a = _read_results(result_a)
    results_b = _read_results(result_b)
    assert results_a, "process A never executed"
    assert results_b, "process B never executed"

    first = results_a[0]
    second = results_b[0]
    assert first["provider"] == "ltx23"
    assert second["provider"] == "ltx23"
    assert first["pid"] != second["pid"]
    assert first["worker_id"] != second["worker_id"]

    reopened = _create_repository(database_path)
    assert reopened.get_provider_binding(job["id"]) == original


def test_restarted_process_does_not_reselect_provider(tmp_path):
    database_path = tmp_path / "database" / "studio.db"
    repository = _create_repository(database_path)
    job, original = _create_job_with_binding(repository, "no-reselect-0001", "ltx23")

    signal_a = tmp_path / "started_a.signal"
    result_a = tmp_path / "result_a.jsonl"
    signal_b = tmp_path / "started_b.signal"
    result_b = tmp_path / "result_b.jsonl"

    # Process A claims the job and enters execution (blocking), then is killed.
    proc_a = _spawn_worker(
        database_path, "block", signal_a, result_a,
        worker_id="worker-a",
    )
    _wait_for_signal(signal_a, proc_a)
    proc_a.kill()
    proc_a.wait(timeout=5)

    time.sleep(1.6)  # lease expires

    # Process B recovers; even if the "current default provider" changed to
    # wan2.1, the runner consumes only the persisted ltx23 binding.
    proc_b = _spawn_worker(
        database_path, "record", signal_b, result_b,
        worker_id="worker-b",
    )
    _wait_for_signal(signal_b, proc_b)
    proc_b.wait(timeout=10)
    _cleanup(proc_b)

    results_b = _read_results(result_b)
    assert results_b, "process B never executed"
    assert results_b[0]["provider"] == "ltx23"

    reopened = _create_repository(database_path)
    assert reopened.get_provider_binding(job["id"]) == original


def test_recovered_job_does_not_fallback_when_bound_provider_is_unavailable(tmp_path):
    database_path = tmp_path / "database" / "studio.db"
    repository = _create_repository(database_path)
    job, original = _create_job_with_binding(repository, "no-fallback-0001", "ltx23")

    signal = tmp_path / "started.signal"
    result = tmp_path / "result.jsonl"

    # Worker B executes against an unavailable bound provider: explicit failure.
    proc = _spawn_worker(
        database_path, "fail", signal, result,
        worker_id="worker-b",
    )
    _wait_for_signal(signal, proc)
    proc.wait(timeout=10)
    _cleanup(proc)

    results = _read_results(result)
    assert results and results[0]["provider"] == "ltx23"

    reopened = _create_repository(database_path)
    current = reopened.get_job(job["id"])
    assert current["status"] == "retry_wait" or current["status"] == "failed"
    assert current["final_video"] == ""
    # Binding unchanged, no wan fallback event.
    assert reopened.get_provider_binding(job["id"]) == original
    assert all(r["provider"] == "ltx23" for r in results)


def test_new_process_does_not_replay_terminal_job(tmp_path):
    database_path = tmp_path / "database" / "studio.db"
    repository = _create_repository(database_path)
    job, original = _create_job_with_binding(repository, "no-replay-0001", "ltx23")

    # Mark the job terminal (cancelled) directly.
    with repository.database.transaction() as connection:
        connection.execute(
            "UPDATE jobs SET status='cancelled', desired_state='cancelled' WHERE id=?",
            (job["id"],),
        )

    signal = tmp_path / "started.signal"
    result = tmp_path / "result.jsonl"

    proc = _spawn_worker(
        database_path, "terminal", signal, result,
        worker_id="worker-b",
    )
    # Terminal job must never reach the adapter; give it time and then stop it.
    time.sleep(1.5)
    _cleanup(proc)

    results = _read_results(result)
    assert results == []

    reopened = _create_repository(database_path)
    assert reopened.get_job(job["id"])["status"] == "cancelled"
    assert reopened.get_provider_binding(job["id"]) == original

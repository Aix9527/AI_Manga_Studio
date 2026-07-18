from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

import backend.orchestration.repository as repository_module

from conftest import create_job, insert_step, set_job


NOW = datetime(2026, 7, 19, 4, 0, tzinfo=timezone.utc)


def test_expired_running_job_requeues_unfinished_steps_and_preserves_completed(
    job_repo, running_job
):
    recovered = job_repo.recover_expired_leases(NOW.isoformat())

    job = job_repo.get_job(running_job["id"])
    assert recovered == 1
    assert job["status"] == "queued"
    assert job["worker_id"] is job["lease_until"] is job["run_after"] is None
    assert "恢复" in job["message"]
    assert [step["status"] for step in job["steps"]] == ["completed", "queued"]
    assert job["steps"][0]["finished_at"] is not None
    assert job["steps"][1]["started_at"] is None


def test_recovery_only_changes_expired_running_jobs(job_repo):
    unexpired = create_job(job_repo, "unexpired")
    insert_step(job_repo, unexpired["id"], status="running")
    set_job(
        job_repo,
        unexpired["id"],
        status="running",
        worker_id="live",
        lease_until=(NOW + timedelta(seconds=1)).isoformat(),
    )
    retrying = create_job(job_repo, "non-running")
    insert_step(job_repo, retrying["id"], status="retry_wait")
    set_job(
        job_repo,
        retrying["id"],
        status="retry_wait",
        worker_id="odd",
        lease_until=(NOW - timedelta(seconds=1)).isoformat(),
    )

    assert job_repo.recover_expired_leases(NOW.isoformat()) == 0
    assert job_repo.get_job(unexpired["id"])["status"] == "running"
    assert job_repo.get_job(retrying["id"])["status"] == "retry_wait"


def test_recovery_resets_retry_wait_step_inside_expired_running_job(job_repo):
    job = create_job(job_repo, "recover-retry-step")
    step_id = insert_step(job_repo, job["id"], status="retry_wait")
    set_job(
        job_repo,
        job["id"],
        status="running",
        worker_id="dead",
        lease_until=(NOW - timedelta(seconds=1)).isoformat(),
        run_after=(NOW + timedelta(seconds=30)).isoformat(),
    )
    with job_repo.database.transaction() as connection:
        connection.execute(
            "UPDATE job_steps SET started_at=? WHERE id=?",
            ((NOW - timedelta(seconds=30)).isoformat(), step_id),
        )

    assert job_repo.recover_expired_leases(NOW.isoformat()) == 1
    restored = job_repo.get_job(job["id"])
    assert restored["steps"][0]["status"] == "queued"
    assert restored["steps"][0]["started_at"] is None


def test_bootstrap_creation_activation_and_idempotency(job_repo):
    empty = create_job(job_repo, "empty-bootstrap")

    first = job_repo.ensure_bootstrap_step(empty["id"])
    second = job_repo.ensure_bootstrap_step(empty["id"])

    restored = job_repo.get_job(empty["id"])
    assert first == second
    assert len(restored["steps"]) == 1
    assert restored["steps"][0]["stage_key"] == "input_parse"
    assert restored["steps"][0]["status"] == "running"
    assert restored["steps"][0]["started_at"] is not None


@pytest.mark.parametrize("status", ["pending", "queued", "retry_wait"])
def test_bootstrap_activates_earliest_unfinished_step(job_repo, status):
    job = create_job(job_repo, f"activate-{status}")
    expected = insert_step(job_repo, job["id"], status=status, stage_key="script_plan")

    assert job_repo.ensure_bootstrap_step(job["id"]) == expected
    assert job_repo.get_job(job["id"])["steps"][0]["status"] == "running"


def test_bootstrap_never_resets_completed_step(job_repo):
    job = create_job(job_repo, "completed-bootstrap")
    completed = insert_step(job_repo, job["id"], status="completed")

    with pytest.raises(LookupError, match="no unfinished step"):
        job_repo.ensure_bootstrap_step(job["id"])

    restored = job_repo.get_job(job["id"])
    assert restored["steps"][0]["id"] == completed
    assert restored["steps"][0]["status"] == "completed"


def test_current_step_and_cancel_reads_use_managed_connections(job_repo, monkeypatch):
    job = create_job(job_repo, "managed-reads")
    step_id = insert_step(job_repo, job["id"], status="running")
    original = job_repo.database.connection
    counts = {"entered": 0, "exited": 0}

    @contextmanager
    def counted():
        counts["entered"] += 1
        try:
            with original() as connection:
                yield connection
        finally:
            counts["exited"] += 1

    monkeypatch.setattr(job_repo.database, "connection", counted)

    assert job_repo.current_step_id(job["id"]) == step_id
    assert job_repo.is_cancel_requested(job["id"]) is False
    assert counts == {"entered": 2, "exited": 2}


def test_current_step_and_cancel_reads_raise_for_missing_job(job_repo):
    with pytest.raises(LookupError, match="missing"):
        job_repo.current_step_id("missing")
    with pytest.raises(LookupError, match="missing"):
        job_repo.is_cancel_requested("missing")


def test_finalize_cancel_requires_desired_cancelled_and_is_idempotent(job_repo):
    job = create_job(job_repo, "finalize-cancel")
    completed = insert_step(job_repo, job["id"], status="completed")
    queued = insert_step(job_repo, job["id"], sequence=1)

    assert job_repo.finalize_cancel(job["id"]) is False
    assert job_repo.get_job(job["id"])["status"] == "queued"

    set_job(job_repo, job["id"], desired_state="cancelled")
    assert job_repo.finalize_cancel(job["id"]) is True
    assert job_repo.finalize_cancel(job["id"]) is True
    restored = job_repo.get_job(job["id"])
    statuses = {step["id"]: step["status"] for step in restored["steps"]}
    assert restored["status"] == "cancelled"
    assert statuses[completed] == "completed"
    assert statuses[queued] == "cancelled"


def test_repeated_finalize_cancel_does_not_rewrite_persisted_state(
    job_repo, monkeypatch
):
    job = create_job(job_repo, "durable-idempotent-cancel")
    insert_step(job_repo, job["id"], status="completed")
    insert_step(job_repo, job["id"], sequence=1)
    set_job(job_repo, job["id"], desired_state="cancelled")

    assert job_repo.finalize_cancel(job["id"]) is True
    first = job_repo.get_job(job["id"])
    monkeypatch.setattr(
        repository_module,
        "utcnow",
        lambda: "2099-01-01T00:00:00+00:00",
    )

    assert job_repo.finalize_cancel(job["id"]) is True
    second = job_repo.get_job(job["id"])

    assert second == first

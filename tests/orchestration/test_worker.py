from __future__ import annotations

import threading
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.orchestration.worker import DurableWorker, StepExecutionError
from backend.orchestration.checkpoints import ArtifactDraft
from backend.orchestration.repository import JobRepository, LeaseOwnershipError

from conftest import create_job, insert_step, set_job


NOW = datetime(2026, 7, 19, 4, 0, tzinfo=timezone.utc)


@dataclass
class AlwaysFails:
    repository: JobRepository
    calls: int = 0

    def run_next(self, job, cancel_requested):
        self.calls += 1
        raise StepExecutionError("COMFY_NODE_MISSING", "缺少必要节点")

    def cancel(self, job_id):
        return True


def test_fourth_failure_exhausts_three_retries_and_clears_lease(job_repo, queued_job):
    runner = AlwaysFails(job_repo)
    worker = DurableWorker(job_repo, runner, retry_delays=[0, 0, 0])

    for _ in range(4):
        assert worker.run_once() is True

    job = job_repo.get_job(queued_job["id"])
    step = job["steps"][0]
    assert runner.calls == 4
    assert job["status"] == "failed"
    assert step["status"] == "failed"
    assert step["attempt"] == 4
    assert (step["error_code"], step["error_message"]) == (
        "COMFY_NODE_MISSING",
        "缺少必要节点",
    )
    assert step["finished_at"] is not None
    assert job["finished_at"] is not None
    assert job["worker_id"] is job["lease_until"] is None


def test_retry_is_not_claimable_before_run_after_but_is_claimable_at_deadline(job_repo):
    job = create_job(job_repo, "future-retry")
    insert_step(job_repo, job["id"], status="retry_wait")
    set_job(
        job_repo,
        job["id"],
        status="retry_wait",
        run_after=(NOW + timedelta(seconds=1)).isoformat(),
    )

    assert job_repo.claim_next("early", NOW.isoformat(), (NOW + timedelta(seconds=30)).isoformat()) is None
    claimed = job_repo.claim_next(
        "on-time",
        (NOW + timedelta(seconds=1)).isoformat(),
        (NOW + timedelta(seconds=31)).isoformat(),
    )

    assert claimed["id"] == job["id"]
    assert claimed["worker_id"] == "on-time"


def test_explicit_empty_retry_delays_fail_on_first_attempt(job_repo, queued_job):
    runner = AlwaysFails(job_repo)
    worker = DurableWorker(job_repo, runner, retry_delays=[])

    worker.run_once()

    job = job_repo.get_job(queued_job["id"])
    assert job["status"] == "failed"
    assert job["steps"][0]["attempt"] == 1


def test_retry_wait_is_nonterminal_and_clears_step_start_time(job_repo, queued_job):
    worker = DurableWorker(job_repo, AlwaysFails(job_repo), retry_delays=[0])

    assert worker.run_once() is True

    job = job_repo.get_job(queued_job["id"])
    step = job["steps"][0]
    assert job["status"] == "retry_wait"
    assert job["finished_at"] is None
    assert step["status"] == "retry_wait"
    assert step["started_at"] is None
    assert step["finished_at"] is None


def test_failed_step_pauses_without_run_after_until_job_is_resumed(job_repo, queued_job):
    class PausingFailure(AlwaysFails):
        def run_next(self, job, cancel_requested):
            set_job(self.repository, job["id"], desired_state="paused")
            return super().run_next(job, cancel_requested)

    runner = PausingFailure(job_repo)
    worker = DurableWorker(job_repo, runner, retry_delays=[0])

    assert worker.run_once() is True
    paused = job_repo.get_job(queued_job["id"])
    assert paused["status"] == "paused"
    assert paused["steps"][0]["status"] == "retry_wait"
    assert paused["steps"][0]["started_at"] is None
    assert paused["steps"][0]["finished_at"] is None
    assert paused["finished_at"] is None
    assert paused["run_after"] is None
    assert paused["worker_id"] is paused["lease_until"] is None
    assert worker.run_once() is False

    set_job(job_repo, queued_job["id"], desired_state="running", status="queued")
    assert worker.run_once() is True
    assert runner.calls == 2


def test_cancel_during_run_calls_runner_once_and_preserves_completed_steps(job_repo):
    job = create_job(job_repo, "cancel-boundary")
    completed = insert_step(job_repo, job["id"], status="completed")
    unfinished = insert_step(job_repo, job["id"], sequence=1)
    cancel_called = threading.Event()

    class CancellingRunner:
        calls = 0

        def run_next(self, claimed, cancel_requested):
            set_job(job_repo, claimed["id"], desired_state="cancelled")
            assert cancel_called.wait(timeout=2)
            assert cancel_requested() is True
            return None

        def cancel(self, job_id):
            self.calls += 1
            cancel_called.set()
            return True

    runner = CancellingRunner()
    worker = DurableWorker(
        job_repo,
        runner,
        retry_delays=[],
        lease_seconds=1,
        heartbeat_seconds=0.01,
    )

    assert worker.run_once() is True

    restored = job_repo.get_job(job["id"])
    statuses = {step["id"]: step["status"] for step in restored["steps"]}
    assert runner.calls == 1
    assert restored["status"] == "cancelled"
    assert statuses[completed] == "completed"
    assert statuses[unfinished] == "cancelled"


def test_cancel_backend_exception_does_not_prevent_durable_finalize(job_repo):
    job = create_job(job_repo, "cancel-backend-error")
    completed = insert_step(job_repo, job["id"], status="completed")
    unfinished = insert_step(job_repo, job["id"], sequence=1)
    cancel_attempted = threading.Event()

    class CancelRaises:
        calls = 0

        def run_next(self, claimed, cancel_requested):
            set_job(job_repo, claimed["id"], desired_state="cancelled")
            assert cancel_attempted.wait(timeout=2)
            return None

        def cancel(self, job_id):
            self.calls += 1
            cancel_attempted.set()
            raise RuntimeError("backend cancel unavailable")

    runner = CancelRaises()
    worker = DurableWorker(
        job_repo,
        runner,
        retry_delays=[],
        lease_seconds=1,
        heartbeat_seconds=0.01,
    )

    assert worker.run_once() is True

    restored = job_repo.get_job(job["id"])
    statuses = {step["id"]: step["status"] for step in restored["steps"]}
    assert runner.calls == 1
    assert restored["status"] == "cancelled"
    assert restored["worker_id"] is restored["lease_until"] is None
    assert statuses[completed] == "completed"
    assert statuses[unfinished] == "cancelled"


def test_unexpected_exception_uses_retry_path_and_does_not_leave_running(job_repo, queued_job):
    class Crashes:
        def run_next(self, job, cancel_requested):
            raise RuntimeError("boom")

        def cancel(self, job_id):
            return True

    worker = DurableWorker(job_repo, Crashes(), retry_delays=[])

    assert worker.run_once() is True
    job = job_repo.get_job(queued_job["id"])
    assert job["status"] == "failed"
    assert job["steps"][0]["status"] == "failed"
    assert job["steps"][0]["error_code"] == "UNEXPECTED_STEP_ERROR"
    assert job["steps"][0]["error_message"] == "boom"
    assert worker.run_once() is False


def test_cancel_requested_after_post_run_check_wins_atomically_over_failure(
    job_repo, monkeypatch
):
    job = create_job(job_repo, "cancel-failure-race")
    completed = insert_step(job_repo, job["id"], status="completed")
    failing = insert_step(job_repo, job["id"], sequence=1)
    original_current_step_id = job_repo.current_step_id
    race_triggered = False

    def cancel_before_failure_transaction(job_id):
        nonlocal race_triggered
        race_triggered = True
        set_job(job_repo, job_id, desired_state="cancelled")
        return original_current_step_id(job_id)

    monkeypatch.setattr(job_repo, "current_step_id", cancel_before_failure_transaction)
    worker = DurableWorker(job_repo, AlwaysFails(job_repo), retry_delays=[0])

    assert worker.run_once() is True

    restored = job_repo.get_job(job["id"])
    steps = {step["id"]: step for step in restored["steps"]}
    assert race_triggered is True
    assert restored["status"] == "cancelled"
    assert restored["worker_id"] is restored["lease_until"] is None
    assert restored["run_after"] is None
    assert restored["finished_at"] is not None
    assert steps[completed]["status"] == "completed"
    assert steps[failing]["status"] == "cancelled"
    assert steps[failing]["attempt"] == 0
    assert steps[failing]["error_code"] == steps[failing]["error_message"] == ""


def test_run_once_returns_false_when_no_job(job_repo):
    worker = DurableWorker(job_repo, AlwaysFails(job_repo), retry_delays=[])

    assert worker.run_once() is False


@pytest.mark.parametrize(
    "options",
    [
        {"lease_seconds": float("nan")},
        {"lease_seconds": float("inf")},
        {"lease_seconds": 1, "heartbeat_seconds": float("nan")},
        {"lease_seconds": 1, "heartbeat_seconds": float("inf")},
        {"retry_delays": [float("nan")]},
        {"retry_delays": [float("inf")]},
    ],
)
def test_worker_rejects_nonfinite_timing_values(job_repo, options):
    with pytest.raises(ValueError, match="finite"):
        DurableWorker(job_repo, AlwaysFails(job_repo), **options)


def test_serve_logs_unexpected_iteration_error_and_stops(
    job_repo, monkeypatch, caplog
):
    worker = DurableWorker(job_repo, AlwaysFails(job_repo), retry_delays=[])

    def crash_once():
        worker.stop()
        raise RuntimeError("iteration crashed")

    monkeypatch.setattr(worker, "run_once", crash_once)

    with caplog.at_level(logging.ERROR, logger="backend.orchestration.worker"):
        worker.serve(poll_seconds=0.01)

    assert any(
        "worker iteration failed" in record.getMessage()
        and record.exc_info is not None
        for record in caplog.records
    )


@pytest.mark.parametrize(
    "poll_seconds",
    [float("nan"), float("inf"), float("-inf")],
)
def test_serve_rejects_nonfinite_poll_interval_without_running_jobs(
    job_repo, monkeypatch, poll_seconds
):
    worker = DurableWorker(job_repo, AlwaysFails(job_repo), retry_delays=[])
    calls = 0

    def unexpected_run():
        nonlocal calls
        calls += 1
        worker.stop()
        return False

    monkeypatch.setattr(worker, "run_once", unexpected_run)

    with pytest.raises(ValueError, match="poll_seconds must be finite and positive"):
        worker.serve(poll_seconds=poll_seconds)

    assert calls == 0


@pytest.mark.parametrize(
    ("mode", "desired_state", "expected"),
    [
        ("automatic", "running", "queued"),
        ("manual_review", "running", "waiting_review"),
        ("automatic", "paused", "paused"),
    ],
)
def test_successful_outcome_checkpoints_real_artifact_and_updates_job(
    job_repo, tmp_path, mode, desired_state, expected
):
    job = create_job(job_repo, f"success-{mode}-{desired_state}", mode=mode)
    step_id = insert_step(job_repo, job["id"])
    output = tmp_path / f"{mode}-{desired_state}.dat"
    output.write_bytes(b"verified output")
    outcome = SimpleNamespace(
        step_id=step_id,
        input_hash="input-v1",
        artifacts=[ArtifactDraft.from_path("file", output)],
        progress=0.5,
        message="阶段完成",
        final_video="",
    )

    class Succeeds:
        def run_next(self, claimed, cancel_requested):
            if desired_state != "running":
                set_job(job_repo, claimed["id"], desired_state=desired_state)
            return outcome

        def cancel(self, job_id):
            return True

    worker = DurableWorker(job_repo, Succeeds(), retry_delays=[])

    assert worker.run_once() is True
    restored = job_repo.get_job(job["id"])
    assert restored["status"] == expected
    assert restored["steps"][0]["status"] == "completed"
    with job_repo.database.connection() as connection:
        artifact = connection.execute(
            "SELECT * FROM artifacts WHERE step_id=? AND active=1", (step_id,)
        ).fetchone()
    assert artifact is not None
    assert Path(artifact["path"]).read_bytes() == b"verified output"


def test_two_repositories_can_only_claim_queued_job_once(job_repo, queued_job):
    second = JobRepository(job_repo.database)
    barrier = threading.Barrier(2)

    def claim(repository, worker_id):
        barrier.wait(timeout=2)
        return repository.claim_next(
            worker_id,
            NOW.isoformat(),
            (NOW + timedelta(seconds=30)).isoformat(),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = [
            executor.submit(claim, repository, worker_id)
            for repository, worker_id in ((job_repo, "one"), (second, "two"))
        ]
        results = [future.result(timeout=5) for future in claims]

    winners = [result for result in results if result is not None]
    assert len(winners) == 1
    assert winners[0]["id"] == queued_job["id"]


def test_claim_filters_jobs_that_do_not_desire_running(job_repo):
    job = create_job(job_repo, "paused-claim")
    insert_step(job_repo, job["id"])
    set_job(job_repo, job["id"], desired_state="paused")

    assert job_repo.claim_next(
        "worker", NOW.isoformat(), (NOW + timedelta(seconds=30)).isoformat()
    ) is None


def test_renew_lease_requires_live_current_owner(job_repo, queued_job):
    lease_until = (NOW + timedelta(seconds=30)).isoformat()
    assert job_repo.claim_next("owner", NOW.isoformat(), lease_until)

    assert job_repo.renew_lease(
        queued_job["id"], "owner", NOW.isoformat(), (NOW + timedelta(seconds=60)).isoformat()
    ) is True
    assert job_repo.renew_lease(
        queued_job["id"], "other", NOW.isoformat(), (NOW + timedelta(seconds=90)).isoformat()
    ) is False
    assert job_repo.renew_lease(
        queued_job["id"], "owner", (NOW + timedelta(seconds=61)).isoformat(), (NOW + timedelta(seconds=120)).isoformat()
    ) is False


def test_claim_rejects_lease_that_is_not_after_now(job_repo, queued_job):
    now = datetime.now(timezone.utc).isoformat()

    with pytest.raises(ValueError, match="lease_until must be after now"):
        job_repo.claim_next("owner", now, now)

    assert job_repo.get_job(queued_job["id"])["status"] == "queued"


def test_renew_rejects_new_lease_that_is_not_after_now(job_repo, queued_job):
    lease_until = (NOW + timedelta(seconds=30)).isoformat()
    assert job_repo.claim_next("owner", NOW.isoformat(), lease_until)

    assert job_repo.renew_lease(
        queued_job["id"], "owner", NOW.isoformat(), NOW.isoformat()
    ) is False
    assert job_repo.get_job(queued_job["id"])["lease_until"] == lease_until


def test_expired_owner_cannot_complete_step(job_repo, tmp_path):
    job = create_job(job_repo, "expired-complete")
    step_id = insert_step(job_repo, job["id"], status="running")
    set_job(
        job_repo,
        job["id"],
        status="running",
        worker_id="expired-owner",
        lease_until="2000-01-01T00:00:00+00:00",
    )
    output = tmp_path / "expired-complete.dat"
    output.write_bytes(b"must not checkpoint")

    with pytest.raises(LeaseOwnershipError):
        job_repo.complete_step(
            job["id"],
            step_id,
            "input-hash",
            [ArtifactDraft.from_path("file", output)],
            expected_worker_id="expired-owner",
        )

    restored = job_repo.get_job(job["id"])
    assert restored["steps"][0]["status"] == "running"
    with job_repo.database.connection() as connection:
        assert connection.execute("SELECT 1 FROM artifacts").fetchone() is None


def test_expired_owner_cannot_fail_step(job_repo):
    job = create_job(job_repo, "expired-fail")
    step_id = insert_step(job_repo, job["id"], status="running")
    set_job(
        job_repo,
        job["id"],
        status="running",
        worker_id="expired-owner",
        lease_until="2000-01-01T00:00:00+00:00",
    )

    with pytest.raises(LeaseOwnershipError):
        job_repo.fail_or_retry_step(
            job["id"],
            step_id,
            "STALE_FAILURE",
            "must not write",
            0,
            None,
            "expired-owner",
        )

    restored = job_repo.get_job(job["id"])
    assert restored["status"] == "running"
    assert restored["steps"][0]["attempt"] == 0
    assert restored["steps"][0]["error_code"] == ""


def test_expired_owner_cannot_apply_outcome(job_repo, tmp_path):
    job = create_job(job_repo, "expired-outcome")
    step_id = insert_step(job_repo, job["id"], status="running")
    set_job(
        job_repo,
        job["id"],
        status="running",
        worker_id="expired-owner",
        lease_until="2000-01-01T00:00:00+00:00",
    )
    output = tmp_path / "expired-outcome.dat"
    output.write_bytes(b"stale outcome")
    outcome = SimpleNamespace(
        step_id=step_id,
        input_hash="input-hash",
        artifacts=[ArtifactDraft.from_path("file", output)],
        progress=1.0,
        message="stale",
        final_video="",
    )

    with pytest.raises(LeaseOwnershipError):
        job_repo.apply_step_outcome(job["id"], outcome, "expired-owner")

    restored = job_repo.get_job(job["id"])
    assert restored["status"] == "running"
    assert restored["steps"][0]["status"] == "running"
    with job_repo.database.connection() as connection:
        assert connection.execute("SELECT 1 FROM artifacts").fetchone() is None


def test_expired_owner_cannot_create_bootstrap_step(job_repo):
    job = create_job(job_repo, "expired-bootstrap")
    set_job(
        job_repo,
        job["id"],
        status="running",
        worker_id="expired-owner",
        lease_until="2000-01-01T00:00:00+00:00",
    )

    with pytest.raises(LeaseOwnershipError):
        job_repo.ensure_bootstrap_step(
            job["id"], expected_worker_id="expired-owner"
        )

    assert job_repo.get_job(job["id"])["steps"] == []


def test_worker_heartbeats_during_long_run_and_joins_thread(job_repo, queued_job, monkeypatch):
    renewed = threading.Event()
    original = job_repo.renew_lease
    calls = []

    def observe(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(result)
        renewed.set()
        return result

    monkeypatch.setattr(job_repo, "renew_lease", observe)

    class WaitsForHeartbeat:
        def run_next(self, job, cancel_requested):
            assert renewed.wait(timeout=2)
            return None

        def cancel(self, job_id):
            return True

    worker = DurableWorker(
        job_repo,
        WaitsForHeartbeat(),
        retry_delays=[],
        lease_seconds=1,
        heartbeat_seconds=0.01,
    )

    assert worker.run_once() is True
    assert calls and calls[0] is True
    assert not any(
        thread.is_alive() and thread.name == f"durable-heartbeat-{worker.worker_id}"
        for thread in threading.enumerate()
    )


@pytest.mark.parametrize("renew_failure", ["returns_false", "raises"])
def test_lost_lease_notifies_runner_and_discards_old_outcome(
    job_repo, queued_job, tmp_path, monkeypatch, renew_failure
):
    step_id = job_repo.get_job(queued_job["id"])["steps"][0]["id"]
    cancel_called = threading.Event()
    output = tmp_path / f"lost-lease-{renew_failure}.dat"
    output.write_bytes(b"stale output")
    outcome = SimpleNamespace(
        step_id=step_id,
        input_hash="stale-input",
        artifacts=[ArtifactDraft.from_path("file", output)],
        progress=1.0,
        message="stale",
        final_video="",
    )

    def lose_lease(*args, **kwargs):
        if renew_failure == "raises":
            raise RuntimeError("database unavailable")
        return False

    monkeypatch.setattr(job_repo, "renew_lease", lose_lease)

    class WaitsForLeaseLoss:
        calls = 0

        def run_next(self, job, cancel_requested):
            assert cancel_called.wait(timeout=2)
            assert cancel_requested() is True
            return outcome

        def cancel(self, job_id):
            self.calls += 1
            cancel_called.set()
            return True

    runner = WaitsForLeaseLoss()
    worker = DurableWorker(
        job_repo,
        runner,
        retry_delays=[],
        lease_seconds=1,
        heartbeat_seconds=0.01,
    )

    assert worker.run_once() is True

    restored = job_repo.get_job(queued_job["id"])
    assert runner.calls == 1
    assert restored["status"] == "running"
    assert restored["steps"][0]["status"] == "running"
    with job_repo.database.connection() as connection:
        assert connection.execute("SELECT 1 FROM artifacts").fetchone() is None
    assert not any(
        thread.is_alive() and thread.name == f"durable-heartbeat-{worker.worker_id}"
        for thread in threading.enumerate()
    )


def test_stale_worker_cannot_checkpoint_or_fail_after_lease_is_reassigned(
    job_repo, queued_job, tmp_path
):
    step_id = job_repo.get_job(queued_job["id"])["steps"][0]["id"]
    assert job_repo.claim_next(
        "old", NOW.isoformat(), (NOW + timedelta(seconds=30)).isoformat()
    )
    job_repo.ensure_bootstrap_step(queued_job["id"])
    set_job(
        job_repo,
        queued_job["id"],
        worker_id="new",
        lease_until=(NOW + timedelta(seconds=60)).isoformat(),
    )
    output = tmp_path / "stale.dat"
    output.write_bytes(b"stale")
    outcome = SimpleNamespace(
        step_id=step_id,
        input_hash="stale-input",
        artifacts=[ArtifactDraft.from_path("file", output)],
        progress=1.0,
        message="stale",
        final_video="",
    )

    with pytest.raises(LeaseOwnershipError):
        job_repo.apply_step_outcome(queued_job["id"], outcome, "old")
    with pytest.raises(LeaseOwnershipError):
        job_repo.fail_or_retry_step(
            queued_job["id"],
            step_id,
            "OLD_ERROR",
            "stale",
            0,
            None,
            "old",
        )

    restored = job_repo.get_job(queued_job["id"])
    assert restored["worker_id"] == "new"
    assert restored["status"] == "running"
    assert restored["steps"][0]["status"] == "running"
    with job_repo.database.connection() as connection:
        assert connection.execute("SELECT 1 FROM artifacts").fetchone() is None

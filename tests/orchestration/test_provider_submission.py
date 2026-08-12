from __future__ import annotations

import pytest

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import (
    JobRepository,
    ProviderSubmissionConflictError,
)
from backend.orchestration.provider_submission import (
    SubmissionOutcome,
    submit_or_resume,
)
from backend.orchestration.schemas import JobCreate

from conftest import create_job


class FakeSubmitter:
    def __init__(self, remote_id="prompt-123"):
        self.remote_id = remote_id
        self.calls = 0

    def submit(self):
        self.calls += 1
        return self.remote_id


def _job_with_step(job_repo):
    job = create_job(job_repo, "submission")
    with job_repo.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO job_steps(id, job_id, sequence, stage_key, shot_id, status)
            VALUES ('step-1', ?, 0, 'video', '', 'queued')
            """,
            (job["id"],),
        )
    return job


def test_submission_reservation_is_first_write_wins(job_repo):
    job = _job_with_step(job_repo)
    first, created1 = job_repo.reserve_provider_submission(
        job["id"], "step-1", 0, "ltx23"
    )
    second, created2 = job_repo.reserve_provider_submission(
        job["id"], "step-1", 0, "ltx23"
    )

    assert created1 is True
    assert created2 is False
    assert first["id"] == second["id"]
    assert second["status"] == "reserved"
    assert second["remote_submission_id"] is None


def test_remote_submission_id_is_immutable(job_repo):
    job = _job_with_step(job_repo)
    submission, _ = job_repo.reserve_provider_submission(
        job["id"], "step-1", 0, "ltx23"
    )

    job_repo.record_provider_submission_id(
        submission["submission_key"], "prompt-123"
    )

    # idempotent same-id write is fine
    job_repo.record_provider_submission_id(
        submission["submission_key"], "prompt-123"
    )

    # different id must conflict
    with pytest.raises(ProviderSubmissionConflictError):
        job_repo.record_provider_submission_id(
            submission["submission_key"], "prompt-999"
        )


def test_restart_with_persisted_prompt_id_does_not_resubmit(tmp_path):
    database_path = tmp_path / "orchestration.db"
    repository = JobRepository(OrchestrationDatabase(database_path))
    job = _job_with_step(repository)

    submitter = FakeSubmitter("prompt-abc")
    first = submit_or_resume(
        repository, job["id"], "step-1", 0, "ltx23", submitter
    )
    assert first.outcome == SubmissionOutcome.SUBMITTED
    assert submitter.calls == 1

    # Simulate restart: new repository, same DB.
    reopened = JobRepository(OrchestrationDatabase(database_path))
    second = submit_or_resume(
        reopened, job["id"], "step-1", 0, "ltx23", FakeSubmitter("prompt-xyz")
    )

    assert second.outcome == SubmissionOutcome.RESUMED
    assert second.remote_submission_id == "prompt-abc"


def test_two_workers_cannot_reserve_same_logical_attempt_twice(job_repo):
    job = _job_with_step(job_repo)
    w1, created1 = job_repo.reserve_provider_submission(
        job["id"], "step-1", 0, "ltx23"
    )
    w2, created2 = job_repo.reserve_provider_submission(
        job["id"], "step-1", 0, "ltx23"
    )

    assert created1 is True
    assert created2 is False


def test_kill_after_prompt_id_persisted_resumes_without_submit(tmp_path):
    database_path = tmp_path / "orchestration.db"
    repository = JobRepository(OrchestrationDatabase(database_path))
    job = _job_with_step(repository)

    submission, _ = repository.reserve_provider_submission(
        job["id"], "step-1", 0, "ltx23"
    )
    # Worker A persisted the remote id, then "died".
    repository.record_provider_submission_id(
        submission["submission_key"], "prompt-777"
    )

    # Worker B comes up fresh.
    reopened = JobRepository(OrchestrationDatabase(database_path))
    submitter = FakeSubmitter("prompt-should-not-be-used")
    decision = submit_or_resume(
        reopened, job["id"], "step-1", 0, "ltx23", submitter
    )

    assert decision.outcome == SubmissionOutcome.RESUMED
    assert decision.remote_submission_id == "prompt-777"
    assert submitter.calls == 0


def test_uncertain_submission_is_not_blindly_resubmitted(job_repo):
    job = _job_with_step(job_repo)
    submission, _ = job_repo.reserve_provider_submission(
        job["id"], "step-1", 0, "ltx23"
    )

    # Crash window: status -> uncertain, no remote id.
    with job_repo.database.transaction() as connection:
        connection.execute(
            "UPDATE provider_submissions SET status='uncertain' "
            "WHERE submission_key = ?",
            (submission["submission_key"],),
        )

    submitter = FakeSubmitter("prompt-999")
    decision = submit_or_resume(
        job_repo, job["id"], "step-1", 0, "ltx23", submitter
    )

    assert decision.outcome == SubmissionOutcome.UNCERTAIN
    assert submitter.calls == 0

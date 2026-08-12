from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class SubmissionOutcome(str, Enum):
    SUBMITTED = "submitted"
    RESUMED = "resumed"
    WAIT = "wait"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class SubmissionDecision:
    outcome: SubmissionOutcome
    submission: dict[str, Any]
    remote_submission_id: str | None = None


class SubmissionRepository(Protocol):
    def reserve_provider_submission(
        self,
        job_id: str,
        step_id: str,
        attempt: int,
        provider: str,
    ) -> tuple[dict[str, Any], bool]:
        ...

    def record_provider_submission_id(
        self,
        submission_key: str,
        remote_submission_id: str,
        status: str = "submitted",
    ) -> dict[str, Any]:
        ...


class ProviderSubmitter(Protocol):
    def submit(self) -> str:
        """Submit to the provider and return the remote submission id."""


def submit_or_resume(
    repository: SubmissionRepository,
    job_id: str,
    step_id: str,
    attempt: int,
    provider: str,
    submitter: ProviderSubmitter,
) -> SubmissionDecision:
    """Submit exactly once per logical attempt, else resume or wait.

    - persisted remote id exists  -> RESUMED (never re-submit)
    - reservation created by us   -> SUBMIT then record id
    - reservation created by peer -> WAIT (do not submit)
    - persisted status uncertain  -> UNCERTAIN (do not blindly resubmit)
    """
    submission, created = repository.reserve_provider_submission(
        job_id, step_id, attempt, provider
    )

    if submission.get("status") == "uncertain":
        return SubmissionDecision(
            SubmissionOutcome.UNCERTAIN, submission,
            submission.get("remote_submission_id"),
        )

    existing = submission.get("remote_submission_id")
    if existing:
        return SubmissionDecision(
            SubmissionOutcome.RESUMED, submission, existing
        )

    if not created:
        # Another worker holds the reservation and may be submitting.
        return SubmissionDecision(SubmissionOutcome.WAIT, submission)

    remote_id = submitter.submit()

    updated = repository.record_provider_submission_id(
        submission["submission_key"],
        remote_id,
    )
    return SubmissionDecision(
        SubmissionOutcome.SUBMITTED, updated, remote_id
    )


def mark_uncertain(
    repository: SubmissionRepository,
    submission_key: str,
) -> dict[str, Any]:
    """Mark a reservation as uncertain after a crash window.

    The provider may or may not have received the submission; the caller must
    decide explicitly rather than blindly resubmitting.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    with repository.database.transaction() as connection:
        connection.execute(
            """
            UPDATE provider_submissions
            SET status = 'uncertain', updated_at = ?
            WHERE submission_key = ? AND remote_submission_id IS NULL
            """,
            (now, submission_key),
        )
        row = connection.execute(
            "SELECT * FROM provider_submissions WHERE submission_key = ?",
            (submission_key,),
        ).fetchone()
    return dict(row)

from __future__ import annotations

import logging
from typing import Any

from backend.orchestration.schemas import JobCreate


logger = logging.getLogger(__name__)


class JobService:
    def __init__(self, repository, runner):
        self.repository = repository
        self.runner = runner

    def create(self, command: JobCreate) -> dict[str, Any]:
        created = self.repository.create_job(command)
        return self.repository.get_job(created["id"])

    def current(self) -> dict[str, Any] | None:
        return self.repository.get_current_job()

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self.repository.get_job(job_id)

    def list(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        return self.repository.list_jobs(limit, offset)

    def pause(
        self, job_id: str, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        return self.repository.request_state(job_id, "paused", idempotency_key)

    def resume(
        self, job_id: str, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        return self.repository.resume_job(job_id, idempotency_key)

    def retry(
        self,
        job_id: str,
        step_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return self.repository.retry_failed_step(
            job_id, step_id, idempotency_key
        )

    def cancel(
        self, job_id: str, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        outcome = self.repository.cancel_job(job_id, idempotency_key)
        if outcome.applied:
            try:
                self.runner.cancel(job_id)
            except Exception:
                logger.warning(
                    "runner cancellation failed for job %s",
                    job_id,
                    exc_info=True,
                )
        return outcome.job

    def rollback_preview(self, job_id: str, step_id: str) -> dict[str, Any]:
        return {
            "step_id": step_id,
            "invalidated_step_ids": self.repository.rollback_preview(
                job_id, step_id
            ),
        }

    def rollback(
        self,
        job_id: str,
        step_id: str,
        confirmed: list[str],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return self.repository.rollback_steps(
            job_id, step_id, confirmed, idempotency_key
        )

    def review(
        self,
        job_id: str,
        step_id: str,
        action: str,
        comment: str,
        patch: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return self.repository.record_review(
            job_id, step_id, action, comment, patch, idempotency_key
        )

from __future__ import annotations

import logging
import math
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol
from uuid import uuid4

from backend.orchestration.repository import LeaseOwnershipError


logger = logging.getLogger(__name__)


class StepExecutionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class StepRunner(Protocol):
    def run_next(
        self,
        job: dict,
        cancel_requested: Callable[[], bool],
    ) -> object | None: ...

    def cancel(self, job_id: str) -> bool: ...


class DurableWorker:
    def __init__(
        self,
        repository,
        runner: StepRunner,
        retry_delays: list[float] | None = None,
        lease_seconds: float = 30,
        heartbeat_seconds: float | None = None,
        worker_id: str | None = None,
    ):
        if not math.isfinite(lease_seconds):
            raise ValueError("lease_seconds must be finite")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if retry_delays is not None:
            if any(not math.isfinite(delay) for delay in retry_delays):
                raise ValueError("retry delays must be finite")
            if any(delay < 0 for delay in retry_delays):
                raise ValueError("retry delays must be non-negative")
        heartbeat = lease_seconds / 3 if heartbeat_seconds is None else heartbeat_seconds
        if not math.isfinite(heartbeat):
            raise ValueError("heartbeat_seconds must be finite")
        if heartbeat <= 0 or heartbeat >= lease_seconds:
            raise ValueError("heartbeat_seconds must be positive and less than lease_seconds")

        self.repository = repository
        self.runner = runner
        self.retry_delays = [5, 15, 45] if retry_delays is None else list(retry_delays)
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat
        self.worker_id = str(uuid4()) if worker_id is None else worker_id
        self._stop = threading.Event()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def run_once(self) -> bool:
        now = self._now()
        self.repository.recover_expired_leases(now.isoformat())
        job = self.repository.claim_next(
            self.worker_id,
            now.isoformat(),
            (now + timedelta(seconds=self.lease_seconds)).isoformat(),
        )
        if job is None:
            return False

        try:
            self.repository.ensure_bootstrap_step(
                job["id"], expected_worker_id=self.worker_id
            )
        except LookupError:
            pass

        heartbeat_stop = threading.Event()
        lease_lost = threading.Event()
        cancel_sent = threading.Event()

        def request_cancel_once() -> None:
            if cancel_sent.is_set():
                return
            cancel_sent.set()
            try:
                self.runner.cancel(job["id"])
            except Exception:
                logger.warning(
                    "runner cancellation failed for job %s",
                    job["id"],
                    exc_info=True,
                )

        def heartbeat() -> None:
            while not heartbeat_stop.wait(self.heartbeat_seconds):
                beat = self._now()
                try:
                    renewed = self.repository.renew_lease(
                        job["id"],
                        self.worker_id,
                        beat.isoformat(),
                        (beat + timedelta(seconds=self.lease_seconds)).isoformat(),
                    )
                except Exception:
                    lease_lost.set()
                    request_cancel_once()
                    return
                if not renewed:
                    lease_lost.set()
                    request_cancel_once()
                    return
                try:
                    if self.repository.is_cancel_requested(job["id"]):
                        request_cancel_once()
                except Exception:
                    lease_lost.set()
                    request_cancel_once()
                    return

        def cancellation_requested() -> bool:
            if lease_lost.is_set():
                return True
            try:
                return self.repository.is_cancel_requested(job["id"])
            except Exception:
                lease_lost.set()
                request_cancel_once()
                return True

        heartbeat_thread = threading.Thread(
            target=heartbeat,
            name=f"durable-heartbeat-{self.worker_id}",
            daemon=True,
        )
        heartbeat_thread.start()
        outcome: object | None = None
        failure: StepExecutionError | None = None
        try:
            outcome = self.runner.run_next(
                job,
                cancellation_requested,
            )
        except StepExecutionError as error:
            failure = error
        except Exception as error:
            failure = StepExecutionError("UNEXPECTED_STEP_ERROR", str(error))
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join()

        try:
            cancel_requested = self.repository.is_cancel_requested(job["id"])
        except Exception:
            lease_lost.set()
            request_cancel_once()
            cancel_requested = False
        if cancel_requested:
            request_cancel_once()
            self.repository.finalize_cancel(job["id"])
            return True

        if lease_lost.is_set():
            return True

        try:
            if failure is not None:
                step_id = self.repository.current_step_id(job["id"])
                current = self.repository.get_job(job["id"])
                step = next(item for item in current["steps"] if item["id"] == step_id)
                delay = None
                if self.retry_delays:
                    delay = self.retry_delays[
                        min(int(step["attempt"]), len(self.retry_delays) - 1)
                    ]
                retry_at = (
                    None
                    if delay is None
                    else (self._now() + timedelta(seconds=delay)).isoformat()
                )
                self.repository.fail_or_retry_step(
                    job["id"],
                    step_id,
                    failure.code,
                    str(failure),
                    len(self.retry_delays),
                    retry_at,
                    self.worker_id,
                )
            elif outcome is not None:
                self.repository.apply_step_outcome(
                    job["id"], outcome, self.worker_id
                )
        except LeaseOwnershipError:
            pass
        return True

    def serve(self, poll_seconds: float = 0.5) -> None:
        if not math.isfinite(poll_seconds) or poll_seconds <= 0:
            raise ValueError("poll_seconds must be finite and positive")
        while not self._stop.is_set():
            try:
                worked = self.run_once()
            except Exception:
                logger.exception("worker iteration failed")
                worked = False
            if not worked:
                self._stop.wait(poll_seconds)

    def stop(self) -> None:
        self._stop.set()

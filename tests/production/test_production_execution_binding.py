from __future__ import annotations

import pytest

from backend.orchestration.worker import StepExecutionError
from backend.orchestration.repository import JobRepository
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.schemas import JobCreate, ProviderBinding
from backend.production.contracts import (
    ProductionExecutionRequest,
    ProductionExecutionResult,
)
from backend.production.executor import ProductionStepRunner
from backend.production.unavailable import UnavailableProductionAdapter

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "orchestration"))

from conftest import create_job, insert_step, set_job


@pytest.fixture
def job_repo(tmp_path):
    from backend.orchestration.database import OrchestrationDatabase

    return JobRepository(OrchestrationDatabase(tmp_path / "orchestration.db"))


@pytest.fixture
def queued_job(job_repo):
    job = create_job(job_repo, "queued")
    insert_step(job_repo, job["id"])
    return job


@pytest.fixture
def running_job(job_repo):
    from datetime import datetime, timezone

    job = create_job(job_repo, "running")
    set_job(
        job_repo,
        job["id"],
        status="running",
        worker_id="dead-worker",
        lease_until="2000-01-01T00:00:00+00:00",
    )
    insert_step(
        job_repo,
        job["id"],
        status="completed",
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    insert_step(
        job_repo,
        job["id"],
        sequence=1,
        status="running",
        stage_key="script_plan",
    )
    return job


class RecordingAdapter:
    def __init__(self):
        self.requests = []
        self.cancel_calls = 0

    def execute(self, request):
        self.requests.append(request)
        return ProductionExecutionResult(
            artifacts=[],
            metadata={"adapter": "recording"},
        )

    def cancel(self, job_id):
        self.cancel_calls += 1
        return True


def _h3_binding() -> ProviderBinding:
    return ProviderBinding(
        provider="h3",
        route="video",
        model="MiniMax-H3",
        workflow="h3/reference-video",
        metadata={"binding_version": 1},
    )


def test_unbound_job_does_not_execute_and_raises_required(job_repo, queued_job):
    adapter = RecordingAdapter()
    runner = ProductionStepRunner(repository=job_repo, execution_port=adapter)

    with pytest.raises(StepExecutionError) as exc_info:
        runner.run_next(queued_job, lambda: False)

    assert exc_info.value.code == "PROVIDER_BINDING_REQUIRED"
    assert adapter.requests == []


def test_bound_job_passes_binding_unchanged_to_adapter(job_repo, queued_job):
    adapter = RecordingAdapter()
    runner = ProductionStepRunner(repository=job_repo, execution_port=adapter)
    binding = _h3_binding()
    job_repo.set_provider_binding(queued_job["id"], binding)

    runner.run_next(queued_job, lambda: False)

    assert len(adapter.requests) == 1
    request = adapter.requests[0]
    assert request.job_id == queued_job["id"]
    assert request.provider_binding == binding


def test_binding_survives_reopen_and_runner_consumes_original(tmp_path):
    database_path = tmp_path / "orchestration.db"
    repository = JobRepository(OrchestrationDatabase(database_path))
    job = create_job(repository, "binding-reopen-exec")

    binding = _h3_binding()
    repository.set_provider_binding(job["id"], binding)

    reopened = JobRepository(OrchestrationDatabase(database_path))
    adapter = RecordingAdapter()
    runner = ProductionStepRunner(repository=reopened, execution_port=adapter)

    runner.run_next(job, lambda: False)

    assert len(adapter.requests) == 1
    assert adapter.requests[0].provider_binding == binding


def test_lease_recovery_does_not_change_binding(job_repo, running_job):
    from datetime import datetime, timezone

    adapter = RecordingAdapter()
    runner = ProductionStepRunner(repository=job_repo, execution_port=adapter)
    binding = _h3_binding()
    job_repo.set_provider_binding(running_job["id"], binding)

    recovered = job_repo.recover_expired_leases(
        datetime(2026, 7, 19, 4, 0, tzinfo=timezone.utc).isoformat()
    )
    assert recovered == 1

    job = job_repo.get_job(running_job["id"])
    assert job_repo.get_provider_binding(running_job["id"]) == binding

    runner.run_next(job, lambda: False)
    assert adapter.requests[0].provider_binding == binding


def test_execution_port_cannot_mutate_binding(job_repo, queued_job):
    class MutatingAdapter:
        def execute(self, request):
            return ProductionExecutionResult(
                artifacts=[],
                metadata={"provider": "ltx23", "rebind_attempt": True},
            )

        def cancel(self, job_id):
            return False

    runner = ProductionStepRunner(repository=job_repo, execution_port=MutatingAdapter())
    binding = _h3_binding()
    job_repo.set_provider_binding(queued_job["id"], binding)

    runner.run_next(queued_job, lambda: False)

    assert job_repo.get_provider_binding(queued_job["id"]) == binding


def test_unavailable_adapter_keeps_legacy_behavior(job_repo, queued_job):
    runner = ProductionStepRunner(
        repository=job_repo,
        execution_port=UnavailableProductionAdapter(),
    )
    binding = _h3_binding()
    job_repo.set_provider_binding(queued_job["id"], binding)

    with pytest.raises(StepExecutionError) as exc_info:
        runner.run_next(queued_job, lambda: False)

    assert exc_info.value.code == "PIPELINE_NOT_READY"

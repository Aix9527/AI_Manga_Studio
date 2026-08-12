from __future__ import annotations

import pytest

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import (
    JobRepository,
    ProviderBindingConflictError,
)
from backend.orchestration.schemas import JobCreate, ProviderBinding

from conftest import create_job


def _h3_binding() -> ProviderBinding:
    return ProviderBinding(
        provider="h3",
        route="video",
        model="MiniMax-H3",
        workflow="h3/reference-video",
        metadata={"binding_version": 1, "source": "provider-router"},
    )


def _wan_binding() -> ProviderBinding:
    return ProviderBinding(
        provider="wan",
        route="video",
        model="wan2.2-ti2v-5b",
        workflow="wan22_ti2v5b_native",
        metadata={"binding_version": 1, "source": "provider-router"},
    )


def test_new_job_has_no_provider_binding(job_repo):
    job = create_job(job_repo, "binding-new")

    assert job_repo.get_provider_binding(job["id"]) is None

    reopened = job_repo.get_job(job["id"])
    assert reopened["provider_binding"] is None


def test_first_binding_is_persisted(job_repo):
    job = create_job(job_repo, "binding-save")

    expected = _h3_binding()
    result = job_repo.set_provider_binding(job["id"], expected)

    assert result == expected
    assert job_repo.get_provider_binding(job["id"]) == expected

    reopened = job_repo.get_job(job["id"])
    assert reopened["provider_binding"] == expected.model_dump(mode="json")


def test_same_binding_is_idempotent(job_repo):
    job = create_job(job_repo, "binding-idempotent")

    expected = _h3_binding()
    first = job_repo.set_provider_binding(job["id"], expected)
    second = job_repo.set_provider_binding(job["id"], expected)

    assert first == expected
    assert second == expected
    assert job_repo.get_provider_binding(job["id"]) == expected


def test_different_binding_cannot_replace_existing_binding(job_repo):
    job = create_job(job_repo, "binding-conflict")

    expected = _h3_binding()
    job_repo.set_provider_binding(job["id"], expected)

    with pytest.raises(ProviderBindingConflictError):
        job_repo.set_provider_binding(job["id"], _wan_binding())

    assert job_repo.get_provider_binding(job["id"]) == expected


def test_binding_survives_runtime_reopen(tmp_path):
    database_path = tmp_path / "orchestration.db"
    repository = JobRepository(OrchestrationDatabase(database_path))
    job = create_job(repository, "binding-reopen")

    expected = _h3_binding()
    repository.set_provider_binding(job["id"], expected)

    reopened = JobRepository(OrchestrationDatabase(database_path))

    assert reopened.get_provider_binding(job["id"]) == expected

    reopened_job = reopened.get_job(job["id"])
    assert reopened_job["provider_binding"] == expected.model_dump(mode="json")


def test_reopened_runtime_rejects_binding_change(tmp_path):
    database_path = tmp_path / "orchestration.db"
    repository = JobRepository(OrchestrationDatabase(database_path))
    job = create_job(repository, "binding-reopen-conflict")

    expected = _h3_binding()
    repository.set_provider_binding(job["id"], expected)

    reopened = JobRepository(OrchestrationDatabase(database_path))

    with pytest.raises(ProviderBindingConflictError):
        reopened.set_provider_binding(job["id"], _wan_binding())

    assert reopened.get_provider_binding(job["id"]) == expected


def test_missing_job_binding_lookup_raises(job_repo):
    with pytest.raises(KeyError):
        job_repo.get_provider_binding("missing-job-id")


def test_missing_job_cannot_be_bound(job_repo):
    with pytest.raises(KeyError):
        job_repo.set_provider_binding("missing-job-id", _h3_binding())


def test_binding_survives_recover_expired_leases(job_repo, running_job):
    from datetime import datetime, timezone

    binding = _h3_binding()
    job_repo.set_provider_binding(running_job["id"], binding)

    recovered = job_repo.recover_expired_leases(
        datetime(2026, 7, 19, 4, 0, tzinfo=timezone.utc).isoformat()
    )

    assert recovered == 1
    assert job_repo.get_provider_binding(running_job["id"]) == binding

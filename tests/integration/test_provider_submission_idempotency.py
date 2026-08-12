from __future__ import annotations

"""Prove whether provider submission identity survives a process kill.

This is the Wave 4D.4 gate: if a worker submits a provider request (obtaining a
prompt_id / remote task id) and is then killed, can the next worker know the
request was already submitted? If the durable store has no submission identity
column, the system cannot distinguish "submitted once" from "never submitted",
which means the same logical attempt may be submitted twice after a restart.
"""

import pytest

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate, ProviderBinding


def _job_columns(database) -> set[str]:
    with database.connection() as connection:
        rows = connection.execute("PRAGMA table_info(jobs)").fetchall()
        return {row["name"] for row in rows}


def test_jobs_table_has_no_provider_submission_identity(tmp_path):
    """Wave 4D.4 expectation: durable submission identity is MISSING today."""
    database = OrchestrationDatabase(tmp_path / "orchestration.db")
    columns = _job_columns(database)

    submission_identity_columns = {
        "provider_submission_id",
        "submission_id",
        "prompt_id",
        "remote_task_id",
        "provider_attempt_id",
    }
    present = columns & submission_identity_columns

    # This is the honest result of the current system: nothing is persisted.
    assert present == set()


def test_repository_exposes_provider_submission_api_after_wave_4d5(tmp_path):
    """Wave 4D.5 implemented durable submission identity APIs."""
    database = OrchestrationDatabase(tmp_path / "orchestration.db")
    repository = JobRepository(database)

    api_names = {
        name
        for name in dir(repository)
        if not name.startswith("_")
        and any(
            token in name
            for token in ("submission", "prompt", "remote", "attempt", "provider")
        )
    }

    required = {
        "get_provider_binding",
        "set_provider_binding",
        "reserve_provider_submission",
        "get_provider_submission",
        "record_provider_submission_id",
    }
    assert required.issubset(api_names)

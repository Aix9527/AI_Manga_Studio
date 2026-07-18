import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate


def _request(*, project_id="p1", idempotency_key="job-key-0001"):
    return JobCreate(
        project_id=project_id,
        input_path="input/story.txt",
        input_type="novel",
        mode="automatic",
        options={"language": "zh-CN"},
        idempotency_key=idempotency_key,
    )


def test_created_job_survives_repository_reconstruction(tmp_path):
    database_path = tmp_path / "orchestration.db"
    repository = JobRepository(OrchestrationDatabase(database_path))

    created = repository.create_job(_request())

    del repository
    reopened = JobRepository(OrchestrationDatabase(database_path))
    loaded = reopened.get_job(created["id"])

    assert loaded is not None
    assert loaded["project_id"] == "p1"
    assert loaded["status"] == "queued"
    assert loaded["settings"] == _request().model_dump(mode="json")
    assert loaded["steps"] == []
    assert "settings_json" not in loaded


def test_repeated_idempotency_key_returns_one_job_and_one_created_event(tmp_path):
    repository = JobRepository(OrchestrationDatabase(tmp_path / "orchestration.db"))
    request = _request()

    first = repository.create_job(request)
    second = repository.create_job(request)

    assert second["id"] == first["id"]
    events = repository.list_events(first["id"])
    assert [event["event_type"] for event in events] == ["job.created"]
    assert events[0]["payload_json"] == "{}"


def test_events_are_created_filtered_and_return_incrementing_ids(tmp_path):
    repository = JobRepository(OrchestrationDatabase(tmp_path / "orchestration.db"))
    job = repository.create_job(_request())
    created_event = repository.list_events(job["id"])[0]

    first_id = repository.append_event(
        job["id"], "job.progress", {"message": "第一幕"}
    )
    second_id = repository.append_event(job["id"], "job.finished", {})

    assert created_event["id"] < first_id < second_id
    events = repository.list_events(job["id"], after_id=first_id)
    assert [event["id"] for event in events] == [second_id]
    assert [event["event_type"] for event in events] == ["job.finished"]

    progress_event = repository.list_events(job["id"], after_id=created_event["id"])[0]
    assert json.loads(progress_event["payload_json"]) == {"message": "第一幕"}


def test_foreign_keys_reject_event_for_missing_job(tmp_path):
    repository = JobRepository(OrchestrationDatabase(tmp_path / "orchestration.db"))

    with pytest.raises(sqlite3.IntegrityError):
        repository.append_event("missing-job", "job.progress", {})


def test_current_job_excludes_terminal_jobs_and_list_jobs_paginates(tmp_path):
    database = OrchestrationDatabase(tmp_path / "orchestration.db")
    repository = JobRepository(database)
    active = repository.create_job(
        _request(project_id="active", idempotency_key="job-key-active")
    )
    completed = repository.create_job(
        _request(project_id="completed", idempotency_key="job-key-complete")
    )
    cancelled = repository.create_job(
        _request(project_id="cancelled", idempotency_key="job-key-cancel")
    )

    with database.transaction() as connection:
        connection.execute(
            "UPDATE jobs SET status = ?, created_at = ?, updated_at = ? WHERE id = ?",
            (
                "queued",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
                active["id"],
            ),
        )
        connection.execute(
            "UPDATE jobs SET status = ?, created_at = ?, updated_at = ? WHERE id = ?",
            (
                "completed",
                "2026-01-02T00:00:00+00:00",
                "2026-01-03T00:00:00+00:00",
                completed["id"],
            ),
        )
        connection.execute(
            "UPDATE jobs SET status = ?, created_at = ?, updated_at = ? WHERE id = ?",
            (
                "cancelled",
                "2026-01-03T00:00:00+00:00",
                "2026-01-04T00:00:00+00:00",
                cancelled["id"],
            ),
        )

    assert repository.get_current_job()["id"] == active["id"]
    page = repository.list_jobs(limit=1, offset=1)
    assert [job["id"] for job in page] == [completed["id"]]
    assert "settings_json" not in page[0]


def test_concurrent_idempotent_creates_make_one_job_and_created_event(tmp_path):
    repository = JobRepository(OrchestrationDatabase(tmp_path / "orchestration.db"))
    request = _request(idempotency_key="job-key-concurrent")
    workers = 8
    barrier = Barrier(workers)

    def create_at_once():
        barrier.wait(timeout=10)
        return repository.create_job(request)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(create_at_once) for _ in range(workers)]
        jobs = [future.result(timeout=30) for future in futures]

    job_ids = {job["id"] for job in jobs}
    assert len(job_ids) == 1
    job_id = job_ids.pop()
    assert [event["event_type"] for event in repository.list_events(job_id)] == [
        "job.created"
    ]
    assert [job["id"] for job in repository.list_jobs()] == [job_id]


def test_migration_version_is_recorded_once_across_reopens(tmp_path):
    database_path = tmp_path / "orchestration.db"
    first = OrchestrationDatabase(database_path)
    second = OrchestrationDatabase(database_path)

    with first.connection() as connection:
        versions = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    with second.connection() as connection:
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert [row["version"] for row in versions] == [1]
    assert foreign_keys == 1


def test_event_cursor_index_uses_job_id_then_event_id(tmp_path):
    database = OrchestrationDatabase(tmp_path / "orchestration.db")

    with database.connection() as connection:
        columns = connection.execute(
            "PRAGMA index_info('idx_events_job_id')"
        ).fetchall()

    assert [row["name"] for row in columns] == ["job_id", "id"]


def test_reopen_replaces_legacy_event_index_without_new_migration_version(tmp_path):
    database_path = tmp_path / "orchestration.db"
    database = OrchestrationDatabase(database_path)
    with database.transaction() as connection:
        connection.execute("DROP INDEX idx_events_job_id")
        connection.execute(
            "CREATE INDEX idx_events_job_id ON job_events(job_id)"
        )

    reopened = OrchestrationDatabase(database_path)
    with reopened.connection() as connection:
        columns = connection.execute(
            "PRAGMA index_info('idx_events_job_id')"
        ).fetchall()
        versions = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert [row["name"] for row in columns] == ["job_id", "id"]
    assert [row["version"] for row in versions] == [1]


def test_reopen_does_not_rebuild_correct_event_index(tmp_path):
    database_path = tmp_path / "orchestration.db"
    database = OrchestrationDatabase(database_path)
    with database.connection() as connection:
        schema_version_before = connection.execute(
            "PRAGMA schema_version"
        ).fetchone()[0]

    reopened = OrchestrationDatabase(database_path)
    with reopened.connection() as connection:
        schema_version_after = connection.execute(
            "PRAGMA schema_version"
        ).fetchone()[0]

    assert schema_version_after == schema_version_before

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate


MIGRATIONS_DIR = (
    Path(__file__).parents[2] / "backend" / "orchestration" / "migrations"
)


def _create_legacy_v1_database(database_path):
    schema = (MIGRATIONS_DIR / "001_jobs.sql").read_text(encoding="utf-8")
    schema = schema.replace(
        "validated_at TEXT NOT NULL,",
        "validated_at TEXT,",
    ).replace(
        "ON job_events(job_id, id);",
        "ON job_events(job_id);",
    )
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(schema)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (1, ?)",
            ("2026-01-01T00:00:00+00:00",),
        )
        connection.commit()
    finally:
        connection.close()


def _insert_job(connection, job_id):
    connection.execute(
        """
        INSERT INTO jobs(
            id, project_id, input_path, input_type, mode, status,
            settings_json, idempotency_key, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            f"project-{job_id}",
            f"{job_id}.txt",
            "novel",
            "automatic",
            "queued",
            "{}",
            f"key-{job_id}-0000",
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:00+00:00",
        ),
    )


def _insert_step(connection, step_id, job_id, sequence=1):
    connection.execute(
        """
        INSERT INTO job_steps(id, job_id, sequence, stage_key, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (step_id, job_id, sequence, "storyboard", "pending"),
    )


def _insert_artifact(
    connection,
    artifact_id,
    job_id,
    step_id,
    *,
    validated_at="2026-01-01T00:00:00+00:00",
):
    connection.execute(
        """
        INSERT INTO artifacts(
            id, job_id, step_id, kind, path, sha256, size,
            metadata_json, validated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            artifact_id,
            job_id,
            step_id,
            "image",
            f"output/{artifact_id}.png",
            "abc123",
            42,
            "{}",
            validated_at,
        ),
    )


def _insert_review_action(connection, action_id, job_id, step_id):
    connection.execute(
        """
        INSERT INTO review_actions(
            id, job_id, step_id, action, comment, patch_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            action_id,
            job_id,
            step_id,
            "approve",
            "",
            "{}",
            "2026-01-01T00:00:00+00:00",
        ),
    )


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

    assert [row["version"] for row in versions] == [1, 2]
    assert foreign_keys == 1


def test_event_cursor_index_uses_job_id_then_event_id(tmp_path):
    database = OrchestrationDatabase(tmp_path / "orchestration.db")

    with database.connection() as connection:
        columns = connection.execute(
            "PRAGMA index_info('idx_events_job_id')"
        ).fetchall()

    assert [row["name"] for row in columns] == ["job_id", "id"]


def test_v2_replaces_legacy_event_index(tmp_path):
    database_path = tmp_path / "orchestration.db"
    _create_legacy_v1_database(database_path)

    reopened = OrchestrationDatabase(database_path)
    with reopened.connection() as connection:
        columns = connection.execute(
            "PRAGMA index_info('idx_events_job_id')"
        ).fetchall()
        versions = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert [row["name"] for row in columns] == ["job_id", "id"]
    assert [row["version"] for row in versions] == [1, 2]


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


def test_artifact_validation_timestamp_is_required_text(tmp_path):
    database = OrchestrationDatabase(tmp_path / "orchestration.db")

    with database.connection() as connection:
        columns = connection.execute("PRAGMA table_info('artifacts')").fetchall()

    validated_at = [
        {
            "name": row["name"],
            "type": row["type"],
            "notnull": row["notnull"],
        }
        for row in columns
        if row["name"] == "validated_at"
    ]
    assert validated_at == [
        {"name": "validated_at", "type": "TEXT", "notnull": 1}
    ]


def test_v2_upgrades_legacy_artifacts_and_preserves_validated_rows(tmp_path):
    database_path = tmp_path / "orchestration.db"
    _create_legacy_v1_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        _insert_job(connection, "job-1")
        _insert_step(connection, "step-1", "job-1")
        _insert_artifact(connection, "artifact-1", "job-1", "step-1")

    upgraded = OrchestrationDatabase(database_path)
    with upgraded.connection() as connection:
        versions = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        validated_at = next(
            row
            for row in connection.execute("PRAGMA table_info('artifacts')")
            if row["name"] == "validated_at"
        )
        artifact = connection.execute(
            "SELECT validated_at FROM artifacts WHERE id = 'artifact-1'"
        ).fetchone()
        artifact_foreign_keys = connection.execute(
            "PRAGMA foreign_key_list('artifacts')"
        ).fetchall()

    composite_groups = {}
    for row in artifact_foreign_keys:
        if row["table"] == "job_steps":
            composite_groups.setdefault(row["id"], []).append(
                (row["seq"], row["from"], row["to"], row["on_delete"])
            )

    assert [row["version"] for row in versions] == [1, 2]
    assert validated_at["type"] == "TEXT"
    assert validated_at["notnull"] == 1
    assert artifact["validated_at"] == "2026-01-01T00:00:00+00:00"
    assert any(
        sorted(group)
        == [
            (0, "job_id", "job_id", "CASCADE"),
            (1, "step_id", "id", "CASCADE"),
        ]
        for group in composite_groups.values()
    )


def test_v2_rejects_null_validation_without_partial_upgrade(tmp_path):
    database_path = tmp_path / "orchestration.db"
    _create_legacy_v1_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        _insert_job(connection, "job-1")
        _insert_step(connection, "step-1", "job-1")
        _insert_artifact(
            connection,
            "artifact-null",
            "job-1",
            "step-1",
            validated_at=None,
        )

    with pytest.raises(sqlite3.IntegrityError, match="validated_at"):
        OrchestrationDatabase(database_path)

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        versions = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        validated_at = next(
            row
            for row in connection.execute("PRAGMA table_info('artifacts')")
            if row["name"] == "validated_at"
        )
        artifact = connection.execute(
            "SELECT validated_at FROM artifacts WHERE id = 'artifact-null'"
        ).fetchone()
        partial_tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE '%_v2'"
        ).fetchall()
    finally:
        connection.close()

    assert [row["version"] for row in versions] == [1]
    assert validated_at["notnull"] == 0
    assert artifact["validated_at"] is None
    assert partial_tables == []


def test_artifacts_and_reviews_require_step_from_same_job(tmp_path):
    database = OrchestrationDatabase(tmp_path / "orchestration.db")
    with database.transaction() as connection:
        _insert_job(connection, "job-1")
        _insert_job(connection, "job-2")
        _insert_step(connection, "step-1", "job-1")
        _insert_step(connection, "step-2", "job-2")

    with database.transaction() as connection:
        _insert_artifact(connection, "artifact-match", "job-1", "step-1")
        _insert_review_action(connection, "review-match", "job-1", "step-1")

    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            _insert_artifact(connection, "artifact-cross", "job-1", "step-2")

    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            _insert_review_action(connection, "review-cross", "job-1", "step-2")


def test_failed_migration_rolls_back_schema_and_version(tmp_path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_base.sql").write_text(
        """
        CREATE TABLE schema_migrations(
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        CREATE TABLE stable(id INTEGER PRIMARY KEY);
        """,
        encoding="utf-8",
    )
    (migrations_dir / "003_broken.sql").write_text(
        """
        CREATE TABLE partial(id INTEGER PRIMARY KEY);
        THIS IS INVALID SQL;
        """,
        encoding="utf-8",
    )
    database_path = tmp_path / "orchestration.db"

    with pytest.raises(sqlite3.OperationalError):
        OrchestrationDatabase(database_path, migrations_dir=migrations_dir)

    connection = sqlite3.connect(database_path)
    try:
        versions = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        connection.execute("SELECT 1")
    finally:
        connection.close()

    assert [row[0] for row in versions] == [1]
    assert "stable" in tables
    assert "partial" not in tables


def test_connect_closes_connection_when_pragma_fails(tmp_path, monkeypatch):
    class FailingConnection:
        row_factory = None

        def __init__(self):
            self.closed = False

        def execute(self, _sql):
            raise sqlite3.OperationalError("pragma failed")

        def close(self):
            self.closed = True

    failing_connection = FailingConnection()
    monkeypatch.setattr(
        "backend.orchestration.database.sqlite3.connect",
        lambda *_args, **_kwargs: failing_connection,
    )
    database = object.__new__(OrchestrationDatabase)
    database.path = tmp_path / "orchestration.db"

    with pytest.raises(sqlite3.OperationalError, match="pragma failed"):
        database.connect()

    assert failing_connection.closed is True

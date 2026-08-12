from __future__ import annotations

from pathlib import Path

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate, ProviderBinding


MIGRATIONS_DIR = (
    Path(__file__).parents[2] / "backend" / "orchestration" / "migrations"
)


def _copy_migrations_through(migrations_dir, version):
    migrations_dir.mkdir()
    for source in MIGRATIONS_DIR.glob("*.sql"):
        if int(source.name.partition("_")[0]) <= version:
            (migrations_dir / source.name).write_text(
                source.read_text(encoding="utf-8"),
                encoding="utf-8",
            )


def _versions(database_path):
    with OrchestrationDatabase(database_path).connection() as connection:
        rows = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        return [row["version"] for row in rows]


def _make_job_with_binding(repository):
    job = repository.create_job(
        JobCreate(
            project_id="migration-p",
            input_path="inputs/story.txt",
            input_type="novel",
            idempotency_key="migration-key-0001",
        )
    )
    binding = ProviderBinding(
        provider="ltx23",
        route="video",
        metadata={"binding_version": 1},
    )
    repository.set_provider_binding(job["id"], binding)
    return job, binding


def test_fresh_database_migrates_001_through_007(tmp_path):
    database_path = tmp_path / "fresh.db"
    database = OrchestrationDatabase(database_path)

    assert _versions(database_path) == [1, 2, 3, 4, 5, 6, 7]

    with database.connection() as connection:
        index = connection.execute(
            "PRAGMA index_list('provider_submissions')"
        ).fetchall()
        index_names = {row["name"] for row in index}
    assert "idx_provider_submissions_job_step_attempt" in index_names


def test_existing_005_database_upgrades_to_007_preserving_rows(tmp_path):
    database_path = tmp_path / "legacy005.db"
    legacy_dir = tmp_path / "legacy-migrations"
    _copy_migrations_through(legacy_dir, 5)
    legacy = OrchestrationDatabase(database_path, legacy_dir)
    legacy_repo = JobRepository(legacy)

    job = legacy_repo.create_job(
        JobCreate(
            project_id="migration-p",
            input_path="inputs/story.txt",
            input_type="novel",
            idempotency_key="legacy-005-key",
        )
    )

    upgraded = OrchestrationDatabase(database_path)
    assert _versions(database_path) == [1, 2, 3, 4, 5, 6, 7]

    upgraded_repo = JobRepository(upgraded)
    restored = upgraded_repo.get_job(job["id"])
    assert restored is not None
    assert restored["status"] == "queued"


def test_existing_006_database_upgrades_to_007_preserving_binding(tmp_path):
    database_path = tmp_path / "legacy006.db"
    legacy_dir = tmp_path / "legacy-migrations-006"
    _copy_migrations_through(legacy_dir, 6)
    legacy = OrchestrationDatabase(database_path, legacy_dir)
    legacy_repo = JobRepository(legacy)

    job, binding = _make_job_with_binding(legacy_repo)
    assert legacy_repo.get_provider_binding(job["id"]) == binding

    upgraded = OrchestrationDatabase(database_path)
    assert _versions(database_path) == [1, 2, 3, 4, 5, 6, 7]

    upgraded_repo = JobRepository(upgraded)
    assert upgraded_repo.get_provider_binding(job["id"]) == binding


def test_already_007_database_migrate_is_idempotent(tmp_path):
    database_path = tmp_path / "current.db"
    repository = JobRepository(OrchestrationDatabase(database_path))
    job, binding = _make_job_with_binding(repository)

    # Reopen many times: migrate must be a no-op and preserve everything.
    for _ in range(3):
        reopened = JobRepository(OrchestrationDatabase(database_path))
        assert reopened.get_job(job["id"]) is not None
        assert reopened.get_provider_binding(job["id"]) == binding

    assert _versions(database_path) == [1, 2, 3, 4, 5, 6, 7]

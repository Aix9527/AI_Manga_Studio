from pathlib import Path

from backend.config import AppConfig
from backend.runtime.paths import RuntimePaths


def test_relative_runtime_paths_resolve_from_application_root(tmp_path, monkeypatch):
    application_root = tmp_path / "application"
    application_root.mkdir()
    unrelated_cwd = tmp_path / "elsewhere"
    unrelated_cwd.mkdir()
    monkeypatch.chdir(unrelated_cwd)
    config = AppConfig(
        runtime={"data_root": "state", "local_only": True},
        orchestration={"database_path": "database/orchestration.db"},
    )

    paths = RuntimePaths.from_config(config, application_root)

    assert paths.data_root == (application_root / "state").resolve()
    assert paths.orchestration_database == (
        application_root / "state" / "database" / "orchestration.db"
    ).resolve()


def test_task_specific_environment_override_changes_only_data_root(
    tmp_path, monkeypatch
):
    override = tmp_path / "portable-data"
    monkeypatch.setenv("AI_MANGA_STUDIO_DATA_ROOT", str(override))
    config = AppConfig(
        runtime={"data_root": "ignored", "local_only": True},
        orchestration={"database_path": "database/jobs.db"},
    )

    paths = RuntimePaths.from_config(config, tmp_path / "application")

    assert paths.data_root == override.resolve()
    assert paths.orchestration_database == (
        override / "database" / "jobs.db"
    ).resolve()


def test_runtime_ensure_creates_only_managed_directories(tmp_path):
    config = AppConfig(
        runtime={"data_root": str(tmp_path), "local_only": True},
        orchestration={"database_path": "database/jobs.db"},
    )
    paths = RuntimePaths.from_config(config, tmp_path / "application")

    paths.ensure()

    assert paths.database_dir.is_dir()
    assert paths.logs_dir.is_dir()
    assert paths.projects_dir.is_dir()
    assert paths.output_dir.is_dir()
    assert paths.cache_dir.is_dir()
    assert paths.temp_dir.is_dir()

from pathlib import Path
from types import SimpleNamespace

import backend.main as backend_main
from backend.orchestration.schemas import JobCreate
from backend.production.executor import ProductionStepRunner
from backend.projects.repository import ProjectRepository
from backend.projects.schemas import ProjectCreate, SourceCreate
from backend.runtime.paths import RuntimePaths


def test_one_database_restores_job_project_and_source(tmp_path):
    config = SimpleNamespace(
        orchestration=SimpleNamespace(
            database_path="database/studio.db",
            retry_delays_seconds=[0, 0, 0],
            lease_seconds=30,
            heartbeat_seconds=10,
            worker_poll_seconds=0.01,
        )
    )
    paths = RuntimePaths(
        application_root=tmp_path,
        data_root=tmp_path,
        database_dir=tmp_path / "database",
        orchestration_database=tmp_path / "database" / "studio.db",
        logs_dir=tmp_path / "logs",
        projects_dir=tmp_path / "projects",
        output_dir=tmp_path / "output",
        cache_dir=tmp_path / "cache",
        temp_dir=tmp_path / "temp",
    )
    job_repository, runner, worker = backend_main.create_job_runtime(
        config, runtime_paths=paths
    )
    assert isinstance(runner, ProductionStepRunner)
    project_repository = ProjectRepository(job_repository.database)
    project = project_repository.create(ProjectCreate(name="统一底座验收"))
    project_repository.add_source(
        project["id"],
        SourceCreate(
            kind="idea",
            original_name="创意",
            original_location="一个来自未来的电话",
            rights_confirmed=True,
        ),
    )
    job = job_repository.create_job(
        JobCreate(
            project_id=project["id"],
            input_path="inputs/idea.txt",
            input_type="novel",
            idempotency_key="acceptance-job-0001",
        )
    )
    assert worker.run_once() is True

    failed_closed = job_repository.get_job(job["id"])
    assert failed_closed["status"] == "retry_wait"
    assert failed_closed["steps"][0]["error_code"] == "PIPELINE_NOT_READY"

    reopened_jobs, _, _ = backend_main.create_job_runtime(
        config, runtime_paths=paths
    )
    reopened_projects = ProjectRepository(reopened_jobs.database)
    reopened_job = reopened_jobs.get_job(job["id"])

    assert reopened_job["status"] == "retry_wait"
    assert reopened_job["steps"][0]["error_code"] == "PIPELINE_NOT_READY"
    assert reopened_projects.get(project["id"])["sources"][0]["kind"] == "idea"
    media_extensions = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".wav",
        ".mp3",
        ".m4a",
        ".mp4",
        ".mov",
        ".mkv",
    }
    assert not [
        path
        for path in tmp_path.rglob("*")
        if path.is_file() and path.suffix.lower() in media_extensions
    ]


def test_reference_directories_are_not_part_of_the_formal_backend():
    main_source = Path(backend_main.__file__).read_text(encoding="utf-8")
    for legacy in (
        "backend_v3",
        "backend_v4",
        "backend_v6",
        "backend_v7",
        "backend_v10",
        "backend_v11",
    ):
        assert legacy not in main_source

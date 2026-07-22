from types import SimpleNamespace

import pytest

from backend.main import app, create_job_runtime
from backend.orchestration.checkpoints import ArtifactDraft
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate
from backend.routes.jobs import router as jobs_router
from backend.runtime.paths import RuntimePaths


@pytest.fixture
def job_repo(tmp_path):
    return JobRepository(OrchestrationDatabase(tmp_path / 'orchestration.db'))


@pytest.fixture
def running_job(job_repo, tmp_path):
    job = job_repo.create_job(
        JobCreate(
            project_id='running',
            input_path='running.txt',
            input_type='novel',
            mode='automatic',
            idempotency_key='lifespan-recovery-running-job',
        )
    )
    completed_step_id = job_repo.ensure_bootstrap_step(job['id'])
    checkpoint_path = tmp_path / 'completed-checkpoint.txt'
    checkpoint_path.write_text('persisted output', encoding='utf-8')
    job_repo.complete_step(
        job['id'],
        completed_step_id,
        'persisted-input',
        [ArtifactDraft.from_path('file', checkpoint_path)],
    )
    with job_repo.database.transaction() as connection:
        connection.execute(
            '''
            UPDATE jobs
            SET status = 'running', worker_id = 'dead-worker',
                lease_until = '2000-01-01T00:00:00+00:00'
            WHERE id = ?
            ''',
            (job['id'],),
        )
        connection.execute(
            '''
            INSERT INTO job_steps(
                id, job_id, sequence, stage_key, shot_id, status
            ) VALUES ('running-step', ?, 1, 'script_plan', '', 'running')
            ''',
            (job['id'],),
        )
    return job


class IdleRunner:
    def __init__(self, repository):
        self.repository = repository

    def run_next(self, job, cancel_requested):
        return None

    def cancel(self, job_id):
        return False


def runtime_config(database_path):
    return SimpleNamespace(
        orchestration=SimpleNamespace(
            database_path=str(database_path),
            retry_delays_seconds=[0, 0, 0],
            lease_seconds=30,
            heartbeat_seconds=10,
            worker_poll_seconds=0.01,
        )
    )


def test_runtime_recovers_expired_running_job(job_repo, running_job, tmp_path):
    config = runtime_config(job_repo.database.path)
    paths = RuntimePaths(
        application_root=tmp_path,
        data_root=tmp_path,
        database_dir=job_repo.database.path.parent,
        orchestration_database=job_repo.database.path,
        logs_dir=tmp_path / 'logs',
        projects_dir=tmp_path / 'projects',
        output_dir=tmp_path / 'output',
        cache_dir=tmp_path / 'cache',
        temp_dir=tmp_path / 'temp',
    )

    repository, _, _ = create_job_runtime(
        config, runner_factory=IdleRunner, runtime_paths=paths
    )

    restored = repository.get_job(running_job['id'])
    assert restored['status'] == 'queued'
    assert restored['steps'][0]['status'] == 'completed'
    assert restored['steps'][1]['status'] == 'queued'


def test_formal_app_mounts_the_durable_jobs_router_once():
    registrations = [
        route
        for route in app.routes
        if getattr(route, 'original_router', None) is jobs_router
    ]
    assert len(registrations) == 1

    paths = app.openapi()['paths']
    assert set(paths['/api/jobs']) == {'post', 'get'}
    assert set(paths['/api/jobs/current']) == {'get'}

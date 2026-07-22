from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.service import JobService
from backend.routes import pipeline


def make_client(database_path):
    app = FastAPI()
    repository = JobRepository(OrchestrationDatabase(database_path))
    app.state.job_service = JobService(
        repository, SimpleNamespace(cancel=lambda _job_id: True)
    )
    app.include_router(pipeline.router)
    return TestClient(app), repository


def test_legacy_run_creates_a_durable_job(tmp_path):
    novel = tmp_path / 'story.txt'
    novel.write_text('\u6d4b\u8bd5\u6545\u4e8b', encoding='utf-8')
    client, repository = make_client(tmp_path / 'jobs.db')

    response = client.post(
        '/api/pipeline/run',
        headers={'Idempotency-Key': 'legacy-run-0001'},
        json={'novel_path': str(novel), 'style': 'realistic'},
    )

    assert response.status_code == 200
    job_id = response.json()['job_id']
    assert repository.get_job(job_id)['status'] == 'queued'
    assert not hasattr(pipeline, '_jobs')


def test_legacy_status_survives_a_new_app_instance(tmp_path):
    novel = tmp_path / 'story.txt'
    novel.write_text('\u6d4b\u8bd5\u6545\u4e8b', encoding='utf-8')
    database = tmp_path / 'jobs.db'
    first, _ = make_client(database)
    job_id = first.post(
        '/api/pipeline/run',
        headers={'Idempotency-Key': 'legacy-run-0002'},
        json={'novel_path': str(novel)},
    ).json()['job_id']

    second, _ = make_client(database)
    restored = second.get(f'/api/pipeline/status/{job_id}')

    assert restored.status_code == 200
    assert restored.json()['job_id'] == job_id


def test_legacy_cancel_uses_the_durable_command(tmp_path):
    novel = tmp_path / 'story.txt'
    novel.write_text('\u6d4b\u8bd5\u6545\u4e8b', encoding='utf-8')
    client, repository = make_client(tmp_path / 'jobs.db')
    job_id = client.post(
        '/api/pipeline/run',
        headers={'Idempotency-Key': 'legacy-run-0003'},
        json={'novel_path': str(novel)},
    ).json()['job_id']

    response = client.delete(
        f'/api/pipeline/jobs/{job_id}',
        headers={'Idempotency-Key': 'legacy-cancel-0003'},
    )

    assert response.status_code == 200
    assert repository.get_job(job_id)['status'] == 'cancelled'


def test_legacy_novel_listing_is_read_only(tmp_path, monkeypatch):
    novels = tmp_path / 'novels'
    novels.mkdir()
    story = novels / 'story.txt'
    story.write_text('\u6d4b\u8bd5\u6545\u4e8b', encoding='utf-8')
    monkeypatch.setattr(pipeline, 'NOVELS_DIR', novels)
    monkeypatch.setattr(pipeline, 'PROJECT_ROOT', tmp_path)
    client, _ = make_client(tmp_path / 'jobs.db')

    response = client.get('/api/pipeline/novels')

    assert response.status_code == 200
    assert response.json()['novels'][0]['path'] == str(story.resolve())
    assert story.read_text(encoding='utf-8') == '\u6d4b\u8bd5\u6545\u4e8b'

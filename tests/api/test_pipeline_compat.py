from types import SimpleNamespace
import hashlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.service import JobService
from backend.routes import pipeline


def make_client(database_path, raise_server_exceptions=True):
    app = FastAPI()
    repository = JobRepository(OrchestrationDatabase(database_path))
    app.state.job_service = JobService(
        repository, SimpleNamespace(cancel=lambda _job_id: True)
    )
    app.include_router(pipeline.router)
    return TestClient(app, raise_server_exceptions=raise_server_exceptions), repository


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


def upload(client, key, content, style='realistic'):
    return client.post(
        '/api/pipeline/upload',
        headers={'Idempotency-Key': key},
        data={'style': style},
        files={'file': ('story.txt', content, 'text/plain')},
    )


def test_legacy_upload_same_filename_keeps_different_content_immutable(
    tmp_path, monkeypatch
):
    novels = tmp_path / 'novels'
    novels.mkdir()
    monkeypatch.setattr(pipeline, 'NOVELS_DIR', novels)
    client, repository = make_client(tmp_path / 'jobs.db')

    first = upload(client, 'immutable-upload-0001', b'first version')
    second = upload(client, 'immutable-upload-0002', b'second version')

    assert first.status_code == second.status_code == 200
    first_path = repository.get_job(first.json()['job_id'])['settings']['input_path']
    second_path = repository.get_job(second.json()['job_id'])['settings']['input_path']
    assert first_path != second_path
    assert Path(first_path).read_bytes() == b'first version'
    assert Path(second_path).read_bytes() == b'second version'


def test_legacy_upload_identical_replay_does_not_mutate_managed_input(
    tmp_path, monkeypatch
):
    novels = tmp_path / 'novels'
    novels.mkdir()
    monkeypatch.setattr(pipeline, 'NOVELS_DIR', novels)
    client, repository = make_client(tmp_path / 'jobs.db')

    first = upload(client, 'immutable-replay-0001', b'unchanged input')
    job_id = first.json()['job_id']
    managed = Path(repository.get_job(job_id)['settings']['input_path'])
    before = (managed.read_bytes(), managed.stat().st_mtime_ns)
    replay = upload(client, 'immutable-replay-0001', b'unchanged input')

    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert (managed.read_bytes(), managed.stat().st_mtime_ns) == before


def test_legacy_upload_conflicting_replay_retains_and_reuses_new_input(
    tmp_path, monkeypatch
):
    novels = tmp_path / 'novels'
    novels.mkdir()
    monkeypatch.setattr(pipeline, 'NOVELS_DIR', novels)
    client, repository = make_client(
        tmp_path / 'jobs.db', raise_server_exceptions=False
    )

    first = upload(client, 'immutable-conflict-0001', b'accepted input')
    accepted = Path(repository.get_job(first.json()['job_id'])['settings']['input_path'])
    retained_bytes = b'conflicting input'
    retained = novels / (
        'story-' + hashlib.sha256(retained_bytes).hexdigest() + '.txt'
    )
    conflict = upload(client, 'immutable-conflict-0001', retained_bytes)

    assert conflict.status_code == 409
    assert retained.read_bytes() == retained_bytes
    reused = upload(client, 'immutable-reuse-0001', retained_bytes)
    assert reused.status_code == 200
    assert accepted.read_bytes() == b'accepted input'
    assert (
        repository.get_job(reused.json()['job_id'])['settings']['input_path']
        == str(retained)
    )


def test_legacy_upload_conflict_never_unlinks_content_addressed_input(
    tmp_path, monkeypatch
):
    novels = tmp_path / 'novels'
    novels.mkdir()
    monkeypatch.setattr(pipeline, 'NOVELS_DIR', novels)
    client, _ = make_client(tmp_path / 'jobs.db', raise_server_exceptions=False)
    assert upload(client, 'immutable-no-unlink-0001', b'accepted').status_code == 200

    def fail_unlink(_path, *args, **kwargs):
        raise AssertionError('upload conflict attempted deletion')

    monkeypatch.setattr(Path, 'unlink', fail_unlink)
    conflict = upload(client, 'immutable-no-unlink-0001', b'conflicting')

    assert conflict.status_code == 409


def test_legacy_run_conflicting_replay_returns_409(tmp_path):
    novel = tmp_path / 'story.txt'
    novel.write_text('source', encoding='utf-8')
    client, _ = make_client(tmp_path / 'jobs.db', raise_server_exceptions=False)

    first = client.post(
        '/api/pipeline/run',
        headers={'Idempotency-Key': 'legacy-run-conflict-0001'},
        json={'novel_path': str(novel), 'style': 'realistic'},
    )
    conflict = client.post(
        '/api/pipeline/run',
        headers={'Idempotency-Key': 'legacy-run-conflict-0001'},
        json={'novel_path': str(novel), 'style': 'anime'},
    )

    assert first.status_code == 200
    assert conflict.status_code == 409


@pytest.mark.parametrize('invalid_key', ['short', 'x' * 129])
def test_legacy_idempotency_header_bounds_apply_to_create_upload_and_cancel(
    tmp_path, monkeypatch, invalid_key
):
    novel = tmp_path / 'story.txt'
    novel.write_text('source', encoding='utf-8')
    novels = tmp_path / 'novels'
    novels.mkdir()
    monkeypatch.setattr(pipeline, 'NOVELS_DIR', novels)
    client, repository = make_client(tmp_path / 'jobs.db')

    create = client.post(
        '/api/pipeline/run',
        headers={'Idempotency-Key': invalid_key},
        json={'novel_path': str(novel)},
    )
    uploaded = upload(client, invalid_key, b'source')
    job = client.post(
        '/api/pipeline/run',
        headers={'Idempotency-Key': 'legacy-cancel-bounds-0001'},
        json={'novel_path': str(novel)},
    ).json()
    cancelled = client.delete(
        '/api/pipeline/jobs/' + job['job_id'],
        headers={'Idempotency-Key': invalid_key},
    )

    assert create.status_code == uploaded.status_code == cancelled.status_code == 422
    assert repository.get_job(job['job_id'])['status'] == 'queued'

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import main
from backend.orchestration.database import OrchestrationDatabase
from backend.projects.repository import ProjectRepository
from backend.projects.service import ProjectService
from backend.routes.project import router


def client_for(path):
    app = FastAPI()
    app.state.project_service = ProjectService(
        ProjectRepository(OrchestrationDatabase(path))
    )
    app.include_router(router)
    return TestClient(app)


def test_project_api_persists_and_delete_archives(tmp_path):
    database = tmp_path / 'studio.db'
    first = client_for(database)
    created = first.post('/api/projects', json={'name': 'Midnight Call'})
    assert created.status_code == 201
    project_id = created.json()['id']

    second = client_for(database)
    assert second.get(f'/api/projects/{project_id}').status_code == 200
    assert second.delete(f'/api/projects/{project_id}').status_code == 200
    assert second.get(f'/api/projects/{project_id}').status_code == 404
    archived = second.get('/api/projects?include_archived=true').json()
    assert archived['projects'][0]['status'] == 'archived'


def test_project_api_requires_rights_for_url_sources(tmp_path):
    client = client_for(tmp_path / 'studio.db')
    created = client.post('/api/projects', json={'name': 'Licensed source'})
    project_id = created.json()['id']

    rejected = client.post(
        f'/api/projects/{project_id}/sources',
        json={
            'kind': 'url',
            'original_name': 'Source video',
            'original_location': 'https://example.invalid/video/1',
            'rights_confirmed': False,
        },
    )

    assert rejected.status_code == 422
    assert 'rights confirmation' in rejected.text


def test_project_api_persists_confirmed_url_source_metadata(tmp_path):
    database = tmp_path / 'studio.db'
    client = client_for(database)
    created = client.post('/api/projects', json={'name': 'Licensed source'})
    project_id = created.json()['id']

    response = client.post(
        f'/api/projects/{project_id}/sources',
        json={
            'kind': 'url',
            'original_name': 'Source video',
            'original_location': 'https://example.invalid/video/1',
            'rights_confirmed': True,
            'metadata': {'license': 'owned'},
        },
    )

    assert response.status_code == 201
    restored = client_for(database).get(f'/api/projects/{project_id}').json()
    assert restored['sources'][0]['rights_confirmed'] is True
    assert restored['sources'][0]['metadata'] == {'license': 'owned'}


@pytest.mark.asyncio
async def test_main_lifespan_uses_job_database_for_projects(
    tmp_path,
    monkeypatch,
):
    database = OrchestrationDatabase(tmp_path / 'studio.db')
    job_repository = SimpleNamespace(database=database)

    class IdleWorker:
        def serve(self, poll_seconds):
            return None

        def stop(self):
            return None

    config = SimpleNamespace(
        orchestration=SimpleNamespace(worker_poll_seconds=0.01)
    )
    monkeypatch.setattr(main, 'load_config', lambda: config)
    monkeypatch.setattr(
        main.RuntimePaths,
        'from_config',
        staticmethod(lambda *_args: SimpleNamespace()),
    )
    monkeypatch.setattr(
        main,
        'create_job_runtime',
        lambda *_args, **_kwargs: (
            job_repository,
            SimpleNamespace(),
            IdleWorker(),
        ),
    )
    monkeypatch.setattr(main, 'init_all_databases', lambda: None)

    def unavailable_llm():
        raise RuntimeError('offline')

    async def shutdown_llm():
        return None

    monkeypatch.setattr(main, 'get_llm_service', unavailable_llm)
    monkeypatch.setattr(main, 'shutdown_llm_service', shutdown_llm)
    test_app = FastAPI()

    async with main.lifespan(test_app):
        project_repository = test_app.state.project_service.repository
        assert project_repository.database is job_repository.database

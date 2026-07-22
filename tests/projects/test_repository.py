from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.orchestration.database import OrchestrationDatabase
from backend.projects.repository import ProjectRepository
from backend.projects.schemas import ProjectCreate, SourceCreate


def test_project_and_source_survive_repository_reopen(tmp_path):
    database_path = tmp_path / 'studio.db'
    first = ProjectRepository(OrchestrationDatabase(database_path))
    project = first.create(ProjectCreate(name=' Midnight Call '))
    source = first.add_source(
        project['id'],
        SourceCreate(
            kind='idea',
            original_name='Concept',
            original_location='A midnight call from your future self',
            rights_confirmed=True,
            metadata={'language': 'en', 'revision': 1},
        ),
    )

    second = ProjectRepository(OrchestrationDatabase(database_path))
    restored = second.get(project['id'])

    assert restored is not None
    assert restored['name'] == 'Midnight Call'
    assert restored['target_duration_seconds'] == 60
    assert restored['sources'][0]['id'] == source['id']
    assert restored['sources'][0]['metadata'] == {
        'language': 'en',
        'revision': 1,
    }


def test_archive_is_non_destructive(tmp_path):
    repository = ProjectRepository(
        OrchestrationDatabase(tmp_path / 'studio.db')
    )
    project = repository.create(ProjectCreate(name='Keep source material'))

    archived = repository.archive(project['id'])

    assert archived['status'] == 'archived'
    assert repository.get(project['id']) is None
    assert repository.get(project['id'], include_archived=True) is not None


def test_url_source_requires_rights_confirmation():
    with pytest.raises(ValidationError, match='rights confirmation'):
        SourceCreate(
            kind='url',
            original_name='Source video',
            original_location='https://example.invalid/video/1',
            rights_confirmed=False,
        )


def test_source_metadata_requires_finite_json_numbers():
    with pytest.raises(ValidationError, match='JSON numbers must be finite'):
        SourceCreate(
            kind='idea',
            original_name='Concept',
            original_location='Local idea',
            metadata={'analysis': {'score': float('nan')}},
        )

from __future__ import annotations

import json

import pytest

from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate
from backend.orchestration.service import JobService
from backend.orchestration.template_resolution import resolve_project_template_job_create
from backend.orchestration.worker import SSEBroadcaster
from backend.workspace.models import ProductionTemplateSaveRequest
from backend.workspace.repository import WorkspaceRepository
from backend.workspace.template_service import ProductionTemplateService, TemplatePublishConflict


def _system(tmp_path):
    db = OrchestrationDatabase(str(tmp_path / "jobs.db"))
    jobs = JobRepository(db)
    service = JobService(
        db,
        jobs,
        SSEBroadcaster(),
        OrchestrationConfig(
            database_path=str(tmp_path / "unused.db"),
            checkpoint_dir=str(tmp_path / "checkpoints"),
            project_root=str(tmp_path / "projects"),
        ),
    )
    templates = ProductionTemplateService(WorkspaceRepository(db))
    return db, jobs, service, templates


def _template(width: int, name: str = "template") -> ProductionTemplateSaveRequest:
    return ProductionTemplateSaveRequest(
        name=name,
        schema_version=1,
        canvas={
            "nodes": [
                {"id": "novel", "data": {"stageKey": "load_input"}},
                {"id": "scene", "data": {"stageKey": "planning"}},
                {"id": "character", "data": {"stageKey": "character_design"}},
                {"id": "storyboard", "data": {"stageKey": "planning"}},
                {"id": "keyframe", "data": {"stageKey": "visual_generate"}},
                {"id": "video", "data": {"stageKey": "video_generate"}},
                {"id": "audio", "data": {"stageKey": "audio_tts"}},
                {"id": "export", "data": {"stageKey": "composition_compose"}},
            ],
            "edges": [],
        },
        production={
            "shot_duration": 7,
            "width": width,
            "height": 1920,
            "fps": 30,
            "options": {"style": "cinematic", "local_first": False},
        },
        stage_policy={"stages": []},
    )


def _stored_settings(repo: JobRepository, job_id: str) -> dict:
    row = repo.get_job(job_id)
    assert row is not None
    return json.loads(row["settings"])


def _create(db: OrchestrationDatabase, service: JobService, data: JobCreate):
    return service.create(resolve_project_template_job_create(db, data))


def test_no_published_template_preserves_request_defaults_and_records_source(tmp_path):
    db, repo, service, _ = _system(tmp_path)

    job = _create(db, service, JobCreate(project_id="project-a", input_path="story.txt"))
    settings = _stored_settings(repo, job.id)

    assert settings["width"] == 1080
    assert settings["height"] == 1920
    assert settings["fps"] == 24
    assert settings["shot_duration"] == 5.0
    assert settings["template"]["source"] == "system_default"


def test_published_template_overrides_job_settings_and_records_provenance(tmp_path):
    db, repo, service, templates = _system(tmp_path)
    saved = templates.save("project-a", _template(1440))
    templates.publish("project-a", saved.version)

    job = _create(db, service, JobCreate(project_id="project-a", input_path="story.txt"))
    settings = _stored_settings(repo, job.id)

    assert settings["width"] == 1440
    assert settings["fps"] == 30
    assert settings["shot_duration"] == 7.0
    assert settings["options"]["style"] == "cinematic"
    assert settings["options"]["local_first"] is False
    assert settings["template"]["source"] == "project_published_template"
    assert settings["template"]["version"] == saved.version
    assert settings["template"]["version_id"] == saved.id
    assert settings["template"]["sha256"] == saved.content_sha256
    assert settings["template"]["compiled_sha256"] == saved.compiled_sha256


def test_existing_job_keeps_v1_after_v2_is_published(tmp_path):
    db, repo, service, templates = _system(tmp_path)
    v1 = templates.save("project-a", _template(1200, "v1"))
    templates.publish("project-a", v1.version)
    job_a = _create(db, service, JobCreate(project_id="project-a", input_path="a.txt"))

    v2 = templates.save("project-a", _template(1600, "v2"))
    templates.publish("project-a", v2.version)
    job_b = _create(db, service, JobCreate(project_id="project-a", input_path="b.txt"))

    settings_a = _stored_settings(repo, job_a.id)
    settings_b = _stored_settings(repo, job_b.id)
    assert settings_a["template"]["version"] == 1
    assert settings_a["width"] == 1200
    assert settings_b["template"]["version"] == 2
    assert settings_b["width"] == 1600


def test_corrupt_published_template_prevents_job_creation(tmp_path):
    db, repo, service, templates = _system(tmp_path)
    saved = templates.save("project-a", _template(1440))
    templates.publish("project-a", saved.version)
    with db.transaction() as conn:
        conn.execute(
            "UPDATE project_production_template_versions SET compiled_json='{}' WHERE id=?",
            (saved.id,),
        )

    with pytest.raises(TemplatePublishConflict, match="hash mismatch"):
        _create(db, service, JobCreate(project_id="project-a", input_path="story.txt"))

    assert repo.list_jobs(project_id="project-a", limit=10, offset=0) == []

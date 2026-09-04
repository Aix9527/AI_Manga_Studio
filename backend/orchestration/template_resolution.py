from __future__ import annotations

import json

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.schemas import JobCreate
from backend.workspace.repository import WorkspaceRepository
from backend.workspace.template_service import ProductionTemplateService


def resolve_project_template_job_create(
    db: OrchestrationDatabase,
    data: JobCreate,
) -> JobCreate:
    """Resolve a project published template into the existing JobCreate contract.

    No published template preserves the incoming request values and records
    system-default provenance. A published template overrides only compiler-
    whitelisted production fields. Stored-template validation happens before a
    Job is created, so invalid publication fails closed.
    """

    templates = ProductionTemplateService(WorkspaceRepository(db))
    published = templates.published(data.project_id)
    options = dict(data.options)

    if not published.published or published.template is None:
        options["template_context"] = {
            "source": "system_default",
            "version_id": None,
            "version": None,
        }
        options["stage_policy_context"] = []
        return data.model_copy(update={"options": options})

    version = published.template
    compiled = json.loads(version.compiled_json)
    production = compiled.get("production")
    if not isinstance(production, dict):
        raise ValueError("published template compiled production is invalid")
    compiled_options = production.get("options", {})
    if not isinstance(compiled_options, dict):
        raise ValueError("published template compiled options are invalid")
    stage_policy = compiled.get("stage_policy", [])
    if not isinstance(stage_policy, list):
        raise ValueError("published template stage policy is invalid")

    options.update(compiled_options)
    options["template_context"] = {
        "source": "project_published_template",
        "version_id": version.id,
        "version": version.version,
        "schema_version": version.schema_version,
        "sha256": version.content_sha256,
        "compiled_sha256": version.compiled_sha256,
    }
    options["stage_policy_context"] = stage_policy

    return data.model_copy(
        update={
            "shot_duration": float(production.get("shot_duration", data.shot_duration)),
            "width": int(production.get("width", data.width)),
            "height": int(production.get("height", data.height)),
            "fps": int(production.get("fps", data.fps)),
            "options": options,
        }
    )

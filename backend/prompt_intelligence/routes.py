"""Prompt Intelligence API (Phase 13.4-A, GPT spec)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.prompt_intelligence.composer import PromptComposer
from backend.prompt_intelligence.service import PromptIntelligenceService

router = APIRouter(prefix="/api/prompt-intelligence", tags=["prompt-intelligence"])

_service = PromptIntelligenceService()
_composer = PromptComposer(_service)


def _http(exception: Exception) -> HTTPException:
    if isinstance(exception, KeyError):
        return HTTPException(status_code=404, detail=str(exception))
    if isinstance(exception, ValueError):
        return HTTPException(status_code=422, detail=str(exception))
    return HTTPException(status_code=500, detail=str(exception))


# ------------------------------------------------------------- templates
class TemplateBody(BaseModel):
    name: str
    kind: str = "generic"
    base_template: str = ""
    negative_prompt: str = ""
    quality_tags: str = ""
    variables: list[str] = []
    description: str = ""


class VersionBody(BaseModel):
    base_template: str
    negative_prompt: str = ""
    quality_tags: str = ""
    variables: list[str] = []
    notes: str = ""
    parent_version: str | None = None


class StatusBody(BaseModel):
    status: str
    approved_by: str = "human"


class ReviewBody(BaseModel):
    reviewer: str
    status: str = "pending"
    comments: str = ""


@router.get("/stats")
def stats():
    return _service.stats()


@router.get("/templates")
def list_templates(kind: str | None = None):
    return {"templates": _service.list_templates(kind=kind)}


@router.post("/templates")
def create_template(body: TemplateBody):
    try:
        return _service.create_template(**body.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/templates/{template_id}")
def get_template(template_id: str):
    try:
        return _service.get_template(template_id)
    except KeyError as exc:
        raise _http(exc)


@router.delete("/templates/{template_id}")
def delete_template(template_id: str):
    if not _service.delete_template(template_id):
        raise HTTPException(status_code=404, detail="template not found")
    return {"ok": True, "template_id": template_id}


# ------------------------------------------------------------- versions
@router.get("/templates/{template_id}/versions")
def list_versions(template_id: str):
    try:
        return {"template_id": template_id, "versions": _service.list_versions(template_id)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/templates/{template_id}/versions")
def create_version(template_id: str, body: VersionBody):
    try:
        return _service.create_version(template_id, **body.model_dump(exclude_none=True))
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/templates/{template_id}/versions/{version_id}/status")
def set_status(template_id: str, version_id: str, body: StatusBody):
    try:
        return _service.set_version_status(template_id, version_id, body.status, body.approved_by)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/templates/{template_id}/versions/{version_id}/diff")
def diff_versions(template_id: str, version_id: str, against: str = "v1"):
    try:
        return _service.diff_versions(template_id, against, version_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


# ------------------------------------------------------------- reviews
@router.get("/reviews")
def list_reviews(template_id: str | None = None):
    return {"reviews": _service.list_reviews(template_id=template_id)}


@router.post("/templates/{template_id}/versions/{version_id}/review")
def add_review(template_id: str, version_id: str, body: ReviewBody):
    try:
        return _service.add_review(
            template_id, version_id, body.reviewer, body.status, body.comments
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


# ------------------------------------------------------------- A/B tests
class ABTestBody(BaseModel):
    template_id: str
    base_version: str
    variant_version: str
    name: str = ""
    metric: str = "success_rate"


class ABResultBody(BaseModel):
    arm: str
    success: bool


class ABDecideBody(BaseModel):
    min_samples: int = 3


@router.get("/ab-tests")
def list_ab_tests():
    return {"tests": _service.list_ab_tests()}


@router.post("/ab-tests")
def create_ab_test(body: ABTestBody):
    try:
        return _service.create_ab_test(**body.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/ab-tests/{ab_id}")
def get_ab_test(ab_id: str):
    try:
        return _service.get_ab_test(ab_id)
    except KeyError as exc:
        raise _http(exc)


@router.post("/ab-tests/{ab_id}/results")
def record_ab_result(ab_id: str, body: ABResultBody):
    try:
        return _service.record_ab_result(ab_id, body.arm, body.success)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/ab-tests/{ab_id}/decide")
def decide_ab(ab_id: str, body: ABDecideBody):
    try:
        return _service.decide_ab(ab_id, min_samples=body.min_samples)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


# ------------------------------------------------------------- compose
class CharacterComposeBody(BaseModel):
    character_id: str
    asset_type: str = "portrait"
    asset_key: str = ""


class WorldComposeBody(BaseModel):
    project_id: str = ""
    world_id: str = ""
    scene_id: str = ""


class ShotComposeBody(BaseModel):
    dna_id: str = ""
    features: dict = {}
    top_k: int = 1


@router.post("/compose/character")
def compose_character(body: CharacterComposeBody):
    try:
        return _composer.compose_character(body.character_id, body.asset_type, body.asset_key)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/compose/world")
def compose_world(body: WorldComposeBody):
    try:
        return _composer.compose_world(body.project_id, body.world_id, body.scene_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/compose/shot")
def compose_shot(body: ShotComposeBody):
    try:
        return _composer.compose_shot(body.dna_id, body.features, body.top_k)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)
"""Prompt Library API（Phase 15.3-B）. """

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.prompt_library.service import PromptLibrary
from backend.prompt_library.skill import PromptSkill

router = APIRouter(prefix="/api/prompt-library", tags=["prompt-library"])

_service = PromptLibrary()
_skill = PromptSkill(_service)


class CompileBody(BaseModel):
    characters: list[str] = []
    location: str = ""
    action: str = ""
    duration_s: int = 15
    beats: list[str] = []
    first_frame: str = ""
    optics: str = ""
    camera: str = ""
    lighting: str = ""
    audio: str = ""
    acting: str = ""


@router.get("/template")
def template():
    return _service.template()


@router.get("/sections")
def sections():
    return {"sections": _service.sections()}


@router.get("/wording-rules")
def wording_rules():
    return {"rules": _service.wording_rules()}


@router.get("/style-prefix")
def style_prefix():
    return {"style_prefix": _service.style_prefix()}


@router.get("/minimax-params")
def minimax_params():
    return _service.minimax_params()


@router.post("/skill/write")
def skill_write(body: CompileBody):
    try:
        design = {
            "id": "skill-shot", "duration_seconds": body.duration_s,
            "layers": {
                "story": body.action, "director_intent": "",
                "photography": {"shot": "", "lens": "", "angle": ""},
                "composition": {"name": body.location},
                "action": {}, "camera_movement": body.camera,
                "lighting": {"name": body.lighting, "effect": ""},
                "style": {}, "characters": body.characters,
                "location": body.location,
            },
        }
        return {"prompt": _skill.write(design)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/compile")
def compile_shot(body: CompileBody):
    try:
        return {"prompt": _service.compile_shot(
            characters=body.characters,
            location=body.location,
            action=body.action,
            duration_s=body.duration_s,
            beats=body.beats,
            first_frame=body.first_frame,
            optics=body.optics,
            camera=body.camera,
            lighting=body.lighting,
            audio=body.audio,
            acting=body.acting,
        )}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=str(exc))

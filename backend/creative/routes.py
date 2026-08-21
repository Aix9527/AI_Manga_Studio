"""Creative Agents API（v1.0 Phase 2）. """

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.creative.agents import CreativeTeam

router = APIRouter(prefix="/api/creative", tags=["creative-agents"])

_team = CreativeTeam()


class ShotBibleBody(BaseModel):
    story: str
    characters: list[str] = ["主角"]
    emotion: str = "默认"
    mood: str = "默认"
    action_type: str = "默认"


class ActBody(BaseModel):
    character: str = "主角"
    emotion: str = "默认"
    action: str = ""


class CameraBody(BaseModel):
    mood: str = "默认"
    scene: str = ""


class MotionBody(BaseModel):
    action_type: str = "默认"
    duration_seconds: int = 5


class SoundBody(BaseModel):
    scene: str = "默认"
    emotion: str = "默认"


@router.post("/shot-bible")
def shot_bible(body: ShotBibleBody):
    return _team.produce_shot_bible(
        story=body.story, characters=body.characters,
        emotion=body.emotion, mood=body.mood, action_type=body.action_type,
    )


@router.post("/actor/act")
def act(body: ActBody):
    return _team.actor.act(character=body.character, emotion=body.emotion, action=body.action)


@router.post("/camera/direct")
def camera(body: CameraBody):
    return _team.camera.direct(mood=body.mood, scene=body.scene)


@router.post("/motion/choreograph")
def motion(body: MotionBody):
    return _team.motion.choreograph(action_type=body.action_type, duration_seconds=body.duration_seconds)


@router.post("/sound/design")
def sound(body: SoundBody):
    return _team.sound.sound(scene=body.scene, emotion=body.emotion)


@router.get("/camera-library")
def camera_library():
    from backend.creative.agents import CAMERA_LIBRARY
    return CAMERA_LIBRARY

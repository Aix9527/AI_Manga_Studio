"""Story API routes for FastAPI."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.story.graph import StoryGraphEngine
from backend.story.models import Scene, Shot
from backend.story.parser import StoryParser
from backend.story.timeline import TimelineManager

router = APIRouter(prefix="/api/story", tags=["Story"])
parser = StoryParser()
graph_engine = StoryGraphEngine()
timeline_mgr = TimelineManager()


class ParseRequest(BaseModel):
    text: str
    novel_id: str = ""


class TimelineEventRequest(BaseModel):
    novel_id: str
    chapter_number: int
    character_id: str
    event_type: str
    description: str
    relative_time: str = ""


class ShotUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shot_type: str = ""
    camera_angle: str = ""
    camera_movement: str = "static"
    description: str = ""
    action: str = ""
    dialogue: str = ""
    narration: str = ""
    emotion: str = ""
    character_ids: list[str] = Field(default_factory=list)
    duration: float = Field(default=5.0, ge=1, le=30)
    positive_prompt: str = ""
    negative_prompt: str = ""
    seed: int = Field(default=0, ge=0, le=4_294_967_295)
    image_model: str = ""
    video_model: str = ""
    thumbnail_url: str = ""
    production_status: str = "pending"
    quality_status: str = "unreviewed"

    @field_validator("thumbnail_url")
    @classmethod
    def validate_thumbnail_url(cls, value: str) -> str:
        if value and not value.lower().startswith(("http://", "https://", "data:")):
            raise ValueError("缩略图地址必须是 HTTP 或 data URL")
        return value


def _shot_response(shot: Shot) -> dict:
    response = asdict(shot)
    thumbnail = response.get("thumbnail_url", "")
    if thumbnail and not thumbnail.lower().startswith(("http://", "https://", "data:")):
        response["thumbnail_url"] = ""
    return response


def _scene_response(scene: Scene, shots: list[Shot]) -> dict:
    return {
        **asdict(scene),
        "description": scene.summary or scene.raw_text[:200],
        "character_count": len(scene.characters),
        "shot_count": len(shots),
        "shots": [_shot_response(shot) for shot in shots],
    }


def _canonical_scenes(novel_id: str) -> list[dict]:
    hierarchy = graph_engine.get_hierarchy_for_novel(novel_id)
    if hierarchy is None:
        return []
    return [
        _scene_response(scene, shots)
        for _chapter, scene_data in hierarchy
        for scene, shots in scene_data
    ]


@router.post("/parse")
def parse_story(req: ParseRequest):
    """Parse and persist one canonical chapter → scene → shot hierarchy."""
    hierarchy = parser.parse_hierarchy(req.text, req.novel_id)
    chapters = [chapter for chapter, _scene_data in hierarchy]
    title = chapters[0].title if chapters else req.novel_id
    graph = graph_engine.build_graph(
        req.novel_id, title, hierarchy, persist=bool(req.novel_id)
    )
    scenes = [
        _scene_response(scene, shots)
        for _chapter, scene_data in hierarchy
        for scene, shots in scene_data
    ]
    return {
        "novel_id": req.novel_id,
        "graph_id": graph.id,
        "title": title,
        "chapters": [
            {**asdict(chapter), "scene_count": len(scene_data)}
            for chapter, scene_data in hierarchy
        ],
        "scenes": scenes,
        "total_chapters": len(chapters),
        "total_scenes": len(scenes),
        "total_shots": sum(len(scene["shots"]) for scene in scenes),
    }


@router.post("/parse/scenes")
def parse_scenes(req: ParseRequest):
    """Return canonical scenes for a novel, parsing only when no record exists."""
    if req.novel_id:
        scenes = _canonical_scenes(req.novel_id)
        if not scenes and not graph_engine.get_graph_for_novel(req.novel_id):
            parse_story(req)
            scenes = _canonical_scenes(req.novel_id)
    else:
        result = parser.parse_single_text(req.text, req.novel_id)
        scenes = [
            _scene_response(entry["scene"], entry["shots"])
            for entry in result["scenes"]
        ]
    return {"scene_count": len(scenes), "scenes": scenes}


@router.get("/graph/{novel_id}")
def get_story_graph(novel_id: str):
    graph = graph_engine.export_frontend_graph(novel_id)
    if not graph:
        raise HTTPException(status_code=404, detail="未找到故事结构")
    return graph


@router.get("/graph/{novel_id}/shots")
def get_sequential_shots(
    novel_id: str,
    chapter: int | None = Query(default=None, ge=0),
):
    if not graph_engine.get_graph_for_novel(novel_id):
        raise HTTPException(status_code=404, detail="未找到故事结构")
    return graph_engine.get_shots_for_novel(novel_id, chapter)


@router.get("/graph/{novel_id}/scenes")
def get_canonical_scenes(novel_id: str):
    hierarchy = graph_engine.get_hierarchy_for_novel(novel_id)
    if hierarchy is None:
        raise HTTPException(status_code=404, detail="故事结构不存在")
    return _canonical_scenes(novel_id)


@router.patch("/{novel_id}/shots/{shot_id}")
def update_shot(novel_id: str, shot_id: str, req: ShotUpdateRequest):
    if graph_engine.get_hierarchy_for_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="故事结构不存在")
    updated = graph_engine.update_shot(
        novel_id,
        shot_id,
        req.model_dump(exclude_unset=True),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="镜头不存在")
    return _shot_response(updated)


@router.get("/timeline/{novel_id}")
def get_timeline(novel_id: str):
    return timeline_mgr.export_timeline(novel_id)


@router.get("/timeline/{novel_id}/character/{character_id}")
def get_character_timeline(novel_id: str, character_id: str):
    events = timeline_mgr.get_character_timeline(novel_id, character_id)
    return {"character_id": character_id, "events": [event.__dict__ for event in events]}


@router.post("/timeline/event")
def add_timeline_event(req: TimelineEventRequest):
    return timeline_mgr.add_event(
        req.novel_id,
        req.chapter_number,
        req.character_id,
        req.event_type,
        req.description,
        req.relative_time,
    )

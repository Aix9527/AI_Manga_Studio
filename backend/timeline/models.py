from __future__ import annotations

from pydantic import BaseModel, Field


class TimelineClipView(BaseModel):
    id: str
    track_id: str
    artifact_id: int | None = None
    artifact_version: int | None = None
    clip_type: str
    timeline_start_tick: int
    duration_tick: int
    source_in_tick: int
    source_out_tick: int
    link_group_id: str | None = None
    enabled: bool = True
    locked: bool = False
    shot_id: str = ""
    scene_id: str = ""
    media_url: str = ""


class TimelineTrackView(BaseModel):
    id: str
    track_type: str
    role: str
    name: str
    sort_index: int
    locked: bool = False
    muted: bool = False
    hidden: bool = False
    clips: list[TimelineClipView] = Field(default_factory=list)


class TimelineDraftView(BaseModel):
    timeline_id: str
    draft_id: str
    project_id: str
    revision: int
    timebase_hz: int
    fps_num: int
    fps_den: int
    tracks: list[TimelineTrackView] = Field(default_factory=list)


class TimelineSummary(BaseModel):
    timeline_id: str
    project_id: str
    name: str
    active_draft_id: str
    revision: int
    timebase_hz: int
    fps_num: int
    fps_den: int
    latest_snapshot_no: int = 0


class TimelinePreflight(BaseModel):
    status: str = "pass"
    warnings: list[dict[str, object]] = Field(default_factory=list)

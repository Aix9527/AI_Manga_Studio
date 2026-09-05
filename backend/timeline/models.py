from __future__ import annotations

from typing import Annotated, Literal

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


class MoveClipOperation(BaseModel):
    type: Literal["MOVE_CLIP"]
    clip_id: str
    insert_before_clip_id: str | None = None
    insert_after_clip_id: str | None = None


class TrimClipOperation(BaseModel):
    type: Literal["TRIM_CLIP"]
    clip_id: str
    edge: Literal["left", "right"]
    target_source_tick: int = Field(ge=0)


class SplitClipOperation(BaseModel):
    type: Literal["SPLIT_CLIP"]
    clip_id: str
    timeline_tick: int = Field(ge=0)


class RemoveClipOperation(BaseModel):
    type: Literal["REMOVE_CLIP"]
    clip_id: str
    mode: Literal["ripple", "lift", "linked"] = "ripple"


class LinkClipsOperation(BaseModel):
    type: Literal["LINK_CLIPS"]
    clip_ids: list[str] = Field(min_length=2)


class UnlinkClipsOperation(BaseModel):
    type: Literal["UNLINK_CLIPS"]
    clip_ids: list[str] = Field(min_length=1)


TimelineOperation = Annotated[
    MoveClipOperation
    | TrimClipOperation
    | SplitClipOperation
    | RemoveClipOperation
    | LinkClipsOperation
    | UnlinkClipsOperation,
    Field(discriminator="type"),
]


class TimelineOperationRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    operation: TimelineOperation


class TimelineRevisionRequest(BaseModel):
    expected_revision: int = Field(ge=0)


class TimelineMutationResult(BaseModel):
    revision: int
    operation_seq: int
    draft: TimelineDraftView
    preflight: TimelinePreflight = Field(default_factory=TimelinePreflight)

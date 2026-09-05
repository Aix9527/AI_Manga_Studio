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


class TimelineSubtitleCueView(BaseModel):
    id: str
    track_id: str
    clip_id: str | None = None
    link_group_id: str | None = None
    start_tick: int
    end_tick: int
    text: str
    speaker: str = ""
    style: dict[str, object] = Field(default_factory=dict)


class TimelineTransitionView(BaseModel):
    id: str
    track_id: str
    from_clip_id: str
    to_clip_id: str
    transition_type: str
    duration_tick: int
    params: dict[str, object] = Field(default_factory=dict)


class TimelineDraftView(BaseModel):
    timeline_id: str
    draft_id: str
    project_id: str
    revision: int
    timebase_hz: int
    fps_num: int
    fps_den: int
    tracks: list[TimelineTrackView] = Field(default_factory=list)
    subtitle_cues: list[TimelineSubtitleCueView] = Field(default_factory=list)
    transitions: list[TimelineTransitionView] = Field(default_factory=list)


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


class AddTransitionOperation(BaseModel):
    type: Literal["ADD_TRANSITION"]
    from_clip_id: str
    to_clip_id: str
    transition_type: Literal["crossfade", "fade_to_black", "fade_from_black"]
    duration_tick: int = Field(gt=0)
    params: dict[str, object] = Field(default_factory=dict)


class UpdateTransitionOperation(BaseModel):
    type: Literal["UPDATE_TRANSITION"]
    transition_id: str
    duration_tick: int | None = Field(default=None, gt=0)
    params: dict[str, object] | None = None


class RemoveTransitionOperation(BaseModel):
    type: Literal["REMOVE_TRANSITION"]
    transition_id: str


class AddSubtitleOperation(BaseModel):
    type: Literal["ADD_SUBTITLE"]
    track_id: str
    start_tick: int = Field(ge=0)
    end_tick: int = Field(ge=0)
    text: str
    speaker: str = ""
    clip_id: str | None = None
    link_group_id: str | None = None
    style: dict[str, object] = Field(default_factory=dict)


class UpdateSubtitleOperation(BaseModel):
    type: Literal["UPDATE_SUBTITLE"]
    cue_id: str
    start_tick: int | None = Field(default=None, ge=0)
    end_tick: int | None = Field(default=None, ge=0)
    text: str | None = None
    speaker: str | None = None
    style: dict[str, object] | None = None


class RemoveSubtitleOperation(BaseModel):
    type: Literal["REMOVE_SUBTITLE"]
    cue_id: str


class ReplaceArtifactVersionOperation(BaseModel):
    type: Literal["REPLACE_ARTIFACT_VERSION"]
    clip_ids: list[str] = Field(min_length=1)
    artifact_id: int = Field(gt=0)


TimelineOperation = Annotated[
    MoveClipOperation
    | TrimClipOperation
    | SplitClipOperation
    | RemoveClipOperation
    | LinkClipsOperation
    | UnlinkClipsOperation
    | AddTransitionOperation
    | UpdateTransitionOperation
    | RemoveTransitionOperation
    | AddSubtitleOperation
    | UpdateSubtitleOperation
    | RemoveSubtitleOperation
    | ReplaceArtifactVersionOperation,
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


class TimelineSnapshotView(BaseModel):
    id: str
    timeline_id: str
    snapshot_no: int
    source_draft_revision: int
    state_sha256: str
    duration_tick: int
    created_at: str


class TimelineQcRunView(BaseModel):
    id: str
    snapshot_id: str
    attempt: int
    status: Literal["running", "passed", "failed", "stale"]
    report: dict[str, object] = Field(default_factory=dict)
    started_at: str
    completed_at: str | None = None


class TimelineQcStatusView(BaseModel):
    snapshot_id: str
    effective_status: Literal["not_run", "running", "passed", "failed", "stale"]
    attempts: list[TimelineQcRunView] = Field(default_factory=list)


class WaveformEnvelope(BaseModel):
    artifact_id: int
    bins: int
    peaks: list[float]
    cache_path: str

from __future__ import annotations

from backend.timeline.models import TimelineClipView, TimelineDraftView, TimelineSummary, TimelineTrackView
from backend.timeline.repository import TimelineRepository


class TimelineNotFound(ValueError):
    pass


class TimelineService:
    def __init__(self, repo: TimelineRepository):
        self.repo = repo

    def initialize_project(self, project_id: str) -> tuple[TimelineDraftView, bool]:
        timeline, created = self.repo.initialize_project(project_id)
        return self._build_draft(str(timeline["id"])), created

    def get_project_timeline(self, project_id: str) -> TimelineSummary | None:
        timeline = self.repo.get_project_timeline(project_id)
        if timeline is None:
            return None
        draft = self.repo.get_draft(str(timeline["active_draft_id"]))
        if draft is None:
            raise TimelineNotFound(f"Active draft missing for timeline {timeline['id']}")
        return TimelineSummary(
            timeline_id=str(timeline["id"]),
            project_id=str(timeline["project_id"]),
            name=str(timeline["name"]),
            active_draft_id=str(timeline["active_draft_id"]),
            revision=int(draft["revision"]),
            timebase_hz=int(timeline["timebase_hz"]),
            fps_num=int(timeline["fps_num"]),
            fps_den=int(timeline["fps_den"]),
            latest_snapshot_no=int(timeline["latest_snapshot_no"]),
        )

    def get_draft(self, timeline_id: str) -> TimelineDraftView:
        return self._build_draft(timeline_id)

    def _build_draft(self, timeline_id: str) -> TimelineDraftView:
        timeline = self.repo.get_timeline(timeline_id)
        if timeline is None:
            raise TimelineNotFound(f"Timeline not found: {timeline_id}")
        draft = self.repo.get_active_draft_for_timeline(timeline_id)
        if draft is None:
            raise TimelineNotFound(f"Active draft missing for timeline {timeline_id}")

        clips = self.repo.list_clips(str(draft["id"]))
        clips_by_track: dict[str, list[TimelineClipView]] = {}
        for clip in clips:
            artifact_id = clip["artifact_id"]
            project_id = str(clip.get("artifact_project_id") or timeline["project_id"])
            media_url = ""
            if artifact_id is not None:
                media_url = f"/api/workspace/{project_id}/assets/{artifact_id}/media"
            clips_by_track.setdefault(str(clip["track_id"]), []).append(
                TimelineClipView(
                    id=str(clip["id"]),
                    track_id=str(clip["track_id"]),
                    artifact_id=int(artifact_id) if artifact_id is not None else None,
                    artifact_version=int(clip["artifact_version"]) if clip["artifact_version"] is not None else None,
                    clip_type=str(clip["clip_type"]),
                    timeline_start_tick=int(clip["timeline_start_tick"]),
                    duration_tick=int(clip["duration_tick"]),
                    source_in_tick=int(clip["source_in_tick"]),
                    source_out_tick=int(clip["source_out_tick"]),
                    link_group_id=str(clip["link_group_id"]) if clip["link_group_id"] else None,
                    enabled=bool(clip["enabled"]),
                    locked=bool(clip["locked"]),
                    shot_id=str(clip.get("artifact_shot_id") or ""),
                    scene_id=str(clip.get("artifact_scene_id") or ""),
                    media_url=media_url,
                )
            )

        tracks = [
            TimelineTrackView(
                id=str(track["id"]),
                track_type=str(track["track_type"]),
                role=str(track["role"]),
                name=str(track["name"]),
                sort_index=int(track["sort_index"]),
                locked=bool(track["locked"]),
                muted=bool(track["muted"]),
                hidden=bool(track["hidden"]),
                clips=clips_by_track.get(str(track["id"]), []),
            )
            for track in self.repo.list_tracks(str(draft["id"]))
        ]
        return TimelineDraftView(
            timeline_id=str(timeline["id"]),
            draft_id=str(draft["id"]),
            project_id=str(timeline["project_id"]),
            revision=int(draft["revision"]),
            timebase_hz=int(timeline["timebase_hz"]),
            fps_num=int(timeline["fps_num"]),
            fps_den=int(timeline["fps_den"]),
            tracks=tracks,
        )

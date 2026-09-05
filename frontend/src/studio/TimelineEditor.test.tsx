import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TimelineEditor from "@/studio/timeline/TimelineEditor";
import type { TimelineDraft, TimelineOperation } from "@/types/timeline";

const draft: TimelineDraft = {
  timeline_id: "timeline-a",
  draft_id: "draft-a",
  project_id: "project-a",
  revision: 7,
  timebase_hz: 1_000_000,
  fps_num: 24,
  fps_den: 1,
  tracks: [
    {
      id: "track-v1",
      track_type: "video",
      role: "video.main",
      name: "V1 主轨",
      sort_index: 0,
      locked: false,
      muted: false,
      hidden: false,
      clips: [
        {
          id: "clip-001",
          track_id: "track-v1",
          artifact_id: 1,
          artifact_version: 1,
          clip_type: "video",
          timeline_start_tick: 0,
          duration_tick: 2_000_000,
          source_in_tick: 0,
          source_out_tick: 2_000_000,
          link_group_id: "link-1",
          enabled: true,
          locked: false,
          shot_id: "shot_001",
          scene_id: "scene-1",
          media_url: "/api/workspace/project-a/assets/1/media",
        },
        {
          id: "clip-002",
          track_id: "track-v1",
          artifact_id: 2,
          artifact_version: 1,
          clip_type: "video",
          timeline_start_tick: 2_000_000,
          duration_tick: 2_000_000,
          source_in_tick: 0,
          source_out_tick: 2_000_000,
          link_group_id: null,
          enabled: true,
          locked: false,
          shot_id: "shot_002",
          scene_id: "scene-1",
          media_url: "/api/workspace/project-a/assets/2/media",
        },
      ],
    },
    { id: "track-a1", track_type: "audio", role: "audio.dialogue", name: "A1 对白", sort_index: 1, locked: false, muted: false, hidden: false, clips: [] },
    { id: "track-a2", track_type: "audio", role: "audio.bgm", name: "A2 BGM / 音效", sort_index: 2, locked: false, muted: false, hidden: false, clips: [] },
    { id: "track-s1", track_type: "subtitle", role: "subtitle.primary", name: "S1 字幕", sort_index: 3, locked: false, muted: false, hidden: false, clips: [] },
  ],
  subtitle_cues: [],
  transitions: [],
};

afterEach(cleanup);

describe("TimelineEditor v0.10 real persisted lanes", () => {
  it("renders V1/A1/A2/S1 from the authoritative draft and no decorative placeholder lanes", () => {
    render(<TimelineEditor draft={draft} playheadTick={0} onPlayheadChange={vi.fn()} onScheduleOperation={vi.fn()} onCriticalOperation={vi.fn()} onSelectClip={vi.fn()} />);

    expect(screen.getByTestId("timeline-track-video.main")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-track-audio.dialogue")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-track-audio.bgm")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-track-subtitle.primary")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-clip-clip-001")).toHaveTextContent("shot_001");
    expect(document.querySelectorAll(".timeline-lane__blocks > i")).toHaveLength(0);
  });

  it("does not commit a magnetic move during pointer preview and schedules one MOVE on release", () => {
    const schedule = vi.fn<(operation: TimelineOperation) => void>();
    render(<TimelineEditor draft={draft} playheadTick={0} onPlayheadChange={vi.fn()} onScheduleOperation={schedule} onCriticalOperation={vi.fn()} onSelectClip={vi.fn()} />);

    const first = screen.getByTestId("timeline-clip-clip-001");
    const second = screen.getByTestId("timeline-clip-clip-002");
    fireEvent.pointerDown(first, { clientX: 10 });
    fireEvent.pointerMove(second, { clientX: 300 });
    expect(schedule).not.toHaveBeenCalled();
    fireEvent.pointerUp(second, { clientX: 300 });

    expect(schedule).toHaveBeenCalledTimes(1);
    expect(schedule.mock.calls[0][0]).toMatchObject({ type: "MOVE_CLIP", clip_id: "clip-001" });
  });

  it("commits split at the current playhead as a critical operation", () => {
    const critical = vi.fn<(operation: TimelineOperation) => void>();
    render(<TimelineEditor draft={draft} playheadTick={1_000_000} selectedClipId="clip-001" onPlayheadChange={vi.fn()} onScheduleOperation={vi.fn()} onCriticalOperation={critical} onSelectClip={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "分割" }));

    expect(critical).toHaveBeenCalledWith({ type: "SPLIT_CLIP", clip_id: "clip-001", timeline_tick: 1_000_000 });
  });
});

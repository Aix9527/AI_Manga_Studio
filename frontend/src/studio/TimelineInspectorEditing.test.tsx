import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import TimelineInspector from "@/studio/timeline/TimelineInspector";
import type { TimelineDraft } from "@/types/timeline";

const baseDraft: TimelineDraft = {
  timeline_id: "timeline-a",
  draft_id: "draft-a",
  project_id: "project-a",
  revision: 8,
  timebase_hz: 1_000_000,
  fps_num: 24,
  fps_den: 1,
  tracks: [
    {
      id: "v1",
      track_type: "video",
      role: "video.main",
      name: "V1",
      sort_index: 0,
      locked: false,
      muted: false,
      hidden: false,
      clips: [
        {
          id: "clip-a",
          track_id: "v1",
          artifact_id: 11,
          artifact_version: 1,
          clip_type: "video",
          timeline_start_tick: 0,
          duration_tick: 2_000_000,
          source_in_tick: 0,
          source_out_tick: 2_000_000,
          link_group_id: "link-a",
          enabled: true,
          locked: false,
          shot_id: "shot-a",
          scene_id: "scene-a",
          media_url: "/assets/11",
        },
        {
          id: "clip-b",
          track_id: "v1",
          artifact_id: 12,
          artifact_version: 1,
          clip_type: "video",
          timeline_start_tick: 2_000_000,
          duration_tick: 2_000_000,
          source_in_tick: 0,
          source_out_tick: 2_000_000,
          link_group_id: "link-b",
          enabled: true,
          locked: false,
          shot_id: "shot-b",
          scene_id: "scene-a",
          media_url: "/assets/12",
        },
      ],
    },
    { id: "s1", track_type: "subtitle", role: "subtitle.primary", name: "S1", sort_index: 1, locked: false, muted: false, hidden: false, clips: [] },
  ],
  subtitle_cues: [],
  transitions: [],
};

afterEach(cleanup);

describe("TimelineInspector transition editing", () => {
  it("adds only an allowlisted explicit transition to the next V1 clip", async () => {
    const user = userEvent.setup();
    const critical = vi.fn();
    render(
      <TimelineInspector
        draft={baseDraft}
        selectedClip={baseDraft.tracks[0].clips[0]}
        onCriticalOperation={critical}
      />,
    );

    const select = screen.getByLabelText("镜头转场");
    expect(Array.from((select as HTMLSelectElement).options).map((item) => item.value)).toEqual([
      "cut",
      "crossfade",
      "fade_to_black",
      "fade_from_black",
    ]);
    await user.selectOptions(select, "crossfade");
    await user.clear(screen.getByLabelText("转场时长毫秒"));
    await user.type(screen.getByLabelText("转场时长毫秒"), "400");
    await user.click(screen.getByRole("button", { name: "应用转场" }));

    expect(critical).toHaveBeenCalledWith({
      type: "ADD_TRANSITION",
      from_clip_id: "clip-a",
      to_clip_id: "clip-b",
      transition_type: "crossfade",
      duration_tick: 400_000,
    });
  });

  it("uses cut as an explicit remove operation when a transition already exists", async () => {
    const user = userEvent.setup();
    const critical = vi.fn();
    const draft: TimelineDraft = {
      ...baseDraft,
      transitions: [{
        id: "tr-1",
        track_id: "v1",
        from_clip_id: "clip-a",
        to_clip_id: "clip-b",
        transition_type: "crossfade",
        duration_tick: 350_000,
        params: {},
      }],
    };
    render(<TimelineInspector draft={draft} selectedClip={draft.tracks[0].clips[0]} onCriticalOperation={critical} />);

    await user.selectOptions(screen.getByLabelText("镜头转场"), "cut");
    await user.click(screen.getByRole("button", { name: "应用转场" }));
    expect(critical).toHaveBeenCalledWith({ type: "REMOVE_TRANSITION", transition_id: "tr-1" });
  });
});

describe("TimelineInspector subtitle editing", () => {
  it("creates a first-class subtitle cue bound to the selected clip", async () => {
    const user = userEvent.setup();
    const critical = vi.fn();
    render(<TimelineInspector draft={baseDraft} selectedClip={baseDraft.tracks[0].clips[0]} onCriticalOperation={critical} />);

    await user.type(screen.getByLabelText("字幕文本"), "她抬头看向天幕");
    await user.click(screen.getByRole("button", { name: "保存字幕" }));

    expect(critical).toHaveBeenCalledWith({
      type: "ADD_SUBTITLE",
      track_id: "s1",
      start_tick: 0,
      end_tick: 2_000_000,
      text: "她抬头看向天幕",
      clip_id: "clip-a",
      link_group_id: "link-a",
    });
  });

  it("updates and deletes an existing subtitle cue without mutating unrelated cues", async () => {
    const user = userEvent.setup();
    const critical = vi.fn();
    const draft: TimelineDraft = {
      ...baseDraft,
      subtitle_cues: [
        { id: "cue-a", track_id: "s1", clip_id: "clip-a", link_group_id: "link-a", start_tick: 0, end_tick: 2_000_000, text: "旧字幕", speaker: "", style: {} },
        { id: "cue-b", track_id: "s1", clip_id: "clip-b", link_group_id: "link-b", start_tick: 2_000_000, end_tick: 4_000_000, text: "保留", speaker: "", style: {} },
      ],
    };
    render(<TimelineInspector draft={draft} selectedClip={draft.tracks[0].clips[0]} onCriticalOperation={critical} />);

    const input = screen.getByLabelText("字幕文本");
    await user.clear(input);
    await user.type(input, "新字幕");
    await user.click(screen.getByRole("button", { name: "保存字幕" }));
    expect(critical).toHaveBeenCalledWith({ type: "UPDATE_SUBTITLE", cue_id: "cue-a", text: "新字幕" });

    critical.mockClear();
    await user.click(screen.getByRole("button", { name: "删除字幕" }));
    expect(critical).toHaveBeenCalledWith({ type: "REMOVE_SUBTITLE", cue_id: "cue-a" });
  });
});

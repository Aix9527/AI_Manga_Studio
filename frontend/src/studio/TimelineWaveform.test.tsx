import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { timelineApi } from "@/api/timeline";
import TimelineTrack from "@/studio/timeline/TimelineTrack";
import type { TimelineTrack as TimelineTrackModel } from "@/types/timeline";

vi.mock("@/api/timeline", () => ({
  timelineApi: {
    getWaveform: vi.fn(),
  },
}));

const track: TimelineTrackModel = {
  id: "a1",
  track_type: "audio",
  role: "audio.dialogue",
  name: "A1",
  sort_index: 1,
  locked: false,
  muted: false,
  hidden: false,
  clips: [{
    id: "audio-1",
    track_id: "a1",
    artifact_id: 31,
    artifact_version: 1,
    clip_type: "audio",
    timeline_start_tick: 500_000,
    duration_tick: 1_500_000,
    source_in_tick: 0,
    source_out_tick: 1_500_000,
    link_group_id: "link-1",
    enabled: true,
    locked: false,
    shot_id: "shot-1",
    scene_id: "scene-1",
    media_url: "/assets/31",
  }],
};

function renderTrack() {
  return render(
    <TimelineTrack
      timelineId="timeline-a"
      track={track}
      pixelsPerSecond={90}
      timebaseHz={1_000_000}
      selectedClipId={null}
      draggingClipId={null}
      onSelectClip={vi.fn()}
      onClipPointerDown={vi.fn()}
      onClipPointerMove={vi.fn()}
      onClipPointerUp={vi.fn()}
      onTrimPointerUp={vi.fn()}
    />,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Timeline audio waveform", () => {
  it("renders a cached waveform envelope for an audio clip", async () => {
    vi.mocked(timelineApi.getWaveform).mockResolvedValue({
      artifact_id: 31,
      bins: 4,
      peaks: [0.2, -0.5, 0.7, 0.1],
      cache_path: "cache/waveforms/31.json",
    });
    const { container } = renderTrack();

    await waitFor(() => expect(timelineApi.getWaveform).toHaveBeenCalledWith("timeline-a", 31, 128));
    await waitFor(() => expect(container.querySelector(".nle-waveform")).toBeInTheDocument());
    expect(screen.getByTestId("timeline-clip-audio-1")).toBeEnabled();
  });

  it("keeps the clip editable when waveform extraction fails", async () => {
    vi.mocked(timelineApi.getWaveform).mockRejectedValue(new Error("decode failed"));
    renderTrack();

    await waitFor(() => expect(screen.getByText("波形不可用")).toBeInTheDocument());
    expect(screen.getByTestId("timeline-clip-audio-1")).toBeEnabled();
  });
});

import { act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { timelineApi } from "@/api/timeline";
import { resetTimelineStoreForTests, useTimelineStore } from "@/state/timelineStore";
import type { TimelineDraft, TimelineMutationResult, TimelineOperation } from "@/types/timeline";

vi.mock("@/api/timeline", () => ({
  timelineApi: {
    getProjectTimeline: vi.fn(),
    initialize: vi.fn(),
    getDraft: vi.fn(),
    applyOperation: vi.fn(),
    undo: vi.fn(),
    redo: vi.fn(),
    createSnapshot: vi.fn(),
    listSnapshots: vi.fn(),
    runQc: vi.fn(),
    getQc: vi.fn(),
    exportSnapshot: vi.fn(),
    getWaveform: vi.fn(),
  },
}));

const draft = (revision = 0): TimelineDraft => ({
  timeline_id: "timeline-a",
  draft_id: "draft-a",
  project_id: "project-a",
  revision,
  timebase_hz: 1_000_000,
  fps_num: 24,
  fps_den: 1,
  tracks: [],
  subtitle_cues: [],
  transitions: [],
});

const move: TimelineOperation = {
  type: "MOVE_CLIP",
  clip_id: "clip-2",
  insert_before_clip_id: "clip-1",
};

function mutation(nextRevision: number): TimelineMutationResult {
  return {
    revision: nextRevision,
    operation_seq: nextRevision,
    draft: draft(nextRevision),
    preflight: { status: "pass", warnings: [] },
  };
}

describe("timelineStore persistence contract", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    resetTimelineStoreForTests();
    useTimelineStore.setState({ projectId: "project-a", timelineId: "timeline-a", draft: draft(0) });
    vi.mocked(timelineApi.applyOperation).mockResolvedValue(mutation(1));
  });

  it("debounces completed normal edits and commits them once", async () => {
    useTimelineStore.getState().scheduleOperation(move);
    expect(timelineApi.applyOperation).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(199);
    });
    expect(timelineApi.applyOperation).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(timelineApi.applyOperation).toHaveBeenCalledTimes(1);
    expect(timelineApi.applyOperation).toHaveBeenCalledWith("timeline-a", {
      expected_revision: 0,
      operation: move,
    });
  });

  it("flushes pending edits before snapshot creation", async () => {
    vi.mocked(timelineApi.createSnapshot).mockResolvedValue({
      id: "snapshot-1",
      timeline_id: "timeline-a",
      snapshot_no: 1,
      source_draft_revision: 1,
      state_sha256: "sha",
      duration_tick: 1_000_000,
      created_at: "2026-09-05T00:00:00Z",
    });

    useTimelineStore.getState().scheduleOperation(move);
    const promise = useTimelineStore.getState().createSnapshot();
    await act(async () => { await promise; });

    expect(timelineApi.applyOperation).toHaveBeenCalledTimes(1);
    expect(timelineApi.createSnapshot).toHaveBeenCalledTimes(1);
    expect(vi.mocked(timelineApi.applyOperation).mock.invocationCallOrder[0])
      .toBeLessThan(vi.mocked(timelineApi.createSnapshot).mock.invocationCallOrder[0]);
  });

  it("reloads authoritative draft after revision conflict and never replays stale edit", async () => {
    vi.mocked(timelineApi.applyOperation).mockRejectedValueOnce(
      new ApiError(409, { code: "TIMELINE_REVISION_CONFLICT", message: "stale" }),
    );
    vi.mocked(timelineApi.getDraft).mockResolvedValue(draft(9));

    useTimelineStore.getState().scheduleOperation(move);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });

    expect(timelineApi.applyOperation).toHaveBeenCalledTimes(1);
    expect(timelineApi.getDraft).toHaveBeenCalledWith("timeline-a");
    expect(useTimelineStore.getState().draft?.revision).toBe(9);
    expect(useTimelineStore.getState().conflict).toBe(true);
  });

  it("ignores a late project response after switching projects", async () => {
    let resolveA!: (value: { timeline_id: string }) => void;
    vi.mocked(timelineApi.getProjectTimeline)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveA = resolve as typeof resolveA; }) as never)
      .mockResolvedValueOnce({
        timeline_id: "timeline-b",
        project_id: "project-b",
        name: "Main Timeline",
        active_draft_id: "draft-b",
        revision: 0,
        timebase_hz: 1_000_000,
        fps_num: 24,
        fps_den: 1,
        latest_snapshot_no: 0,
      });
    vi.mocked(timelineApi.getDraft).mockResolvedValue({ ...draft(), timeline_id: "timeline-b", draft_id: "draft-b", project_id: "project-b" });

    const requestA = useTimelineStore.getState().loadProject("project-a");
    const requestB = useTimelineStore.getState().loadProject("project-b");
    await act(async () => { await requestB; });
    resolveA({ timeline_id: "timeline-a" });
    await act(async () => { await requestA; });

    expect(useTimelineStore.getState().projectId).toBe("project-b");
    expect(useTimelineStore.getState().timelineId).toBe("timeline-b");
    expect(useTimelineStore.getState().draft?.project_id).toBe("project-b");
  });
});

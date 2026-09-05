import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { workspaceApi } from "@/api/workspace";
import TimelineQcWorkspace from "@/studio/TimelineQcWorkspace";
import type { JobDetail } from "@/types/jobs";
import type { TimelineDraft, TimelineQcStatus, TimelineSnapshot } from "@/types/timeline";

const { mockedWorkspaceStore, state, actions, timelineState, timelineActions, mockedTimelineStore } = vi.hoisted(() => {
  const workspaceState = {
    projectId: "project-a",
    snapshot: {
      project_id: "project-a",
      title: "归墟",
      source_path: "D:/projects/gui-xu/story.txt",
      version: "v0.10",
      progress: 0.95,
      pending_reviews: 0,
      active_jobs: 0,
      estimated_minutes: null,
      stages: [],
      system_health: {},
    },
  };
  const timelineActions = {
    loadProject: vi.fn().mockResolvedValue(undefined),
    scheduleOperation: vi.fn(),
    commitCritical: vi.fn(),
    flushPending: vi.fn().mockResolvedValue(undefined),
    createSnapshot: vi.fn(),
    runQc: vi.fn().mockResolvedValue(undefined),
    exportSnapshot: vi.fn().mockResolvedValue({ snapshot_id: "snapshot-1", job_id: "timeline-job", status: "queued" }),
    undo: vi.fn(),
    redo: vi.fn(),
    clearConflict: vi.fn(),
  };
  const timelineState = {
    projectId: "project-a",
    timelineId: "timeline-a",
    draft: null as TimelineDraft | null,
    preflight: null,
    snapshots: [] as TimelineSnapshot[],
    selectedSnapshotId: null as string | null,
    qcBySnapshot: {} as Record<string, TimelineQcStatus>,
    exportBySnapshot: {},
    loading: false,
    pendingSave: false,
    conflict: false,
    error: null as string | null,
    ...timelineActions,
  };
  const mockedTimelineStore = Object.assign(
    (selector: (value: typeof timelineState) => unknown) => selector(timelineState),
    { getState: () => timelineState },
  );
  return {
    mockedWorkspaceStore: Object.assign(
      (selector: (value: typeof workspaceState) => unknown) => selector(workspaceState),
      { getState: () => workspaceState },
    ),
    state: { jobs: new Map<string, JobDetail>(), recentIds: [] as string[] },
    actions: { retryJob: vi.fn(), resumeJob: vi.fn(), reviewJob: vi.fn() },
    timelineState,
    timelineActions,
    mockedTimelineStore,
  };
});

vi.mock("@/state/workspaceStore", () => ({ useWorkspaceStore: mockedWorkspaceStore }));
vi.mock("@/state/jobStore", () => ({
  useJobStore: () => ({ jobs: state.jobs, recentIds: state.recentIds }),
  jobStoreActions: () => actions,
}));
vi.mock("@/state/timelineStore", () => ({ useTimelineStore: mockedTimelineStore }));
vi.mock("@/api/workspace", () => ({ workspaceApi: { listAssets: vi.fn() } }));

const passedVideo = {
  id: 1,
  project_id: "project-a",
  job_id: "job-export",
  step_id: "step-video",
  kind: "video",
  path: "outputs/shot-01.mp4",
  media_url: "/api/workspace/project-a/assets/1/media",
  stage_key: "video",
  scene_id: "scene-1",
  shot_id: "shot-01",
  version: 1,
  parent_artifact_id: null,
  active: true,
  quality_status: "passed",
  quality_attempt: 0,
  quality_report: {},
  metadata: {},
  created_at: "2026-09-05T00:00:00Z",
};

const draft: TimelineDraft = {
  timeline_id: "timeline-a",
  draft_id: "draft-a",
  project_id: "project-a",
  revision: 4,
  timebase_hz: 1_000_000,
  fps_num: 24,
  fps_den: 1,
  tracks: [
    { id: "v1", track_type: "video", role: "video.main", name: "V1", sort_index: 0, locked: false, muted: false, hidden: false, clips: [] },
    { id: "a1", track_type: "audio", role: "audio.dialogue", name: "A1", sort_index: 1, locked: false, muted: false, hidden: false, clips: [] },
    { id: "a2", track_type: "audio", role: "audio.bgm", name: "A2", sort_index: 2, locked: false, muted: false, hidden: false, clips: [] },
    { id: "s1", track_type: "subtitle", role: "subtitle.primary", name: "S1", sort_index: 3, locked: false, muted: false, hidden: false, clips: [] },
  ],
  subtitle_cues: [],
  transitions: [],
};

const snapshot: TimelineSnapshot = {
  id: "snapshot-1",
  timeline_id: "timeline-a",
  snapshot_no: 1,
  source_draft_revision: 4,
  state_sha256: "a".repeat(64),
  duration_tick: 4_000_000,
  created_at: "2026-09-05T00:00:00Z",
};

function qc(effective_status: TimelineQcStatus["effective_status"]): TimelineQcStatus {
  return { snapshot_id: snapshot.id, effective_status, attempts: [] };
}

function job(status: JobDetail["status"], currentStage = "export"): JobDetail {
  return {
    id: "job-export",
    project_id: "project-a",
    status,
    mode: "automatic",
    desired_state: "running",
    current_stage: currentStage,
    current_shot: "",
    progress: 0.95,
    message: "export interrupted",
    final_video: "",
    created_at: "2026-09-05T00:00:00Z",
    updated_at: "2026-09-05T00:01:00Z",
    finished_at: null,
    steps: [],
    artifacts: [],
  };
}

describe("TimelineQcWorkspace v0.10 export gate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceApi.listAssets).mockResolvedValue([passedVideo]);
    state.jobs = new Map();
    state.recentIds = [];
    timelineState.draft = draft;
    timelineState.timelineId = "timeline-a";
    timelineState.snapshots = [snapshot];
    timelineState.selectedSnapshotId = snapshot.id;
    timelineState.qcBySnapshot = {};
    timelineState.pendingSave = false;
    timelineState.error = null;
  });

  afterEach(cleanup);

  it.each(["not_run", "failed", "stale"] as const)("disables Timeline export while Snapshot QC is %s", async (status) => {
    timelineState.qcBySnapshot = { [snapshot.id]: qc(status) };
    render(<TimelineQcWorkspace />);
    await waitFor(() => expect(workspaceApi.listAssets).toHaveBeenCalledWith("project-a"));

    expect(screen.getByRole("button", { name: /导出 Snapshot/ })).toBeDisabled();
    expect(actions.retryJob).not.toHaveBeenCalled();
    expect(actions.resumeJob).not.toHaveBeenCalled();
  });

  it("exports only the selected passed Snapshot and never resumes unrelated production jobs", async () => {
    const user = userEvent.setup();
    timelineState.qcBySnapshot = { [snapshot.id]: qc("passed") };
    state.jobs = new Map([["job-export", job("retry_wait")]]);
    state.recentIds = ["job-export"];

    render(<TimelineQcWorkspace />);
    await waitFor(() => expect(workspaceApi.listAssets).toHaveBeenCalledWith("project-a"));
    await user.click(screen.getByRole("button", { name: /导出 Snapshot/ }));

    expect(timelineActions.exportSnapshot).toHaveBeenCalledWith(snapshot.id, {
      width: 1080,
      height: 1920,
      fps_num: 24,
      fps_den: 1,
    });
    expect(actions.retryJob).not.toHaveBeenCalled();
    expect(actions.resumeJob).not.toHaveBeenCalled();
  });

  it("keeps the v0.9 compatible export path when the project has no Timeline", async () => {
    const user = userEvent.setup();
    timelineState.draft = null;
    timelineState.timelineId = "";
    timelineState.snapshots = [];
    timelineState.selectedSnapshotId = null;
    state.jobs = new Map([["job-export", job("retry_wait")]]);
    state.recentIds = ["job-export"];
    actions.retryJob.mockResolvedValue(job("queued"));

    render(<TimelineQcWorkspace />);
    await waitFor(() => expect(workspaceApi.listAssets).toHaveBeenCalledWith("project-a"));
    const legacyButton = screen.getByRole("button", { name: "恢复导出" });
    expect(legacyButton).toBeEnabled();
    await user.click(legacyButton);

    expect(actions.retryJob).toHaveBeenCalledWith("job-export");
    expect(timelineActions.exportSnapshot).not.toHaveBeenCalled();
  });
});

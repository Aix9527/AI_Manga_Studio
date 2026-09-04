import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { workspaceApi } from "@/api/workspace";
import TimelineQcWorkspace from "@/studio/TimelineQcWorkspace";
import type { JobDetail } from "@/types/jobs";

const { mockedWorkspaceStore, state, actions } = vi.hoisted(() => {
  const workspaceState = {
    projectId: "project-a",
    snapshot: {
      project_id: "project-a",
      title: "归墟",
      source_path: "D:/projects/gui-xu/story.txt",
      version: "v0.9",
      progress: 0.95,
      pending_reviews: 0,
      active_jobs: 0,
      estimated_minutes: null,
      stages: [],
      system_health: {},
    },
  };
  return {
    mockedWorkspaceStore: Object.assign(
      (selector: (value: typeof workspaceState) => unknown) => selector(workspaceState),
      { getState: () => workspaceState },
    ),
    state: { jobs: new Map<string, JobDetail>(), recentIds: [] as string[] },
    actions: { retryJob: vi.fn(), resumeJob: vi.fn(), reviewJob: vi.fn() },
  };
});

vi.mock("@/state/workspaceStore", () => ({ useWorkspaceStore: mockedWorkspaceStore }));
vi.mock("@/state/jobStore", () => ({
  useJobStore: () => ({ jobs: state.jobs, recentIds: state.recentIds }),
  jobStoreActions: () => actions,
}));
vi.mock("@/api/workspace", () => ({
  workspaceApi: { listAssets: vi.fn() },
}));

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

describe("TimelineQcWorkspace v0.9 export gate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceApi.listAssets).mockResolvedValue([passedVideo]);
    state.jobs = new Map();
    state.recentIds = [];
  });

  afterEach(cleanup);

  it("retries the existing export-stage job instead of showing fake success", async () => {
    const user = userEvent.setup();
    state.jobs = new Map([["job-export", job("retry_wait")]]);
    state.recentIds = ["job-export"];
    actions.retryJob.mockResolvedValue(job("queued"));

    render(<TimelineQcWorkspace />);
    await waitFor(() => expect(workspaceApi.listAssets).toHaveBeenCalledWith("project-a"));

    const exportButton = screen.getByRole("button", { name: "恢复导出" });
    expect(exportButton).toBeEnabled();
    await user.click(exportButton);

    expect(actions.retryJob).toHaveBeenCalledWith("job-export");
    expect(await screen.findByRole("status")).toHaveTextContent("已恢复导出任务");
  });

  it("fails closed when any asset failed QC", async () => {
    vi.mocked(workspaceApi.listAssets).mockResolvedValue([
      passedVideo,
      { ...passedVideo, id: 2, shot_id: "shot-02", quality_status: "failed" },
    ]);
    state.jobs = new Map([["job-export", job("retry_wait")]]);
    state.recentIds = ["job-export"];

    render(<TimelineQcWorkspace />);
    await waitFor(() => expect(workspaceApi.listAssets).toHaveBeenCalledWith("project-a"));

    expect(screen.getByRole("button", { name: "恢复导出" })).toBeDisabled();
    expect(screen.getByText(/存在未通过 QC 的资产/)).toBeInTheDocument();
    expect(actions.retryJob).not.toHaveBeenCalled();
  });

  it("fails closed while any asset still has pending QC", async () => {
    vi.mocked(workspaceApi.listAssets).mockResolvedValue([
      passedVideo,
      { ...passedVideo, id: 2, shot_id: "shot-02", quality_status: "unreviewed" },
    ]);
    state.jobs = new Map([["job-export", job("retry_wait")]]);
    state.recentIds = ["job-export"];

    render(<TimelineQcWorkspace />);
    await waitFor(() => expect(workspaceApi.listAssets).toHaveBeenCalledWith("project-a"));

    expect(screen.getByRole("button", { name: "恢复导出" })).toBeDisabled();
    expect(screen.getByText(/仍有未完成 QC 的资产/)).toBeInTheDocument();
    expect(actions.retryJob).not.toHaveBeenCalled();
  });
});

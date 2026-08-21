import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StoryAssetsWorkspace from "@/studio/StoryAssetsWorkspace";
import { workspaceApi } from "@/api/workspace";
import type { JobDetail } from "@/types/jobs";

const { workspaceState, jobState } = vi.hoisted(() => ({
  workspaceState: {
    projectId: "project-a",
    snapshot: {
      project_id: "project-a",
      title: "归墟第一部",
      source_path: "D:/AI_Manga_Projects/归墟",
      version: "v0.8",
      progress: 0.42,
      pending_reviews: 0,
      active_jobs: 0,
      estimated_minutes: 12,
      stages: [],
      system_health: { database: "ok" },
    },
  },
  jobState: {
    jobs: new Map<string, JobDetail>(),
    refreshJob: vi.fn(),
  },
}));

vi.mock("@/state/workspaceStore", () => ({
  useWorkspaceStore: Object.assign(
    (selector: (state: typeof workspaceState) => unknown) => selector(workspaceState),
    { getState: () => workspaceState },
  ),
}));

vi.mock("@/state/jobStore", () => ({
  useJobStore: () => ({
    jobs: jobState.jobs,
    refreshJob: jobState.refreshJob,
  }),
}));

vi.mock("@/api/workspace", () => ({
  workspaceApi: {
    listAssets: vi.fn(),
    regenerateAsset: vi.fn(),
  },
}));

function reviewJob(status: JobDetail["status"] = "waiting_review"): JobDetail {
  return {
    id: "job-a",
    project_id: "project-a",
    status,
    mode: "automatic",
    desired_state: "running",
    current_stage: "character",
    current_shot: "苏晚",
    progress: 0.5,
    message: "等待资产审核",
    final_video: "",
    created_at: "2026-08-21T00:00:00Z",
    updated_at: "2026-08-21T00:01:00Z",
    finished_at: null,
    steps: [
      {
        id: "step-a",
        stage_key: "character_generate",
        shot_id: "苏晚",
        status: status === "waiting_review" ? "waiting_review" : "completed",
        attempt: 1,
        progress: 1,
        error_code: "",
        error_message: "",
        quality_attempt: 0,
        ui_stage_key: "character",
        quality_report: {},
        started_at: null,
        finished_at: null,
      },
    ],
    artifacts: [],
  };
}

const characterAsset = {
  id: 1,
  project_id: "project-a",
  job_id: "job-a",
  step_id: "step-a",
  kind: "character_ref",
  path: "D:/assets/suwan.png",
  media_url: "/api/media/suwan.png",
  stage_key: "character",
  scene_id: "",
  shot_id: "苏晚",
  version: 2,
  parent_artifact_id: null,
  active: true,
  quality_status: "passed",
  quality_attempt: 0,
  quality_report: {},
  metadata: {},
  created_at: "2026-08-21T00:00:00Z",
};

describe("StoryAssetsWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    jobState.jobs = new Map([["job-a", reviewJob()]]);
    jobState.refreshJob.mockResolvedValue(reviewJob("queued"));
    vi.mocked(workspaceApi.listAssets).mockResolvedValue([characterAsset]);
    vi.mocked(workspaceApi.regenerateAsset).mockResolvedValue({ status: "accepted" } as never);
  });

  afterEach(cleanup);

  it("loads project assets into reusable categories and exposes the selected asset inspector", async () => {
    render(<StoryAssetsWorkspace />);

    expect(screen.getByRole("heading", { name: "故事 · 资产台" })).toBeInTheDocument();
    for (const category of ["角色", "场景", "道具", "声音", "风格"]) {
      expect(screen.getByRole("button", { name: category })).toBeInTheDocument();
    }

    expect(await screen.findByRole("img", { name: "苏晚" })).toBeInTheDocument();
    expect(screen.getByText(/character_ref · v2 · passed/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "苏晚", level: 3 })).toBeInTheDocument();
    expect(screen.getByDisplayValue("character_ref")).toBeInTheDocument();
    expect(screen.getByDisplayValue("v2")).toBeInTheDocument();
    expect(workspaceApi.listAssets).toHaveBeenCalledWith("project-a");
  });

  it("regenerates the selected asset and switches category views", async () => {
    render(<StoryAssetsWorkspace />);
    await screen.findByRole("img", { name: "苏晚" });

    fireEvent.click(screen.getByRole("button", { name: "重新生成此资产" }));
    await waitFor(() => expect(workspaceApi.regenerateAsset).toHaveBeenCalledWith("project-a", 1));

    fireEvent.click(screen.getByRole("button", { name: "场景" }));
    expect(screen.getByText(/当前类别暂无资产/)).toBeInTheDocument();
  });

  it("disables regeneration when the selected asset job is no longer waiting for review", async () => {
    jobState.jobs = new Map([["job-a", reviewJob("completed")]]);
    render(<StoryAssetsWorkspace />);
    await screen.findByRole("img", { name: "苏晚" });

    expect(screen.getByRole("button", { name: "重新生成此资产" })).toBeDisabled();
    expect(workspaceApi.regenerateAsset).not.toHaveBeenCalled();
  });
});

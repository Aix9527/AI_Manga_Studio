import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StoryboardDirectorWorkspace from "@/studio/StoryboardDirectorWorkspace";
import { workspaceApi } from "@/api/workspace";
import type { JobDetail } from "@/types/jobs";

const { mockedWorkspaceStore, jobState } = vi.hoisted(() => {
  const workspaceState = {
    projectId: "project-a",
    snapshot: {
      project_id: "project-a",
      title: "《归墟》第一部",
      source_path: "D:/AI_Manga_Projects/归墟",
      version: "v0.8",
      progress: 0.68,
      pending_reviews: 1,
      active_jobs: 1,
      estimated_minutes: 12,
      stages: [],
      system_health: { database: "ok" },
    },
  };

  const mockedWorkspaceStore = Object.assign(
    (selector: (state: typeof workspaceState) => unknown) => selector(workspaceState),
    { getState: () => workspaceState },
  );

  return {
    mockedWorkspaceStore,
    jobState: {
      jobs: new Map<string, JobDetail>(),
      loadingProjectId: "",
      loadError: null as unknown | null,
      reviewJob: vi.fn(),
      refreshJob: vi.fn(),
    },
  };
});

vi.mock("@/state/workspaceStore", () => ({ useWorkspaceStore: mockedWorkspaceStore }));
vi.mock("@/state/jobStore", () => ({
  useJobStore: () => ({
    jobs: jobState.jobs,
    loadingProjectId: jobState.loadingProjectId,
    loadError: jobState.loadError,
    reviewJob: jobState.reviewJob,
    refreshJob: jobState.refreshJob,
  }),
}));
vi.mock("@/api/workspace", () => ({
  workspaceApi: {
    listAssets: vi.fn(),
    regenerateAsset: vi.fn(),
  },
}));

function waitingReviewJob(status: JobDetail["status"] = "waiting_review"): JobDetail {
  return {
    id: "job-a",
    project_id: "project-a",
    status,
    mode: "automatic",
    desired_state: "running",
    current_stage: "keyframe",
    current_shot: "shot-01",
    progress: 0.5,
    message: "等待关键帧审核",
    final_video: "",
    created_at: "2026-08-21T00:00:00Z",
    updated_at: "2026-08-21T00:01:00Z",
    finished_at: null,
    steps: [
      {
        id: "step-a",
        stage_key: "visual_generate",
        shot_id: "shot-01",
        status: status === "waiting_review" ? "waiting_review" : "completed",
        attempt: 1,
        progress: 1,
        error_code: "",
        error_message: "",
        quality_attempt: 0,
        ui_stage_key: "keyframe",
        quality_report: {},
        started_at: null,
        finished_at: null,
      },
      {
        id: "video-step",
        stage_key: "video_generate",
        shot_id: "shot-01",
        status: "pending",
        attempt: 0,
        progress: 0,
        error_code: "",
        error_message: "",
        quality_attempt: 0,
        ui_stage_key: "video",
        quality_report: {},
        started_at: null,
        finished_at: null,
      },
    ],
    artifacts: [],
  };
}

const keyframeAsset = {
  id: 1,
  project_id: "project-a",
  job_id: "job-a",
  step_id: "step-a",
  kind: "image/keyframe",
  path: "D:/shots/shot-01.png",
  media_url: "/api/media/shot-01.png",
  stage_key: "keyframe",
  scene_id: "scene-01",
  shot_id: "shot-01",
  version: 2,
  parent_artifact_id: null,
  active: true,
  quality_status: "passed",
  quality_attempt: 0,
  quality_report: {},
  metadata: { title: "建立镜头", duration: 6 },
  created_at: "2026-08-21T00:00:00Z",
};

describe("StoryboardDirectorWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    jobState.jobs = new Map([["job-a", waitingReviewJob()]]);
    jobState.loadingProjectId = "";
    jobState.loadError = null;
    jobState.reviewJob.mockResolvedValue(waitingReviewJob("queued"));
    jobState.refreshJob.mockResolvedValue(waitingReviewJob("queued"));
    vi.mocked(workspaceApi.listAssets).mockResolvedValue([keyframeAsset]);
    vi.mocked(workspaceApi.regenerateAsset).mockResolvedValue(waitingReviewJob("queued"));
  });

  afterEach(cleanup);

  it("renders the approved director console around shot-level controls", async () => {
    render(<StoryboardDirectorWorkspace />);

    expect(screen.getByRole("heading", { name: "分镜导演台" })).toBeInTheDocument();
    expect(screen.getByText("导演参数")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "推镜" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "平移" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "跟拍" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "摇镜" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("建立镜头").length).toBeGreaterThan(0));
    expect(screen.getByText(/当前 v2/)).toBeInTheDocument();
    expect(screen.getByText(/画面质量 passed/)).toBeInTheDocument();
  });

  it("approves the current keyframe to continue into video generation", async () => {
    const user = userEvent.setup();
    render(<StoryboardDirectorWorkspace />);
    await screen.findByRole("img", { name: "建立镜头" });

    const generate = screen.getByRole("button", { name: /生成视频/ });
    expect(generate).toBeEnabled();
    await user.click(generate);

    expect(jobState.reviewJob).toHaveBeenCalledWith(
      "job-a",
      "approve",
      "导演台批准 shot-01 关键帧，继续后续视频生成",
    );
    expect(workspaceApi.regenerateAsset).not.toHaveBeenCalled();
    expect(await screen.findByRole("status")).toHaveTextContent("已批准建立镜头，生产将继续到视频生成");
  });

  it("retries the exact waiting-review asset when retaking the shot", async () => {
    const user = userEvent.setup();
    render(<StoryboardDirectorWorkspace />);
    await screen.findByRole("img", { name: "建立镜头" });

    await user.click(screen.getByRole("button", { name: /重拍镜头/ }));

    expect(workspaceApi.regenerateAsset).toHaveBeenCalledWith("project-a", 1);
    expect(jobState.refreshJob).toHaveBeenCalledWith("job-a");
    expect(jobState.reviewJob).not.toHaveBeenCalled();
    expect(await screen.findByRole("status")).toHaveTextContent("已为建立镜头创建重新生成任务");
  });

  it("disables review actions when the selected asset is no longer the active review step", async () => {
    jobState.jobs = new Map([["job-a", waitingReviewJob("completed")]]);
    render(<StoryboardDirectorWorkspace />);
    await screen.findByRole("img", { name: "建立镜头" });

    expect(screen.getByRole("button", { name: /生成视频/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /重拍镜头/ })).toBeDisabled();
  });
});

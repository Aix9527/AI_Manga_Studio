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
      title: "归墟",
      source_path: "D:/AI_Manga_Projects/归墟",
      version: "v0.9",
      progress: 0.68,
      pending_reviews: 1,
      active_jobs: 1,
      estimated_minutes: 12,
      stages: [],
      system_health: {},
    },
  };
  return {
    mockedWorkspaceStore: Object.assign(
      (selector: (state: typeof workspaceState) => unknown) => selector(workspaceState),
      { getState: () => workspaceState },
    ),
    jobState: {
      jobs: new Map<string, JobDetail>(),
      reviewJob: vi.fn(),
      refreshJob: vi.fn(),
    },
  };
});

vi.mock("@/state/workspaceStore", () => ({ useWorkspaceStore: mockedWorkspaceStore }));
vi.mock("@/state/jobStore", () => ({
  useJobStore: () => ({
    jobs: jobState.jobs,
    reviewJob: jobState.reviewJob,
    refreshJob: jobState.refreshJob,
  }),
}));
vi.mock("@/api/workspace", () => ({
  workspaceApi: {
    listAssets: vi.fn(),
    regenerateAsset: vi.fn(),
    updateDirectorSettings: vi.fn(),
  },
}));

const asset = {
  id: 9,
  project_id: "project-a",
  job_id: "job-a",
  step_id: "step-a",
  kind: "image/keyframe",
  path: "frames/shot-01.png",
  media_url: "/api/workspace/project-a/assets/9/media",
  stage_key: "keyframe",
  scene_id: "scene-01",
  shot_id: "shot-01",
  version: 2,
  parent_artifact_id: null,
  active: true,
  quality_status: "passed",
  quality_attempt: 0,
  quality_report: {},
  metadata: {
    title: "建立镜头",
    duration: 6,
    director: {
      composition: "中心构图",
      shot_size: "特写",
      camera_movement: "平移",
      movement_strength: 35,
      focal_length: "85mm",
      lighting: "柔光",
      emotion: ["压迫"],
      prompt: "旧导演参数",
    },
  },
  created_at: "2026-09-05T00:00:00Z",
};

describe("StoryboardDirectorWorkspace v0.9 director persistence", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    jobState.jobs = new Map();
    vi.mocked(workspaceApi.listAssets).mockResolvedValue([asset]);
    vi.mocked(workspaceApi.updateDirectorSettings).mockResolvedValue(asset);
  });

  afterEach(cleanup);

  it("hydrates director controls from asset metadata and persists edits", async () => {
    const user = userEvent.setup();
    render(<StoryboardDirectorWorkspace />);

    await waitFor(() => expect(workspaceApi.listAssets).toHaveBeenCalledWith("project-a"));
    await waitFor(() => expect(screen.getByLabelText("构图")).toHaveValue("中心构图"));
    expect(screen.getByLabelText("景别")).toHaveValue("特写");
    expect(screen.getByRole("button", { name: "平移" })).toHaveClass("is-active");
    expect(screen.getByLabelText("运动强度")).toHaveValue("35");
    expect(screen.getByLabelText("焦段")).toHaveValue("85mm");
    expect(screen.getByLabelText("光线")).toHaveValue("柔光");
    expect(screen.getByLabelText("执行提示词")).toHaveValue("旧导演参数");

    await user.selectOptions(screen.getByLabelText("构图"), "三分构图");
    await user.selectOptions(screen.getByLabelText("景别"), "中近景");
    await user.click(screen.getByRole("button", { name: "跟拍" }));
    await user.clear(screen.getByLabelText("执行提示词"));
    await user.type(screen.getByLabelText("执行提示词"), "新导演参数");
    await user.click(screen.getByRole("button", { name: /保存导演参数/ }));

    expect(workspaceApi.updateDirectorSettings).toHaveBeenCalledWith(
      "project-a",
      9,
      expect.objectContaining({
        composition: "三分构图",
        shot_size: "中近景",
        camera_movement: "跟拍",
        movement_strength: 35,
        focal_length: "85mm",
        lighting: "柔光",
        prompt: "新导演参数",
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("导演参数已保存");
  });
});

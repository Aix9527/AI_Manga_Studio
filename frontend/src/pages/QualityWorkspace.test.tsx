import React from "react";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { workspaceApi } from "@/api/workspace";
import QualityWorkspace from "@/pages/QualityWorkspace";
import { useWorkspaceStore } from "@/state/workspaceStore";
import type { JobDetail } from "@/types/jobs";
import type { ProjectAsset } from "@/workbench/types";

const jobMocks = vi.hoisted(() => ({
  jobs: new Map<string, JobDetail>(),
  recentIds: [] as string[],
  refreshJob: vi.fn(),
  retryProjectJobs: vi.fn(),
  loadingProjectId: "",
  loadError: null as unknown | null,
}));

vi.mock("@/state/jobStore", () => ({
  useJobStore: () => ({
    jobs: jobMocks.jobs,
    recentIds: jobMocks.recentIds,
    refreshJob: jobMocks.refreshJob,
    retryProjectJobs: jobMocks.retryProjectJobs,
    loadingProjectId: jobMocks.loadingProjectId,
    loadError: jobMocks.loadError,
  }),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function asset(overrides: Partial<ProjectAsset> = {}): ProjectAsset {
  return {
    id: 12,
    project_id: "gui-xu",
    job_id: "job-review",
    step_id: "step-review",
    kind: "image",
    path: "outputs/private-path.png",
    media_url: "/api/workspace/gui-xu/assets/12/media",
    stage_key: "keyframe",
    scene_id: "scene-1",
    shot_id: "shot_03",
    version: 2,
    parent_artifact_id: 8,
    active: true,
    quality_status: "failed",
    quality_attempt: 1,
    quality_report: {
      overall_score: 0.58,
      passed: false,
      character_consistency: 0.8,
      composition_score: 7.5,
      style_consistency: 0,
      technical_quality: 11,
      issues: ["人物五官偏移"],
      suggestions: ["加强角色参考权重"],
      unknown_metric: 9,
    },
    metadata: {},
    created_at: "2026-08-02T08:00:00Z",
    ...overrides,
  };
}

function reviewJob(): JobDetail {
  return {
    id: "job-review",
    project_id: "gui-xu",
    status: "waiting_review",
    mode: "automatic",
    desired_state: "running",
    current_stage: "visual_generate",
    current_shot: "shot_03",
    progress: 0.5,
    message: "",
    final_video: "",
    created_at: "2026-08-02T08:00:00Z",
    updated_at: "2026-08-02T08:01:00Z",
    finished_at: null,
    steps: [{
      id: "step-review",
      stage_key: "visual_generate",
      shot_id: "shot_03",
      status: "waiting_review",
      attempt: 2,
      progress: 1,
      error_code: "",
      error_message: "",
      quality_attempt: 1,
      ui_stage_key: "keyframe",
      quality_report: {},
      started_at: null,
      finished_at: null,
    }],
    artifacts: [],
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
  const job = reviewJob();
  jobMocks.jobs = new Map([[job.id, job]]);
  jobMocks.recentIds = [job.id];
  jobMocks.refreshJob.mockReset().mockResolvedValue(job);
  jobMocks.retryProjectJobs.mockReset().mockResolvedValue([job]);
  jobMocks.loadingProjectId = "";
  jobMocks.loadError = null;
  useWorkspaceStore.setState({
    projectId: "gui-xu",
    snapshot: {
      project_id: "gui-xu",
      title: "归墟",
      source_path: "",
      version: "v01",
      progress: 0,
      pending_reviews: 1,
      active_jobs: 1,
      estimated_minutes: null,
      stages: [],
      system_health: {},
    },
    selectedObject: null,
    loading: false,
    error: null,
  });
});

afterEach(cleanup);

describe("视觉质检工作台", () => {
  it("加载全部版本并显示版本绑定的真实报告，分数兼容 0..1 与 0..10", async () => {
    vi.spyOn(workspaceApi, "listAssets").mockResolvedValue([asset()]);
    render(<QualityWorkspace />);

    const heading = await screen.findByRole("heading", { name: "镜头 03 · 版本 2" });
    const card = heading.closest("article");
    expect(workspaceApi.listAssets).toHaveBeenCalledWith("gui-xu", {});
    expect(within(card!).getByText("人物一致性")).toBeInTheDocument();
    expect(within(card!).getByText("8.0 / 10")).toBeInTheDocument();
    expect(within(card!).getByText("7.5 / 10")).toBeInTheDocument();
    expect(within(card!).getByText("0.0 / 10")).toBeInTheDocument();
    expect(within(card!).getByText("自动重试 1 / 2")).toBeInTheDocument();
    expect(within(card!).getByText("人物五官偏移")).toBeInTheDocument();
    expect(within(card!).getByText("加强角色参考权重")).toBeInTheDocument();
    expect(within(card!).queryByText("unknown_metric")).not.toBeInTheDocument();
    expect(within(card!).queryByText("11.0 / 10")).not.toBeInTheDocument();
    expect(within(card!).getByRole("img", { name: "镜头 03 版本 2 预览" })).toHaveAttribute(
      "src",
      "/api/workspace/gui-xu/assets/12/media",
    );
    expect(document.body).not.toHaveTextContent("private-path.png");
  });

  it("空或损坏报告明确显示尚无报告，不补造分数", async () => {
    vi.spyOn(workspaceApi, "listAssets").mockResolvedValue([
      asset({ id: 13, version: 1, quality_report: {} }),
    ]);
    render(<QualityWorkspace />);

    const heading = await screen.findByRole("heading", { name: "镜头 03 · 版本 1" });
    const card = heading.closest("article");
    expect(within(card!).getByText("尚无质检报告")).toBeInTheDocument();
    expect(within(card!).queryByText(/\/ 10/)).not.toBeInTheDocument();
  });

  it("仅待审版本可通过安全素材接口重生，成功后刷新素材和任务", async () => {
    const user = userEvent.setup();
    const item = asset();
    vi.spyOn(workspaceApi, "listAssets").mockResolvedValue([item]);
    const regenerate = vi.spyOn(workspaceApi, "regenerateAsset").mockResolvedValue({
      ...reviewJob(),
      status: "queued",
    });
    render(<QualityWorkspace />);

    await user.click(await screen.findByRole("button", { name: "根据质检建议重新生成" }));

    expect(regenerate).toHaveBeenCalledWith("gui-xu", 12);
    await waitFor(() => expect(workspaceApi.listAssets).toHaveBeenCalledTimes(2));
    expect(jobMocks.refreshJob).toHaveBeenCalledWith("job-review");
  });

  it("任务或步骤不处于待审时禁用重生并给出中文原因", async () => {
    const item = asset();
    jobMocks.jobs = new Map([["job-review", { ...reviewJob(), status: "running" }]]);
    vi.spyOn(workspaceApi, "listAssets").mockResolvedValue([item]);
    render(<QualityWorkspace />);

    const button = await screen.findByRole("button", { name: /根据质检建议重新生成/ });
    expect(button).toBeDisabled();
    expect(screen.getByText("该版本当前不处于待审核状态")).toBeInTheDocument();
  });

  it("旧的 inactive 版本即使关联当前待审步骤也不能重生", async () => {
    vi.spyOn(workspaceApi, "listAssets").mockResolvedValue([asset({ active: false })]);
    render(<QualityWorkspace />);

    const button = await screen.findByRole("button", { name: /根据质检建议重新生成/ });
    expect(button).toBeDisabled();
    expect(screen.getByText("该版本当前不处于待审核状态")).toBeInTheDocument();
  });

  it("任务状态加载失败时显示独立原因和重试入口", async () => {
    const user = userEvent.setup();
    jobMocks.loadError = new Error("jobs offline");
    vi.spyOn(workspaceApi, "listAssets").mockResolvedValue([asset()]);
    render(<QualityWorkspace />);

    expect(await screen.findByText("任务状态加载失败，请重新加载任务")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /根据质检建议重新生成/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "重新加载任务" }));
    expect(jobMocks.retryProjectJobs).toHaveBeenCalledTimes(1);
  });

  it("切换项目后忽略旧项目的重生回包", async () => {
    const user = userEvent.setup();
    const regeneration = deferred<JobDetail>();
    vi.spyOn(workspaceApi, "listAssets").mockImplementation(async (projectId) =>
      projectId === "gui-xu" ? [asset()] : [],
    );
    vi.spyOn(workspaceApi, "regenerateAsset").mockReturnValue(regeneration.promise);
    render(<QualityWorkspace />);
    await user.click(await screen.findByRole("button", { name: "根据质检建议重新生成" }));

    useWorkspaceStore.setState({
      projectId: "project-b",
      snapshot: {
        ...useWorkspaceStore.getState().snapshot!,
        project_id: "project-b",
        title: "项目 B",
      },
    });
    regeneration.resolve({ ...reviewJob(), status: "queued" });
    await waitFor(() => expect(workspaceApi.listAssets).toHaveBeenCalledWith("project-b", {}));

    expect(jobMocks.refreshJob).not.toHaveBeenCalled();
    expect(workspaceApi.listAssets).toHaveBeenCalledTimes(2);
  });
});

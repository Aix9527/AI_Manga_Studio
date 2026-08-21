import React from "react";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/jobs";
import TaskWorkspace from "@/pages/TaskWorkspace";
import { useWorkspaceStore } from "@/state/workspaceStore";
import type { JobDetail, JobStatus, StepInfo } from "@/types/jobs";

const jobMocks = vi.hoisted(() => ({
  loadProjectJobs: vi.fn(),
  subscribeActiveJobs: vi.fn(),
  retryProjectJobs: vi.fn(),
  pauseJob: vi.fn(),
  resumeJob: vi.fn(),
  retryJob: vi.fn(),
  cancelJob: vi.fn(),
  reviewJob: vi.fn(),
  jobs: new Map<string, JobDetail>(),
  recentIds: [] as string[],
  loadingProjectId: "",
  loadError: null as unknown | null,
}));

vi.mock("@/state/jobStore", () => ({
  useJobStore: () => ({
    jobs: jobMocks.jobs,
    recentIds: jobMocks.recentIds,
    loadProjectJobs: jobMocks.loadProjectJobs,
    subscribeActiveJobs: jobMocks.subscribeActiveJobs,
    retryProjectJobs: jobMocks.retryProjectJobs,
    loadingProjectId: jobMocks.loadingProjectId,
    loadError: jobMocks.loadError,
    pauseJob: jobMocks.pauseJob,
    resumeJob: jobMocks.resumeJob,
    retryJob: jobMocks.retryJob,
    cancelJob: jobMocks.cancelJob,
    reviewJob: jobMocks.reviewJob,
  }),
}));

function step(overrides: Partial<StepInfo> = {}): StepInfo {
  return {
    id: "step-visual",
    stage_key: "visual_generate",
    shot_id: "shot_03",
    status: "running",
    attempt: 1,
    progress: 0.45,
    error_code: "",
    error_message: "",
    quality_attempt: 0,
    ui_stage_key: "keyframe",
    quality_report: {},
    started_at: null,
    finished_at: null,
    ...overrides,
  };
}

function job(id: string, status: JobStatus, overrides: Partial<JobDetail> = {}): JobDetail {
  return {
    id,
    project_id: "gui-xu",
    status,
    mode: "automatic",
    desired_state: "running",
    current_stage: "visual_generate",
    current_shot: "shot_03",
    progress: 0.45,
    message: "",
    final_video: "",
    created_at: "2026-08-02T08:00:00Z",
    updated_at: "2026-08-02T08:01:00Z",
    finished_at: null,
    steps: [step({ status: status === "waiting_review" ? "waiting_review" : status === "failed" ? "failed" : "running" })],
    artifacts: [{
      id: 7,
      project_id: "gui-xu",
      kind: "image",
      path: "outputs/shot_03.png",
      sha256: "sha",
      stage_key: "keyframe",
      scene_id: "scene-1",
      shot_id: "shot_03",
      version: 2,
      parent_artifact_id: 3,
      active: true,
      quality_status: "unreviewed",
      metadata: {},
      media_url: "",
    }],
    ...overrides,
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
  jobMocks.jobs = new Map([
    ["job-running", job("job-running", "running")],
    ["job-paused", job("job-paused", "paused")],
    ["job-failed", job("job-failed", "failed", {
      message: "CUDA out of memory",
      steps: [step({ status: "failed", error_code: "GPU_OOM", error_message: "CUDA out of memory" })],
    })],
    ["job-review", job("job-review", "waiting_review")],
  ]);
  jobMocks.recentIds = [...jobMocks.jobs.keys()];
  jobMocks.loadProjectJobs.mockReset().mockResolvedValue([...jobMocks.jobs.values()]);
  jobMocks.subscribeActiveJobs.mockReset().mockReturnValue(vi.fn());
  jobMocks.retryProjectJobs.mockReset().mockResolvedValue([...jobMocks.jobs.values()]);
  jobMocks.loadingProjectId = "";
  jobMocks.loadError = null;
  for (const action of [
    jobMocks.pauseJob,
    jobMocks.resumeJob,
    jobMocks.retryJob,
    jobMocks.cancelJob,
    jobMocks.reviewJob,
  ]) action.mockReset().mockResolvedValue(undefined);
  useWorkspaceStore.setState({
    projectId: "gui-xu",
    snapshot: {
      project_id: "gui-xu",
      title: "归墟",
      source_path: "",
      version: "v01",
      progress: 0,
      pending_reviews: 1,
      active_jobs: 2,
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

describe("任务工作台", () => {
  it("从当前项目恢复持久任务并复用统一 SSE 生命周期", async () => {
    const close = vi.fn();
    jobMocks.subscribeActiveJobs.mockReturnValue(close);

    const page = render(<TaskWorkspace />);

    expect(await screen.findByRole("heading", { name: "生成任务" })).toBeInTheDocument();
    await waitFor(() => expect(jobMocks.loadProjectJobs).toHaveBeenCalledWith("gui-xu"));
    await waitFor(() => expect(jobMocks.subscribeActiveJobs).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: /选择任务 job-running/ })).toBeInTheDocument();
    page.unmount();
    expect(close).toHaveBeenCalledTimes(1);
  });

  it("按真实状态提供中文动作并同步选中任务", async () => {
    const user = userEvent.setup();
    render(<TaskWorkspace />);

    await user.click(screen.getByRole("button", { name: /选择任务 job-running/ }));
    expect(screen.getByRole("button", { name: "暂停任务 job-running" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "取消任务 job-running" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "暂停任务 job-running" }));
    expect(jobMocks.pauseJob).toHaveBeenCalledWith("job-running");
    expect(useWorkspaceStore.getState().selectedObject).toEqual({ type: "任务", id: "job-running" });

    await user.click(screen.getByRole("button", { name: /选择任务 job-paused/ }));
    expect(screen.getByRole("button", { name: "恢复任务 job-paused" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "取消任务 job-paused" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: /选择任务 job-failed/ }));
    expect(screen.getByRole("button", { name: "重试任务 job-failed" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "取消任务 job-failed" })).toBeEnabled();
    expect(screen.getByText("显存不足，请降低分辨率或释放显存后重试")).toBeInTheDocument();
    const technical = screen.getByText("原始技术详情").closest("details");
    expect(technical).not.toHaveAttribute("open");
    expect(within(technical!).getByText("CUDA out of memory")).toBeInTheDocument();
  });

  it("待审回滚先展示影响预览，再由用户确认", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "rollbackPreview").mockResolvedValue({
      step_id: "step-visual",
      invalidated_step_ids: ["step-audio", "step-compose"],
    });
    render(<TaskWorkspace />);

    await user.click(screen.getByRole("button", { name: /选择任务 job-review/ }));
    expect(screen.getByRole("button", { name: "批准任务 job-review" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "重新生成任务 job-review" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "回滚任务 job-review" }));

    expect(api.rollbackPreview).toHaveBeenCalledWith("job-review", "step-visual");
    expect(await screen.findByText("将影响 2 个后续步骤")).toBeInTheDocument();
    expect(jobMocks.reviewJob).not.toHaveBeenCalledWith("job-review", "rollback");
    await user.click(screen.getByRole("button", { name: "确认回滚任务 job-review" }));
    expect(jobMocks.reviewJob).toHaveBeenCalledWith("job-review", "rollback");
  });

  it("可按状态和阶段筛选并展示步骤、镜头、进度与产物", async () => {
    const user = userEvent.setup();
    render(<TaskWorkspace />);

    await user.selectOptions(screen.getByLabelText("任务状态"), "failed");
    expect(screen.getByRole("button", { name: /选择任务 job-failed/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /选择任务 job-running/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /选择任务 job-failed/ }));
    const detail = screen.getByRole("region", { name: "job-failed" });
    expect(within(detail).getByText("关键帧生成")).toBeInTheDocument();
    expect(within(detail).getAllByText("镜头 03").length).toBeGreaterThan(0);
    expect(within(detail).getAllByText("45%").length).toBeGreaterThan(0);
    expect(within(detail).getByText("版本 2 · 图片")).toBeInTheDocument();
  });

  it("自动同步筛选后的回退选择，并在空列表时清除旧任务选择", async () => {
    const user = userEvent.setup();
    render(<TaskWorkspace manageLifecycle={false} />);

    await waitFor(() => expect(useWorkspaceStore.getState().selectedObject).toEqual({
      type: "任务",
      id: "job-running",
    }));
    await user.selectOptions(screen.getByLabelText("任务状态"), "failed");
    await waitFor(() => expect(useWorkspaceStore.getState().selectedObject).toEqual({
      type: "任务",
      id: "job-failed",
    }));
    await user.selectOptions(screen.getByLabelText("任务状态"), "completed");
    await waitFor(() => expect(useWorkspaceStore.getState().selectedObject).toBeNull());
  });

  it("壳层生命周期模式也显示任务加载失败并提供显式重试", async () => {
    const user = userEvent.setup();
    jobMocks.loadError = new Error("offline");
    render(<TaskWorkspace manageLifecycle={false} />);

    expect(screen.getByRole("alert")).toHaveTextContent("offline");
    await user.click(screen.getByRole("button", { name: "重新加载任务" }));

    expect(jobMocks.retryProjectJobs).toHaveBeenCalledTimes(1);
    expect(jobMocks.loadProjectJobs).not.toHaveBeenCalled();
  });
});

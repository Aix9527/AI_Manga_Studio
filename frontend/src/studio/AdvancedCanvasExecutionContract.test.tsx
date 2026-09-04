import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdvancedCanvasWorkspace from "@/studio/AdvancedCanvasWorkspace";
import type { JobDetail } from "@/types/jobs";

const { workspaceStore, jobState, executeFromStage } = vi.hoisted(() => {
  const workspace = {
    projectId: "project-a",
    snapshot: { project_id: "project-a" },
  };
  return {
    workspaceStore: Object.assign(
      (selector: (value: typeof workspace) => unknown) => selector(workspace),
      { getState: () => workspace },
    ),
    jobState: { jobs: new Map<string, JobDetail>(), recentIds: [] as string[] },
    executeFromStage: vi.fn(),
  };
});

vi.mock("@xyflow/react", () => ({
  ReactFlow: ({ children }: { children?: React.ReactNode }) => <div data-testid="flow-surface">{children}</div>,
  Background: () => null,
  Controls: () => null,
  MiniMap: () => null,
}));
vi.mock("@/state/workspaceStore", () => ({ useWorkspaceStore: workspaceStore }));
vi.mock("@/state/jobStore", () => ({
  useJobStore: () => ({ jobs: jobState.jobs, recentIds: jobState.recentIds }),
  jobStoreActions: () => ({ executeFromStage }),
}));

function job(status: JobDetail["status"] = "paused"): JobDetail {
  return {
    id: "job-canvas",
    project_id: "project-a",
    status,
    mode: "automatic",
    desired_state: "running",
    current_stage: "video_generate",
    current_shot: "shot_001",
    progress: 0.6,
    message: "paused",
    final_video: "",
    created_at: "2026-09-05T00:00:00Z",
    updated_at: "2026-09-05T00:01:00Z",
    finished_at: null,
    steps: [{
      id: "step-video-1",
      stage_key: "video_generate",
      shot_id: "shot_001",
      status: "completed",
      attempt: 1,
      progress: 1,
      error_code: "",
      error_message: "",
      quality_attempt: 0,
      ui_stage_key: "video",
      quality_report: {},
      started_at: null,
      finished_at: null,
    }],
    artifacts: [],
  };
}

describe("AdvancedCanvasWorkspace v0.9 formal execution contract", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const current = job();
    jobState.jobs = new Map([[current.id, current]]);
    jobState.recentIds = [current.id];
    executeFromStage.mockResolvedValue({ ...current, status: "queued" });
  });

  afterEach(cleanup);

  it("submits the selected video node as a formal rerun_node command", async () => {
    render(<AdvancedCanvasWorkspace />);

    expect(screen.getByLabelText("目标镜头")).toHaveValue("shot_001");
    fireEvent.click(screen.getByRole("button", { name: "运行选中节点" }));

    await waitFor(() => expect(executeFromStage).toHaveBeenCalledWith("job-canvas", {
      stage_key: "video_generate",
      shot_id: "shot_001",
      mode: "rerun_node",
    }));
    expect(await screen.findByRole("status")).toHaveTextContent("已提交单节点重跑");
  });

  it("submits continue without bypassing the same formal job", async () => {
    render(<AdvancedCanvasWorkspace />);
    fireEvent.click(screen.getByRole("button", { name: "从当前节点继续" }));

    await waitFor(() => expect(executeFromStage).toHaveBeenCalledWith("job-canvas", {
      stage_key: "video_generate",
      shot_id: "shot_001",
      mode: "continue",
    }));
  });

  it("fails closed while the production job is waiting for review", () => {
    const current = job("waiting_review");
    jobState.jobs = new Map([[current.id, current]]);
    jobState.recentIds = [current.id];

    render(<AdvancedCanvasWorkspace />);

    expect(screen.getByRole("button", { name: "运行选中节点" })).toBeDisabled();
    expect(screen.getByText(/不能绕过 Review Gate/)).toBeInTheDocument();
    expect(executeFromStage).not.toHaveBeenCalled();
  });

  it("does not claim a professional template was published without persistence", () => {
    render(<AdvancedCanvasWorkspace />);

    fireEvent.click(screen.getByRole("button", { name: "发布到一键成片" }));

    expect(screen.queryByText("当前流程已设为一键成片专业模板")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/模板发布尚未接入持久化契约/);
  });
});

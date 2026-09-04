import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { workspaceApi } from "@/api/workspace";
import { useWorkspaceStore } from "@/state/workspaceStore";
import TimelineQcWorkspace from "@/studio/TimelineQcWorkspace";
import type { ProjectAsset } from "@/workbench/types";

vi.mock("@/state/jobStore", () => ({
  useJobStore: () => ({ jobs: new Map(), recentIds: [] }),
  jobStoreActions: () => ({ retryJob: vi.fn(), resumeJob: vi.fn(), reviewJob: vi.fn() }),
}));

function asset(overrides: Partial<ProjectAsset> = {}): ProjectAsset {
  return {
    id: 1,
    project_id: "gui-xu",
    job_id: "job-1",
    step_id: "step-1",
    kind: "video",
    path: "outputs/shot_01.mp4",
    media_url: "/api/workspace/gui-xu/assets/1/media",
    stage_key: "video",
    scene_id: "scene-1",
    shot_id: "shot_01",
    version: 1,
    parent_artifact_id: null,
    active: true,
    quality_status: "passed",
    quality_attempt: 0,
    quality_report: {},
    metadata: {},
    created_at: "2026-08-21T00:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
  useWorkspaceStore.setState({
    projectId: "gui-xu",
    snapshot: {
      project_id: "gui-xu",
      title: "归墟",
      source_path: "F:/projects/gui-xu.txt",
      version: "v01",
      progress: 0.8,
      pending_reviews: 0,
      active_jobs: 0,
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

describe("时间线质检工作台", () => {
  it("使用真实资产构建时间线、QC 汇总与媒体预览，并在 QC 失败时闭锁导出", async () => {
    vi.spyOn(workspaceApi, "listAssets").mockResolvedValue([
      asset(),
      asset({ id: 2, kind: "image", media_url: "/api/workspace/gui-xu/assets/2/media", shot_id: "shot_02", quality_status: "failed" }),
      asset({ id: 3, kind: "audio", media_url: "/api/workspace/gui-xu/assets/3/media", shot_id: "shot_03", quality_status: "unreviewed" }),
    ]);

    render(<TimelineQcWorkspace />);

    expect(await screen.findByRole("heading", { name: "时间线 · 质检 · 导出" })).toBeInTheDocument();
    await waitFor(() => expect(workspaceApi.listAssets).toHaveBeenCalledWith("gui-xu"));
    expect(screen.getByRole("button", { name: "shot_01" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "shot_02" })).toBeEnabled();
    expect(screen.getByText("通过").parentElement).toHaveTextContent("1");
    expect(screen.getByText("失败").parentElement).toHaveTextContent("1");
    expect(screen.getByText("待检测").parentElement).toHaveTextContent("1");
    expect(document.querySelector("video")).toHaveAttribute("src", "/api/workspace/gui-xu/assets/1/media");

    expect(screen.getByRole("button", { name: "导出成片" })).toBeDisabled();
    expect(screen.getByText(/存在未通过 QC 的资产/)).toBeInTheDocument();
  });
});

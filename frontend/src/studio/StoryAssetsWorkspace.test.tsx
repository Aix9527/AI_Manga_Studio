import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StoryAssetsWorkspace from "@/studio/StoryAssetsWorkspace";
import { workspaceApi } from "@/api/workspace";

const { workspaceState } = vi.hoisted(() => ({
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
}));

vi.mock("@/state/workspaceStore", () => ({
  useWorkspaceStore: Object.assign(
    (selector: (state: typeof workspaceState) => unknown) => selector(workspaceState),
    { getState: () => workspaceState },
  ),
}));

vi.mock("@/api/workspace", () => ({
  workspaceApi: {
    listAssets: vi.fn(),
    regenerateAsset: vi.fn(),
  },
}));

describe("StoryAssetsWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceApi.listAssets).mockResolvedValue([
      {
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
      },
    ]);
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
});

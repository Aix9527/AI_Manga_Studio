import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import StoryboardDirectorWorkspace from "@/studio/StoryboardDirectorWorkspace";
import { workspaceApi } from "@/api/workspace";

const { mockedWorkspaceStore } = vi.hoisted(() => {
  const workspaceState = {
    projectId: "project-a",
    snapshot: {
      project_id: "project-a",
      title: "《归墟》第一部",
      source_path: "D:/AI_Manga_Projects/归墟",
      version: "v0.8",
      progress: 0.68,
      pending_reviews: 0,
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

  return { mockedWorkspaceStore };
});

vi.mock("@/state/workspaceStore", () => ({ useWorkspaceStore: mockedWorkspaceStore }));
vi.mock("@/api/workspace", () => ({
  workspaceApi: {
    listAssets: vi.fn(),
    regenerateAsset: vi.fn(),
  },
}));

describe("StoryboardDirectorWorkspace", () => {
  it("renders the approved director console around shot-level controls", async () => {
    vi.mocked(workspaceApi.listAssets).mockResolvedValue([
      {
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
      },
    ]);

    render(<StoryboardDirectorWorkspace />);

    expect(screen.getByRole("heading", { name: "分镜导演台" })).toBeInTheDocument();
    expect(screen.getByText("导演参数")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "推镜" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "平移" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "跟拍" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "摇镜" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /生成视频/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /重拍镜头/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("建立镜头")).toBeInTheDocument());
    expect(screen.getByText(/当前 v2/)).toBeInTheDocument();
    expect(screen.getByText(/画面质量 passed/)).toBeInTheDocument();
  });
});

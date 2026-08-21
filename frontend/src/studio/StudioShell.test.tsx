import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import StudioShell from "@/studio/StudioShell";

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
  loading: false,
  loadWorkspace: vi.fn().mockResolvedValue(undefined),
};

const mockedWorkspaceStore = Object.assign(
  (selector: (state: typeof workspaceState) => unknown) => selector(workspaceState),
  { getState: () => workspaceState },
);

const jobActions = {
  resetProjectJobs: vi.fn(),
  loadProjectJobs: vi.fn().mockResolvedValue([]),
  subscribeActiveJobs: vi.fn(() => () => undefined),
};

vi.mock("@/state/workspaceStore", () => ({ useWorkspaceStore: mockedWorkspaceStore }));
vi.mock("@/state/projectStore", () => ({
  useProjectStore: (selector: (state: { project: { id: string } }) => unknown) => selector({ project: { id: "project-a" } }),
}));
vi.mock("@/state/jobStore", () => ({
  useJobStore: () => ({ loadedProjectId: "project-a", loadRevision: 1 }),
  jobStoreActions: () => jobActions,
}));

describe("StudioShell", () => {
  it("exposes only the five unified production workspaces", () => {
    render(
      <MemoryRouter initialEntries={["/project"]}>
        <Routes>
          <Route element={<StudioShell />}>
            <Route path="/project" element={<div>项目台内容</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    const nav = screen.getByRole("navigation", { name: "制作工作台导航" });
    expect(nav).toHaveTextContent("项目");
    expect(nav).toHaveTextContent("故事·资产");
    expect(nav).toHaveTextContent("分镜导演台");
    expect(nav).toHaveTextContent("高级画布");
    expect(nav).toHaveTextContent("时间线·质检");
    expect(screen.getByText("项目台内容")).toBeInTheDocument();
    expect(screen.getByText("本地模式")).toBeInTheDocument();
    expect(screen.queryByText("工业化制作台")).not.toBeInTheDocument();
    expect(screen.queryByText("提示词操作系统")).not.toBeInTheDocument();
  });
});

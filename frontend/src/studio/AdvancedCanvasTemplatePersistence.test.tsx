import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdvancedCanvasWorkspace from "@/studio/AdvancedCanvasWorkspace";

const {
  workspaceStore,
  listProductionTemplates,
  getProductionTemplate,
  saveProductionTemplate,
  publishProductionTemplate,
} = vi.hoisted(() => {
  const workspace = { projectId: "project-a", snapshot: { project_id: "project-a" } };
  return {
    workspaceStore: Object.assign(
      (selector: (value: typeof workspace) => unknown) => selector(workspace),
      { getState: () => workspace },
    ),
    listProductionTemplates: vi.fn(),
    getProductionTemplate: vi.fn(),
    saveProductionTemplate: vi.fn(),
    publishProductionTemplate: vi.fn(),
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
  useJobStore: () => ({ jobs: new Map(), recentIds: [] }),
  jobStoreActions: () => ({ executeFromStage: vi.fn() }),
}));
vi.mock("@/api/productionTemplates", () => ({
  listProductionTemplates,
  getProductionTemplate,
  saveProductionTemplate,
  publishProductionTemplate,
}));

const version = (value: number, name = `v${value}`) => ({
  id: `ptv-${value}`,
  project_id: "project-a",
  version: value,
  name,
  schema_version: 1,
  content_json: JSON.stringify({
    schema_version: 1,
    canvas: { nodes: [], edges: [] },
    production: {
      shot_duration: 5,
      width: 1080,
      height: 1920,
      fps: 24,
      options: { style: "anime", local_first: true },
    },
    stage_policy: { stages: [] },
  }),
  content_sha256: `source-${value}`,
  compiled_json: JSON.stringify({ production: { width: 1080 } }),
  compiled_sha256: `compiled-${value}`,
  status: "active",
  created_at: "2026-09-05T00:00:00Z",
  published_at: null,
});

describe("AdvancedCanvasWorkspace v0.9.1 template persistence", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listProductionTemplates.mockResolvedValue({
      project_id: "project-a",
      latest_version: 0,
      published_version: null,
      versions: [],
    });
    saveProductionTemplate.mockResolvedValue(version(1));
    publishProductionTemplate.mockResolvedValue({ ...version(1), published_at: "2026-09-05T00:01:00Z" });
  });

  afterEach(cleanup);

  it("requires a real saved version before publish", async () => {
    render(<AdvancedCanvasWorkspace />);

    await waitFor(() => expect(listProductionTemplates).toHaveBeenCalledWith("project-a"));
    expect(screen.getByRole("button", { name: "发布到一键成片" })).toBeDisabled();
    expect(screen.getByText(/最新保存：未保存/)).toBeInTheDocument();
  });

  it("saves the current canvas as an immutable backend version and then publishes it", async () => {
    render(<AdvancedCanvasWorkspace />);
    await waitFor(() => expect(listProductionTemplates).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "保存为模板" }));

    await waitFor(() => expect(saveProductionTemplate).toHaveBeenCalledTimes(1));
    expect(saveProductionTemplate).toHaveBeenCalledWith("project-a", expect.objectContaining({
      schema_version: 1,
      canvas: expect.objectContaining({ nodes: expect.any(Array), edges: expect.any(Array) }),
      production: expect.objectContaining({ width: 1080, height: 1920, fps: 24 }),
    }));
    expect(await screen.findByText(/最新保存：v1/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "发布到一键成片" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "发布到一键成片" }));

    await waitFor(() => expect(publishProductionTemplate).toHaveBeenCalledWith("project-a", 1));
    expect(await screen.findByText(/当前发布：v1/)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/v1 已发布/);
  });

  it("loads the latest saved canvas and can republish an older version as rollback", async () => {
    listProductionTemplates.mockResolvedValue({
      project_id: "project-a",
      latest_version: 2,
      published_version: 2,
      versions: [version(2), version(1)],
    });
    getProductionTemplate.mockResolvedValue(version(2));
    publishProductionTemplate.mockResolvedValue({ ...version(1), published_at: "2026-09-05T00:02:00Z" });

    render(<AdvancedCanvasWorkspace />);

    await waitFor(() => expect(getProductionTemplate).toHaveBeenCalledWith("project-a", 2));
    expect(screen.getByText(/最新保存：v2/)).toBeInTheDocument();
    expect(screen.getByText(/当前发布：v2/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("模板历史版本"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "发布历史版本" }));

    await waitFor(() => expect(publishProductionTemplate).toHaveBeenCalledWith("project-a", 1));
    expect(await screen.findByText(/当前发布：v1/)).toBeInTheDocument();
  });
});

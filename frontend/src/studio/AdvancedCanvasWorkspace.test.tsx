import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdvancedCanvasWorkspace from "@/studio/AdvancedCanvasWorkspace";

const { workspaceStore } = vi.hoisted(() => {
  const workspace = { projectId: "project-a", snapshot: { project_id: "project-a" } };
  return {
    workspaceStore: Object.assign(
      (selector: (value: typeof workspace) => unknown) => selector(workspace),
      { getState: () => workspace },
    ),
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

describe("AdvancedCanvasWorkspace", () => {
  afterEach(cleanup);

  it("renders the professional canvas controls and formal production description", () => {
    render(<AdvancedCanvasWorkspace />);

    expect(screen.getByRole("heading", { name: "高级画布 / 精修工作台" })).toBeInTheDocument();
    expect(screen.getByLabelText("高级生产节点画布")).toBeInTheDocument();
    expect(screen.getByTestId("flow-surface")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "运行选中节点" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "从当前节点继续" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "保存为模板" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "发布到一键成片" })).toBeInTheDocument();
    expect(screen.getByText(/默认流程：小说文本/)).toHaveTextContent("TI2V视频生成");
    expect(screen.getByText(/当前项目没有可执行的 Production Job/)).toBeInTheDocument();
  });
});

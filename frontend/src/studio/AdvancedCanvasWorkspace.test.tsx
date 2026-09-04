import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdvancedCanvasWorkspace from "@/studio/AdvancedCanvasWorkspace";

vi.mock("@xyflow/react", () => ({
  ReactFlow: ({ children }: { children?: React.ReactNode }) => <div data-testid="flow-surface">{children}</div>,
  Background: () => null,
  Controls: () => null,
  MiniMap: () => null,
}));

describe("AdvancedCanvasWorkspace", () => {
  afterEach(cleanup);

  it("renders the professional canvas controls and default pipeline description", () => {
    render(<AdvancedCanvasWorkspace />);

    expect(screen.getByRole("heading", { name: "高级画布 / 精修工作台" })).toBeInTheDocument();
    expect(screen.getByLabelText("高级生产节点画布")).toBeInTheDocument();
    expect(screen.getByTestId("flow-surface")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "运行选中节点" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "从当前节点继续" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存为模板" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "发布到一键成片" })).toBeInTheDocument();
    expect(screen.getByText(/默认流程：小说文本/)).toHaveTextContent("TI2V视频生成");
  });

  it("delegates execution to the real production job instead of claiming a node ran", () => {
    render(<AdvancedCanvasWorkspace />);

    fireEvent.click(screen.getByRole("button", { name: "运行选中节点" }));
    expect(screen.getByText(/高级画布暂不直接提交单节点任务：TI2V视频生成/)).toBeInTheDocument();
    expect(screen.getByText(/项目台或时间线任务队列/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "发布到一键成片" }));
    expect(screen.getByText(/模板发布尚未接入持久化契约/)).toBeInTheDocument();
    expect(screen.queryByText("当前流程已设为一键成片专业模板")).not.toBeInTheDocument();
  });
});

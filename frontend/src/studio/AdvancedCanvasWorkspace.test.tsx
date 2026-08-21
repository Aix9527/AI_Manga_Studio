import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AdvancedCanvasWorkspace from "@/studio/AdvancedCanvasWorkspace";

vi.mock("@xyflow/react", () => ({
  ReactFlow: ({ children }: { children?: React.ReactNode }) => <div data-testid="flow-surface">{children}</div>,
  Background: () => null,
  Controls: () => null,
  MiniMap: () => null,
}));

describe("AdvancedCanvasWorkspace", () => {
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

  it("reports local professional-mode actions without bypassing orchestration", () => {
    render(<AdvancedCanvasWorkspace />);

    fireEvent.click(screen.getByRole("button", { name: "运行选中节点" }));
    expect(screen.getByText("运行选中节点：TI2V视频生成")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "发布到一键成片" }));
    expect(screen.getByText("当前流程已设为一键成片专业模板")).toBeInTheDocument();
  });
});

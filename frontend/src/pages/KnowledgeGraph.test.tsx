import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterAll, beforeAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import KnowledgeGraph from "@/pages/KnowledgeGraph";
import * as kg from "@/api/knowledgeGraph";

vi.mock("@/api/client", () => ({
  request: vi.fn(),
  userMessage: (err: unknown) => String(err),
}));

vi.mock("@/api/knowledgeGraph", () => ({
  kgStats: vi.fn(),
  kgIngest: vi.fn(),
  kgNodes: vi.fn(),
  kgGetNode: vi.fn(),
  kgNeighbors: vi.fn(),
  kgPaths: vi.fn(),
  kgSearch: vi.fn(),
  kgRecommend: vi.fn(),
}));

const mocked = vi.mocked(kg);

function stats() {
  return {
    nodes: 12,
    edges: 10,
    node_types: ["project", "episode", "assignment"],
    by_type: { project: 1, episode: 2, assignment: 3, production_event: 4, review: 2 },
    by_edge: { HAS_PHASE: 4, DEPENDS_ON: 3, REVIEWED_BY: 3 },
    by_project: { P1: 12 },
  };
}

function node(overrides: Record<string, unknown> = {}) {
  return {
    id: "ASG-1",
    type: "assignment",
    label: "EP1 · planning · Producer",
    properties: { status: "done" },
    project_id: "P1",
    created_at: "t",
    ...overrides,
  };
}

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
});

afterAll(() => {
  // @ts-expect-error restore original if defined
  if (window.__originalMatchMedia) Object.defineProperty(window, "matchMedia", { value: window.__originalMatchMedia });
});

beforeEach(() => {
  mocked.kgStats.mockResolvedValue(stats() as never);
  mocked.kgNodes.mockResolvedValue({ nodes: [node(), node({ id: "ep:EP1", type: "episode", label: "Episode EP1" })] } as never);
  mocked.kgGetNode.mockResolvedValue(node() as never);
  mocked.kgNeighbors.mockResolvedValue({
    node_id: "ASG-1", depth: 1, count: 2,
    neighbors: [
      { node: node({ id: "ep:EP1", type: "episode" }), edge: { type: "HAS_PHASE", properties: {} } },
      { node: node({ id: "RVW-1", type: "review" }), edge: { type: "REVIEWED_BY", properties: {} } },
    ],
  } as never);
  mocked.kgRecommend.mockResolvedValue({
    node_id: "ASG-1",
    recommendations: [{ node: node({ id: "ASG-2" }), score: 1.5 }],
    note: "仅建议，不自动修改生产资产",
  } as never);
  mocked.kgPaths.mockResolvedValue({
    from: "ASG-1", to: "ASG-2",
    paths: [[{ id: "ASG-1", edge: "" }, { id: "ASG-2", edge: "DEPENDS_ON" }]],
  } as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("KnowledgeGraph", () => {
  it("renders stats and node list", async () => {
    render(<KnowledgeGraph />);
    await waitFor(() => expect(screen.getByText("节点")).toBeInTheDocument());
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("EP1 · planning · Producer")).toBeInTheDocument();
    expect(screen.getByText("生产知识图谱")).toBeInTheDocument();
    expect(mocked.kgStats).toHaveBeenCalledTimes(1);
    expect(mocked.kgNodes).toHaveBeenCalledWith({ limit: "50" });
  });

  it("selects a node and shows neighbors / recommendation / path", async () => {
    render(<KnowledgeGraph />);
    await waitFor(() => expect(screen.getByText("节点")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "ASG-1" }));
    await waitFor(() => expect(screen.getByText("邻居 2：")).toBeInTheDocument());
    expect(mocked.kgPaths).toHaveBeenCalled();
    expect(screen.getByText("智能推荐：")).toBeInTheDocument();
    expect(screen.getByText("推荐关联路径：")).toBeInTheDocument();
    expect(mocked.kgNeighbors).toHaveBeenCalledWith("ASG-1");
    expect(mocked.kgRecommend).toHaveBeenCalledWith("ASG-1");
  });

  it("re-ingests via button", async () => {
    mocked.kgIngest.mockResolvedValue({ node_total: 12 } as never);
    render(<KnowledgeGraph />);
    await waitFor(() => expect(screen.getByText("节点")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /重新摄取/ }));
    await waitFor(() => expect(mocked.kgIngest).toHaveBeenCalledWith(
      expect.objectContaining({ actor: "human", reason: "重建知识图谱" }),
    ));
  });
});

import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterAll, beforeAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProducerAgent from "@/pages/ProducerAgent";
import * as pa from "@/api/producerAgent";

vi.mock("@/api/client", () => ({
  request: vi.fn(),
  userMessage: (err: unknown) => String(err),
}));

vi.mock("@/api/producerAgent", () => ({
  producerPlan: vi.fn(),
  producerResource: vi.fn(),
  producerExplainRisk: vi.fn(),
  producerReport: vi.fn(),
}));

const mocked = vi.mocked(pa);

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
  mocked.producerPlan.mockResolvedValue({
    project_id: "P1",
    steps: [{ priority: 1, action: "处理人工审批队列", detail: "1 个任务等待人工", evidence: {} }],
    summary: { active_tasks: 4, waiting_human: 1, blocked: 1, parallel_episodes: 2 },
    auto_approve: false,
    note: "规划建议仅参考",
  } as never);
  mocked.producerResource.mockResolvedValue({
    suggestions: [{ kind: "capacity", suggestion: "建议扩充 GPU/Worker 容量", evidence: {} }],
    auto_schedule: false,
    note: "资源建议仅参考",
  } as never);
  mocked.producerReport.mockResolvedValue({
    project_id: "P1",
    production_state: { task_total: 10, active_tasks: 4, worker_count: 2 },
    prediction: [],
    timeline_summary: { blocked_total: 1, rework_total: 2, waiting_human_total: 1, parallel_episodes: 2 },
    knowledge_graph: { nodes: 100, edges: 80 },
    risks: [],
    optimization_candidates: [],
    plan: [],
    resource_suggestions: [],
    approvals_pending: { waiting_human: 1, pi_candidates: 0, risk_candidates: 0 },
    governance: { auto_control: false },
    note: "制作报告仅供决策参考",
  } as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ProducerAgent", () => {
  it("renders plan, resource suggestion and report", async () => {
    render(<ProducerAgent />);
    await waitFor(() => expect(screen.getByText("处理人工审批队列")).toBeInTheDocument());
    expect(screen.getByText("AI 制片人")).toBeInTheDocument();
    expect(screen.getByText("建议扩充 GPU/Worker 容量")).toBeInTheDocument();
    expect(screen.getByText("制作报告（Producer Report）")).toBeInTheDocument();
    expect(screen.getAllByText((c) => c.includes("auto_approve=false")).length).toBeGreaterThan(0);
    expect(mocked.producerPlan).toHaveBeenCalledTimes(1);
    expect(mocked.producerReport).toHaveBeenCalledTimes(1);
  });
});

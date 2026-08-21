import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterAll, beforeAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CommandCenter from "@/pages/CommandCenter";
import * as cc from "@/api/commandCenter";

vi.mock("@/api/client", () => ({
  request: vi.fn(),
  userMessage: (err: unknown) => String(err),
}));

vi.mock("@/api/commandCenter", () => ({
  ccOverview: vi.fn(),
}));

const mocked = vi.mocked(cc);

function overview() {
  return {
    mode: "command_center",
    governance: { auto_control: false, auto_apply: false, auto_deploy: false, human_approval: true },
    production_state: { task_total: 10, active_tasks: 4, worker_count: 2, queue_depth: 2, waiting_human: 1, assignment_active: 3, gpu_usage: 0.5, worker_idle_rate: 0.1 },
    prediction: [
      { scenario: "baseline", label: "基线（当前负载）", eta_hours: 0.5, cost: 10, bottleneck: "当前队列" },
      { scenario: "20_episodes", label: "同时生产 20 集", eta_hours: 10, cost: 200, bottleneck: "队列吞吐（任务量放大）" },
    ],
    timeline_summary: { blocked_total: 1, rework_total: 2, waiting_human_total: 1, parallel_episodes: 3 },
    knowledge_graph: { nodes: 100, edges: 80 },
    intelligence: { pi_candidates: [{ id: "AC-1", target_type: "episode", target_id: "EP1", reason: "retention 低", status: "proposed" }] },
    risks: [{ id: "RK-1", risk_type: "schedule", target_id: "waiting_human", severity: "medium", suggestion: "优先处理人工审批队列" }],
    approvals_pending: { waiting_human: 1, pi_candidates: 1, risk_candidates: 1 },
    audit_coverage: 1,
    note: "所有建议需人工审批后生效",
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
  mocked.ccOverview.mockResolvedValue(overview() as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("CommandCenter", () => {
  it("renders fused overview", async () => {
    render(<CommandCenter />);
    await waitFor(() => expect(screen.getByText("任务总量")).toBeInTheDocument());
    expect(screen.getByText("生产指挥中心")).toBeInTheDocument();
    expect(screen.getByText("同时生产 20 集")).toBeInTheDocument();
    expect(screen.getByText("优先处理人工审批队列")).toBeInTheDocument();
    expect(screen.getByText("AC-1")).toBeInTheDocument();
    expect(screen.getByText((c) => c.includes("Control Suggestion ≠ Auto Control"))).toBeInTheDocument();
    expect(mocked.ccOverview).toHaveBeenCalledTimes(1);
  });
});

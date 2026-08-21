import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterAll, beforeAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DigitalTwin from "@/pages/DigitalTwin";
import * as dt from "@/api/digitalTwin";

vi.mock("@/api/client", () => ({
  request: vi.fn(),
  userMessage: (err: unknown) => String(err),
}));

vi.mock("@/api/digitalTwin", () => ({
  dtOverview: vi.fn(),
  dtState: vi.fn(),
  dtTimeline: vi.fn(),
  dtHeatmap: vi.fn(),
  dtScenarios: vi.fn(),
  dtSimulate: vi.fn(),
  dtPredict: vi.fn(),
  dtRiskCandidates: vi.fn(),
  dtDismissRisk: vi.fn(),
}));

const mocked = vi.mocked(dt);

function timeline() {
  return {
    episodes: [
      {
        episode_id: "EP1",
        stages: [
          { stage: "planning", role: "Producer", status: "done", started_at: "t", completed_at: "t", duration_s: 300, attempt: 1, rework_count: 0, blocked_reason: "" },
          { stage: "script", role: "Writer", status: "in_progress", started_at: "t", completed_at: "", duration_s: null, attempt: 2, rework_count: 1, blocked_reason: "" },
        ],
        blocked_count: 0, rework_count: 1, waiting_human: 0,
      },
      {
        episode_id: "EP2",
        stages: [
          { stage: "generation", role: "Production", status: "escalated", started_at: "", completed_at: "", duration_s: null, attempt: 1, rework_count: 0, blocked_reason: "GPU 不足" },
        ],
        blocked_count: 1, rework_count: 0, waiting_human: 1,
      },
    ],
    blocked_total: 1, rework_total: 1, waiting_human_total: 1,
  };
}

function heatmap() {
  return {
    gpu: { usage: 0.5, vram_mb: 100, queue_length: 3, worker_idle_rate: 0.2, active_tasks: 2 },
    production: { parallel_episodes: 2, assignment_density: 3, stage_density: { script: 1 }, retry_hotspots: { script: 1 } },
  };
}

function risk(overrides: Record<string, unknown> = {}) {
  return {
    id: "RK-1", risk_type: "schedule", target_type: "production", target_id: "waiting_human",
    severity: "medium", evidence: {}, suggestion: "优先处理人工审批队列", status: "proposed",
    project_id: "P1", created_at: "t", ...overrides,
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
  mocked.dtOverview.mockResolvedValue({
    mode: "simulation_and_visibility_only", auto_control: false,
    state: { task_total: 4, active_tasks: 2, worker_count: 2, queue_depth: 1, waiting_human: 1 },
    timeline_summary: { blocked_total: 1, rework_total: 1, waiting_human_total: 1 },
  } as never);
  mocked.dtTimeline.mockResolvedValue(timeline() as never);
  mocked.dtHeatmap.mockResolvedValue(heatmap() as never);
  mocked.dtRiskCandidates.mockResolvedValue({ candidates: [risk()] } as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("DigitalTwin", () => {
  it("renders mode, timeline and heatmap", async () => {
    render(<DigitalTwin />);
    await waitFor(() => expect(screen.getByText("EP1")).toBeInTheDocument());
    expect(screen.getByText((content) => content.includes("simulation_and_visibility_only") && content.includes("auto_control=false"))).toBeInTheDocument();
    expect(screen.getByText("EP2")).toBeInTheDocument();
    expect(screen.getByText("Retry 热点：")).toBeInTheDocument();
    expect(mocked.dtTimeline).toHaveBeenCalledTimes(1);
  });

  it("runs simulation and shows scenarios", async () => {
    mocked.dtSimulate.mockResolvedValue({
      auto_control: false,
      results: [
        { scenario: "baseline", label: "基线（当前负载）", eta_s: 100, eta_hours: 0.03, cost: 1, bottleneck: "当前队列", assumptions: {} },
        { scenario: "20_episodes", label: "同时生产 20 集", eta_s: 2000, eta_hours: 0.56, cost: 10, bottleneck: "队列吞吐（任务量放大）", assumptions: {} },
      ],
    } as never);
    render(<DigitalTwin />);
    await waitFor(() => expect(screen.getByText("EP1")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /运行模拟/ }));
    await waitFor(() => expect(screen.getByText("基线（当前负载）")).toBeInTheDocument());
    expect(screen.getByText("同时生产 20 集")).toBeInTheDocument();
    expect(mocked.dtSimulate).toHaveBeenCalledTimes(1);
  });

  it("predicts risks and dismisses candidate", async () => {
    mocked.dtPredict.mockResolvedValue({ candidates: [risk()], count: 1, auto_control: false } as never);
    render(<DigitalTwin />);
    await waitFor(() => expect(screen.getByText("EP1")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /生成风险候选/ }));
    await waitFor(() => expect(mocked.dtPredict).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByText("优先处理人工审批队列")).toBeInTheDocument());
    const dismiss = Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.replace(/\s/g, "") === "驳回")!;
    fireEvent.click(dismiss);
    await waitFor(() => expect(mocked.dtDismissRisk).toHaveBeenCalledWith("RK-1", expect.objectContaining({ actor: "human" })));
  });
});

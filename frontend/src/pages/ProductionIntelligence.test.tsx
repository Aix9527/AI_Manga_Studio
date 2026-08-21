import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterAll, beforeAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as antd from "antd";
import ProductionIntelligence from "@/pages/ProductionIntelligence";
import * as pi from "@/api/productionIntelligence";

vi.mock("@/api/client", () => ({
  request: vi.fn(),
  userMessage: {
    success: () => undefined,
    error: () => undefined,
  },
}));

vi.mock("@/api/productionIntelligence", () => ({
  productionIntelligenceStats: vi.fn(),
  recordProductionEvent: vi.fn(),
  listProductionEvents: vi.fn(),
  overview: vi.fn(),
  costIntelligence: vi.fn(),
  cycleIntelligence: vi.fn(),
  directorIntelligence: vi.fn(),
  promptRoi: vi.fn(),
  episodeRoi: vi.fn(),
  riskRadar: vi.fn(),
  optimizationCandidates: vi.fn(),
  proposeAnalyticsCandidates: vi.fn(),
  listAnalyticsCandidates: vi.fn(),
  reviewAnalyticsCandidate: vi.fn(),
  applyAnalyticsCandidate: vi.fn(),
}));

const mocked = vi.mocked(pi);

function stats() {
  return {
    warehouse: { events: 12, events_by_type: { shot_completed: 12 }, audit_coverage: 1, shot_metrics: 2, episode_metrics: 1 },
    candidates: { candidates: 1, by_status: { proposed: 1 }, auto_learning: false, auto_apply: false },
    governance: { auto_learning: false, auto_apply: false, auto_deploy: false, human_approval: true, rollback: true, audit: true },
  };
}

function overviewData() {
  return {
    project_id: "p1",
    episodes: 1,
    shots: 2,
    success_rate: 0.75,
    avg_quality: 0.812,
    total_cost: 12.5,
    revision_rate: 0.2,
    cost: { project_id: "p1", planned: 10, actual: 12.5, variance: 2.5, factors: [{ factor: "retry", cost: 2.5 }], unexplained: 0, explanation_rate: 1 },
    cycle: { project_id: "p1", lead_time_s: 60, segments: { waiting: 10, generation: 40, review: 5, approval: 5 }, ratios: { waiting: 0.17, generation: 0.67, review: 0.08, approval: 0.08 } },
  };
}

function candidate(overrides: Record<string, unknown> = {}) {
  return {
    id: "C-1",
    target_type: "shot_design",
    target_id: "shot-1",
    project_id: "p1",
    suggested_changes: {},
    evidence: {},
    reason: "retention 低",
    status: "proposed",
    reviewer: "",
    created_at: "",
    decided_at: "",
    applied_at: "",
    ...overrides,
  };
}

beforeAll(() => {
  vi.spyOn(antd.message, "success").mockImplementation(() => undefined as never);
  vi.spyOn(antd.message, "error").mockImplementation(() => undefined as never);
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
  mocked.productionIntelligenceStats.mockResolvedValue(stats() as never);
  mocked.overview.mockResolvedValue(overviewData() as never);
  mocked.costIntelligence.mockResolvedValue(overviewData().cost as never);
  mocked.cycleIntelligence.mockResolvedValue(overviewData().cycle as never);
  mocked.episodeRoi.mockResolvedValue({
    episodes: [{ episode_id: "E1", project_id: "p1", retention: 0.6, hook_score: 0.8, cliffhanger: 0.5, avg_qc: 0.9, failure_rate: 0.1, cost_actual: 8, cost_planned: 6, roi: 0.1125, lead_time_s: 60 }],
  } as never);
  mocked.riskRadar.mockResolvedValue({
    risks: [{ risk_type: "qc_failure_rate", target_id: "E1", value: 0.12, severity: 0.4, message: "QC 失败率偏高" }],
  } as never);
  mocked.directorIntelligence.mockResolvedValue({
    directors: [{ director: "D1", shots: 5, success_rate: 0.8, avg_quality: 0.85, avg_revision: 0.2, total_cost: 10 }],
  } as never);
  mocked.promptRoi.mockResolvedValue({
    prompts: [{ prompt_version: "P1", usage: 3, success_rate: 0.67, avg_quality: 0.8, revision_rate: 0.1 }],
  } as never);
  mocked.listAnalyticsCandidates.mockResolvedValue({ candidates: [candidate()] } as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function clickTab(label: RegExp) {
  fireEvent.click(screen.getByRole("tab", { name: label }));
}

describe("ProductionIntelligence", () => {
  it("renders warehouse stats, governance gate and overview", async () => {
    render(<ProductionIntelligence />);
    await waitFor(() => expect(screen.getByText("事件数")).toBeInTheDocument());
    expect(screen.getByText("Production Intelligence")).toBeInTheDocument();
    expect(screen.getByText("auto_learning=false / auto_apply=false")).toBeInTheDocument();
    expect(screen.getByText("集数")).toBeInTheDocument();
    expect(screen.getAllByText("12").length).toBeGreaterThan(0);
    expect(screen.getByText("成本智能 Cost Intelligence")).toBeInTheDocument();
    expect(screen.getByText("总 Lead Time")).toBeInTheDocument();
    expect(mocked.productionIntelligenceStats).toHaveBeenCalledTimes(1);
  });

  it("shows episode ROI rows", async () => {
    render(<ProductionIntelligence />);
    await waitFor(() => expect(screen.getByText("事件数")).toBeInTheDocument());
    clickTab(/集 ROI/);
    await waitFor(() => expect(screen.getByText("E1")).toBeInTheDocument());
    expect(screen.getAllByText("60s").length).toBeGreaterThan(0);
  });

  it("shows risk radar rows", async () => {
    render(<ProductionIntelligence />);
    await waitFor(() => expect(screen.getByText("事件数")).toBeInTheDocument());
    clickTab(/风险雷达/);
    await waitFor(() => expect(screen.getByText("QC 失败率")).toBeInTheDocument());
    expect(screen.getByText("QC 失败率偏高")).toBeInTheDocument();
  });

  it("proposes candidates from analytics", async () => {
    mocked.proposeAnalyticsCandidates.mockResolvedValue({ candidates: [] } as never);
    render(<ProductionIntelligence />);
    await waitFor(() => expect(screen.getByText("事件数")).toBeInTheDocument());
    clickTab(/优化候选/);
    const propose = await screen.findByRole("button", { name: /从分析生成候选/ });
    fireEvent.click(propose);
    await waitFor(() => expect(mocked.proposeAnalyticsCandidates).toHaveBeenCalledTimes(1));
  });

  it("reviews a proposed candidate", async () => {
    render(<ProductionIntelligence />);
    await waitFor(() => expect(screen.getByText("事件数")).toBeInTheDocument());
    clickTab(/优化候选/);
    await waitFor(() => expect(screen.getByText("C-1")).toBeInTheDocument());
    await waitFor(() => {
      expect(Array.from(document.querySelectorAll("button")).some((b) => b.textContent?.replace(/\s/g, "") === "批准")).toBe(true);
    });
    const approve = Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.replace(/\s/g, "") === "批准")!;
    fireEvent.click(approve);
    await waitFor(() => expect(mocked.reviewAnalyticsCandidate).toHaveBeenCalledWith("C-1", "approved", "human"));
  });
});
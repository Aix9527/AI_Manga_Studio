import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import DirectorEvolutionCenter from "@/pages/DirectorEvolutionCenter";
import * as api from "@/api/directorEvolution";
import * as adaptiveApi from "@/api/adaptiveRouter";

vi.mock("@/api/directorEvolution", () => ({
  getEvolutionStats: vi.fn(),
  getCandidates: vi.fn(),
  getHistory: vi.fn(),
  approveCandidate: vi.fn(),
  rejectCandidate: vi.fn(),
  rollbackPolicy: vi.fn(),
  seedMockData: vi.fn(),
}));

vi.mock("@/api/adaptiveRouter", () => ({
  getAdaptiveProposal: vi.fn(),
  approveAdaptiveRecommendation: vi.fn(),
  rejectAdaptiveRecommendation: vi.fn(),
  rollbackAdaptivePolicy: vi.fn(),
  getAbValidation: vi.fn(),
}));

vi.mock("@/api/governance", () => ({
  getRegistry: vi.fn(),
  getAudit: vi.fn(),
  createRelease: vi.fn(),
  approveRelease: vi.fn(),
  rollbackRelease: vi.fn(),
  certifyRelease: vi.fn(),
  freezeRelease: vi.fn(),
}));

import * as governanceApi from "@/api/governance";

const mocked = vi.mocked(api);
const mockedAdaptive = vi.mocked(adaptiveApi);
const mockedGovernance = vi.mocked(governanceApi);

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

function stats() {
  return {
    source: "production",
    policy_version: 1.0,
    routes: { action: "rule", dialogue: "qwen", world: "hybrid" },
    policy_learning: { min_samples: 20, confidence_threshold: 0.85, mode: "manual_approval" },
    accumulation: {
      shots: 520,
      projects: 3,
      episodes: 4,
      feedback_records: 1040,
      revisions: 12,
      targets: { shots: 500, projects: 3, feedback_records: 1000 },
    },
    policy_performance: [
      { scene_type: "action", director: "rule-v2", shots: 120, avg_score: 91.2, avg_cost: 8.0, avg_generation_time: 30.0, avg_human_score: 90.0, revisions: 5 },
      { scene_type: "dialogue", director: "llm-qwen", shots: 240, avg_score: 94.5, avg_cost: 12.0, avg_generation_time: 45.0, avg_human_score: 93.0, revisions: 7 },
    ],
    win_rate: {
      counts: { rule: 1, qwen: 1, hybrid: 0 },
      by_scene_type: [
        { scene_type: "action", winner: "rule-v2", avg_score: 91.2, shots: 120 },
        { scene_type: "dialogue", winner: "llm-qwen", avg_score: 94.5, shots: 240 },
      ],
    },
  };
}

function candidates() {
  return {
    mode: "manual_approval",
    min_samples: 20,
    confidence_threshold: 0.85,
    count: 1,
    candidates: [
      {
        id: "action|rule-v2->llm-qwen",
        scene_type: "action",
        from_director: "rule-v2",
        to_director: "llm-qwen",
        samples_from: 120,
        samples_to: 143,
        avg_from: 91.2,
        avg_to: 96.0,
        score_delta: 4.8,
        confidence: 0.91,
        reason: "avg_quality comparison",
      },
    ],
  };
}

describe("DirectorEvolutionCenter", () => {
  beforeEach(() => {
    mocked.getEvolutionStats.mockResolvedValue(stats() as never);
    mocked.getCandidates.mockResolvedValue(candidates() as never);
    mocked.getHistory.mockResolvedValue({ entries: [] } as never);
    mockedGovernance.getRegistry.mockResolvedValue({
      components: {
        pipeline: { name: "pipeline", version: "v12.9", updated_at: "2026-08-06T00:00:00" },
        director: { name: "director", version: "council-v1", updated_at: "2026-08-06T00:00:00" },
      },
      releases: 1,
    } as never);
    mockedGovernance.getAudit.mockResolvedValue({
      entries: [
        {
          id: "AUD-1",
          action: "release_create",
          created_at: "2026-08-06T00:00:00",
          detail: { release_id: "rel-12.9-1" },
        },
      ],
    } as never);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the current policy version and accumulation targets", async () => {
    render(<DirectorEvolutionCenter />);
    await waitFor(() => expect(screen.getByText("Director Evolution Center")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("当前策略版本 v1")).toBeInTheDocument());
    expect(screen.getByText(/520/)).toBeInTheDocument();
    expect(document.body.textContent).toContain("1,040");
  });

  async function openCandidateTab() {
    render(<DirectorEvolutionCenter />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /Candidate Queue/i })).toBeInTheDocument());
    screen.getByRole("tab", { name: /Candidate Queue/i }).click();
    await waitFor(() => expect(screen.getByText("Score Δ")).toBeInTheDocument());
  }

  it("shows candidate queue with approve/reject actions", async () => {
    await openCandidateTab();
    expect(screen.getAllByText("action").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /Approve/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /Reject/i }).length).toBeGreaterThan(0);
  });

  it("approve calls the API and refreshes", async () => {
    mocked.approveCandidate.mockResolvedValue({ log: { id: "EVO-1", action: "approve" } } as never);
    await openCandidateTab();
    screen.getByRole("button", { name: /Approve/i }).click();
    await waitFor(() => expect(mocked.approveCandidate).toHaveBeenCalledWith(
      "action|rule-v2->llm-qwen",
      "production",
      "dashboard approval",
    ));
    expect(mocked.getEvolutionStats).toHaveBeenCalledTimes(2); // initial + refresh
  });

  function adaptiveProposal() {
    return {
      source: "production",
      count: 40,
      cells: 20,
      scope_isolation: { checked: 40, violations: 0, isolated: true },
      production_value_weights: { quality: 0.4, continuity: 0.2, stability: 0.15, cost: 0.15, latency: 0.1 },
      recommendations: [
        {
          id: "科幻|action|primary",
          cell: "科幻|action",
          genre: "科幻",
          scene_type: "action",
          role: "primary",
          director: "llm-gpt",
          pvs: 75.4,
          delta_to_next: 14.3,
          samples: 30,
          status: "pending",
          reason: "",
          evidence: { shots: 30, pvs: {}, memory: { present: false, rows: 0 } },
        },
        {
          id: "科幻|action|fallback",
          cell: "科幻|action",
          genre: "科幻",
          scene_type: "action",
          role: "fallback",
          director: "rule-v2",
          pvs: 89.7,
          delta_to_next: 0,
          samples: 30,
          status: "pending",
          reason: "",
          evidence: { shots: 30, pvs: {}, memory: { present: false, rows: 0 } },
        },
      ],
    } as never;
  }

  function abValidation() {
    return {
      shots: 100,
      before: { director_route: {}, avg_quality: 0.902, avg_cost: 0.416 },
      after: { adaptive_primary: {}, avg_quality: 0.96, avg_cost: 0.9 },
      quality_gain_pct: 6.4,
      cost_reduction_pct: -122.7,
      cost_delta_pct: 122.7,
      passed: true,
      gate: { quality_gain_min: 5, cost_reduction_min: 10 },
    } as never;
  }

  it("renders Adaptive Router recommendations and A/B gate", async () => {
    mockedAdaptive.getAdaptiveProposal.mockResolvedValue(adaptiveProposal());
    mockedAdaptive.getAbValidation.mockResolvedValue(abValidation());
    render(<DirectorEvolutionCenter />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /Adaptive Router/i })).toBeInTheDocument());
    screen.getByRole("tab", { name: /Adaptive Router/i }).click();
    await waitFor(() => expect(screen.getByText("Production Value Score 权重")).toBeInTheDocument());
    expect(screen.getByText(/40 条建议/)).toBeInTheDocument();
    expect(screen.getByText("llm-gpt")).toBeInTheDocument();
    expect(screen.getByText(/PASS/)).toBeInTheDocument();
  });

  it("adaptive approve calls API and refreshes", async () => {
    mockedAdaptive.getAdaptiveProposal.mockResolvedValue(adaptiveProposal());
    mockedAdaptive.getAbValidation.mockResolvedValue(abValidation());
    mockedAdaptive.approveAdaptiveRecommendation.mockResolvedValue({ cell: "科幻|action" } as never);
    render(<DirectorEvolutionCenter />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /Adaptive Router/i })).toBeInTheDocument());
    screen.getByRole("tab", { name: /Adaptive Router/i }).click();
    await waitFor(() => expect(screen.getAllByRole("button", { name: /Approve/i }).length).toBeGreaterThan(0));
    screen.getAllByRole("button", { name: /Approve/i })[0].click();
    await waitFor(() => expect(mockedAdaptive.approveAdaptiveRecommendation).toHaveBeenCalledWith(
      "科幻|action|primary",
      "production",
    ));
  });

  async function openProductionTab() {
    render(<DirectorEvolutionCenter />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /Production OS/i })).toBeInTheDocument());
    screen.getByRole("tab", { name: /Production OS/i }).click();
    await waitFor(() => expect(screen.getByText("Registry 组件版本")).toBeInTheDocument());
  }

  it("renders Production OS console with registry, release and audit", async () => {
    await openProductionTab();
    expect(screen.getByText("Pipeline Health")).toBeInTheDocument();
    expect(screen.getByText("Director Intelligence")).toBeInTheDocument();
    expect(screen.getByText("Production History")).toBeInTheDocument();
    expect(screen.getByText("pipeline")).toBeInTheDocument();
    expect(screen.getByText("v12.9")).toBeInTheDocument();
    expect(screen.getByText("release_create")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /创建 Release 签名/i })).toBeInTheDocument();
  });

  it("create release calls governance API and updates state", async () => {
    mockedGovernance.createRelease.mockResolvedValue({
      release_id: "rel-12.9-123",
      manifest: { project: "归墟觉醒·天倾", pipeline: "v12.9", director: "council-v1", policy: "adaptive-v3", models: ["wan2.2", "qwen"] },
      audit: { id: "AUD-2", action: "release_create", created_at: "2026-08-06T00:00:00", detail: {} },
    } as never);
    await openProductionTab();
    screen.getByRole("button", { name: /创建 Release 签名/i }).click();
    await waitFor(() => expect(mockedGovernance.createRelease).toHaveBeenCalledWith(
      expect.objectContaining({ pipeline: "v12.9", director: "council-v1", policy: "adaptive-v3" }),
    ));
    await waitFor(() => expect(screen.getAllByText("rel-12.9-123").length).toBeGreaterThan(0));
  });

  it("freeze button calls governance freeze API", async () => {
    mockedGovernance.freezeRelease.mockResolvedValue({
      manifest: { release_id: "rel-12.9-9", artifacts: {} },
      root: "production_release",
    } as never);
    await openProductionTab();
    screen.getByRole("button", { name: /打包冻结/i }).click();
    await waitFor(() => expect(mockedGovernance.freezeRelease).toHaveBeenCalledWith(
      expect.objectContaining({ project: "归墟觉醒·天倾" }),
    ));
    await waitFor(() => expect(screen.getAllByText("production_release").length).toBeGreaterThan(0));
  });
});

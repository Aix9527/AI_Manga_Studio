import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import IndustrialStudio from "@/pages/IndustrialStudio";
import * as industrial from "@/api/industrial";
import * as feedback from "@/api/feedback";

vi.mock("@/api/industrial", () => ({
  projectReadiness: vi.fn(),
  listBibles: vi.fn(),
  listWorlds: vi.fn(),
  listScenes: vi.fn(),
  environmentSummary: vi.fn(),
  listShotDna: vi.fn(),
  shotDnaStats: vi.fn(),
  createBible: vi.fn(),
  addBibleView: vi.fn(),
  addBibleExpression: vi.fn(),
  addBibleAction: vi.fn(),
  addBibleVersion: vi.fn(),
  createWorld: vi.fn(),
  createScene: vi.fn(),
  retrieveShotDna: vi.fn(),
  addShotDna: vi.fn(),
  productionReadinessMatrix: vi.fn(),
}));

vi.mock("@/api/feedback", () => ({
  feedbackStats: vi.fn(),
  listFeedbackEvents: vi.fn(),
  listFeedbackCandidates: vi.fn(),
  recordFeedbackEvent: vi.fn(),
  recordShotOutcome: vi.fn(),
  autoProposeCandidates: vi.fn(),
  reviewCandidate: vi.fn(),
  applyCandidate: vi.fn(),
}));

const mocked = vi.mocked(industrial);
const fbMocked = vi.mocked(feedback);

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

function bible(overrides: Record<string, unknown> = {}) {
  return {
    character_id: "CH001",
    identity: { name: "陈夜", age: 26, gender: "male", personality: ["brave"], background: "" },
    versions: { v1: { id: "v1", parent: "", approved: true, locked: true } },
    views: { front: { key: "front", image_path: "", prompt: "front view" } },
    expressions: { smile: { key: "smile", image_path: "", prompt: "smile" } },
    actions: { walk: { key: "walk", description: "walk", prompt: "" } },
    completeness: { views: 1, views_required: 3, expressions: 1, expressions_required: 6, actions: 1, actions_required: 6, versions: 1, ratio: 0.2 },
    ...overrides,
  };
}

describe("IndustrialStudio", () => {
  beforeEach(() => {
    mocked.projectReadiness.mockResolvedValue({
      project_id: "default",
      ready: true,
      missing: [],
      gates: { character: { pass: true }, world: { pass: true }, shot_dna: { pass: true } },
    } as never);
    mocked.listBibles.mockResolvedValue({ bibles: [bible()] } as never);
    mocked.listWorlds.mockResolvedValue({
      worlds: [{ id: "WLD-1", project_id: "default", name: "归墟", era: "未来科幻", power_system: "量子能力", visual_style: "赛博朋克", color_language: "冷蓝" }],
    } as never);
    mocked.listScenes.mockResolvedValue({ scenes: [] } as never);
    mocked.environmentSummary.mockResolvedValue({ project_id: "default", entries: 2, by_kind: { physics_rule: 1 }, updated_at: "" } as never);
    mocked.listShotDna.mockResolvedValue({ items: [{ id: "dna-1", category: "action", scene: "battle", camera: {}, lens: "35mm", lighting: "strobe", composition: "", emotion: "fury→focus", style: "", tags: [], prompt_template: "", success_rate: 0.84, usage_count: 143 }] } as never);
    mocked.shotDnaStats.mockResolvedValue({ total: 20, by_category: { action: 4 }, avg_success_rate: 0.86, total_usage: 100 } as never);
    mocked.productionReadinessMatrix.mockResolvedValue({
      project_id: "default", status: "READY",
      gates: { asset_ready: { status: "READY", required: true, checks: 3, missing: [], recommended_actions: [], evidence: [], checked_at: "" } },
    } as never);
    fbMocked.feedbackStats.mockResolvedValue({ events: 1, by_kind: { critic: 1 }, by_target_type: { character: 1 }, candidates: 1, by_status: { proposed: 1 } } as never);
    fbMocked.listFeedbackEvents.mockResolvedValue({ events: [{ id: "EV-1", kind: "critic", source: "vision_critic", target_type: "character", target_id: "CH-001", project_id: "", severity: "high", issues: ["expression_forced"], metrics: {}, created_at: "" }] } as never);
    fbMocked.listFeedbackCandidates.mockResolvedValue({ candidates: [{ id: "CD-1", target_type: "shot_dna", target_id: "dna-1", project_id: "", suggested_changes: {}, evidence: {}, reason: "反馈样本达标", status: "proposed", reviewer: "", created_at: "", decided_at: "", applied_at: "" }] } as never);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders readiness gate, character bible list and world builder", async () => {
    render(<IndustrialStudio />);
    await waitFor(() => expect(screen.getByText("Industrial Asset Studio")).toBeInTheDocument());
    expect(screen.getAllByText("READY").length).toBeGreaterThan(0);
    expect(screen.getByText("陈夜")).toBeInTheDocument();
    screen.getByRole("tab", { name: /World Builder/i }).click();
    await waitFor(() => expect(screen.getByText("归墟")).toBeInTheDocument());
  });

  it("renders blocked readiness when assets missing", async () => {
    mocked.projectReadiness.mockResolvedValue({
      project_id: "default",
      ready: false,
      missing: ["character", "world"],
      gates: { character: { pass: false }, world: { pass: false }, shot_dna: { pass: true } },
    } as never);
    render(<IndustrialStudio />);
    await waitFor(() => expect(screen.getByText("BLOCKED")).toBeInTheDocument());
    expect(screen.getByText("Episode 无法进入 ASSET_READY：资产未达标")).toBeInTheDocument();
  });

  it("create bible calls API and refreshes", async () => {
    mocked.createBible.mockResolvedValue(bible({ character_id: "CH002" }) as never);
    render(<IndustrialStudio />);
    await waitFor(() => expect(screen.getByRole("button", { name: /创\s*建/ })).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText("角色 ID，如 CH001"), { target: { value: "CH002" } });
    screen.getByRole("button", { name: /创\s*建/ }).click();
    await waitFor(() => expect(mocked.createBible).toHaveBeenCalledWith(expect.objectContaining({ character_id: "CH002" })));
  });

  it("feedback tab reviews and applies candidates", async () => {
    fbMocked.reviewCandidate.mockResolvedValue({ id: "CD-1", status: "approved" } as never);
    render(<IndustrialStudio />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /反馈回流/ })).toBeInTheDocument());
    screen.getByRole("tab", { name: /反馈回流/ }).click();
    await waitFor(() => expect(screen.getByText("CD-1")).toBeInTheDocument());
    screen.getByRole("button", { name: /通\s*过/ }).click();
    await waitFor(() => expect(fbMocked.reviewCandidate).toHaveBeenCalledWith("CD-1", "approve"));
    expect(screen.getByText("自动记录反馈 ≠ 自动修改生产资产")).toBeInTheDocument();
  });

  it("shot dna tab retrieves patterns", async () => {
    mocked.retrieveShotDna.mockResolvedValue({
      query: {},
      is_hit: true,
      hits: [{ id: "reveal_001", category: "reveal", scene: "exploration", camera: { movement: "push" }, lens: "35mm", lighting: "low_key", emotion: "curiosity→fear", success_rate: 0.91, score: 3, matched: ["category", "scene"] }],
    } as never);
    render(<IndustrialStudio />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /Shot DNA Studio/i })).toBeInTheDocument());
    screen.getByRole("tab", { name: /Shot DNA Studio/i }).click();
    await waitFor(() => expect(screen.getByText("Top-K 检索（特征匹配）")).toBeInTheDocument());
    screen.getByRole("button", { name: /检\s*索/ }).click();
    await waitFor(() => expect(mocked.retrieveShotDna).toHaveBeenCalled());
    expect(screen.getByText("reveal_001")).toBeInTheDocument();
  });
});

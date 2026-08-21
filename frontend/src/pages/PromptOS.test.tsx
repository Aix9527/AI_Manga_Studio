import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterAll, beforeAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PromptOS from "@/pages/PromptOS";
import * as promptOs from "@/api/promptOs";

vi.mock("@/api/client", () => ({
  userMessage: {
    success: () => undefined,
    error: () => undefined,
  },
}));

vi.mock("@/api/promptOs", () => ({
  promptOsStats: vi.fn(),
  listEngines: vi.fn(),
  listDna: vi.fn(),
  addDna: vi.fn(),
  compileShot: vi.fn(),
  compileSequence: vi.fn(),
  listShotDesigns: vi.fn(),
  setShotDesignStatus: vi.fn(),
  deriveShotDesignVersion: vi.fn(),
  recordMetric: vi.fn(),
  evolutionLeaderboard: vi.fn(),
  proposeCandidates: vi.fn(),
  listEvolutionRecords: vi.fn(),
  reviewCandidate: vi.fn(),
  applyCandidate: vi.fn(),
}));

const mocked = vi.mocked(promptOs);

function stats(overrides: Record<string, unknown> = {}) {
  return {
    engines: 10,
    engines_active: 10,
    dna: { entries: 53, by_kind: { character: 3, continuity: 4, negative: 5 }, kinds: ["character", "continuity", "negative"] },
    shot_designs: 1,
    evolution: { metrics: 3, records: 1, by_status: { candidate: 1 }, weights: { completion: 0.5 }, min_samples: 10, min_score: 0.55, auto_learning: false, auto_apply: false },
    layers: ["story", "director_intent"],
    ...overrides,
  };
}

function shot(overrides: Record<string, unknown> = {}) {
  return {
    id: "shot-1",
    version: "v1",
    parent_version: "",
    layers: {
      story: "少年进入地下遗迹",
      director_intent: "体现渺小与震撼",
      photography: { shot: "wide", lens: "24mm", angle: "low_angle" },
      composition: { id: "comp_negative_001", name: "留白", detail: "人物位于画面下方 1/3" },
      action: { motion: "slow_walk", detail: "探索/入场", subject: "少年" },
      camera_movement: "slow_push_in",
      lighting: { id: "lit_cold_top_001", name: "顶部冷光", effect: "未知、疏离" },
      style: { id: "sty_epic_001", name: "广角史诗", visual: "广角史诗感" },
    },
    continuity_contract: { characters: {}, props: {}, space: { "地下遗迹": { time: "inherit" } }, constraints: ["人物服装/表情/站位跨镜一致"] },
    transition_in: "",
    transition_out: "match_cut",
    duration_seconds: 10,
    negative_words: ["表情僵硬"],
    status: "draft",
    approved_by: "",
    approved_at: "",
    notes: "",
    created_at: "",
    updated_at: "",
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
  mocked.promptOsStats.mockResolvedValue(stats() as never);
  mocked.listEngines.mockResolvedValue({
    engines: [
      { key: "compiler", name: "Prompt Compiler", description: "一句剧情 → 八层 ShotDesign", input_schema: {}, output_schema: {}, status: "active", version: "v1", created_at: "" },
      { key: "evolution", name: "Prompt Evolution", description: "指标 → 候选 → 审批", input_schema: {}, output_schema: {}, status: "active", version: "v1", created_at: "" },
    ],
  } as never);
  mocked.listDna.mockResolvedValue({
    entries: [
      { id: "cont_state_001", kind: "continuity", name: "人物状态继承", description: "", values: { rule: "character_state_inherit" }, tags: [], usage_count: 0, success_score: 0, created_at: "", updated_at: "" },
      { id: "neg_face_001", kind: "negative", name: "面部失败模式", description: "", values: { failures: ["表情僵硬"] }, tags: [], usage_count: 0, success_score: 0, created_at: "", updated_at: "" },
    ],
  } as never);
  mocked.listShotDesigns.mockResolvedValue({ shots: [shot()] } as never);
  mocked.evolutionLeaderboard.mockResolvedValue({ leaderboard: [{ shot_design_id: "shot-1", samples: 3, score: 0.5775, completion: 0.7, like: 0.3, comment: 0.2, favorite: 0.25, views: 15000 }] } as never);
  mocked.listEvolutionRecords.mockResolvedValue({
    records: [{ id: "EV-1", shot_design_id: "shot-1", score: 0.5775, samples: 3, status: "candidate", suggested_layers: { director_intent: "强化开场钩子" }, reason: "score", reviewer: "", decided_at: "", applied_version: "", created_at: "" }],
  } as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function clickTab(label: RegExp) {
  fireEvent.click(screen.getByRole("tab", { name: label }));
}

describe("PromptOS", () => {
  it("renders stats, ten engines and DNA tabs", async () => {
    render(<PromptOS />);
    await waitFor(() => expect(screen.getByText("引擎")).toBeInTheDocument());
    expect(screen.getByText("十引擎")).toBeInTheDocument();
    expect(screen.getByText("Prompt Compiler")).toBeInTheDocument();
    expect(screen.getByText("Prompt Evolution")).toBeInTheDocument();
    expect(screen.getByText("auto_learning / auto_apply = false")).toBeInTheDocument();
    clickTab(/Prompt DNA 知识库/);
    await waitFor(() => expect(screen.getByText("人物状态继承")).toBeInTheDocument());
  });

  it("compiles a shot into eight-layer ShotDesign", async () => {
    mocked.compileShot.mockResolvedValue(shot({ status: "draft" }) as never);
    render(<PromptOS />);
    await waitFor(() => expect(screen.getByText("引擎")).toBeInTheDocument());
    clickTab(/Compiler 试算台/);
    const panel = await screen.findByRole("button", { name: /编译 ShotDesign/ });
    fireEvent.click(panel);
    await waitFor(() => expect(mocked.compileShot).toHaveBeenCalledWith(expect.objectContaining({ logline: "少年进入地下遗迹" })));
    await waitFor(() => expect(screen.getByText(/shot-1 · v1/)).toBeInTheDocument());
    expect(screen.getByText("导演意图")).toBeInTheDocument();
    expect(screen.getByText("continuity_contract")).toBeInTheDocument();
  });

  it("records metrics and shows leaderboard", async () => {
    render(<PromptOS />);
    await waitFor(() => expect(screen.getByText("引擎")).toBeInTheDocument());
    clickTab(/Evolution/);
    const input = await screen.findByPlaceholderText("先编译一个 ShotDesign 拿到 ID");
    fireEvent.change(input, { target: { value: "shot-1" } });
    fireEvent.click(screen.getByRole("button", { name: /记录指标/ }));
    await waitFor(() => expect(mocked.recordMetric).toHaveBeenCalledWith(expect.objectContaining({ shot_design_id: "shot-1" })));
    await waitFor(() => expect(screen.getAllByText("0.578").length).toBeGreaterThan(0));
  });

  it("proposes evolution candidates and reviews them", async () => {
    mocked.proposeCandidates.mockResolvedValue({ candidates: [] } as never);
    render(<PromptOS />);
    await waitFor(() => expect(screen.getByText("引擎")).toBeInTheDocument());
    clickTab(/Evolution/);
    await waitFor(() => expect(screen.getByText("EV-1")).toBeInTheDocument());
    const propose = await screen.findByRole("button", { name: /生成进化候选/ });
    fireEvent.click(propose);
    await waitFor(() => expect(mocked.proposeCandidates).toHaveBeenCalledTimes(1));
    await waitFor(() => {
      expect(Array.from(document.querySelectorAll("button")).some((b) => b.textContent?.replace(/\s/g, "") === "批准")).toBe(true);
    });
    const approveBtn = Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.replace(/\s/g, "") === "批准")!;
    fireEvent.click(approveBtn);
    await waitFor(() => expect(mocked.reviewCandidate).toHaveBeenCalledWith("EV-1", "approved", "human"));
  });

  it("approves then locks a draft ShotDesign", async () => {
    render(<PromptOS />);
    await waitFor(() => expect(screen.getByText("引擎")).toBeInTheDocument());
    clickTab(/ShotDesign 版本/);
    await waitFor(() => expect(screen.getByText("shot-1")).toBeInTheDocument());
    await waitFor(() => {
      expect(Array.from(document.querySelectorAll("button")).some((b) => b.textContent?.replace(/\s/g, "") === "批准")).toBe(true);
    });
    const approve = Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.replace(/\s/g, "") === "批准")!;
    fireEvent.click(approve);
    await waitFor(() => expect(mocked.setShotDesignStatus).toHaveBeenCalledWith("shot-1", "approved", "human"));
  });
});
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterAll, beforeAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import ProductionStudioV1 from "@/pages/ProductionStudioV1";
import * as v1 from "@/api/productionStudioV1";

vi.mock("@/api/client", () => ({
  request: vi.fn(),
  userMessage: (err: unknown) => String(err),
}));

vi.mock("@/api/productionStudioV1", () => ({
  v1CreateProject: vi.fn(),
  v1StartProject: vi.fn(),
  v1AdvanceProject: vi.fn(),
  v1ProjectStatus: vi.fn(),
  v1Projects: vi.fn(),
  v1ShotBible: vi.fn(),
  v1CinemaScore: vi.fn(),
  v1Repair: vi.fn(),
  v1SeasonPlan: vi.fn(),
  v1EvolutionLearn: vi.fn(),
  v1EvolutionDirect: vi.fn(),
  v1CeoDecide: vi.fn(),
  v1Certify: vi.fn(),
  v1Workers: vi.fn(),
  v1Templates: vi.fn(),
  v1Shots: vi.fn(),
}));

const mocked = vi.mocked(v1);

beforeAll(() => {
  // jsdom 无 EventSource，生产页面通过 SSE 接收 Agent Runtime 状态
  vi.stubGlobal(
    "EventSource",
    class {
      onmessage: ((ev: unknown) => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(_url: string) {}
      close() {}
    }
  );
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false, media: query, onchange: null,
      addListener: () => undefined, removeListener: () => undefined,
      addEventListener: () => undefined, removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
});

afterAll(() => {
  vi.unstubAllGlobals();
  // @ts-expect-error restore original if defined
  if (window.__originalMatchMedia) Object.defineProperty(window, "matchMedia", { value: window.__originalMatchMedia });
});

beforeEach(() => {
  mocked.v1Projects.mockResolvedValue({ projects: [{ id: "P1", name: "归墟", state: "init", progress: 0, tasks: [] }] } as never);
  mocked.v1Workers.mockResolvedValue({ workers: [{ id: "gpu1", models: ["Wan2.2"] }] } as never);
  mocked.v1CreateProject.mockResolvedValue({ id: "P1", name: "归墟", state: "init", progress: 0, tasks: [] } as never);
  mocked.v1StartProject.mockResolvedValue({ current: "script_analysis", progress: 8, completed: 0, failed: 0 } as never);
  mocked.v1AdvanceProject.mockResolvedValue({ current: "character_design", progress: 18, completed: 1, failed: 0 } as never);
  mocked.v1ShotBible.mockResolvedValue({ id: "gx001", camera: { shot_type: "crane shot" } } as never);
  mocked.v1SeasonPlan.mockResolvedValue({ total_shots: 12 } as never);
  mocked.v1CinemaScore.mockResolvedValue({ score: 85.7, level: "cinema", recommendation: "approve" } as never);
  mocked.v1EvolutionDirect.mockResolvedValue({ pattern: "hero_intro", solution: { camera: "low_angle" }, best_score: 92 } as never);
  mocked.v1CeoDecide.mockResolvedValue({ project: { name: "玄幻觉醒", episodes: 12 } } as never);
  mocked.v1Certify.mockResolvedValue({ certificate: "S", level: "电影级", score: 92 } as never);
  mocked.v1Shots.mockResolvedValue({ shots: [{ id: "MMH3-001", provider: "MiniMaxH3", thumb: "/static/shots/MMH3-001.png", duration_s: "15s" }] } as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ProductionStudioV1", () => {
  it("renders studio console with director and agents", async () => {
    render(<MemoryRouter><ProductionStudioV1 /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("项目总控")).toBeInTheDocument());
    expect(screen.getByText("AI 制作团队")).toBeInTheDocument();
    expect(screen.getAllByText("编剧").length).toBeGreaterThan(0);
    expect(screen.getByText("AI 制片建议")).toBeInTheDocument();
  });

  it("runs demo panel and shows scores", async () => {
    render(<MemoryRouter><ProductionStudioV1 /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("项目总控")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /演示面板/ }));
    await waitFor(() => expect(mocked.v1CinemaScore).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("制作评分：")).toBeInTheDocument());
    expect(screen.getByText("85.7")).toBeInTheDocument();
    expect(screen.getByText("认证等级：")).toBeInTheDocument();
  });
});

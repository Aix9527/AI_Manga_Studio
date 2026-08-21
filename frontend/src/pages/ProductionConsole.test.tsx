import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import ProductionConsole from "@/pages/ProductionConsole";
import * as pc from "@/api/productionConsole";

vi.mock("@/api/productionConsole", () => ({
  listSeasons: vi.fn(),
  seasonStats: vi.fn(),
  listResources: vi.fn(),
  resourceStats: vi.fn(),
  budgetSummary: vi.fn(),
  listSchedulePlans: vi.fn(),
  orchestratorAudit: vi.fn(),
  createSeason: vi.fn(),
  attachSeasonEpisode: vi.fn(),
  setSeasonStatus: vi.fn(),
  planResource: vi.fn(),
  gpuQueueRecommend: vi.fn(),
  setBudgetPolicy: vi.fn(),
  recordBudgetCost: vi.fn(),
  authorizeBudget: vi.fn(),
  approveBudgetOverride: vi.fn(),
  registerDependency: vi.fn(),
  buildSchedulePlan: vi.fn(),
  approveSchedulePlan: vi.fn(),
  dispatchSchedulePlan: vi.fn(),
}));

const mocked = vi.mocked(pc);

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

describe("ProductionConsole", () => {
  beforeEach(() => {
    mocked.listSeasons.mockResolvedValue({ seasons: [{ id: "SN-1", project_id: "default", season_no: 1, name: "第1季", target_episodes: 100, status: "planning", episode_ids: ["EP-001"], created_at: "", updated_at: "" }] } as never);
    mocked.seasonStats.mockResolvedValue({ seasons: 1, episodes_attached: 1, by_status: { planning: 1 } } as never);
    mocked.listResources.mockResolvedValue({ resources: [{ id: "RS-1", project_id: "default", season_id: "", gpu_capacity: 2, gpu_allocated: 0, budget_allocated: 5000, deadline: "", priority: 3, status: "active", created_at: "", updated_at: "" }] } as never);
    mocked.resourceStats.mockResolvedValue({ projects: 1, resources: 1, gpu_capacity: 2, gpu_allocated: 0, budget_allocated: 5000 } as never);
    mocked.budgetSummary.mockResolvedValue({ project_id: "default", spent: 100, monthly_limit: 1000, ratio: 0.1, status: "ok", entries: 1, cost_meter_shots: 1, cost_meter_gpu_time_s: 12 } as never);
    mocked.listSchedulePlans.mockResolvedValue({ plans: [{ id: "PL-1", project_id: "default", status: "draft", scheduled: [], blocked: [{ episode_id: "EP-001", reasons: ["production_not_ready"] }], parallelism: 1, reviewer: "", created_at: "", decided_at: "" }] } as never);
    mocked.orchestratorAudit.mockResolvedValue({ audit: [{ action: "season.create", target: "SN-1", detail: "project=default season_no=1", actor: "system", at: "" }] } as never);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders console stats and season list", async () => {
    render(<ProductionConsole />);
    await waitFor(() => expect(screen.getByText("Production Console")).toBeInTheDocument());
    expect(screen.getAllByText("第1季").length).toBeGreaterThan(0);
  });

  it("creates a season via API", async () => {
    mocked.createSeason.mockResolvedValue({ id: "SN-2", project_id: "default", season_no: 2, name: "", target_episodes: 0, status: "planning", episode_ids: [], created_at: "", updated_at: "" } as never);
    render(<ProductionConsole />);
    await waitFor(() => expect(screen.getByRole("button", { name: /创\s*建/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /创\s*建/ }));
    await waitFor(() => expect(mocked.createSeason).toHaveBeenCalledWith(expect.objectContaining({ project_id: "default", season_no: 1 })));
  });

  it("shows audit chain in audit tab", async () => {
    render(<ProductionConsole />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /审\s*计/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("tab", { name: /审\s*计/ }));
    await waitFor(() => expect(screen.getByText("season.create")).toBeInTheDocument());
  });

  it("approves a schedule plan in scheduler tab", async () => {
    mocked.approveSchedulePlan.mockResolvedValue({ id: "PL-1", project_id: "default", status: "approved", scheduled: [], blocked: [], parallelism: 1, reviewer: "producer", created_at: "", decided_at: "" } as never);
    render(<ProductionConsole />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /并行调度/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("tab", { name: /并行调度/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: /审\s*批/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /审\s*批/ }));
    await waitFor(() => expect(mocked.approveSchedulePlan).toHaveBeenCalledWith("PL-1", "producer"));
  });
});
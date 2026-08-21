import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterAll, beforeAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import WorkflowVisualizer from "@/pages/WorkflowVisualizer";
import * as team from "@/api/team";

vi.mock("@/api/client", () => ({
  request: vi.fn(),
  userMessage: (err: unknown) => String(err),
}));

vi.mock("@/api/team", () => ({
  teamFlow: vi.fn(),
  teamStats: vi.fn(),
}));

const mocked = vi.mocked(team);

function flow() {
  return {
    project_id: "guixu2",
    episodes: [
      {
        episode_id: "EP001",
        stages: {
          planning: { stage: "planning", status: "done", role: "Producer", assignment_id: "A1", assignee_id: "p", attempt: 1, rework_count: 0, started_at: "t", completed_at: "t" },
          script: { stage: "script", status: "in_progress", role: "Writer", assignment_id: "A2", assignee_id: "w", attempt: 1, rework_count: 0, started_at: "t", completed_at: "" },
        },
        assignments: 9, rework_count: 0, waiting_human: 0,
      },
    ],
  };
}

function stats() {
  return {
    teams: 1, assignments: 900, reviews: 500, audit_records: 4500, audit_coverage: 1,
    by_status: { done: 890, in_progress: 5, escalated: 3 },
    new_queue_count: 0, illegal_transitions: 0, infinite_rework: 0,
    governance: { human_approval: true, rollback: true, audit: true, auto_learning: false, auto_apply: false, auto_deploy: false, auto_budget_change: false },
  };
}

beforeAll(() => {
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
  // @ts-expect-error restore original if defined
  if (window.__originalMatchMedia) Object.defineProperty(window, "matchMedia", { value: window.__originalMatchMedia });
});

beforeEach(() => {
  mocked.teamFlow.mockResolvedValue(flow() as never);
  mocked.teamStats.mockResolvedValue(stats() as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("WorkflowVisualizer", () => {
  it("renders pipeline, stats and stage lanes", async () => {
    render(<MemoryRouter><WorkflowVisualizer /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Production Health")).toBeInTheDocument());
    expect(screen.getByText("工作流可视化")).toBeInTheDocument();
    expect(screen.getByText((t) => t.includes("EP001"))).toBeInTheDocument();
    expect(screen.getByText("Pipeline Stage Analytics")).toBeInTheDocument();
    expect(screen.getByText("Episode Production Board（Stage Heatmap）")).toBeInTheDocument();
    expect(mocked.teamFlow).toHaveBeenCalledWith("guixu2");
  });
});

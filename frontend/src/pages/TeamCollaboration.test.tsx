import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterAll, beforeAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TeamCollaboration from "@/pages/TeamCollaboration";
import * as team from "@/api/team";

vi.mock("@/api/client", () => ({
  request: vi.fn(),
  userMessage: {
    success: () => undefined,
    error: () => undefined,
  },
}));

vi.mock("@/api/team", () => ({
  teamStats: vi.fn(),
  teamFlow: vi.fn(),
  listAssignments: vi.fn(),
  teamAudit: vi.fn(),
  startAssignment: vi.fn(),
  reviewAssignment: vi.fn(),
  completeAssignment: vi.fn(),
  escalateAssignment: vi.fn(),
  createTeam: vi.fn(),
  getTeam: vi.fn(),
  assignTask: vi.fn(),
  getAssignment: vi.fn(),
  reworkAssignment: vi.fn(),
  blockAssignment: vi.fn(),
  unblockAssignment: vi.fn(),
  failAssignment: vi.fn(),
  teamArtifacts: vi.fn(),
}));

const mocked = vi.mocked(team);

function stats() {
  return {
    teams: 1,
    assignments: 8,
    reviews: 5,
    audit_records: 12,
    audit_coverage: 1,
    by_status: { assigned: 2, in_progress: 3, approved: 1, done: 2 },
    new_queue_count: 0,
    illegal_transitions: 0,
    infinite_rework: 0,
    governance: { human_approval: true, rollback: true, audit: true, auto_learning: false, auto_apply: false, auto_deploy: false, auto_budget_change: false },
  };
}

function flow() {
  return {
    project_id: "P1",
    episodes: [
      {
        episode_id: "EP1",
        stages: {
          planning: { stage: "planning", status: "done", role: "Producer", assignment_id: "A1", assignee_id: "p1", attempt: 1, rework_count: 0, started_at: "t", completed_at: "t" },
          script: { stage: "script", status: "in_progress", role: "Writer", assignment_id: "A2", assignee_id: "w1", attempt: 1, rework_count: 1, started_at: "t", completed_at: "" },
        },
        assignments: 8,
        rework_count: 1,
        waiting_human: 0,
      },
    ],
  };
}

function assignment(overrides: Record<string, unknown> = {}) {
  return {
    id: "A2",
    project_id: "P1",
    season_id: "",
    episode_id: "EP1",
    stage: "script",
    role: "Writer",
    assignee_type: "agent",
    assignee_id: "w1",
    status: "in_progress",
    input_artifacts: [],
    output_artifacts: [],
    dependencies: ["A1"],
    task_id: "TASK-1",
    checkpoint_id: "",
    attempt: 1,
    max_attempts: 2,
    rework_count: 1,
    blocked_reason: "",
    deadline: "",
    created_at: "t",
    started_at: "t",
    completed_at: "",
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
  mocked.teamStats.mockResolvedValue(stats() as never);
  mocked.teamFlow.mockResolvedValue(flow() as never);
  mocked.listAssignments.mockResolvedValue({
    assignments: [
      assignment(),
      assignment({ id: "A1", stage: "planning", role: "Producer", status: "assigned" }),
      assignment({ id: "A9", stage: "final", role: "Producer", status: "in_progress" }),
    ],
  } as never);
  mocked.teamAudit.mockResolvedValue({
    audit: [
      { id: "TA-1", project_id: "P1", episode_id: "EP1", assignment_id: "A2", event: "rework_routed", actor: "orchestrator", before: {}, after: {}, reason: "定向返工", evidence: {}, timestamp: "t" },
      { id: "TA-2", project_id: "P1", episode_id: "EP1", assignment_id: "A1", event: "assigned", actor: "admin", before: {}, after: {}, reason: "分派任务", evidence: {}, timestamp: "t" },
    ],
  } as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("TeamCollaboration", () => {
  it("renders stats, stage lane and audit timeline", async () => {
    render(<TeamCollaboration projectId="P1" />);
    await waitFor(() => expect(screen.getByText("任务数")).toBeInTheDocument());
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("EP1")).toBeInTheDocument();
    expect(screen.getByText("策划")).toBeInTheDocument();
    expect(screen.getByText("编剧")).toBeInTheDocument();
    expect(screen.getByText("定向返工")).toBeInTheDocument();
    expect(screen.getByText("审计覆盖率")).toBeInTheDocument();
    expect(mocked.teamStats).toHaveBeenCalledTimes(1);
    expect(mocked.teamFlow).toHaveBeenCalledWith("P1");
  });

  it("selects an assignment and approves it", async () => {
    mocked.reviewAssignment.mockResolvedValue(assignment({ status: "approved" }) as never);
    render(<TeamCollaboration projectId="P1" />);
    await waitFor(() => expect(screen.getByText("任务数")).toBeInTheDocument());
    const select = screen.getByRole("combobox");
    fireEvent.mouseDown(select);
    await waitFor(() => expect(document.querySelectorAll(".ant-select-item-option").length).toBeGreaterThan(0));
    const options = Array.from(document.querySelectorAll(".ant-select-item-option"));
    const target = options.find((o) => o.textContent?.includes("编剧")) ?? options[0];
    fireEvent.click(target);
    await waitFor(() => expect(screen.getAllByText("进行中").length).toBeGreaterThan(0));
    const approveBtn = Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.replace(/\s/g, "") === "通过评审")!;
    fireEvent.click(approveBtn);
    await waitFor(() => expect(mocked.reviewAssignment).toHaveBeenCalledWith(
      "A2",
      expect.objectContaining({ verdict: "approve", evidence: { frontend_manual: true } }),
    ));
  });

  it("requires approval_id for final-stage approval", async () => {
    mocked.reviewAssignment.mockResolvedValue(assignment({ stage: "final", status: "approved" }) as never);
    render(<TeamCollaboration projectId="P1" />);
    await waitFor(() => expect(screen.getByText("任务数")).toBeInTheDocument());
    const select = screen.getByRole("combobox");
    fireEvent.mouseDown(select);
    await waitFor(() => expect(document.querySelectorAll(".ant-select-item-option").length).toBeGreaterThan(0));
    const options = Array.from(document.querySelectorAll(".ant-select-item-option"));
    const finalOption = options.find((o) => o.textContent?.includes("成片")) ?? options[options.length - 1];
    fireEvent.click(finalOption);
    await waitFor(() => expect(screen.getByPlaceholderText("approval_id（人工审批门）")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText("approval_id（人工审批门）"), { target: { value: "AP-1" } });
    const approveBtn = Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.replace(/\s/g, "") === "通过评审")!;
    fireEvent.click(approveBtn);
    await waitFor(() => expect(mocked.reviewAssignment).toHaveBeenCalledWith(
      "A9",
      expect.objectContaining({ approval_id: "AP-1" }),
    ));
  });
});

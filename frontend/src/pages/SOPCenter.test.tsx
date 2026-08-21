import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterAll, beforeAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SOPCenter from "@/pages/SOPCenter";
import * as team from "@/api/team";

vi.mock("@/api/client", () => ({
  request: vi.fn(),
  userMessage: (err: unknown) => String(err),
}));

vi.mock("@/api/team", () => ({
  teamStats: vi.fn(),
}));

const mocked = vi.mocked(team);

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
  mocked.teamStats.mockResolvedValue({
    teams: 1, assignments: 900, reviews: 500, audit_records: 4500, audit_coverage: 1,
    by_status: { done: 890 }, new_queue_count: 0, illegal_transitions: 0, infinite_rework: 0,
    governance: { human_approval: true, rollback: true, audit: true, auto_learning: false, auto_apply: false, auto_deploy: false, auto_budget_change: false },
  } as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SOPCenter", () => {
  it("renders six SOP stages and stats", async () => {
    render(<SOPCenter />);
    await waitFor(() => expect(screen.getByText("生产任务")).toBeInTheDocument());
    expect(screen.getByText("Story Intelligence")).toBeInTheDocument();
    expect(screen.getByText("MiniMaxH3 Provider")).toBeInTheDocument();
    expect(screen.getByText("Human Approval")).toBeInTheDocument();
    expect(mocked.teamStats).toHaveBeenCalledTimes(1);
  });
});

import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { chainPlan, chainStatus, directorPlan, identityVerify } from "@/api/studio";
import { getPipelineStats } from "@/api/pipeline";
import StudioDashboard from "@/pages/StudioDashboard";

vi.mock("@/api/studio", () => ({
  directorPlan: vi.fn(),
  chainPlan: vi.fn(),
  chainStatus: vi.fn(),
  identityVerify: vi.fn(),
}));

vi.mock("@/api/pipeline", () => ({
  getPipelineStats: vi.fn(),
}));

const mockedDirectorPlan = vi.mocked(directorPlan);
const mockedChainPlan = vi.mocked(chainPlan);
const mockedChainStatus = vi.mocked(chainStatus);
const mockedGetStats = vi.mocked(getPipelineStats);

function stats() {
  return {
    version: "0.5.0",
    phases: { phase_1_character_memory: true, phase_3b_director_v2: true },
    modules: { video: ["chain_manager", "runtime", "identity_gate"], director: ["director_bridge"] },
  };
}

function planResult() {
  return {
    novel_id: "gx",
    chapters: 1,
    scenes: 1,
    shots_total: 1,
    sections: [],
    directives: [
      {
        shot_id: "gx_001",
        shot_intent: "dialogue_beat",
        camera: { angle: "eye-level", movement: "static", distance: "medium" },
        lighting: { style: "natural" },
        emotion_curve: [],
        continuity: { previous_shot: "", constraints: [] },
        directive_id: "DIR-gx_001-v1",
      },
    ],
  };
}

function chainResult() {
  return {
    project: "gx",
    shots_total: 1,
    links: [{ shot_id: "gx_001", mode: "keyframe", note: "first_shot" }],
    report: { total: 1, by_mode: { keyframe: 1 } },
  };
}

function chainStatusResult() {
  return {
    project: "gx",
    completed: ["gx_001"],
    current: "",
    resume_from: "",
    last_frame: "lf.png",
    total_shots: 1,
    pending: [],
    failed: [],
    manifest_path: "storage/chains/gx/video_checkpoint_manifest.json",
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
  mockedGetStats.mockResolvedValue(stats() as never);
  mockedDirectorPlan.mockResolvedValue(planResult() as never);
  mockedChainPlan.mockResolvedValue(chainResult() as never);
  mockedChainStatus.mockResolvedValue(chainStatusResult() as never);
});

afterEach(() => cleanup());

describe("StudioDashboard", () => {
  it("renders stats and phase 10 cards", async () => {
    render(<StudioDashboard />);
    expect(screen.getByText("Studio 导演工作台")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("Director v2 分镜指令")).toBeTruthy());
    expect(screen.getByText("Chain Runtime（长视频续接）")).toBeTruthy();
    expect(screen.getByText("Identity Gate（生成后角色校验）")).toBeTruthy();
    expect(screen.getByText("管线模块")).toBeTruthy();
  });

  it("loads pipeline stats", async () => {
    render(<StudioDashboard />);
    await waitFor(() => expect(screen.getByText("版本 v0.5.0")).toBeTruthy());
    expect(mockedGetStats).toHaveBeenCalled();
  });
});

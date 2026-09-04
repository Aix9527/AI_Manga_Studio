import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProjectCockpit from "@/studio/ProjectCockpit";
import { api } from "@/api/jobs";

const { workspaceState, actions, parseStory, extractFromText, getPublishedProductionTemplate } = vi.hoisted(() => ({
  workspaceState: {
    projectId: "project-a",
    snapshot: {
      project_id: "project-a",
      title: "归墟第一部",
      source_path: "D:/AI_Manga_Projects/归墟",
      version: "v0.8",
      progress: 0.42,
      pending_reviews: 0,
      active_jobs: 0,
      estimated_minutes: 12,
      stages: [],
      system_health: { database: "ok" },
    },
  },
  actions: {
    createJob: vi.fn(),
    subscribeSSE: vi.fn(),
    pauseJob: vi.fn(),
    resumeJob: vi.fn(),
    retryJob: vi.fn(),
  },
  parseStory: vi.fn(),
  extractFromText: vi.fn(),
  getPublishedProductionTemplate: vi.fn(),
}));

vi.mock("@/state/workspaceStore", () => ({
  useWorkspaceStore: Object.assign(
    (selector: (state: typeof workspaceState) => unknown) => selector(workspaceState),
    { getState: () => workspaceState },
  ),
}));

vi.mock("@/state/jobStore", () => ({
  useJobStore: () => ({ jobs: new Map(), recentIds: [] }),
  jobStoreActions: () => actions,
}));

vi.mock("@/state/storyStore", () => ({
  useStoryStore: Object.assign(
    (selector: (state: { parseStory: typeof parseStory }) => unknown) => selector({ parseStory }),
    { getState: () => ({ parseStory, parseError: null }) },
  ),
}));

vi.mock("@/state/characterStore", () => ({
  useCharacterStore: {
    getState: () => ({ extractFromText, error: null }),
  },
}));

vi.mock("@/api/jobs", () => ({
  api: {
    uploadInput: vi.fn(),
    health: vi.fn(),
  },
}));

vi.mock("@/api/productionTemplates", () => ({ getPublishedProductionTemplate }));

describe("ProjectCockpit", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    workspaceState.projectId = "project-a";
    workspaceState.snapshot.project_id = "project-a";
    workspaceState.snapshot.title = "归墟第一部";
    vi.mocked(api.uploadInput).mockResolvedValue({ path: "inputs/story.txt" });
    actions.createJob.mockResolvedValue({ id: "job-12345678" });
    parseStory.mockResolvedValue(undefined);
    extractFromText.mockResolvedValue(undefined);
    getPublishedProductionTemplate.mockResolvedValue({
      project_id: "project-a",
      published: false,
      template: null,
    });
  });

  afterEach(cleanup);

  it("renders the six-step local-first one-click production cockpit", () => {
    render(<ProjectCockpit />);

    expect(screen.getByRole("heading", { name: "一站式 · 一键成片" })).toBeInTheDocument();
    for (const label of [
      "导入小说/剧本",
      "AI 拆解角色与场景",
      "批量分镜",
      "关键帧 / 视频生成",
      "配音与字幕",
      "质检与导出",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: /开始一键生成/ })).toBeInTheDocument();
    expect(screen.getByLabelText("任务队列")).toBeInTheDocument();
  });

  it("imports the selected script and starts the existing automatic job lifecycle", async () => {
    const { container } = render(<ProjectCockpit />);
    const input = container.querySelector('input[type="file"]');
    expect(input).not.toBeNull();
    const file = new File(["第一章：归墟苏醒"], "story.txt", { type: "text/plain" });
    Object.defineProperty(file, "text", { value: vi.fn().mockResolvedValue("第一章：归墟苏醒") });

    fireEvent.change(input as HTMLInputElement, { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: /开始一键生成/ }));

    await waitFor(() => expect(actions.createJob).toHaveBeenCalledTimes(1));
    expect(api.uploadInput).toHaveBeenCalledWith(file, "project-a");
    expect(parseStory).toHaveBeenCalledWith("第一章：归墟苏醒", "project-a");
    expect(extractFromText).toHaveBeenCalledWith({ text: "第一章：归墟苏醒", novel_id: "project-a" });
    expect(actions.createJob).toHaveBeenCalledWith(expect.objectContaining({
      project_id: "project-a",
      input_path: "inputs/story.txt",
      mode: "automatic",
      width: 1080,
      height: 1920,
      fps: 24,
    }));
    expect(actions.subscribeSSE).toHaveBeenCalledWith("job-12345678");
    expect(await screen.findByText(/一键生产已启动/)).toBeInTheDocument();
  });

  it("stops a late upload from parsing or starting production after the active project changes", async () => {
    let resolveUpload: ((value: { path: string }) => void) | undefined;
    vi.mocked(api.uploadInput).mockImplementation(() => new Promise((resolve) => {
      resolveUpload = resolve;
    }));

    const { container } = render(<ProjectCockpit />);
    const input = container.querySelector('input[type="file"]');
    expect(input).not.toBeNull();
    const file = new File(["旧项目正文"], "old-project.txt", { type: "text/plain" });
    Object.defineProperty(file, "text", { value: vi.fn().mockResolvedValue("旧项目正文") });

    fireEvent.change(input as HTMLInputElement, { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: /开始一键生成/ }));
    await waitFor(() => expect(api.uploadInput).toHaveBeenCalledWith(file, "project-a"));

    workspaceState.projectId = "project-b";
    workspaceState.snapshot.project_id = "project-b";
    workspaceState.snapshot.title = "新项目";
    resolveUpload?.({ path: "inputs/old-project.txt" });
    await Promise.resolve();
    await Promise.resolve();

    expect(parseStory).not.toHaveBeenCalled();
    expect(extractFromText).not.toHaveBeenCalled();
    expect(actions.createJob).not.toHaveBeenCalled();
    expect(actions.subscribeSSE).not.toHaveBeenCalled();
  });
});

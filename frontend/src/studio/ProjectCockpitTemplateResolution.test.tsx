import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProjectCockpit from "@/studio/ProjectCockpit";
import { api } from "@/api/jobs";

const {
  workspaceState,
  actions,
  parseStory,
  extractFromText,
  getPublishedProductionTemplate,
} = vi.hoisted(() => ({
  workspaceState: {
    projectId: "project-a",
    snapshot: {
      project_id: "project-a",
      title: "归墟第一部",
      source_path: "D:/AI_Manga_Projects/归墟",
      version: "v0.9",
      progress: 0,
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

const published = (version = 3) => ({
  project_id: "project-a",
  published: true,
  template: {
    id: `ptv-${version}`,
    project_id: "project-a",
    version,
    name: "电影感 H3 模板",
    schema_version: 1,
    content_json: "{}",
    content_sha256: "source-hash",
    compiled_json: JSON.stringify({
      schema_version: 1,
      production: {
        shot_duration: 7,
        width: 1440,
        height: 1920,
        fps: 30,
        options: { style: "cinematic", local_first: false },
      },
      stage_policy: [],
    }),
    compiled_sha256: "compiled-hash",
    status: "active",
    created_at: "2026-09-05T00:00:00Z",
    published_at: "2026-09-05T00:01:00Z",
  },
});

function selectFile(container: HTMLElement) {
  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File(["第一章：模板生产"], "story.txt", { type: "text/plain" });
  Object.defineProperty(file, "text", { value: vi.fn().mockResolvedValue("第一章：模板生产") });
  fireEvent.change(input, { target: { files: [file] } });
  return file;
}

describe("ProjectCockpit v0.9.1 published template resolution", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    workspaceState.projectId = "project-a";
    workspaceState.snapshot.project_id = "project-a";
    vi.mocked(api.uploadInput).mockResolvedValue({ path: "inputs/story.txt" });
    actions.createJob.mockResolvedValue({ id: "job-template" });
    parseStory.mockResolvedValue(undefined);
    extractFromText.mockResolvedValue(undefined);
    getPublishedProductionTemplate.mockResolvedValue({
      project_id: "project-a",
      published: false,
      template: null,
    });
  });

  afterEach(cleanup);

  it("shows system defaults and preserves the legacy one-click request when no template is published", async () => {
    const { container } = render(<ProjectCockpit />);

    expect(await screen.findByText(/生产模板：系统默认/)).toBeInTheDocument();
    selectFile(container);
    fireEvent.click(screen.getByRole("button", { name: /开始一键生成/ }));

    await waitFor(() => expect(actions.createJob).toHaveBeenCalledTimes(1));
    expect(actions.createJob).toHaveBeenCalledWith(expect.objectContaining({
      shot_duration: 5,
      width: 1080,
      height: 1920,
      fps: 24,
      options: { style: "anime", local_first: true },
    }));
  });

  it("uses the published compiled production settings instead of hardcoded defaults", async () => {
    getPublishedProductionTemplate.mockResolvedValue(published(3));
    const { container } = render(<ProjectCockpit />);

    expect(await screen.findByText(/生产模板：v3/)).toBeInTheDocument();
    selectFile(container);
    fireEvent.click(screen.getByRole("button", { name: /开始一键生成/ }));

    await waitFor(() => expect(actions.createJob).toHaveBeenCalledTimes(1));
    expect(actions.createJob).toHaveBeenCalledWith(expect.objectContaining({
      shot_duration: 7,
      width: 1440,
      height: 1920,
      fps: 30,
      options: { style: "cinematic", local_first: false },
    }));
  });

  it("fails closed and never creates a job when the published template cannot be resolved", async () => {
    getPublishedProductionTemplate.mockRejectedValue(new Error("TEMPLATE_PUBLISH_CONFLICT"));
    const { container } = render(<ProjectCockpit />);

    selectFile(container);
    fireEvent.click(screen.getByRole("button", { name: /开始一键生成/ }));

    await waitFor(() => expect(getPublishedProductionTemplate).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/TEMPLATE_PUBLISH_CONFLICT/));
    expect(actions.createJob).not.toHaveBeenCalled();
    expect(actions.subscribeSSE).not.toHaveBeenCalled();
  });
});

import React from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/jobs";
import { ApiError } from "@/api/client";
import ProjectOverview from "@/pages/ProjectOverview";
import { useCharacterStore } from "@/state/characterStore";
import { useStoryStore } from "@/state/storyStore";
import { useWorkspaceStore } from "@/state/workspaceStore";
import type { JobDetail } from "@/types/jobs";
import type { WorkspaceSnapshot } from "@/workbench/types";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

const jobState = vi.hoisted(() => ({ jobs: [] as JobDetail[] }));

vi.mock("@/state/jobStore", () => ({
  useJobStore: () => ({
    jobs: new Map(jobState.jobs.map((job) => [job.id, job])),
    recentIds: jobState.jobs.map((job) => job.id),
  }),
}));

function snapshot(overrides: Partial<WorkspaceSnapshot> = {}): WorkspaceSnapshot {
  return {
    project_id: "project-a",
    title: "归墟",
    source_path: "F:/projects/归墟.txt",
    version: "v08",
    progress: 0.68,
    pending_reviews: 2,
    active_jobs: 1,
    estimated_minutes: null,
    stages: [
      {
        stage_key: "import",
        status: "completed",
        progress: 1,
        waiting_review: 0,
        automation: {
          stage_key: "import",
          auto_produce: true,
          quality_threshold: 0.8,
          max_quality_retries: 2,
          auto_advance: true,
          provider_settings: {},
        },
      },
      {
        stage_key: "story",
        status: "running",
        progress: 0.4,
        waiting_review: 0,
        automation: {
          stage_key: "story",
          auto_produce: true,
          quality_threshold: 0.8,
          max_quality_retries: 2,
          auto_advance: true,
          provider_settings: {},
        },
      },
    ],
    system_health: { database: "ok" },
    ...overrides,
  };
}

function job(): JobDetail {
  return {
    id: "job-1",
    project_id: "project-a",
    status: "running",
    mode: "automatic",
    desired_state: "running",
    current_stage: "story",
    current_shot: "shot-1",
    progress: 0.5,
    message: "正在解析第二章",
    final_video: "",
    created_at: "2026-08-02T00:00:00Z",
    updated_at: "2026-08-02T00:01:00Z",
    finished_at: null,
    steps: [],
    artifacts: [
      {
        id: 1,
        project_id: "gui-xu",
        kind: "story_graph",
        path: "outputs/story/graph.json",
        sha256: "abc",
        stage_key: "story",
        scene_id: "",
        shot_id: "",
        version: 1,
        parent_artifact_id: null,
        active: true,
        quality_status: "unreviewed",
        metadata: {},
        media_url: "",
      },
    ],
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ProjectOverview />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
  jobState.jobs = [];
  useWorkspaceStore.setState({
    projectId: "project-a",
    snapshot: snapshot(),
    activeModule: "总览",
    selectedObject: null,
    loading: false,
    error: null,
  });
  useStoryStore.setState({
    graph: null,
    scenes: [],
    shots: [],
    timeline: [],
    loading: false,
    error: null,
    parsing: false,
    parseError: null,
    selectedChapterIndex: null,
    selectedSceneId: null,
    selectedShotId: null,
  });
});

afterEach(cleanup);

describe("项目总览", () => {
  it("展示六项真实快照指标且不虚构本机能力", () => {
    renderPage();
    const page = screen.getByRole("region", { name: "项目总览" });
    expect(within(page).getByRole("heading", { name: "项目总览", level: 1 })).toBeInTheDocument();
    for (const value of ["68%", "故事结构", "2", "1", "暂无估算", "数据库正常"]) {
      expect(within(page).getByText(value)).toBeInTheDocument();
    }
    expect(page).not.toHaveTextContent(/GPU|显存|ComfyUI|磁盘|模型/i);
  });

  it("预检成功显示真实版本，可重复检查，服务与网络失败均中文化", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "health")
      .mockResolvedValueOnce({ status: "ok", version: "5.2.1" })
      .mockRejectedValueOnce(new ApiError(500, "internal stack"))
      .mockRejectedValueOnce(new TypeError("fetch failed"));
    renderPage();
    const button = screen.getByRole("button", { name: "运行环境预检" });

    await user.click(button);
    expect(await screen.findByText("本地服务正常 · 版本 5.2.1")).toBeInTheDocument();
    await user.click(button);
    expect(await screen.findByText("服务暂时不可用，请稍后重试")).toBeInTheDocument();
    await user.click(button);
    expect(await screen.findByText("无法连接本地服务，请检查后端是否运行")).toBeInTheDocument();
  });

  it("只在真实待审存在时提供质检入口，并始终提供继续制作", () => {
    const first = renderPage();
    expect(screen.getByRole("link", { name: "继续制作" })).toHaveAttribute("href", "/director");
    expect(screen.getByRole("link", { name: "处理待审核" })).toHaveAttribute("href", "/quality");
    first.unmount();
    useWorkspaceStore.setState({ snapshot: snapshot({ pending_reviews: 0 }) });
    renderPage();
    expect(screen.queryByRole("link", { name: "处理待审核" })).not.toBeInTheDocument();
  });

  it("展示当前项目的真实任务与产物，空时不构造内容", () => {
    jobState.jobs = [job(), { ...job(), id: "foreign", project_id: "project-b" }];
    const first = renderPage();
    expect(screen.getByText("正在解析第二章")).toBeInTheDocument();
    expect(screen.getByText("outputs/story/graph.json")).toBeInTheDocument();
    expect(screen.queryByText("foreign")).not.toBeInTheDocument();
    first.unmount();
    jobState.jobs = [];
    renderPage();
    expect(screen.getByText("暂无运行任务")).toBeInTheDocument();
    expect(screen.getByText("暂无产物")).toBeInTheDocument();
  });

  it("拒绝空文件选择，并用真实上传与解析完成小说导入", async () => {
    const user = userEvent.setup();
    const upload = vi.spyOn(api, "uploadInput").mockResolvedValue({ path: "inputs/story.md" });
    const parse = vi.spyOn(useStoryStore.getState(), "parseStory").mockResolvedValue();
    const extract = vi.spyOn(useCharacterStore.getState(), "extractFromText").mockResolvedValue();
    useCharacterStore.setState({ characters: [{ id: "c1", name: "苏晚" } as never] });
    renderPage();

    await user.click(screen.getByRole("button", { name: "上传并解析小说" }));
    expect(screen.getByText("请选择小说文件")).toBeInTheDocument();

    const file = new File(["# 第一章\n海潮漫过城墙。"], "归墟.md", { type: "text/markdown" });
    await user.upload(screen.getByLabelText("选择小说文件"), file);
    await user.click(screen.getByRole("button", { name: "上传并解析小说" }));
    expect(await screen.findByText(/小说已上传并完成解析/)).toBeInTheDocument();
    expect(upload).toHaveBeenCalledWith(file, "project-a");
    expect(parse).toHaveBeenCalledWith("# 第一章\n海潮漫过城墙。", "project-a");
  });

  it("导入期间禁用操作并将失败中文化", async () => {
    let reject!: (error: unknown) => void;
    vi.spyOn(api, "uploadInput").mockReturnValue(new Promise((_resolve, rejectPromise) => { reject = rejectPromise; }));
    renderPage();
    const file = new File(["正文"], "story.txt", { type: "text/plain" });
    fireEvent.change(screen.getByLabelText("选择小说文件"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "上传并解析小说" }));
    expect(screen.getByRole("button", { name: "正在上传并解析" })).toBeDisabled();
    act(() => reject(new TypeError("offline")));
    expect(await screen.findByText("无法连接本地服务，请检查后端是否运行")).toBeInTheDocument();
  });

  it("项目切换会使迟到的预检响应失效", async () => {
    const user = userEvent.setup();
    const pending = deferred<{ status: string; version: string }>();
    vi.spyOn(api, "health").mockReturnValue(pending.promise);
    renderPage();
    await user.click(screen.getByRole("button", { name: "运行环境预检" }));

    act(() => useWorkspaceStore.setState({
      projectId: "project-b",
      snapshot: snapshot({ project_id: "project-b" }),
    }));
    await act(async () => pending.resolve({ status: "ok", version: "old-version" }));

    expect(screen.queryByText(/old-version/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "运行环境预检" })).toBeEnabled();
  });

  it("项目切换会停止迟到上传进入旧项目解析", async () => {
    const pending = deferred<{ path: string }>();
    vi.spyOn(api, "uploadInput").mockReturnValue(pending.promise);
    const parse = vi.spyOn(useStoryStore.getState(), "parseStory").mockResolvedValue();
    renderPage();
    const file = new File(["正文"], "story.txt", { type: "text/plain" });
    fireEvent.change(screen.getByLabelText("选择小说文件"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "上传并解析小说" }));

    act(() => useWorkspaceStore.setState({
      projectId: "project-b",
      snapshot: snapshot({ project_id: "project-b" }),
    }));
    await act(async () => pending.resolve({ path: "inputs/story.txt" }));

    expect(parse).not.toHaveBeenCalled();
    expect(screen.queryByText(/小说已上传并完成解析/)).not.toBeInTheDocument();
  });
});

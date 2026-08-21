import React, { StrictMode } from "react";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "@/App";
import { workspaceApi } from "@/api/workspace";
import { useProjectStore } from "@/state/projectStore";
import { useWorkspaceStore } from "@/state/workspaceStore";
import type { JobDetail, JobStatus } from "@/types/jobs";
import { STAGE_KEYS, type StageKey, type WorkspaceSnapshot } from "@/workbench/types";

const jobMocks = vi.hoisted(() => ({
  jobs: new Map<string, JobDetail>(),
  recentIds: [] as string[],
  loadProjectJobs: vi.fn<() => Promise<JobDetail[]>>(),
  subscribeActiveJobs: vi.fn<() => () => void>(),
  retryProjectJobs: vi.fn<() => Promise<JobDetail[]>>(),
  resetProjectJobs: vi.fn<(projectId?: string) => void>(),
  loadingProjectId: "",
  loadedProjectId: "project-a",
  loadRevision: 1,
  loadError: null as unknown | null,
}));

vi.mock("@/state/jobStore", () => ({
  useJobStore: () => ({
    jobs: jobMocks.jobs,
    recentIds: jobMocks.recentIds,
    polling: false,
    loadingProjectId: jobMocks.loadingProjectId,
    loadedProjectId: jobMocks.loadedProjectId,
    loadRevision: jobMocks.loadRevision,
    loadError: jobMocks.loadError,
    retryProjectJobs: jobMocks.retryProjectJobs,
  }),
  jobStoreActions: () => ({
    loadProjectJobs: jobMocks.loadProjectJobs,
    subscribeActiveJobs: jobMocks.subscribeActiveJobs,
    resetProjectJobs: jobMocks.resetProjectJobs,
  }),
}));

const stageLabels = [
  "导入",
  "故事解析",
  "角色定妆",
  "分镜规划",
  "关键帧",
  "视频",
  "音频",
  "合成",
  "导出",
];

const navigation = [
  ["项目总览", "/overview"],
  ["故事与角色", "/story"],
  ["分镜导演台", "/director"],
  ["素材库", "/assets"],
  ["生成任务", "/tasks"],
  ["视觉质检", "/quality"],
  ["成片与导出", "/export"],
];

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function workspace(overrides: Partial<WorkspaceSnapshot> = {}): WorkspaceSnapshot {
  return {
    project_id: "project-a",
    title: "《归墟》第一部",
    source_path: "/projects/project-a",
    version: "v08",
    progress: 0.68,
    pending_reviews: 3,
    active_jobs: 2,
    estimated_minutes: null,
    stages: STAGE_KEYS.map((stage_key, index) => ({
      stage_key,
      status: index < 3 ? "completed" : index === 3 ? "running" : "pending",
      progress: index < 3 ? 1 : index === 3 ? 0.72 : 0,
      waiting_review: stage_key === "keyframe" ? 1 : 0,
      automation: {
        stage_key,
        auto_produce: true,
        quality_threshold: 0.82,
        max_quality_retries: 2,
        auto_advance: true,
        provider_settings: {},
      },
    })),
    system_health: { database: "ok", jobs: 2 },
    ...overrides,
  };
}

function job(id: string, status: JobStatus): JobDetail {
  return {
    id,
    project_id: "project-a",
    status,
    mode: "automatic",
    desired_state: "running",
    current_stage: "keyframe",
    current_shot: "shot-1",
    progress: 0.5,
    message: "生成中",
    final_video: "",
    created_at: "2026-08-02T00:00:00Z",
    updated_at: "2026-08-02T00:01:00Z",
    finished_at: null,
    steps: [],
    artifacts: [],
  };
}

function resetStores(snapshot: WorkspaceSnapshot | null = workspace()) {
  useWorkspaceStore.setState({
    projectId: snapshot?.project_id ?? "",
    snapshot,
    activeModule: "总览",
    selectedObject: null,
    loading: false,
    error: null,
  });
  useProjectStore.setState({ project: null, activeTab: "novel" });
}

function renderApp(path = "/director", strict = false) {
  const content = (
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <App />
    </MemoryRouter>
  );
  return render(strict ? <StrictMode>{content}</StrictMode> : content);
}

beforeEach(() => {
  vi.restoreAllMocks();
  jobMocks.jobs = new Map();
  jobMocks.recentIds = [];
  jobMocks.loadProjectJobs.mockReset().mockResolvedValue([]);
  jobMocks.subscribeActiveJobs.mockReset().mockReturnValue(vi.fn());
  jobMocks.retryProjectJobs.mockReset().mockResolvedValue([]);
  jobMocks.loadingProjectId = "";
  jobMocks.loadedProjectId = "project-a";
  jobMocks.loadRevision = 1;
  jobMocks.loadError = null;
  jobMocks.resetProjectJobs.mockReset();
  vi.spyOn(workspaceApi, "getSnapshot").mockResolvedValue(workspace());
  resetStores();
});

afterEach(cleanup);

describe("单项目中文可视化工作台", () => {
  it("在导演台显示唯一顶栏、七模块导航、检查器与完整九阶段顺序", () => {
    renderApp();

    const banners = screen.getAllByRole("banner");
    expect(banners).toHaveLength(1);
    expect(within(banners[0]).getByText("AI 漫画工作台")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "项目工作区" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /分镜导演台/, current: "page" })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "属性检查器" })).toBeInTheDocument();
    expect(screen.getAllByRole("main")).toHaveLength(1);

    const rail = screen.getByLabelText("制作阶段");
    expect(within(rail).getAllByRole("listitem")).toHaveLength(9);
    expect(within(rail).getAllByRole("link").map((link) => link.textContent)).toEqual(
      stageLabels,
    );
  });

  it("不再显示旧英文品牌、旧页签或英文加载文案", () => {
    renderApp();

    expect(screen.queryByText(/AI Manager Studio V5/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Production Studio/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Task Center/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Loading\.\.\./i)).not.toBeInTheDocument();
  });

  it("按固定顺序提供分组真实链接，并将旧分镜路径替换到导演台", async () => {
    const firstRender = renderApp();
    const nav = screen.getByRole("navigation", { name: "项目工作区" });
    // GPT P4: 5 组导航收敛；设置组默认收起，故只断言展开组链接
    expect(within(nav).getAllByRole("link").map((link) => [link.getAttribute("aria-label"), link.getAttribute("href")])).toEqual([
      ["项目总览", "/overview"],
      ["生产指挥中心", "/command-center"],
      ["生产智能", "/production-intelligence"],
      ["故事与角色", "/story"],
      ["分镜导演台", "/director"],
      ["AI 创作台", "/creator"],
      ["导演工作台", "/studio"],
      ["生产工作台", "/production-studio-v1"],
      ["生产控制台", "/production-console"],
      ["工业资产", "/industrial"],
      ["素材库", "/assets"],
      ["生成任务，2 个运行中", "/tasks"],
      ["视觉质检，3 个待审核", "/quality"],
      ["成片与导出", "/export"],
    ]);
    expect(within(nav).getByText("生成任务")).toBeVisible();
    expect(within(nav).getByText("视觉质检")).toBeVisible();
    expect(within(nav).getByRole("link", { name: "生成任务，2 个运行中" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "视觉质检，3 个待审核" })).toBeInTheDocument();

    firstRender.unmount();
    renderApp("/storyboard");
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "分镜导演台" })).toBeInTheDocument(),
    );
    expect(screen.getByRole("link", { name: /分镜导演台/, current: "page" })).toBeInTheDocument();
  });

  it("只展示真实快照项目、版本、指标和数据库状态", () => {
    renderApp();

    expect(screen.getByText("《归墟》第一部")).toBeInTheDocument();
    expect(screen.getByText("版本 v08")).toBeInTheDocument();
    expect(screen.getByText("整体进度 68%")).toBeInTheDocument();
    expect(screen.getByText("待审核 3")).toBeInTheDocument();
    expect(screen.getByText("暂无估算")).toBeInTheDocument();
    expect(screen.getByText("数据库正常")).toBeInTheDocument();
    expect(screen.getByText("2 个任务")).toBeInTheDocument();
    expect(screen.queryByText(/GPU|显存|ComfyUI/i)).not.toBeInTheDocument();
  });

  it("用可访问开关更新关键帧自动生产，并捕获失败显示固定中文错误", async () => {
    const user = userEvent.setup();
    const failure = new Error("write failed");
    vi.spyOn(workspaceApi, "updateStageAutomation").mockRejectedValue(failure);
    renderApp();

    const toggle = screen.getByRole("switch", { name: "关键帧自动生产" });
    expect(toggle).toHaveAttribute("aria-checked", "true");
    await user.click(toggle);

    expect(workspaceApi.updateStageAutomation).toHaveBeenCalledWith(
      "project-a",
      "keyframe",
      expect.objectContaining({ auto_produce: false }),
    );
    expect(await screen.findByText("保存自动生产设置失败，请重试")).toBeInTheDocument();
  });

  it("快照未载入时保留九阶段并禁用全部自动生产开关", () => {
    resetStores(null);
    vi.spyOn(workspaceApi, "getSnapshot").mockReturnValue(new Promise(() => undefined));
    renderApp();

    const rail = screen.getByLabelText("制作阶段");
    expect(within(rail).getAllByRole("listitem")).toHaveLength(9);
    for (const toggle of within(rail).getAllByRole("switch")) {
      expect(toggle).toBeDisabled();
      expect(toggle).toHaveAccessibleDescription("项目载入后可设置自动生产");
    }
  });

  it("检查器在选择对象前显示空态，选择后显示真实标识", () => {
    renderApp();
    const inspector = screen.getByRole("complementary", { name: "属性检查器" });
    expect(inspector).toHaveAttribute("data-collapsed", "true");
    expect(
      within(inspector).getByText("选择角色、镜头、素材或任务后，在这里查看属性与生成参数。"),
    ).toBeInTheDocument();

    act(() => useWorkspaceStore.getState().selectObject({ type: "镜头", id: "shot-03" }));

    expect(within(inspector).getByText("镜头 · shot-03")).toBeInTheDocument();
  });

  it("任务快捷区使用 /tasks 链接和真实活动任务中文计数", () => {
    const running = job("job-running", "running");
    const completed = job("job-completed", "completed");
    jobMocks.jobs = new Map([[running.id, running], [completed.id, completed]]);
    jobMocks.recentIds = [running.id, completed.id];
    renderApp();

    const link = screen.getByRole("link", { name: /生成任务 1 个运行中/ });
    expect(link).toHaveAttribute("href", "/tasks");
  });

  it("加载任务完成后由壳层统一订阅活动任务，并在卸载时清理", async () => {
    const running = job("job-running", "running");
    const waiting = job("job-review", "waiting_review");
    const completed = job("job-completed", "completed");
    const close = vi.fn();
    jobMocks.loadProjectJobs.mockResolvedValue([running, waiting, completed]);
    jobMocks.subscribeActiveJobs.mockReturnValue(close);
    resetStores(null);
    const workspaceLoading = deferred<WorkspaceSnapshot>();
    vi.mocked(workspaceApi.getSnapshot).mockReturnValue(workspaceLoading.promise);

    const rendered = renderApp("/overview", true);

    await waitFor(() => expect(workspaceApi.getSnapshot).toHaveBeenCalledTimes(1));
    expect(jobMocks.loadProjectJobs).not.toHaveBeenCalled();
    workspaceLoading.resolve(workspace({ project_id: "default" }));
    jobMocks.loadedProjectId = "default";
    jobMocks.loadRevision += 1;
    await waitFor(() => expect(jobMocks.loadProjectJobs).toHaveBeenCalledWith("default"));
    await waitFor(() => expect(jobMocks.subscribeActiveJobs).toHaveBeenCalledTimes(1));
    rendered.unmount();
    expect(close).toHaveBeenCalledTimes(1);
  });

  it("预置同项目 ID 但空快照时仍加载工作区", async () => {
    resetStores(null);
    useWorkspaceStore.setState({ projectId: "project-a" });
    vi.mocked(workspaceApi.getSnapshot).mockReturnValue(new Promise(() => undefined));

    renderApp("/overview");

    await waitFor(() =>
      expect(workspaceApi.getSnapshot).toHaveBeenCalledWith("project-a"),
    );
  });

  it("同项目加载失败后卸载并重新挂载会再次请求且不自动无限重试", async () => {
    resetStores(null);
    vi.mocked(workspaceApi.getSnapshot).mockRejectedValue(new Error("offline"));

    const first = renderApp("/overview");
    await waitFor(() => expect(useWorkspaceStore.getState().error).not.toBeNull());
    expect(workspaceApi.getSnapshot).toHaveBeenCalledTimes(1);
    first.unmount();

    renderApp("/overview");
    await waitFor(() => expect(workspaceApi.getSnapshot).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(useWorkspaceStore.getState().error).not.toBeNull());
    expect(workspaceApi.getSnapshot).toHaveBeenCalledTimes(2);
  });

  it("任务加载失败在壳层任务页可见并可显式重试，不创建第二套生命周期", async () => {
    const user = userEvent.setup();
    jobMocks.loadError = new Error("jobs offline");
    renderApp("/tasks");

    expect(await screen.findByRole("alert")).toHaveTextContent("jobs offline");
    await user.click(screen.getByRole("button", { name: "重新加载任务" }));

    expect(jobMocks.retryProjectJobs).toHaveBeenCalledTimes(1);
    expect(jobMocks.loadProjectJobs).toHaveBeenCalledTimes(1);
    expect(jobMocks.subscribeActiveJobs).toHaveBeenCalledTimes(1);
  });

  it("A 切换到 B 时立即重置任务并隐藏残留的 A 活动计数", async () => {
    const runningA = job("job-a", "running");
    jobMocks.jobs = new Map([[runningA.id, runningA]]);
    jobMocks.recentIds = [runningA.id];
    const loadingB = deferred<WorkspaceSnapshot>();
    vi.mocked(workspaceApi.getSnapshot).mockImplementation((projectId) =>
      projectId === "B" ? loadingB.promise : Promise.resolve(workspace()),
    );
    renderApp("/overview");
    expect(screen.getByRole("link", { name: "生成任务 1 个运行中" })).toBeInTheDocument();
    jobMocks.resetProjectJobs.mockClear();

    act(() => {
      useProjectStore.getState().setProject({
        id: "B",
        title: "项目 B",
        novel_text: "",
      });
    });

    expect(jobMocks.resetProjectJobs).toHaveBeenCalledWith("B");
    expect(screen.getByRole("link", { name: "生成任务 暂无运行任务" })).toBeInTheDocument();
    expect(jobMocks.loadProjectJobs).not.toHaveBeenCalledWith("B");
    loadingB.reject(new Error("B workspace failed"));
    await waitFor(() => expect(useWorkspaceStore.getState().error).not.toBeNull());
    expect(screen.getByRole("link", { name: "生成任务 暂无运行任务" })).toBeInTheDocument();
  });
});

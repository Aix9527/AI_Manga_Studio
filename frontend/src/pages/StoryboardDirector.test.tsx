import React, { StrictMode } from "react";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as storyApi from "@/api/story";
import { ApiError } from "@/api/client";
import * as pipelineApi from "@/api/pipeline";
import { workspaceApi } from "@/api/workspace";
import App from "@/App";
import { usePipelineStore } from "@/state/pipelineStore";
import { useProjectStore } from "@/state/projectStore";
import { useStoryStore } from "@/state/storyStore";
import { useWorkspaceStore } from "@/state/workspaceStore";
import type { SceneData, ShotData } from "@/api/story";

vi.mock("@/api/story", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/story")>();
  return {
    ...actual,
    getStoryboardScenes: vi.fn(),
    updateShot: vi.fn(),
  };
});

vi.mock("@/components/workbench/WorkbenchShell", async () => {
  const ReactModule = await vi.importActual<typeof import("react")>("react");
  const RouterModule = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  const { default: InspectorPanel } = await vi.importActual<
    typeof import("@/components/workbench/InspectorPanel")
  >("@/components/workbench/InspectorPanel");
  const { default: StageRail } = await vi.importActual<
    typeof import("@/components/workbench/StageRail")
  >("@/components/workbench/StageRail");
  const { default: ProjectHeader } = await vi.importActual<
    typeof import("@/components/workbench/ProjectHeader")
  >("@/components/workbench/ProjectHeader");
  return {
    default: () => ReactModule.createElement(
      ReactModule.Fragment,
      null,
      ReactModule.createElement(ProjectHeader),
      ReactModule.createElement(StageRail),
      ReactModule.createElement(RouterModule.Outlet),
      ReactModule.createElement(InspectorPanel),
    ),
  };
});

type StoryApiWithDirector = typeof storyApi & {
  getStoryboardScenes: ReturnType<typeof vi.fn<(novelId: string) => Promise<SceneData[]>>>;
  updateShot: ReturnType<typeof vi.fn<(novelId: string, shotId: string, patch: Partial<ShotData>) => Promise<ShotData>>>;
};

const directorApi = storyApi as StoryApiWithDirector;

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function shot(overrides: Partial<ShotData> & Pick<ShotData, "id" | "scene_id" | "index">): ShotData {
  return {
    shot_type: "wide",
    camera_angle: "eye-level",
    camera_movement: "static",
    description: "风暴中的海堤",
    action: "守塔人扶住栏杆",
    dialogue: "灯不能灭。",
    narration: "潮水正在上涨。",
    emotion: "紧张",
    character_ids: ["char-a"],
    duration: 2,
    positive_prompt: "storm coast",
    negative_prompt: "watermark",
    seed: 0,
    image_model: "",
    video_model: "",
    thumbnail_url: "",
    production_status: "pending",
    quality_status: "unreviewed",
    ...overrides,
  };
}

const canonicalScenes: SceneData[] = [
  {
    id: "scene-a",
    chapter_id: "chapter-1",
    index: 0,
    raw_text: "海浪越过堤岸。",
    description: "海堤外景",
    location: "北港海堤",
    shots: [
      shot({ id: "shot-1", scene_id: "scene-a", index: 0, thumbnail_url: "https://cdn.test/shot-1.png" }),
      shot({ id: "shot-2", scene_id: "scene-a", index: 1, shot_type: "medium", duration: 3, character_ids: ["char-a", "char-b"], thumbnail_url: "C:\\shots\\local.png", production_status: "completed", quality_status: "approved" }),
    ],
  },
  {
    id: "scene-b",
    chapter_id: "chapter-1",
    index: 1,
    raw_text: "灯塔重新亮起。",
    description: "灯塔内景",
    location: "旧灯塔",
    shots: [
      shot({ id: "shot-3", scene_id: "scene-b", index: 2, shot_type: "close-up", duration: 4, character_ids: [], description: "火苗映亮眼睛", thumbnail_url: "data:image/png;base64,AAAA", production_status: "unexpected", quality_status: "unexpected" }),
    ],
  },
];

function automation(stage_key: "keyframe" | "video", auto_produce: boolean) {
  return {
    stage_key,
    auto_produce,
    quality_threshold: 0.8,
    max_quality_retries: 2,
    auto_advance: false,
    provider_settings: {},
  } as const;
}

function seed(novelId = "novel-a") {
  useProjectStore.setState({
    project: { id: "project-a", novel_id: novelId, title: "潮汐", novel_text: "" },
    activeTab: "novel",
  });
  useStoryStore.getState().clearAll();
  usePipelineStore.getState().clearAll();
  useWorkspaceStore.setState({
    projectId: "project-a",
    snapshot: {
      project_id: "project-a",
      title: "潮汐",
      source_path: "novel.txt",
      version: "v1",
      progress: 0,
      pending_reviews: 0,
      active_jobs: 0,
      estimated_minutes: null,
      stages: [
        { stage_key: "keyframe", status: "pending", progress: 0, waiting_review: 0, automation: automation("keyframe", false) },
        { stage_key: "video", status: "pending", progress: 0, waiting_review: 0, automation: automation("video", true) },
      ],
      system_health: {},
    },
    selectedObject: null,
    loading: false,
    error: null,
  });
}

function renderDirector(strict = false) {
  const content = <MemoryRouter initialEntries={["/director"]}><App /></MemoryRouter>;
  return render(strict ? <StrictMode>{content}</StrictMode> : content);
}

beforeEach(() => {
  vi.restoreAllMocks();
  seed();
  directorApi.getStoryboardScenes.mockReset().mockResolvedValue([]);
  directorApi.updateShot.mockReset();
  vi.spyOn(pipelineApi, "compileSingleShot").mockResolvedValue({
    positive_prompt: "compiled positive",
    negative_prompt: "compiled negative",
    parameters: {},
  });
});

afterEach(() => {
  cleanup();
  useStoryStore.getState().clearAll();
});

describe("分镜导演台", () => {
  it("路由展示真实导演台空态且不再提供第二套小说粘贴入口", async () => {
    renderDirector();

    expect(screen.getByRole("heading", { name: "分镜导演台", level: 1 })).toBeInTheDocument();
    expect(await screen.findByText("此项目尚未生成分镜")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回故事与角色" })).toHaveAttribute("href", "/story");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/Import Novel Text|Paste novel text|Parse & Generate/i);
  });

  it("恢复 canonical 场景并在场景切换时呈现真实中文镜头字段", async () => {
    const user = userEvent.setup();
    directorApi.getStoryboardScenes.mockResolvedValue(canonicalScenes);
    renderDirector();

    const sceneSelect = await screen.findByRole("combobox", { name: "选择场景" });
    expect(sceneSelect).toHaveValue("scene-a");
    expect(screen.getByRole("button", { name: "选择镜头 01" })).toHaveTextContent("远景");
    expect(screen.getByRole("button", { name: "选择镜头 02" })).toHaveTextContent("3 秒");
    expect(screen.getByRole("button", { name: "选择镜头 02" })).toHaveTextContent("2 个人物");
    expect(screen.getByRole("button", { name: "选择镜头 02" })).toHaveTextContent("已完成");
    expect(screen.getByRole("button", { name: "选择镜头 02" })).toHaveTextContent("已通过");
    expect(screen.getByRole("img", { name: "镜头 01 缩略图" })).toHaveAttribute("src", "https://cdn.test/shot-1.png");
    expect(screen.getByText("尚未生成关键帧")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/wide|medium|pending|unreviewed/);

    await user.selectOptions(sceneSelect, "scene-b");
    const third = screen.getByRole("button", { name: "选择镜头 03" });
    expect(third).toHaveTextContent("特写");
    expect(third).toHaveTextContent("未知生产状态");
    expect(third).toHaveTextContent("未知质检状态");
  });

  it("镜头 03 的网格、全片时间线和镜头参数检查器保持同步", async () => {
    const user = userEvent.setup();
    directorApi.getStoryboardScenes.mockResolvedValue(canonicalScenes);
    renderDirector();
    await screen.findByRole("combobox", { name: "选择场景" });
    await user.selectOptions(screen.getByRole("combobox", { name: "选择场景" }), "scene-b");
    await user.click(screen.getByRole("button", { name: "选择镜头 03" }));

    expect(screen.getByRole("button", { name: "选择镜头 03" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "定位镜头 03" })).toHaveAttribute("aria-pressed", "true");
    const inspector = screen.getByRole("complementary", { name: "镜头参数" });
    expect(within(inspector).getByLabelText("动作")).toHaveValue("守塔人扶住栏杆");
    expect(useStoryStore.getState().selectedShotId).toBe("shot-3");
    expect(useWorkspaceStore.getState().selectedObject).toEqual({ type: "镜头", id: "shot-3" });
  });

  it("显式角色选择优先于残留镜头 ID，不误显示镜头检查器", async () => {
    const user = userEvent.setup();
    directorApi.getStoryboardScenes.mockResolvedValue(canonicalScenes);
    renderDirector();
    await user.click(await screen.findByRole("button", { name: "选择镜头 01" }));

    act(() => useWorkspaceStore.getState().selectObject({ type: "角色", id: "char-a" }));

    expect(useStoryStore.getState().selectedShotId).toBe("shot-1");
    expect(screen.getByRole("complementary", { name: "属性检查器" })).toHaveTextContent("角色 · char-a");
    expect(screen.queryByRole("complementary", { name: "镜头参数" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("动作")).not.toBeInTheDocument();
  });

  it("切换场景会清除不属于目标场景的镜头选择并同步网格、时间线和检查器", async () => {
    const user = userEvent.setup();
    directorApi.getStoryboardScenes.mockResolvedValue(canonicalScenes);
    renderDirector();
    await user.click(await screen.findByRole("button", { name: "选择镜头 01" }));

    await user.selectOptions(screen.getByRole("combobox", { name: "选择场景" }), "scene-b");

    expect(useStoryStore.getState().selectedShotId).toBeNull();
    expect(useWorkspaceStore.getState().selectedObject).toBeNull();
    expect(screen.getByRole("button", { name: "定位镜头 01" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "选择镜头 03" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("complementary", { name: "属性检查器" })).toHaveTextContent("尚未选择对象");
  });

  it("全片时间线使用真实 2 秒/3 秒比例并显示累计区间", async () => {
    directorApi.getStoryboardScenes.mockResolvedValue([{ ...canonicalScenes[0], shots: canonicalScenes[0].shots.slice(0, 2) }]);
    renderDirector();

    const timeline = await screen.findByRole("list", { name: "全片时间线" });
    expect(within(timeline).getByRole("button", { name: "定位镜头 01" })).toHaveStyle({ width: "40%" });
    expect(within(timeline).getByRole("button", { name: "定位镜头 02" })).toHaveStyle({ width: "60%" });
    expect(within(timeline).getByText("0–2 秒")).toBeInTheDocument();
    expect(within(timeline).getByText("2–5 秒")).toBeInTheDocument();
    expect(screen.getByText("总时长 5 秒")).toBeInTheDocument();
  });

  it("编辑后只发送真实 PATCH，失败保留草稿且切换镜头隔离迟到保存响应", async () => {
    const user = userEvent.setup();
    directorApi.getStoryboardScenes.mockResolvedValue(canonicalScenes);
    const firstSave = deferred<ShotData>();
    directorApi.updateShot.mockReturnValueOnce(firstSave.promise);
    renderDirector();
    await user.click(await screen.findByRole("button", { name: "选择镜头 01" }));

    const duration = screen.getByLabelText("时长");
    await user.clear(duration);
    await user.type(duration, "6.5");
    expect(screen.getByRole("status")).toHaveTextContent("有未保存修改");
    await user.click(screen.getByRole("button", { name: "保存镜头设置" }));
    expect(directorApi.updateShot).toHaveBeenCalledWith(
      "novel-a",
      "shot-1",
      expect.objectContaining({ duration: 6.5 }),
    );

    await user.click(screen.getByRole("button", { name: "选择镜头 02" }));
    firstSave.resolve({ ...canonicalScenes[0].shots[0], duration: 6.5 });
    await act(async () => { await firstSave.promise; });
    expect(screen.getByLabelText("时长")).toHaveValue(3);
    expect(screen.queryByText("已保存")).not.toBeInTheDocument();

    directorApi.updateShot.mockRejectedValueOnce(new ApiError(500, "disk failed"));
    await user.clear(screen.getByLabelText("旁白"));
    await user.type(screen.getByLabelText("旁白"), "新的旁白");
    await user.click(screen.getByRole("button", { name: "保存镜头设置" }));
    expect(await screen.findByText("服务暂时不可用，请稍后重试")).toBeInTheDocument();
    expect(screen.getByLabelText("旁白")).toHaveValue("新的旁白");
    expect(screen.getByRole("status")).toHaveTextContent("有未保存修改");
  });

  it("同一项目同一镜头的快速保存按 FIFO 发出并以第二版更新状态", async () => {
    const firstSave = deferred<ShotData>();
    const secondSave = deferred<ShotData>();
    directorApi.updateShot
      .mockReturnValueOnce(firstSave.promise)
      .mockReturnValueOnce(secondSave.promise);
    useStoryStore.setState({
      scenes: canonicalScenes,
      shots: canonicalScenes.flatMap((scene) => scene.shots),
      storyboardNovelId: "novel-a",
    });

    const first = useStoryStore.getState().updateShot("novel-a", "shot-1", { duration: 6 });
    const second = useStoryStore.getState().updateShot("novel-a", "shot-1", { duration: 8 });

    expect(directorApi.updateShot).toHaveBeenCalledTimes(1);
    expect(directorApi.updateShot).toHaveBeenNthCalledWith(1, "novel-a", "shot-1", { duration: 6 });
    firstSave.resolve({ ...canonicalScenes[0].shots[0], duration: 6 });
    await first;
    await waitFor(() => expect(directorApi.updateShot).toHaveBeenCalledTimes(2));
    expect(directorApi.updateShot).toHaveBeenNthCalledWith(2, "novel-a", "shot-1", { duration: 8 });

    secondSave.resolve({ ...canonicalScenes[0].shots[0], duration: 8 });
    await second;
    expect(useStoryStore.getState().shots.find((item) => item.id === "shot-1")?.duration).toBe(8);
  });

  it("旧项目 generation 的 FIFO 保存完成后不写入当前项目 UI", async () => {
    const firstSave = deferred<ShotData>();
    const secondSave = deferred<ShotData>();
    directorApi.updateShot
      .mockReturnValueOnce(firstSave.promise)
      .mockReturnValueOnce(secondSave.promise);
    useStoryStore.setState({
      scenes: canonicalScenes,
      shots: canonicalScenes.flatMap((scene) => scene.shots),
      storyboardNovelId: "novel-a",
    });

    const first = useStoryStore.getState().updateShot("novel-a", "shot-1", { duration: 6 });
    const second = useStoryStore.getState().updateShot("novel-a", "shot-1", { duration: 8 });
    useStoryStore.getState().invalidateRequests();
    const projectBScenes = [{
      ...canonicalScenes[1],
      id: "scene-project-b",
      shots: [shot({ id: "shot-b", scene_id: "scene-project-b", index: 0, duration: 4 })],
    }];
    useStoryStore.setState({
      scenes: projectBScenes,
      shots: projectBScenes[0].shots,
      storyboardNovelId: "novel-b",
    });

    firstSave.resolve({ ...canonicalScenes[0].shots[0], duration: 6 });
    await first;
    await waitFor(() => expect(directorApi.updateShot).toHaveBeenCalledTimes(2));
    secondSave.resolve({ ...canonicalScenes[0].shots[0], duration: 8 });
    await second;

    expect(useStoryStore.getState().storyboardNovelId).toBe("novel-b");
    expect(useStoryStore.getState().shots).toEqual(projectBScenes[0].shots);
  });

  it("真实编译合并返回字段但不冒充已保存，失败显示中文错误", async () => {
    const user = userEvent.setup();
    directorApi.getStoryboardScenes.mockResolvedValue(canonicalScenes);
    vi.mocked(pipelineApi.compileSingleShot).mockResolvedValueOnce({
      positive_prompt: "cinematic lighthouse",
      negative_prompt: "blur, text",
      parameters: { seed: 91, image_model: "flux-2", video_model: "ltx-2.3" },
    });
    renderDirector();
    await user.click(await screen.findByRole("button", { name: "选择镜头 01" }));
    await user.clear(screen.getByLabelText("动作"));
    await user.type(screen.getByLabelText("动作"), "冲向灯塔");
    await user.click(screen.getByRole("button", { name: "编译提示词" }));

    expect(pipelineApi.compileSingleShot).toHaveBeenCalledWith(expect.objectContaining({
      id: "shot-1",
      action: "冲向灯塔",
      character_ids: ["char-a"],
    }));
    expect(await screen.findByLabelText("正向提示词")).toHaveValue("cinematic lighthouse");
    expect(screen.getByLabelText("负向提示词")).toHaveValue("blur, text");
    expect(screen.getByLabelText("随机种子")).toHaveValue(91);
    expect(screen.getByLabelText("图像模型")).toHaveValue("flux-2");
    expect(screen.queryByText("已保存")).not.toBeInTheDocument();
    expect(directorApi.updateShot).not.toHaveBeenCalled();

    vi.mocked(pipelineApi.compileSingleShot).mockRejectedValueOnce(new ApiError(500, "compiler down"));
    await user.click(screen.getByRole("button", { name: "编译提示词" }));
    expect(await screen.findByText("服务暂时不可用，请稍后重试")).toBeInTheDocument();
    expect(directorApi.updateShot).not.toHaveBeenCalled();
  });

  it("关键帧和视频自动开关调用对应阶段并捕获失败", async () => {
    const user = userEvent.setup();
    directorApi.getStoryboardScenes.mockResolvedValue(canonicalScenes);
    const updateStageAutomation = vi.spyOn(workspaceApi, "updateStageAutomation")
      .mockResolvedValueOnce(automation("keyframe", true))
      .mockRejectedValueOnce(new ApiError(500, "save failed"));
    renderDirector();
    await screen.findByRole("combobox", { name: "选择场景" });

    const keyframe = screen.getByRole("switch", { name: "关键帧自动生产" });
    const video = screen.getByRole("switch", { name: "视频自动生产" });
    expect(keyframe).toHaveAttribute("aria-checked", "false");
    expect(video).toHaveAttribute("aria-checked", "true");
    await user.click(keyframe);
    await user.click(video);
    expect(updateStageAutomation).toHaveBeenNthCalledWith(
      1,
      "project-a",
      "keyframe",
      expect.objectContaining({ auto_produce: true }),
    );
    expect(updateStageAutomation).toHaveBeenNthCalledWith(
      2,
      "project-a",
      "video",
      expect.objectContaining({ auto_produce: false }),
    );
    expect(await screen.findByText("保存自动生产设置失败，请重试")).toBeInTheDocument();
  });

  it("批量 checkbox 按稳定顺序逐个编译，展示进度且失败保留选择", async () => {
    const user = userEvent.setup();
    const secondCompile = deferred<pipelineApi.CompiledPrompt>();
    directorApi.getStoryboardScenes.mockResolvedValue(canonicalScenes);
    vi.mocked(pipelineApi.compileSingleShot)
      .mockResolvedValueOnce({ positive_prompt: "one", negative_prompt: "", parameters: {} })
      .mockReturnValueOnce(secondCompile.promise);
    renderDirector();
    await screen.findByRole("combobox", { name: "选择场景" });
    await user.click(screen.getByRole("checkbox", { name: "加入批量生成：镜头 01" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "选择场景" }), "scene-b");
    await user.click(screen.getByRole("checkbox", { name: "加入批量生成：镜头 03" }));
    expect(screen.getByText("已选择 2 个镜头")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "编译所选镜头提示词" }));
    expect(await screen.findByText("正在编译 2/2")).toBeInTheDocument();
    secondCompile.reject(new ApiError(500, "failed"));
    expect(await screen.findByText("编译完成：成功 1 个，失败 1 个")).toBeInTheDocument();
    expect(screen.getByText("已选择 2 个镜头")).toBeInTheDocument();
    expect(vi.mocked(pipelineApi.compileSingleShot).mock.calls.map(([value]) => value.id)).toEqual(["shot-1", "shot-3"]);
  });

  it("切换项目会终止旧项目批量编译且不写入旧任务总结", async () => {
    const user = userEvent.setup();
    const firstCompile = deferred<pipelineApi.CompiledPrompt>();
    directorApi.getStoryboardScenes.mockImplementation((id) => Promise.resolve(id === "novel-a" ? canonicalScenes : []));
    vi.mocked(pipelineApi.compileSingleShot).mockReturnValueOnce(firstCompile.promise);
    renderDirector();
    await screen.findByRole("combobox", { name: "选择场景" });
    await user.click(screen.getByRole("checkbox", { name: "加入批量生成：镜头 01" }));
    await user.click(screen.getByRole("checkbox", { name: "加入批量生成：镜头 02" }));
    await user.click(screen.getByRole("button", { name: "编译所选镜头提示词" }));
    await screen.findByText("正在编译 1/2");

    act(() => useProjectStore.setState({ project: { id: "project-b", novel_id: "novel-b", title: "B", novel_text: "" } }));
    firstCompile.resolve({ positive_prompt: "one", negative_prompt: "", parameters: {} });
    await act(async () => { await firstCompile.promise; });
    await Promise.resolve();

    expect(vi.mocked(pipelineApi.compileSingleShot).mock.calls.map(([value]) => value.id)).toEqual(["shot-1"]);
    expect(screen.queryByText(/编译完成：/)).not.toBeInTheDocument();
  });

  it("卸载会终止旧批量编译且不继续编译剩余镜头", async () => {
    const user = userEvent.setup();
    const firstCompile = deferred<pipelineApi.CompiledPrompt>();
    directorApi.getStoryboardScenes.mockResolvedValue(canonicalScenes);
    vi.mocked(pipelineApi.compileSingleShot).mockReturnValueOnce(firstCompile.promise);
    const rendered = renderDirector();
    await screen.findByRole("combobox", { name: "选择场景" });
    await user.click(screen.getByRole("checkbox", { name: "加入批量生成：镜头 01" }));
    await user.click(screen.getByRole("checkbox", { name: "加入批量生成：镜头 02" }));
    await user.click(screen.getByRole("button", { name: "编译所选镜头提示词" }));
    await screen.findByText("正在编译 1/2");

    rendered.unmount();
    firstCompile.resolve({ positive_prompt: "one", negative_prompt: "", parameters: {} });
    await firstCompile.promise;
    await Promise.resolve();

    expect(vi.mocked(pipelineApi.compileSingleShot).mock.calls.map(([value]) => value.id)).toEqual(["shot-1"]);
  });

  it("只为 HTTP、HTTPS 或 data URL 渲染真实缩略图", async () => {
    const user = userEvent.setup();
    directorApi.getStoryboardScenes.mockResolvedValue(canonicalScenes);
    renderDirector();
    await screen.findByRole("img", { name: "镜头 01 缩略图" });
    expect(screen.queryByAltText("镜头 02 缩略图")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByRole("combobox", { name: "选择场景" }), "scene-b");
    expect(screen.getByRole("img", { name: "镜头 03 缩略图" })).toHaveAttribute("src", "data:image/png;base64,AAAA");
  });

  it("导演台 API 编码动态 ID，并以重复查询参数和 body 传递人物 ID", async () => {
    const actualStory = await vi.importActual<typeof storyApi>("@/api/story");
    vi.mocked(pipelineApi.compileSingleShot).mockRestore();
    const fetchSpy = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(canonicalScenes[0].shots[0]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        positive_prompt: "compiled",
        negative_prompt: "",
        parameters: {},
      }), { status: 200 }));

    await actualStory.getStoryboardScenes("小说/a?");
    await actualStory.updateShot("小说/a?", "镜头/1?", { duration: 6 });
    await pipelineApi.compileSingleShot(canonicalScenes[0].shots[0], ["人物/a", "人物 b"]);

    expect(fetchSpy.mock.calls[0][0]).toBe("/api/story/graph/%E5%B0%8F%E8%AF%B4%2Fa%3F/scenes");
    expect(fetchSpy.mock.calls[1][0]).toBe("/api/story/%E5%B0%8F%E8%AF%B4%2Fa%3F/shots/%E9%95%9C%E5%A4%B4%2F1%3F");
    expect(JSON.parse(String((fetchSpy.mock.calls[1][1] as RequestInit).body))).toEqual({ duration: 6 });
    expect(fetchSpy.mock.calls[2][0]).toBe(
      "/api/pipeline/compile/shot?character_ids=%E4%BA%BA%E7%89%A9%2Fa&character_ids=%E4%BA%BA%E7%89%A9+b",
    );
    expect(JSON.parse(String((fetchSpy.mock.calls[2][1] as RequestInit).body)).character_ids).toEqual([
      "人物/a",
      "人物 b",
    ]);
  });

  it("A→B、卸载与 StrictMode 都不会让迟到或重复加载污染当前项目", async () => {
    const first = deferred<SceneData[]>();
    const second = deferred<SceneData[]>();
    directorApi.getStoryboardScenes.mockImplementation((id) => id === "novel-a" ? first.promise : second.promise);
    const rendered = renderDirector();
    expect(directorApi.getStoryboardScenes).toHaveBeenCalledWith("novel-a");

    act(() => useProjectStore.setState({ project: { id: "project-b", novel_id: "novel-b", title: "B", novel_text: "" } }));
    second.resolve([{ ...canonicalScenes[1], id: "scene-project-b", shots: [shot({ id: "shot-b", scene_id: "scene-project-b", index: 0, description: "B 项目镜头" })] }]);
    await act(async () => { await second.promise; });
    first.resolve(canonicalScenes);
    await act(async () => { await first.promise; });
    expect(useStoryStore.getState().storyboardNovelId).toBe("novel-b");
    expect(useStoryStore.getState().shots.map((item) => item.id)).toEqual(["shot-b"]);

    const lateUnmount = deferred<SceneData[]>();
    act(() => useProjectStore.setState({ project: { id: "project-c", novel_id: "novel-c", title: "C", novel_text: "" } }));
    directorApi.getStoryboardScenes.mockReturnValueOnce(lateUnmount.promise);
    rendered.unmount();
    useStoryStore.getState().clearAll();
    lateUnmount.resolve(canonicalScenes);
    await lateUnmount.promise;
    await Promise.resolve();
    expect(useStoryStore.getState().scenes).toEqual([]);

    seed("strict-project");
    directorApi.getStoryboardScenes.mockClear().mockResolvedValue([]);
    renderDirector(true);
    await waitFor(() => expect(directorApi.getStoryboardScenes).toHaveBeenCalledTimes(1));
  });
});

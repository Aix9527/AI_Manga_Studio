import React from "react";
import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as characterApi from "@/api/character";
import { ApiError } from "@/api/client";
import * as storyApi from "@/api/story";
import ReferenceGallery from "@/components/ReferenceGallery";
import StoryCharacterWorkspace from "@/pages/StoryCharacterWorkspace";
import { useCharacterStore } from "@/state/characterStore";
import { useProjectStore } from "@/state/projectStore";
import { useStoryStore } from "@/state/storyStore";
import { useWorkspaceStore } from "@/state/workspaceStore";
import type { CharacterData } from "@/api/character";
import type { StoryGraph } from "@/api/story";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

const graph: StoryGraph = {
  id: "graph-a",
  novel_id: "project-a",
  title: "归墟",
  nodes: [
    { id: "chapter-1", type: "chapter", label: "潮声", index: 0, data: {} },
    { id: "scene-1", type: "scene", label: "海堤", index: 0, parent_id: "chapter-1", data: {} },
    { id: "shot-1", type: "shot", label: "远景海潮", index: 0, parent_id: "scene-1", data: {} },
  ],
  edges: [{ source: "shot-1", target: "shot-2", edge_type: "sequence" }],
};

const character: CharacterData = {
  id: "char-1",
  name: "林默",
  role: "protagonist",
  gender: "male",
  species: "human",
  age: 22,
  appearance: { hair_color: "黑色", mystery_key: "银色耳坠" },
  personality: { brave: "勇敢" },
};

function seed() {
  useWorkspaceStore.setState({
    projectId: "project-a",
    snapshot: {
      project_id: "project-a", title: "归墟", source_path: "story.txt", version: "v1",
      progress: 0.2, pending_reviews: 0, active_jobs: 0, estimated_minutes: null,
      stages: [], system_health: { database: "ok" },
    },
    selectedObject: null,
    loading: false,
    error: null,
  });
  useProjectStore.setState({ project: null, activeTab: "novel" });
  useStoryStore.setState({
    graph: null, scenes: [], shots: [], timeline: [], loading: false, error: null,
    parsing: false, parseError: null, timelineError: null,
    selectedChapterIndex: null, selectedSceneId: null, selectedShotId: null,
  });
  useCharacterStore.setState({
    characters: [], selectedId: null, relationships: {}, loading: false,
    extracting: false, error: null, relationshipError: null,
  });
}

function renderPage() {
  return render(<MemoryRouter><StoryCharacterWorkspace /></MemoryRouter>);
}

beforeEach(() => {
  vi.restoreAllMocks();
  seed();
  vi.spyOn(storyApi, "getStoryGraph").mockRejectedValue(new ApiError(404, "missing"));
  vi.spyOn(characterApi, "listCharacters").mockResolvedValue([]);
  vi.spyOn(characterApi, "listRelationships").mockResolvedValue([]);
  vi.spyOn(characterApi, "listCharacterImages").mockResolvedValue([]);
});

afterEach(cleanup);

describe("故事与角色工作区", () => {
  it("提供原生 tabs 语义并可切换两个视图", async () => {
    const user = userEvent.setup();
    renderPage();
    expect(screen.getByRole("heading", { name: "故事与角色", level: 1 })).toBeInTheDocument();
    const tabs = screen.getByRole("tablist", { name: "故事与角色视图" });
    expect(within(tabs).getByRole("tab", { name: "故事结构" })).toHaveAttribute("aria-selected", "true");
    await user.click(within(tabs).getByRole("tab", { name: "角色圣经" }));
    expect(within(tabs).getByRole("tab", { name: "角色圣经" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "角色圣经" })).toBeInTheDocument();
  });

  it("故事和角色空态均提供可执行导入链接且不泄漏英文 API 错误", async () => {
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText("尚未生成故事结构")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "导入并解析小说" })).toHaveAttribute("href", "/overview#import");
    await user.click(screen.getByRole("tab", { name: "角色圣经" }));
    expect(await screen.findByText("尚未提取角色")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "导入并解析小说" })).toHaveAttribute("href", "/overview#import");
    expect(document.body).not.toHaveTextContent(/API error 500/i);
  });

  it("故事层级使用可展开按钮、中文计数并将镜头送入检查器", async () => {
    const user = userEvent.setup();
    vi.mocked(storyApi.getStoryGraph).mockResolvedValue(graph);
    renderPage();
    expect(await screen.findByText("3 个节点 · 1 条关系")).toBeInTheDocument();
    const chapter = screen.getByRole("button", { name: /第 1 章.*潮声.*1 个场景/ });
    expect(chapter).toHaveAttribute("aria-expanded", "true");
    const scene = screen.getByRole("button", { name: /第 1 场.*海堤.*1 个镜头/ });
    expect(scene).toHaveAttribute("aria-expanded", "false");
    await user.click(scene);
    await user.click(screen.getByRole("button", { name: /第 1 镜.*远景海潮.*1 条关联/ }));
    expect(useWorkspaceStore.getState().selectedObject).toEqual({ type: "镜头", id: "shot-1" });
    await user.click(chapter);
    expect(chapter).toHaveAttribute("aria-expanded", "false");
  });

  it("角色以 aria-pressed 选择，展示五组中文详情并更新检查器", async () => {
    const user = userEvent.setup();
    vi.mocked(characterApi.listCharacters).mockResolvedValue([character]);
    vi.mocked(characterApi.listCharacterImages).mockResolvedValue([
      { id: "ref-unknown", character_id: "char-1", url: "/refs/unknown.png" },
    ]);
    vi.mocked(characterApi.listRelationships).mockResolvedValue([{
      id: "rel-1", source_id: "char-1", target_id: "char-2", relation_type: "friend",
      related_name: "苏晚", description: "共同守城",
    }]);
    renderPage();
    await user.click(screen.getByRole("tab", { name: "角色圣经" }));
    const roleButton = await screen.findByRole("button", { name: /林默.*主角.*男/ });
    expect(roleButton).toHaveAttribute("aria-pressed", "false");
    await user.click(roleButton);
    expect(roleButton).toHaveAttribute("aria-pressed", "true");
    for (const heading of ["外观设定", "性格设定", "人物关系", "一致性检查", "角色参考图"]) {
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    }
    expect(screen.getByText("补充设定 1")).toBeInTheDocument();
    expect(screen.getByText(/苏晚.*共同守城/)).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: "林默：补充参考" })).toHaveAttribute("src", "/refs/unknown.png");
    expect(useWorkspaceStore.getState().selectedObject).toEqual({ type: "角色", id: "char-1" });
  });

  it("卸载工作区后在途故事响应不会写回已离开的视图", async () => {
    const pending = deferred<StoryGraph>();
    vi.mocked(storyApi.getStoryGraph).mockReturnValue(pending.promise);
    const rendered = renderPage();
    expect(storyApi.getStoryGraph).toHaveBeenCalledWith("project-a");
    rendered.unmount();

    pending.resolve(graph);
    await pending.promise;
    await Promise.resolve();

    expect(useStoryStore.getState().graph).toBeNull();
  });

  it("参考图库使用真实图片、中文 alt、可访问选择和独立删除按钮", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const onDelete = vi.fn();
    const { rerender } = render(
      <ReferenceGallery
        characterId="char-1" characterName="林默" selectedId="ref-1"
        references={[{ id: "ref-1", url: "/refs/front.png", label: "front", characterId: "char-1" }]}
        onSelect={onSelect} onDeleteReference={onDelete}
      />,
    );
    expect(screen.getByText("参考图库 · 1 张")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "林默：正面" })).toHaveAttribute("src", "/refs/front.png");
    const select = screen.getByRole("button", { name: "选择参考图：正面" });
    expect(select).toHaveAttribute("aria-pressed", "true");
    const remove = screen.getByRole("button", { name: "删除参考图：正面" });
    expect(select).not.toContainElement(remove);
    await user.click(select);
    await user.click(remove);
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onDelete).toHaveBeenCalledWith("ref-1");
    rerender(<ReferenceGallery characterId="char-1" characterName="林默" references={[]} />);
    expect(screen.getByText("尚无参考图，请添加正面、侧面、动作或表情参考。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "添加参考图" })).not.toBeInTheDocument();
  });

  it("角色和故事 API 编码动态 ID，并将 500 转为中文错误", async () => {
    vi.restoreAllMocks();
    const fetchSpy = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
      .mockResolvedValueOnce(new Response("boom", { status: 500 }));
    await characterApi.listCharacterImages("林默/a?");
    expect(fetchSpy.mock.calls[0][0]).toBe("/api/characters/%E6%9E%97%E9%BB%98%2Fa%3F/images");
    await expect(storyApi.getStoryGraph("坏/id?")).rejects.toThrow("服务暂时不可用，请稍后重试");
    expect(fetchSpy.mock.calls[1][0]).toBe("/api/story/graph/%E5%9D%8F%2Fid%3F");
  });

  it("A→B 加载以及快速切换角色时，迟到响应不能覆盖新选择", async () => {
    const storyA = deferred<StoryGraph>();
    const storyB = deferred<StoryGraph>();
    vi.mocked(storyApi.getStoryGraph).mockImplementation((id) => id === "A" ? storyA.promise : storyB.promise);
    const loadA = useStoryStore.getState().loadGraph("A");
    const loadB = useStoryStore.getState().loadGraph("B");
    storyB.resolve({ ...graph, id: "graph-b", novel_id: "B", title: "B" });
    await loadB;
    storyA.resolve({ ...graph, id: "graph-a", novel_id: "A", title: "A" });
    await loadA;
    expect(useStoryStore.getState().graph?.novel_id).toBe("B");

    const relA = deferred<characterApi.Relationship[]>();
    const relB = deferred<characterApi.Relationship[]>();
    vi.mocked(characterApi.listRelationships).mockImplementation((id) => id === "A" ? relA.promise : relB.promise);
    const first = useCharacterStore.getState().loadRelationships("A");
    const second = useCharacterStore.getState().loadRelationships("B");
    relB.resolve([{ id: "b", source_id: "B", target_id: "C", relation_type: "friend" }]);
    await second;
    relA.resolve([{ id: "a", source_id: "A", target_id: "C", relation_type: "enemy" }]);
    await first;
    expect(useCharacterStore.getState().relationships).toEqual({
      B: [{ id: "b", source_id: "B", target_id: "C", relation_type: "friend" }],
    });
  });

  it("parse 按项目独立防竞态，且 invalidateRequests 会取消在途解析", async () => {
    const parseA = deferred<storyApi.ParseResponse>();
    const parseB = deferred<storyApi.ParseResponse>();
    vi.spyOn(storyApi, "parseStory").mockImplementation((req) => req.novel_id === "A" ? parseA.promise : parseB.promise);
    const parseScenes = vi.spyOn(storyApi, "parseScenes");

    const first = useStoryStore.getState().parseStory("A 正文", "A");
    const second = useStoryStore.getState().parseStory("B 正文", "B");
    parseB.resolve({
      novel_id: "B", title: "", chapters: 1, scenes: 1, shots: 1,
      scene_data: [{ id: "scene-b", chapter_id: "chapter-b", index: 0, raw_text: "B", description: "B", shots: [] }],
    });
    await second;
    parseA.resolve({
      novel_id: "A", title: "", chapters: 1, scenes: 1, shots: 1,
      scene_data: [{ id: "scene-a", chapter_id: "chapter-a", index: 0, raw_text: "A", description: "A", shots: [] }],
    });
    await first;
    expect(useStoryStore.getState().scenes.map((scene) => scene.id)).toEqual(["scene-b"]);
    expect(parseScenes).not.toHaveBeenCalled();

    const cancelledParse = deferred<storyApi.ParseResponse>();
    vi.mocked(storyApi.parseStory).mockReturnValue(cancelledParse.promise);
    const cancelled = useStoryStore.getState().parseStory("旧正文", "old-project");
    useStoryStore.getState().invalidateRequests();
    cancelledParse.resolve({ novel_id: "old-project", title: "", chapters: 1, scenes: 0, shots: 0, scene_data: [] });
    await cancelled;
    expect(parseScenes).not.toHaveBeenCalled();
    expect(useStoryStore.getState().scenes.map((scene) => scene.id)).toEqual(["scene-b"]);
  });

  it("角色切换会重置一致性输入并忽略旧角色迟到结果", async () => {
    const user = userEvent.setup();
    const pending = deferred<characterApi.ConsistencyResult>();
    const secondCharacter: CharacterData = {
      ...character,
      id: "char-2",
      name: "苏晚",
      role: "enigmatic",
      gender: "nonbinary",
      species: "spirit",
    };
    vi.mocked(characterApi.listCharacters).mockResolvedValue([character, secondCharacter]);
    vi.spyOn(characterApi, "checkCharacterConsistency").mockReturnValue(pending.promise);
    renderPage();
    await user.click(screen.getByRole("tab", { name: "角色圣经" }));
    await user.click(await screen.findByRole("button", { name: /林默/ }));
    const input = screen.getByLabelText("待检查图像地址");
    await user.type(input, "generated/old.png");
    await user.click(screen.getByRole("button", { name: "检查一致性" }));
    const secondButton = screen.getByRole("button", { name: /苏晚/ });
    expect(secondButton).toHaveAccessibleName(/苏晚.*其他角色.*未说明性别/);
    await user.click(secondButton);

    expect(screen.getByLabelText("待检查图像地址")).toHaveValue("");
    await act(async () => pending.resolve({
      character_id: "char-1", passed: true, similarity: 0.9, threshold: 0.75, message: "",
    }));
    expect(screen.queryByText("0.900")).not.toBeInTheDocument();
  });
});

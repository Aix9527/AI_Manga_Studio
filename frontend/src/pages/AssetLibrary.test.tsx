import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { workspaceApi } from "@/api/workspace";
import AssetLibrary from "@/pages/AssetLibrary";
import { useWorkspaceStore } from "@/state/workspaceStore";
import type { ProjectAsset, WorkspaceSnapshot } from "@/workbench/types";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function snapshot(projectId = "project-a"): WorkspaceSnapshot {
  return {
    project_id: projectId,
    title: "归墟",
    source_path: "",
    version: "v01",
    progress: 0,
    pending_reviews: 0,
    active_jobs: 0,
    estimated_minutes: null,
    stages: [],
    system_health: {},
  };
}

function asset(overrides: Partial<ProjectAsset> = {}): ProjectAsset {
  return {
    id: 1,
    project_id: "project-a",
    job_id: "job-1",
    step_id: "step-1",
    kind: "image",
    path: "frames/hero.png",
    media_url: "/api/workspace/project-a/assets/1/media",
    stage_key: "keyframe",
    scene_id: "scene-1",
    shot_id: "shot-1",
    version: 2,
    parent_artifact_id: 0,
    active: true,
    quality_status: "passed",
    quality_attempt: 0,
    quality_report: {},
    metadata: {},
    created_at: "2026-08-02T08:30:00+00:00",
    ...overrides,
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
  useWorkspaceStore.setState({
    projectId: "project-a",
    snapshot: snapshot(),
    activeModule: "总览",
    selectedObject: null,
    loading: false,
    error: null,
  });
});

afterEach(cleanup);

describe("素材库", () => {
  it("加载当前项目并将筛选条件传给真实列表接口", async () => {
    const user = userEvent.setup();
    const listAssets = vi.spyOn(workspaceApi, "listAssets").mockResolvedValue([
      asset(),
      asset({ id: 2, kind: "audio", stage_key: "audio", scene_id: "scene-2", shot_id: "shot-8" }),
    ]);
    render(<AssetLibrary />);

    expect(await screen.findByRole("heading", { name: "素材库" })).toBeInTheDocument();
    expect(listAssets).toHaveBeenCalledWith("project-a", {});
    expect(listAssets).toHaveBeenCalledWith("project-a", { active: true });
    await user.selectOptions(screen.getByLabelText("媒体类型"), "audio");
    await waitFor(() => expect(listAssets).toHaveBeenLastCalledWith("project-a", {
      active: true,
      kind: "audio",
    }));
    await user.selectOptions(screen.getByLabelText("场景"), "scene-2");
    await waitFor(() => expect(listAssets).toHaveBeenLastCalledWith("project-a", {
      active: true,
      kind: "audio",
      scene_id: "scene-2",
    }));
  });

  it("全部版本请求省略 active 并显示真实历史版本", async () => {
    const user = userEvent.setup();
    const current = asset({ id: 2, path: "current.png", version: 2, active: true });
    const historical = asset({ id: 1, path: "history.png", version: 1, active: false });
    const listAssets = vi.spyOn(workspaceApi, "listAssets").mockImplementation(async (_projectId, filters = {}) => (
      filters.active === true ? [current] : [current, historical]
    ));
    render(<AssetLibrary />);

    expect(await screen.findByRole("heading", { name: "current.png" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "history.png" })).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("版本"), "all");
    expect(await screen.findByRole("heading", { name: "history.png" })).toBeInTheDocument();
    const finalFilters = listAssets.mock.calls[listAssets.mock.calls.length - 1][1] ?? {};
    expect(finalFilters).not.toHaveProperty("active");
  });

  it("慢基线目录不会被快速筛选覆盖且最终保留完整 facets", async () => {
    const user = userEvent.setup();
    const catalog = deferred<ProjectAsset[]>();
    vi.spyOn(workspaceApi, "listAssets").mockImplementation((_projectId, filters = {}) => {
      if (Object.keys(filters).length === 0) return catalog.promise;
      if (filters.quality_status === "passed") {
        return Promise.resolve([asset({ id: 2, kind: "audio", path: "voice.wav", stage_key: "audio" })]);
      }
      return Promise.resolve([asset({ id: 2, kind: "audio", path: "voice.wav", stage_key: "audio" })]);
    });
    render(<AssetLibrary />);

    await user.selectOptions(screen.getByLabelText("质检状态"), "passed");
    expect(await screen.findByRole("heading", { name: "voice.wav" })).toBeInTheDocument();
    await act(async () => catalog.resolve([
      asset({ id: 1, kind: "image", path: "hero.png", stage_key: "keyframe", scene_id: "scene-1", shot_id: "shot-1" }),
      asset({ id: 2, kind: "audio", path: "voice.wav", stage_key: "audio", scene_id: "scene-2", shot_id: "shot-2" }),
    ]));

    expect(screen.getByRole("option", { name: "图片" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "音频" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "scene-1" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "scene-2" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "voice.wav" })).toBeInTheDocument();
  });

  it("项目 A 的迟到响应不会覆盖项目 B，卸载后也不更新", async () => {
    const a = deferred<ProjectAsset[]>();
    const b = deferred<ProjectAsset[]>();
    vi.spyOn(workspaceApi, "listAssets").mockImplementation((projectId) => (
      projectId === "project-a" ? a.promise : b.promise
    ));
    const page = render(<AssetLibrary />);

    act(() => useWorkspaceStore.setState({ projectId: "project-b", snapshot: snapshot("project-b") }));
    await act(async () => b.resolve([asset({ id: 8, project_id: "project-b", path: "b.png" })]));
    expect(await screen.findByRole("heading", { name: "b.png" })).toBeInTheDocument();
    await act(async () => a.resolve([asset({ path: "late-a.png" })]));
    expect(screen.queryByText("late-a.png")).not.toBeInTheDocument();

    page.unmount();
    await act(async () => Promise.resolve());
  });

  it("展示图片、视频、音频与文本真实媒体，并明确中文版本状态", async () => {
    vi.spyOn(workspaceApi, "listAssets").mockResolvedValue([
      asset({ id: 1, kind: "image", path: "hero.png", media_url: "/media/hero.png" }),
      asset({ id: 2, kind: "video", path: "clip.mp4", media_url: "/media/clip.mp4", version: 1, active: false, quality_status: "failed" }),
      asset({ id: 3, kind: "audio", path: "voice.wav", media_url: "/media/voice.wav", quality_status: "unreviewed" }),
      asset({ id: 4, kind: "subtitle", path: "dialogue.srt", media_url: "/media/dialogue.srt", quality_status: "reviewing" }),
    ]);
    render(<AssetLibrary />);

    expect(await screen.findByRole("img", { name: /素材 hero\.png.*版本 2/ })).toHaveAttribute("src", "/media/hero.png");
    expect(screen.getByLabelText(/素材 clip\.mp4.*版本 1/).tagName).toBe("VIDEO");
    expect(screen.getByLabelText(/素材 voice\.wav.*版本 2/).tagName).toBe("AUDIO");
    expect(screen.getByRole("link", { name: "打开素材 dialogue.srt 版本 2" })).toHaveAttribute("href", "/media/dialogue.srt");
    const historical = screen.getByRole("heading", { name: "clip.mp4" }).closest("article");
    expect(historical).not.toBeNull();
    expect(within(historical!).getByText("版本 v1")).toBeInTheDocument();
    expect(within(historical!).getByText("历史版本")).toBeInTheDocument();
    expect(within(historical!).getByText("质检未通过")).toBeInTheDocument();
    expect(within(screen.getByRole("heading", { name: "hero.png" }).closest("article")!).getByText("质检通过")).toBeInTheDocument();
    expect(within(screen.getByRole("heading", { name: "voice.wav" }).closest("article")!).getByText("未质检")).toBeInTheDocument();
    expect(within(screen.getByRole("heading", { name: "dialogue.srt" }).closest("article")!).getByText("质检中")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/F:\\|C:\\|\/Users\//);
  });

  it("媒体加载失败显示中文错误和文件名，不使用假缩略图", async () => {
    vi.spyOn(workspaceApi, "listAssets").mockResolvedValue([asset({ path: "broken.png" })]);
    render(<AssetLibrary />);

    fireEvent.error(await screen.findByRole("img", { name: /broken\.png/ }));
    expect(screen.getByRole("alert")).toHaveTextContent("素材加载失败：broken.png");
    expect(screen.queryByText(/示例|占位|thumbnail/i)).not.toBeInTheDocument();
  });

  it("错误可重新加载；筛选空态可清除，默认空态没有伪操作", async () => {
    const user = userEvent.setup();
    const listAssets = vi.spyOn(workspaceApi, "listAssets").mockImplementation(async (_projectId, filters = {}) => {
      if (Object.keys(filters).length === 0) return [];
      if (listAssets.mock.calls.filter(([, value]) => value?.active === true).length === 1) {
        throw new TypeError("offline");
      }
      return [];
    });
    render(<AssetLibrary />);

    expect(await screen.findByText("无法连接本地服务，请检查后端是否运行")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重新加载" }));
    expect(await screen.findByText("当前筛选条件下暂无素材")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "清除筛选" })).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("质检状态"), "passed");
    expect(await screen.findByRole("button", { name: "清除筛选" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "清除筛选" }));
    expect(screen.queryByRole("button", { name: "清除筛选" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /删除|恢复|下载/ })).not.toBeInTheDocument();
    expect(listAssets).toHaveBeenCalled();
  });
});

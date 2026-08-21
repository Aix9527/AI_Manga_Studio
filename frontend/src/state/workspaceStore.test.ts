import { beforeEach, describe, expect, it, vi } from "vitest";

import { request } from "@/api/client";
import { workspaceApi } from "@/api/workspace";
import { useWorkspaceStore } from "@/state/workspaceStore";
import type {
  StageAutomation,
  StageKey,
  WorkspaceSnapshot,
} from "@/workbench/types";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function automation(
  stage_key: StageKey,
  overrides: Partial<StageAutomation> = {},
): StageAutomation {
  return {
    stage_key,
    auto_produce: true,
    quality_threshold: 0.82,
    max_quality_retries: 2,
    auto_advance: true,
    provider_settings: {},
    ...overrides,
  };
}

function workspace(project_id: string): WorkspaceSnapshot {
  return {
    project_id,
    title: `项目 ${project_id}`,
    source_path: `/projects/${project_id}`,
    version: "v01",
    progress: 0.4,
    pending_reviews: 1,
    active_jobs: 2,
    estimated_minutes: 12,
    stages: [
      {
        stage_key: "keyframe",
        status: "running",
        progress: 0.5,
        waiting_review: 0,
        automation: automation("keyframe"),
      },
      {
        stage_key: "video",
        status: "pending",
        progress: 0,
        waiting_review: 0,
        automation: automation("video", { quality_threshold: 0.9 }),
      },
    ],
    system_health: { database: "ok" },
  };
}

function resetWorkspaceStore() {
  useWorkspaceStore.setState({
    projectId: "",
    snapshot: null,
    activeModule: "总览",
    selectedObject: null,
    loading: false,
    error: null,
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
  resetWorkspaceStore();
});

describe("workspace store", () => {
  it("loads and stores a workspace snapshot while clearing loading and errors", async () => {
    const expected = workspace("project-a");
    vi.spyOn(workspaceApi, "getSnapshot").mockResolvedValue(expected);
    useWorkspaceStore.setState({ error: "旧错误" });

    await useWorkspaceStore.getState().loadWorkspace("project-a");

    expect(useWorkspaceStore.getState()).toMatchObject({
      projectId: "project-a",
      snapshot: expected,
      loading: false,
      error: null,
    });
  });

  it("maps a fetch network failure to a Chinese connection error", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"));

    await useWorkspaceStore.getState().loadWorkspace("offline-project");

    expect(useWorkspaceStore.getState().error).toBe(
      "无法连接本地服务，请检查后端是否运行",
    );
    expect(useWorkspaceStore.getState().loading).toBe(false);
  });

  it("maps an HTML 500 response to a stable Chinese service error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("<html>internal stack trace</html>", {
        status: 500,
        headers: { "Content-Type": "text/html" },
      }),
    );

    await useWorkspaceStore.getState().loadWorkspace("broken-project");

    expect(useWorkspaceStore.getState().error).toBe("服务暂时不可用，请稍后重试");
    expect(useWorkspaceStore.getState().error).not.toContain("html");
  });

  it("keeps a Chinese string detail returned by a 422 response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "阶段标识不一致" }), {
        status: 422,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await useWorkspaceStore.getState().loadWorkspace("invalid-project");

    expect(useWorkspaceStore.getState().error).toBe("阶段标识不一致");
  });

  it("does not let a late project A response overwrite project B", async () => {
    const projectA = deferred<WorkspaceSnapshot>();
    const projectB = deferred<WorkspaceSnapshot>();
    vi.spyOn(workspaceApi, "getSnapshot").mockImplementation((projectId) =>
      projectId === "A" ? projectA.promise : projectB.promise,
    );

    const loadingA = useWorkspaceStore.getState().loadWorkspace("A");
    const loadingB = useWorkspaceStore.getState().loadWorkspace("B");
    projectB.resolve(workspace("B"));
    await loadingB;
    projectA.resolve(workspace("A"));
    await loadingA;

    expect(useWorkspaceStore.getState()).toMatchObject({
      projectId: "B",
      snapshot: workspace("B"),
      loading: false,
    });
  });

  it("optimistically changes only keyframe automation without changing video", async () => {
    const saving = deferred<StageAutomation>();
    vi.spyOn(workspaceApi, "updateStageAutomation").mockReturnValue(saving.promise);
    useWorkspaceStore.setState({ projectId: "project-a", snapshot: workspace("project-a") });
    const videoBefore = useWorkspaceStore.getState().snapshot?.stages[1];

    const pending = useWorkspaceStore
      .getState()
      .setStageAutomation("keyframe", { auto_produce: false });

    expect(
      useWorkspaceStore.getState().snapshot?.stages[0].automation.auto_produce,
    ).toBe(false);
    expect(useWorkspaceStore.getState().snapshot?.stages[1]).toBe(videoBefore);

    saving.resolve(automation("keyframe", { auto_produce: false }));
    await pending;
  });

  it("rolls back only the failed stage, sets a fixed error, and rejects", async () => {
    const failure = new Error("disk write failed");
    vi.spyOn(workspaceApi, "updateStageAutomation").mockRejectedValue(failure);
    const initial = workspace("project-a");
    useWorkspaceStore.setState({ projectId: "project-a", snapshot: initial });

    const result = useWorkspaceStore
      .getState()
      .setStageAutomation("keyframe", { auto_produce: false });

    await expect(result).rejects.toBe(failure);
    expect(useWorkspaceStore.getState().snapshot?.stages[0]).toEqual(initial.stages[0]);
    expect(useWorkspaceStore.getState().snapshot?.stages[1]).toEqual(initial.stages[1]);
    expect(useWorkspaceStore.getState().error).toBe(
      "保存自动生产设置失败，请重试",
    );
  });

  it("does not let an earlier failed mutation roll back a newer success", async () => {
    const firstRequest = deferred<StageAutomation>();
    const secondRequest = deferred<StageAutomation>();
    vi.spyOn(workspaceApi, "updateStageAutomation")
      .mockReturnValueOnce(firstRequest.promise)
      .mockReturnValueOnce(secondRequest.promise);
    useWorkspaceStore.setState({ projectId: "project-a", snapshot: workspace("project-a") });

    const first = useWorkspaceStore
      .getState()
      .setStageAutomation("keyframe", { auto_produce: false })
      .catch((error: unknown) => error);
    const second = useWorkspaceStore
      .getState()
      .setStageAutomation("keyframe", { quality_threshold: 0.96 });
    const newest = automation("keyframe", {
      quality_threshold: 0.96,
    });
    firstRequest.reject(new Error("late failure"));
    await first;
    await Promise.resolve();
    expect(workspaceApi.updateStageAutomation).toHaveBeenCalledTimes(2);
    secondRequest.resolve(newest);
    await second;

    expect(useWorkspaceStore.getState().snapshot?.stages[0].automation).toEqual(newest);
    expect(useWorkspaceStore.getState().error).toBeNull();
  });

  it("returns to the original confirmed automation when two queued mutations both fail", async () => {
    const firstRequest = deferred<StageAutomation>();
    const secondRequest = deferred<StageAutomation>();
    const update = vi
      .spyOn(workspaceApi, "updateStageAutomation")
      .mockReturnValueOnce(firstRequest.promise)
      .mockReturnValueOnce(secondRequest.promise);
    const initial = workspace("project-a");
    useWorkspaceStore.setState({ projectId: "project-a", snapshot: initial });

    const first = useWorkspaceStore
      .getState()
      .setStageAutomation("keyframe", { auto_produce: false })
      .catch((error: unknown) => error);
    const second = useWorkspaceStore
      .getState()
      .setStageAutomation("keyframe", { quality_threshold: 0.96 })
      .catch((error: unknown) => error);

    expect(update).toHaveBeenCalledTimes(1);
    expect(
      useWorkspaceStore.getState().snapshot?.stages[0].automation,
    ).toEqual(automation("keyframe", { auto_produce: false, quality_threshold: 0.96 }));
    firstRequest.reject(new Error("first failed"));
    await first;
    await Promise.resolve();
    expect(update).toHaveBeenCalledTimes(2);
    expect(update.mock.calls[1][2]).toEqual(
      automation("keyframe", { quality_threshold: 0.96 }),
    );
    secondRequest.reject(new Error("second failed"));
    await second;

    expect(useWorkspaceStore.getState().snapshot?.stages[0].automation).toEqual(
      initial.stages[0].automation,
    );
  });

  it("keeps an earlier server-normalized baseline when a later queued mutation fails", async () => {
    const firstRequest = deferred<StageAutomation>();
    const secondRequest = deferred<StageAutomation>();
    const update = vi
      .spyOn(workspaceApi, "updateStageAutomation")
      .mockReturnValueOnce(firstRequest.promise)
      .mockReturnValueOnce(secondRequest.promise);
    useWorkspaceStore.setState({ projectId: "project-a", snapshot: workspace("project-a") });

    const first = useWorkspaceStore
      .getState()
      .setStageAutomation("keyframe", { quality_threshold: 0.913 });
    const second = useWorkspaceStore
      .getState()
      .setStageAutomation("keyframe", { auto_advance: false })
      .catch((error: unknown) => error);
    const normalized = automation("keyframe", {
      quality_threshold: 0.91,
      provider_settings: { normalized_by: "server" },
    });

    firstRequest.resolve(normalized);
    await first;
    await Promise.resolve();
    expect(update.mock.calls[1][2]).toEqual({ ...normalized, auto_advance: false });
    secondRequest.reject(new Error("second failed"));
    await second;

    expect(useWorkspaceStore.getState().snapshot?.stages[0].automation).toEqual(
      normalized,
    );
  });

  it("URL-encodes the project ID and sends the complete merged automation", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify(
          automation("keyframe", {
            quality_threshold: 0.93,
            provider_settings: { model: "local" },
          }),
        ),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    useWorkspaceStore.setState({
      projectId: "项目/第一章?draft",
      snapshot: workspace("项目/第一章?draft"),
    });

    await useWorkspaceStore.getState().setStageAutomation("keyframe", {
      quality_threshold: 0.93,
      provider_settings: { model: "local" },
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe(
      "/api/workspace/%E9%A1%B9%E7%9B%AE%2F%E7%AC%AC%E4%B8%80%E7%AB%A0%3Fdraft/automation/keyframe",
    );
    expect(init).toMatchObject({ method: "PUT" });
    expect(JSON.parse(String(init?.body))).toEqual({
      stage_key: "keyframe",
      auto_produce: true,
      quality_threshold: 0.93,
      max_quality_retries: 2,
      auto_advance: true,
      provider_settings: { model: "local" },
    });
  });

  it("preserves caller headers and does not add JSON content type to FormData", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ path: "/tmp/input.txt" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const form = new FormData();
    form.append("project_id", "A");

    await request<{ path: string }>("/upload/input", {
      method: "POST",
      body: form,
      headers: { "X-Trace-Id": "trace-1" },
    });

    const headers = new Headers(fetchSpy.mock.calls[0][1]?.headers);
    expect(headers.get("X-Trace-Id")).toBe("trace-1");
    expect(headers.has("Content-Type")).toBe(false);
  });
});

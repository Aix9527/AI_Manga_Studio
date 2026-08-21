import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/jobs";
import { jobStoreActions } from "@/state/jobStore";
import type { JobDetail, JobStatus, JobSummary } from "@/types/jobs";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function job(id: string, projectId: string, status: JobStatus): JobDetail {
  return {
    id,
    project_id: projectId,
    status,
    mode: "automatic",
    desired_state: "running",
    current_stage: "keyframe",
    current_shot: "shot-1",
    progress: 0.5,
    message: `${id} message`,
    final_video: "",
    created_at: "2026-08-02T00:00:00Z",
    updated_at: "2026-08-02T00:01:00Z",
    finished_at: null,
    steps: [
      {
        id: `${id}-step`,
        stage_key: "generate_keyframes",
        shot_id: "shot-1",
        status: "running",
        attempt: 1,
        progress: 0.5,
        error_code: "",
        error_message: "",
        quality_attempt: 0,
        ui_stage_key: "keyframe",
        quality_report: {},
        started_at: "2026-08-02T00:00:30Z",
        finished_at: null,
      },
    ],
    artifacts: [],
  };
}

function summary(detail: JobDetail): JobSummary {
  const { steps: _steps, artifacts: _artifacts, ...value } = detail;
  return value;
}

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readonly url: string;
  readonly listeners = new Map<string, Set<EventListener>>();
  closed = false;
  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;

  constructor(url: string | URL) {
    this.url = String(url);
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    const handler =
      typeof listener === "function" ? listener : listener.handleEvent.bind(listener);
    const listeners = this.listeners.get(type) ?? new Set<EventListener>();
    listeners.add(handler);
    this.listeners.set(type, listeners);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, data: Record<string, unknown>) {
    const event = new MessageEvent(type, { data: JSON.stringify(data) });
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }
}

async function resetJobStore() {
  vi.restoreAllMocks();
  vi.spyOn(api, "listJobs").mockResolvedValue({ items: [] });
  await jobStoreActions().loadProjectJobs("__test_reset__");
  vi.restoreAllMocks();
  FakeEventSource.instances = [];
}

beforeEach(resetJobStore);

describe("job store restoration", () => {
  it("restores the complete jobs map from list plus parallel detail calls and clears it for an empty list", async () => {
    const first = job("job-1", "project-a", "running");
    const second = job("job-2", "project-a", "completed");
    vi.spyOn(api, "listJobs")
      .mockResolvedValueOnce({ items: [summary(first), summary(second)] })
      .mockResolvedValueOnce({ items: [] });
    vi.spyOn(api, "getJob").mockImplementation(async (id) =>
      id === first.id ? first : second,
    );

    const restored = await jobStoreActions().loadProjectJobs("project-a");

    expect(restored).toEqual([first, second]);
    expect(jobStoreActions().listJobs()).toEqual([first, second]);
    expect(jobStoreActions().recentIds()).toEqual(["job-1", "job-2"]);

    await jobStoreActions().loadProjectJobs("project-a");
    expect(jobStoreActions().listJobs()).toEqual([]);
    expect(jobStoreActions().recentIds()).toEqual([]);
  });

  it("does not let a late project A response overwrite restored project B jobs", async () => {
    const listA = deferred<{ items: JobSummary[] }>();
    const projectA = job("job-a", "A", "running");
    const projectB = job("job-b", "B", "queued");
    vi.spyOn(api, "listJobs").mockImplementation((projectId) =>
      projectId === "A"
        ? listA.promise
        : Promise.resolve({ items: [summary(projectB)] }),
    );
    vi.spyOn(api, "getJob").mockImplementation(async (id) =>
      id === projectA.id ? projectA : projectB,
    );

    const loadingA = jobStoreActions().loadProjectJobs("A");
    const loadingB = jobStoreActions().loadProjectJobs("B");
    await loadingB;
    listA.resolve({ items: [summary(projectA)] });
    await loadingA;

    expect(jobStoreActions().listJobs()).toEqual([projectB]);
    expect(jobStoreActions().recentIds()).toEqual(["job-b"]);
  });

  it("scopes loading failures to the active project and supports an explicit retry", async () => {
    const actions = jobStoreActions();
    vi.spyOn(api, "listJobs")
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({ items: [] });

    await expect(actions.loadProjectJobs("project-a")).rejects.toThrow("offline");
    expect(actions.loadState()).toEqual({
      loadingProjectId: "",
      loadError: expect.any(Error),
    });

    await actions.retryProjectJobs();
    expect(actions.loadState()).toEqual({
      loadingProjectId: "",
      loadError: null,
    });
  });

  it("does not store a refresh result from a non-active project", async () => {
    const projectB = job("job-b", "B", "running");
    const staleA = job("job-a", "A", "queued");
    vi.spyOn(api, "listJobs").mockResolvedValue({ items: [summary(projectB)] });
    vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(projectB)
      .mockResolvedValueOnce(staleA);
    await jobStoreActions().loadProjectJobs("B");

    await jobStoreActions().refreshJob(staleA.id);

    expect(jobStoreActions().listJobs()).toEqual([projectB]);
    expect(jobStoreActions().getJob(staleA.id)).toBeUndefined();
  });

  it("returns but does not store a late create response after switching projects", async () => {
    const creatingA = deferred<JobDetail>();
    const createdA = job("job-created-a", "A", "queued");
    vi.spyOn(api, "listJobs").mockResolvedValue({ items: [] });
    vi.spyOn(api, "createJob").mockReturnValue(creatingA.promise);
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    await jobStoreActions().loadProjectJobs("A");

    const result = jobStoreActions().createJob({
      project_id: "A",
      input_path: "story.txt",
    });
    jobStoreActions().resetProjectJobs("B");
    creatingA.resolve(createdA);

    await expect(result).resolves.toEqual(createdA);
    expect(jobStoreActions().listJobs()).toEqual([]);
    expect(jobStoreActions().recentIds()).toEqual([]);
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it("does not store a create response whose project differs from the request", async () => {
    const mismatched = job("job-mismatch", "B", "queued");
    vi.spyOn(api, "listJobs").mockResolvedValue({ items: [] });
    vi.spyOn(api, "createJob").mockResolvedValue(mismatched);
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    await jobStoreActions().loadProjectJobs("A");

    const result = await jobStoreActions().createJob({
      project_id: "A",
      input_path: "story.txt",
    });

    expect(result).toEqual(mismatched);
    expect(jobStoreActions().listJobs()).toEqual([]);
    expect(jobStoreActions().recentIds()).toEqual([]);
    expect(FakeEventSource.instances).toHaveLength(0);
  });
});

describe("job store SSE lifecycle", () => {
  it("does not open an EventSource for an unknown job", () => {
    const subscribe = vi.spyOn(api, "subscribeJobEvents");

    const cleanup = jobStoreActions().subscribeSSE("missing-job");

    expect(subscribe).not.toHaveBeenCalled();
    cleanup();
  });

  it("subscribes only active jobs, closes all sources, and replaces old subscriptions without leaks", async () => {
    const statuses: JobStatus[] = [
      "queued",
      "running",
      "waiting_review",
      "retry_wait",
      "paused",
      "completed",
      "failed",
      "cancelled",
    ];
    const jobs = statuses.map((status, index) =>
      job(`job-${index}`, "project-a", status),
    );
    vi.spyOn(api, "listJobs").mockResolvedValue({ items: jobs.map(summary) });
    vi.spyOn(api, "getJob").mockImplementation(async (id) =>
      jobs.find((candidate) => candidate.id === id)!,
    );
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    await jobStoreActions().loadProjectJobs("project-a");

    const cleanupFirst = jobStoreActions().subscribeActiveJobs();
    const firstSources = [...FakeEventSource.instances];
    expect(firstSources).toHaveLength(4);
    expect(firstSources.map((source) => source.url)).toEqual([
      "/api/jobs/job-0/events",
      "/api/jobs/job-1/events",
      "/api/jobs/job-2/events",
      "/api/jobs/job-3/events",
    ]);

    const cleanupSecond = jobStoreActions().subscribeActiveJobs();
    const secondSources = FakeEventSource.instances.slice(4);
    expect(firstSources.every((source) => source.closed)).toBe(true);
    expect(secondSources).toHaveLength(4);
    expect(secondSources.every((source) => !source.closed)).toBe(true);

    cleanupFirst();
    expect(secondSources.every((source) => !source.closed)).toBe(true);
    cleanupSecond();
    expect(secondSources.every((source) => source.closed)).toBe(true);
  });

  it("defensively excludes active jobs from another project during batch subscription", async () => {
    const activeA = job("job-a", "A", "running");
    const leakedB = job("job-b", "B", "queued");
    vi.spyOn(api, "listJobs").mockResolvedValue({
      items: [summary(activeA), summary(leakedB)],
    });
    vi.spyOn(api, "getJob").mockImplementation(async (id) =>
      id === activeA.id ? activeA : leakedB,
    );
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    await jobStoreActions().loadProjectJobs("A");

    jobStoreActions().subscribeActiveJobs();

    expect(FakeEventSource.instances.map((source) => source.url)).toEqual([
      "/api/jobs/job-a/events",
    ]);
  });

  it("refreshes the corresponding job when a named quality_retry event arrives", async () => {
    const running = job("job-running", "project-a", "running");
    const retried: JobDetail = {
      ...running,
      progress: 0.7,
      message: "质量重试 1/2",
      steps: [
        {
          ...running.steps[0],
          status: "retry_wait",
          quality_attempt: 1,
          quality_report: { score: 0.71 },
        },
      ],
    };
    vi.spyOn(api, "listJobs").mockResolvedValue({ items: [summary(running)] });
    const getJob = vi
      .spyOn(api, "getJob")
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(retried);
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    await jobStoreActions().loadProjectJobs("project-a");
    const cleanup = jobStoreActions().subscribeActiveJobs();
    const source = FakeEventSource.instances[0];

    expect(source.listeners.has("quality_retry")).toBe(true);
    source.emit("quality_retry", { job_id: running.id, quality_attempt: 1 });
    await Promise.resolve();

    expect(getJob).toHaveBeenCalledTimes(2);
    expect(jobStoreActions().getJob(running.id)).toEqual(retried);
    cleanup();
  });

  it("reconciles paused resume and failed retry into exactly one live source", async () => {
    const paused = job("job-paused", "project-a", "paused");
    const failed = job("job-failed", "project-a", "failed");
    vi.spyOn(api, "listJobs").mockResolvedValue({
      items: [summary(paused), summary(failed)],
    });
    vi.spyOn(api, "getJob").mockImplementation(async (id) =>
      id === paused.id ? paused : failed,
    );
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    vi.spyOn(api, "resumeJob").mockResolvedValue({ ...paused, status: "queued" });
    vi.spyOn(api, "retryJob").mockResolvedValue({ ...failed, status: "queued" });
    await jobStoreActions().loadProjectJobs("project-a");
    jobStoreActions().subscribeActiveJobs();
    expect(FakeEventSource.instances).toHaveLength(0);

    await jobStoreActions().resumeJob(paused.id);
    await jobStoreActions().retryJob(failed.id);

    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.instances.every((source) => !source.closed)).toBe(true);
  });

  it("keeps one source for an active refresh and closes it after pausing", async () => {
    const running = job("job-running", "project-a", "running");
    const queued = { ...running, status: "queued" as const };
    const paused = { ...running, status: "paused" as const };
    vi.spyOn(api, "listJobs").mockResolvedValue({ items: [summary(running)] });
    vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(queued);
    vi.spyOn(api, "pauseJob").mockResolvedValue(paused);
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    await jobStoreActions().loadProjectJobs("project-a");
    jobStoreActions().subscribeActiveJobs();
    const source = FakeEventSource.instances[0];

    await jobStoreActions().refreshJob(running.id);
    expect(FakeEventSource.instances).toHaveLength(1);
    await jobStoreActions().pauseJob(running.id);

    expect(source.closed).toBe(true);
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it("reopens when an active mutation replaces a terminal in-flight record", async () => {
    const running = job("job-running", "project-a", "running");
    const pendingRefresh = deferred<JobDetail>();
    vi.spyOn(api, "listJobs").mockResolvedValue({ items: [summary(running)] });
    vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(running)
      .mockReturnValueOnce(pendingRefresh.promise);
    vi.spyOn(api, "retryJob").mockResolvedValue({ ...running, status: "queued" });
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    await jobStoreActions().loadProjectJobs("project-a");
    jobStoreActions().subscribeActiveJobs();
    const terminalSource = FakeEventSource.instances[0];
    terminalSource.emit("step_completed", { job_id: running.id });
    terminalSource.emit("terminal", { status: "completed" });

    await jobStoreActions().retryJob(running.id);

    expect(terminalSource.closed).toBe(true);
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.instances[1].closed).toBe(false);
    pendingRefresh.resolve(running);
  });

  it("subscribes a newly created active job in the current project once", async () => {
    const created = job("job-created", "project-a", "queued");
    vi.spyOn(api, "listJobs").mockResolvedValue({ items: [] });
    vi.spyOn(api, "createJob").mockResolvedValue(created);
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    await jobStoreActions().loadProjectJobs("project-a");

    await jobStoreActions().createJob({
      project_id: "project-a",
      input_path: "story.txt",
    });

    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.instances[0].url).toContain("job-created");
  });

  it("refreshes on the reviewed event without replacing the active source", async () => {
    const waiting = job("job-review", "project-a", "waiting_review");
    const queued = { ...waiting, status: "queued" as const };
    vi.spyOn(api, "listJobs").mockResolvedValue({ items: [summary(waiting)] });
    vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(waiting)
      .mockResolvedValueOnce(queued);
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    await jobStoreActions().loadProjectJobs("project-a");
    jobStoreActions().subscribeActiveJobs();
    const source = FakeEventSource.instances[0];

    expect(source.listeners.has("reviewed")).toBe(true);
    source.emit("reviewed", { job_id: waiting.id, action: "retry" });
    await Promise.resolve();

    expect(jobStoreActions().getJob(waiting.id)).toEqual(queued);
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(source.closed).toBe(false);
  });

  it("closes and removes a matching source when refresh returns a completed job", async () => {
    const running = job("job-running", "project-a", "running");
    const completed = { ...running, status: "completed" as const, progress: 1 };
    vi.spyOn(api, "listJobs").mockResolvedValue({ items: [summary(running)] });
    vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(completed);
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    await jobStoreActions().loadProjectJobs("project-a");
    const cleanup = jobStoreActions().subscribeActiveJobs();
    const source = FakeEventSource.instances[0];

    source.emit("job_completed", { job_id: running.id, status: "completed" });
    await Promise.resolve();

    expect(source.closed).toBe(true);
    expect(jobStoreActions().getJob(running.id)).toEqual(completed);
    cleanup();
  });

  it("closes a terminal source immediately so EventSource cannot reconnect", async () => {
    const running = job("job-running", "project-a", "running");
    vi.spyOn(api, "listJobs").mockResolvedValue({ items: [summary(running)] });
    vi.spyOn(api, "getJob").mockResolvedValue(running);
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    await jobStoreActions().loadProjectJobs("project-a");
    const cleanup = jobStoreActions().subscribeActiveJobs();
    const source = FakeEventSource.instances[0];

    source.emit("terminal", { job_id: running.id, status: "completed" });

    expect(source.closed).toBe(true);
    cleanup();
  });

  it("keeps an in-flight job_completed refresh through terminal and stores the completed detail", async () => {
    const running = job("job-running", "project-a", "running");
    const completed = { ...running, status: "completed" as const, progress: 1 };
    const terminalRefresh = deferred<JobDetail>();
    vi.spyOn(api, "listJobs").mockResolvedValue({ items: [summary(running)] });
    const getJob = vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(running)
      .mockReturnValueOnce(terminalRefresh.promise);
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    await jobStoreActions().loadProjectJobs("project-a");
    const cleanup = jobStoreActions().subscribeActiveJobs();
    const source = FakeEventSource.instances[0];

    source.emit("job_completed", { job_id: running.id, status: "completed" });
    source.emit("terminal", { status: "completed" });

    expect(source.closed).toBe(true);
    expect(getJob).toHaveBeenCalledTimes(2);
    terminalRefresh.resolve(completed);
    await Promise.resolve();
    await Promise.resolve();

    expect(jobStoreActions().getJob(running.id)).toEqual(completed);
    cleanup();
  });

  it("does not let a stale running refresh downgrade a validated completed terminal status", async () => {
    const running = job("job-running", "project-a", "running");
    const staleRunning = {
      ...running,
      progress: 0.9,
      message: "步骤已完成，终态尚未写入详情接口",
    };
    const staleRefresh = deferred<JobDetail>();
    vi.spyOn(api, "listJobs").mockResolvedValue({ items: [summary(running)] });
    const getJob = vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(running)
      .mockReturnValueOnce(staleRefresh.promise);
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    await jobStoreActions().loadProjectJobs("project-a");
    const cleanup = jobStoreActions().subscribeActiveJobs();
    const source = FakeEventSource.instances[0];

    source.emit("step_completed", { job_id: running.id });
    source.emit("terminal", { status: "completed" });

    expect(source.closed).toBe(true);
    expect(jobStoreActions().getJob(running.id)?.status).toBe("completed");
    staleRefresh.resolve(staleRunning);
    await Promise.resolve();
    await Promise.resolve();

    expect(getJob).toHaveBeenCalledTimes(2);
    expect(jobStoreActions().getJob(running.id)).toEqual({
      ...staleRunning,
      status: "completed",
    });
    cleanup();
  });

  it("keeps fallback refresh behavior when a terminal payload is malformed", async () => {
    const running = job("job-running", "project-a", "running");
    const failed = { ...running, status: "failed" as const, message: "生成失败" };
    const fallbackRefresh = deferred<JobDetail>();
    vi.spyOn(api, "listJobs").mockResolvedValue({ items: [summary(running)] });
    const getJob = vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(running)
      .mockReturnValueOnce(fallbackRefresh.promise);
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    await jobStoreActions().loadProjectJobs("project-a");
    const cleanup = jobStoreActions().subscribeActiveJobs();
    const source = FakeEventSource.instances[0];

    source.emit("step_failed", { job_id: running.id });
    source.emit("terminal", { status: "not-a-job-status" });
    fallbackRefresh.resolve(failed);
    await Promise.resolve();
    await Promise.resolve();

    expect(source.closed).toBe(true);
    expect(getJob).toHaveBeenCalledTimes(2);
    expect(jobStoreActions().getJob(running.id)).toEqual(failed);
    cleanup();
  });

  it("does not reopen a terminal source when its fallback detail is still active", async () => {
    const running = job("job-running", "project-a", "running");
    vi.spyOn(api, "listJobs").mockResolvedValue({ items: [summary(running)] });
    vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(running);
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    await jobStoreActions().loadProjectJobs("project-a");
    jobStoreActions().subscribeActiveJobs();
    const source = FakeEventSource.instances[0];

    source.emit("step_completed", { job_id: running.id });
    source.emit("terminal", { status: "malformed" });
    await Promise.resolve();
    await Promise.resolve();

    expect(source.closed).toBe(true);
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it("does not let an old terminal refresh or cleanup overwrite or delete a replacement source", async () => {
    const running = job("job-running", "project-a", "running");
    const oldRefresh = deferred<JobDetail>();
    vi.spyOn(api, "listJobs").mockResolvedValue({ items: [summary(running)] });
    vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(running)
      .mockReturnValueOnce(oldRefresh.promise)
      .mockResolvedValueOnce(running);
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    await jobStoreActions().loadProjectJobs("project-a");
    const cleanupOld = jobStoreActions().subscribeActiveJobs();
    const oldSource = FakeEventSource.instances[0];
    oldSource.emit("job_completed", { job_id: running.id, status: "completed" });
    oldSource.emit("terminal", { status: "completed" });

    await jobStoreActions().loadProjectJobs("project-a");
    const cleanupNew = jobStoreActions().subscribeActiveJobs();
    const newSource = FakeEventSource.instances[1];
    oldRefresh.resolve({ ...running, status: "completed", progress: 1 });
    await Promise.resolve();
    await Promise.resolve();

    expect(jobStoreActions().getJob(running.id)).toEqual(running);
    expect(newSource.closed).toBe(false);
    cleanupOld();
    expect(newSource.closed).toBe(false);
    cleanupNew();
  });

  it("does not let an old source refresh close or overwrite its replacement", async () => {
    const running = job("job-running", "project-a", "running");
    const oldRefresh = deferred<JobDetail>();
    vi.spyOn(api, "listJobs").mockResolvedValue({ items: [summary(running)] });
    vi.spyOn(api, "getJob")
      .mockResolvedValueOnce(running)
      .mockReturnValueOnce(oldRefresh.promise);
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    await jobStoreActions().loadProjectJobs("project-a");
    const cleanupOld = jobStoreActions().subscribeActiveJobs();
    const oldSource = FakeEventSource.instances[0];
    oldSource.emit("quality_retry", { job_id: running.id });

    const cleanupNew = jobStoreActions().subscribeActiveJobs();
    const newSource = FakeEventSource.instances[1];
    oldRefresh.resolve({ ...running, status: "completed", progress: 1 });
    await Promise.resolve();

    expect(newSource.closed).toBe(false);
    expect(jobStoreActions().getJob(running.id)).toEqual(running);
    cleanupOld();
    expect(newSource.closed).toBe(false);
    cleanupNew();
  });

  it("resets immediately for project B, closes project A SSE, and invalidates late A results", async () => {
    const actions = jobStoreActions();
    const runningA = job("job-a", "A", "running");
    vi.spyOn(api, "listJobs").mockResolvedValueOnce({ items: [summary(runningA)] });
    vi.spyOn(api, "getJob").mockResolvedValue(runningA);
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(
      (id) => new FakeEventSource(`/api/jobs/${id}/events`) as unknown as EventSource,
    );
    await actions.loadProjectJobs("A");
    const cleanupA = actions.subscribeActiveJobs();
    const sourceA = FakeEventSource.instances[0];
    const lateAList = deferred<{ items: JobSummary[] }>();
    vi.mocked(api.listJobs).mockReturnValueOnce(lateAList.promise);
    const lateALoad = actions.loadProjectJobs("A");

    actions.resetProjectJobs("B");

    expect(sourceA.closed).toBe(true);
    expect(actions.listJobs()).toEqual([]);
    vi.mocked(api.listJobs).mockRejectedValueOnce(new Error("B jobs failed"));
    await expect(actions.loadProjectJobs("B")).rejects.toThrow("B jobs failed");
    expect(actions.listJobs()).toEqual([]);

    lateAList.resolve({ items: [summary(runningA)] });
    await lateALoad;
    expect(actions.listJobs()).toEqual([]);
    cleanupA();
  });
});

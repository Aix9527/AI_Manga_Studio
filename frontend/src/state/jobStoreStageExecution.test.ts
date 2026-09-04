import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/jobs";
import { jobStoreActions } from "@/state/jobStore";
import type { JobDetail } from "@/types/jobs";

function detail(status: JobDetail["status"]): JobDetail {
  return {
    id: "job-stage",
    project_id: "project-a",
    status,
    mode: "automatic",
    desired_state: "running",
    current_stage: "video_generate",
    current_shot: "shot_001",
    progress: status === "queued" ? 0 : 1,
    message: status,
    final_video: "",
    created_at: "2026-09-05T00:00:00Z",
    updated_at: "2026-09-05T00:01:00Z",
    finished_at: null,
    steps: [],
    artifacts: [],
  };
}

function fakeEventSource(): EventSource {
  return {
    addEventListener: vi.fn(),
    close: vi.fn(),
    onmessage: null,
    onerror: null,
  } as unknown as EventSource;
}

beforeEach(async () => {
  vi.restoreAllMocks();
  vi.spyOn(api, "listJobs").mockResolvedValue({ items: [] });
  await jobStoreActions().loadProjectJobs("__stage_reset__");
  vi.restoreAllMocks();
});

describe("job store formal stage execution", () => {
  it("reconciles the authoritative returned JobDetail into the existing job entry", async () => {
    const paused = detail("paused");
    const queued = detail("queued");
    vi.spyOn(api, "listJobs").mockResolvedValue({ items: [{
      id: paused.id,
      project_id: paused.project_id,
      status: paused.status,
      mode: paused.mode,
      desired_state: paused.desired_state,
      current_stage: paused.current_stage,
      current_shot: paused.current_shot,
      progress: paused.progress,
      message: paused.message,
      final_video: paused.final_video,
      created_at: paused.created_at,
      updated_at: paused.updated_at,
      finished_at: paused.finished_at,
    }] });
    vi.spyOn(api, "getJob").mockResolvedValue(paused);
    const execute = vi.spyOn(api, "executeFromStage").mockResolvedValue(queued);
    vi.spyOn(api, "subscribeJobEvents").mockImplementation(() => fakeEventSource());
    await jobStoreActions().loadProjectJobs("project-a");

    const result = await jobStoreActions().executeFromStage("job-stage", {
      stage_key: "video_generate",
      shot_id: "shot_001",
      mode: "continue",
    });

    expect(result).toEqual(queued);
    expect(execute).toHaveBeenCalledWith("job-stage", {
      stage_key: "video_generate",
      shot_id: "shot_001",
      mode: "continue",
    });
    expect(jobStoreActions().getJob("job-stage")).toEqual(queued);
  });
});

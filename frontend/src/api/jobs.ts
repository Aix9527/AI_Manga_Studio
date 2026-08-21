// V5 API client (same-origin, no cross-origin issues)

import type {
  JobCreateRequest,
  JobDetail,
  JobListResponse,
  RetryRequest,
  ReviewRequest,
  RollbackPreview,
  ScannedProject,
} from "@/types/jobs";
import { request } from "@/api/client";

const BASE = "/api";

export const api = {
  // ── Jobs ──────────────────────────────────────────────────
  createJob: (data: JobCreateRequest) =>
    request<JobDetail>("/jobs", { method: "POST", body: JSON.stringify(data) }),

  listJobs: (projectId?: string, limit = 50, offset = 0) => {
    const params = new URLSearchParams({ limit: `${limit}`, offset: `${offset}` });
    if (projectId) params.set("project_id", projectId);
    return request<JobListResponse>(`/jobs?${params}`);
  },

  getJob: (jobId: string) => request<JobDetail>(`/jobs/${encodeURIComponent(jobId)}`),

  pauseJob: (jobId: string) =>
    request<JobDetail>(`/jobs/${encodeURIComponent(jobId)}/pause`, { method: "POST" }),

  resumeJob: (jobId: string) =>
    request<JobDetail>(`/jobs/${encodeURIComponent(jobId)}/resume`, { method: "POST" }),

  retryJob: (jobId: string, body: RetryRequest = {}) =>
    request<JobDetail>(`/jobs/${encodeURIComponent(jobId)}/retry`, { method: "POST", body: JSON.stringify(body) }),

  cancelJob: (jobId: string) =>
    request<JobDetail>(`/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" }),

  reviewJob: (jobId: string, body: ReviewRequest) =>
    request<JobDetail>(`/jobs/${encodeURIComponent(jobId)}/review`, { method: "POST", body: JSON.stringify(body) }),

  rollbackPreview: (jobId: string, stepId: string) =>
    request<RollbackPreview>(`/jobs/${encodeURIComponent(jobId)}/rollback-preview?step_id=${encodeURIComponent(stepId)}`),

  // ── SSE ───────────────────────────────────────────────────
  subscribeJobEvents: (jobId: string): EventSource =>
    new EventSource(`${BASE}/jobs/${encodeURIComponent(jobId)}/events`),

  // ── Upload ────────────────────────────────────────────────
  uploadInput: async (file: File, projectId: string): Promise<{ path: string }> => {
    const form = new FormData();
    form.append("file", file);
    form.append("project_id", projectId);
    return request<{ path: string }>("/upload/input", { method: "POST", body: form });
  },

  // ── Projects ──────────────────────────────────────────────
  listProjects: () =>
    request<{ projects: ScannedProject[] }>("/projects"),

  // ── Health ────────────────────────────────────────────────
  health: () => request<{ status: string; version: string }>("/health"),
};

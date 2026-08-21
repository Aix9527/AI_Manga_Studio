// Global Job Store using useSyncExternalStore.

import { useSyncExternalStore } from "react";

import { api } from "@/api/jobs";
import { refreshWorkspaceSnapshot } from "@/state/workspaceStore";
import type { JobCreateRequest, JobDetail, ReviewRequest } from "@/types/jobs";

interface JobStoreSnapshot {
  jobs: Map<string, JobDetail>;
  recentIds: string[];
  polling: boolean;
  loadingProjectId: string;
  loadedProjectId: string;
  loadRevision: number;
  loadError: unknown | null;
}

let snapshot: JobStoreSnapshot = {
  jobs: new Map(),
  recentIds: [],
  polling: false,
  loadingProjectId: "",
  loadedProjectId: "",
  loadRevision: 0,
  loadError: null,
};

let activeProjectId = "";
let projectLoadSequence = 0;
const listeners = new Set<() => void>();

interface EventSourceRecord {
  source: EventSource;
  refreshPromise: Promise<void> | null;
  terminal: boolean;
  terminalStatus: "completed" | "failed" | "cancelled" | null;
}

const eventSources = new Map<string, EventSourceRecord>();

const ACTIVE_STATUSES = new Set<JobDetail["status"]>([
  "queued",
  "running",
  "waiting_review",
  "retry_wait",
]);

const SSE_EVENT_NAMES = [
  "initial",
  "step_started",
  "step_completed",
  "step_failed",
  "quality_retry",
  "review_needed",
  "reviewed",
  "automation_changed",
  "job_completed",
  "job_failed",
  "paused",
  "resumed",
  "cancelled",
  "terminal",
] as const;

function emit() {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): JobStoreSnapshot {
  return snapshot;
}

function setSnapshot(partial: Partial<JobStoreSnapshot>) {
  snapshot = { ...snapshot, ...partial };
  emit();
}

function storeJob(job: JobDetail): boolean {
  if (!activeProjectId || job.project_id !== activeProjectId) return false;
  const jobs = new Map(snapshot.jobs);
  jobs.set(job.id, job);
  setSnapshot({ jobs });
  return true;
}

function closeAllEventSources() {
  for (const record of eventSources.values()) record.source.close();
  eventSources.clear();
}

function closeJobEventSource(jobId: string) {
  const record = eventSources.get(jobId);
  if (!record) return;
  record.source.close();
  eventSources.delete(jobId);
}

function resetProjectJobs(nextProjectId = "") {
  projectLoadSequence += 1;
  activeProjectId = nextProjectId;
  closeAllEventSources();
  setSnapshot({
    jobs: new Map(),
    recentIds: [],
    loadingProjectId: "",
    loadedProjectId: "",
    loadRevision: 0,
    loadError: null,
  });
}

async function refreshJob(jobId: string): Promise<JobDetail> {
  const job = await api.getJob(jobId);
  if (storeJob(job)) reconcileJobSubscription(job);
  return job;
}

function refreshSubscribedJob(
  jobId: string,
  record: EventSourceRecord,
): Promise<void> {
  if (record.refreshPromise) return record.refreshPromise;
  record.refreshPromise = (async () => {
    try {
      const job = await api.getJob(jobId);
      if (eventSources.get(jobId) !== record) return;
      const refreshed = record.terminalStatus
        ? { ...job, status: record.terminalStatus }
        : job;
      if (!storeJob(refreshed)) return;
      reconcileJobSubscription(refreshed, false);
    } catch {
      // SSE refresh is best-effort; failures must not become unhandled rejections.
    } finally {
      record.refreshPromise = null;
      if (record.terminal && eventSources.get(jobId) === record) {
        eventSources.delete(jobId);
      }
    }
  })();
  return record.refreshPromise;
}

function openEventSource(jobId: string): { source: EventSource; cleanup: () => void } {
  eventSources.get(jobId)?.source.close();
  const source = api.subscribeJobEvents(jobId);
  const record: EventSourceRecord = {
    source,
    refreshPromise: null,
    terminal: false,
    terminalStatus: null,
  };
  eventSources.set(jobId, record);

  const refresh = () => {
    void refreshSubscribedJob(jobId, record);
    void refreshWorkspaceSnapshot();
  };
  for (const eventName of SSE_EVENT_NAMES) {
    if (eventName === "terminal") {
      source.addEventListener(eventName, (event) => {
        if (eventSources.get(jobId) !== record) return;
        record.terminal = true;
        source.close();
        let terminalStatus: EventSourceRecord["terminalStatus"] = null;
        try {
          const parsed = JSON.parse((event as MessageEvent).data) as {
            status?: unknown;
          };
          if (
            parsed.status === "completed" ||
            parsed.status === "failed" ||
            parsed.status === "cancelled"
          ) {
            terminalStatus = parsed.status;
          }
        } catch {
          // A malformed terminal payload still closes and falls back to in-flight detail.
        }
        if (terminalStatus) {
          record.terminalStatus = terminalStatus;
          const existing = snapshot.jobs.get(jobId);
          if (existing) storeJob({ ...existing, status: terminalStatus });
        }
        if (!record.refreshPromise) {
          if (eventSources.get(jobId) === record) eventSources.delete(jobId);
        }
      });
    } else {
      source.addEventListener(eventName, refresh);
    }
  }
  source.onmessage = refresh;

  return {
    source,
    cleanup: () => {
      source.close();
      if (eventSources.get(jobId) === record) eventSources.delete(jobId);
    },
  };
}

function reconcileJobSubscription(job: JobDetail, replaceTerminal = true) {
  if (job.project_id !== activeProjectId) return;
  const existing = eventSources.get(job.id);
  if (ACTIVE_STATUSES.has(job.status)) {
    if (existing && !existing.terminal) return;
    if (existing?.terminal && !replaceTerminal) return;
    if (existing) closeJobEventSource(job.id);
    openEventSource(job.id);
    return;
  }
  closeJobEventSource(job.id);
}

async function createJob(data: JobCreateRequest): Promise<JobDetail> {
  const requestGeneration = projectLoadSequence;
  const requestProjectId = activeProjectId;
  const job = await api.createJob(data);
  if (
    requestGeneration !== projectLoadSequence
    || activeProjectId !== requestProjectId
    || data.project_id !== requestProjectId
    || job.project_id !== requestProjectId
    || job.project_id !== data.project_id
  ) {
    return job;
  }
  const jobs = new Map(snapshot.jobs);
  jobs.set(job.id, job);
  setSnapshot({
    jobs,
    recentIds: [job.id, ...snapshot.recentIds.filter((id) => id !== job.id)].slice(0, 20),
  });
  if (job.project_id === activeProjectId) reconcileJobSubscription(job);
  return job;
}

async function loadProjectJobs(projectId: string): Promise<JobDetail[]> {
  const requestToken = ++projectLoadSequence;
  activeProjectId = projectId;
  closeAllEventSources();
  setSnapshot({ loadingProjectId: projectId, loadError: null });
  let details: JobDetail[];
  try {
    const response = await api.listJobs(projectId);
    details = await Promise.all(response.items.map((item) => api.getJob(item.id)));
  } catch (error) {
    if (requestToken === projectLoadSequence && activeProjectId === projectId) {
      setSnapshot({ loadingProjectId: "", loadError: error });
    }
    throw error;
  }
  if (requestToken !== projectLoadSequence || activeProjectId !== projectId) {
    return details;
  }
  setSnapshot({
    jobs: new Map(details.map((job) => [job.id, job])),
    recentIds: details.map((job) => job.id),
    loadingProjectId: "",
    loadedProjectId: projectId,
    loadRevision: snapshot.loadRevision + 1,
    loadError: null,
  });
  return details;
}

async function retryProjectJobs(): Promise<JobDetail[]> {
  if (!activeProjectId) return [];
  return loadProjectJobs(activeProjectId);
}

function subscribeSSE(jobId: string): () => void {
  const knownJob = snapshot.jobs.get(jobId);
  if (!knownJob || !ACTIVE_STATUSES.has(knownJob.status)) return () => undefined;
  return openEventSource(jobId).cleanup;
}

function subscribeActiveJobs(): () => void {
  closeAllEventSources();
  const opened = snapshot.recentIds
    .map((id) => snapshot.jobs.get(id))
    .filter((job): job is JobDetail => Boolean(
      job
      && job.project_id === activeProjectId
      && ACTIVE_STATUSES.has(job.status),
    ))
    .map((job) => openEventSource(job.id));

  return () => {
    for (const { cleanup } of opened) cleanup();
  };
}

async function updateJob(
  operation: () => Promise<JobDetail>,
): Promise<JobDetail> {
  const job = await operation();
  if (storeJob(job)) reconcileJobSubscription(job);
  return job;
}

const actions = {
  createJob,
  refreshJob,
  loadProjectJobs,
  retryProjectJobs,
  resetProjectJobs,
  subscribeSSE,
  subscribeActiveJobs,
  pauseJob: (jobId: string) => updateJob(() => api.pauseJob(jobId)),
  resumeJob: (jobId: string) => updateJob(() => api.resumeJob(jobId)),
  retryJob: (jobId: string, stepId?: string) =>
    updateJob(() => api.retryJob(jobId, { step_id: stepId })),
  cancelJob: (jobId: string) => updateJob(() => api.cancelJob(jobId)),
  reviewJob: (
    jobId: string,
    action: ReviewRequest["action"],
    comment?: string,
  ) => updateJob(() => api.reviewJob(jobId, { action, comment })),
};

export function useJobStore() {
  const current = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  return { ...current, ...actions };
}

export function jobStoreActions() {
  return {
    ...actions,
    getJob: (jobId: string) => snapshot.jobs.get(jobId),
    listJobs: () =>
      snapshot.recentIds
        .map((id) => snapshot.jobs.get(id))
        .filter((job): job is JobDetail => Boolean(job)),
    recentIds: () => [...snapshot.recentIds],
    loadState: () => ({
      loadingProjectId: snapshot.loadingProjectId,
      loadError: snapshot.loadError,
    }),
  };
}

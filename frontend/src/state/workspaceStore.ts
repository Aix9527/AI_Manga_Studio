import { create } from "zustand";

import { userMessage } from "@/api/client";
import { workspaceApi } from "@/api/workspace";
import type {
  StageAutomation,
  StageKey,
  WorkspaceSnapshot,
} from "@/workbench/types";

export type WorkbenchModule =
  | "总览"
  | "故事"
  | "角色"
  | "分镜"
  | "关键帧"
  | "视频"
  | "音频"
  | "合成"
  | "导出";

interface SelectedObject {
  type: string;
  id: string;
}

interface WorkspaceStore {
  projectId: string;
  snapshot: WorkspaceSnapshot | null;
  activeModule: WorkbenchModule;
  selectedObject: SelectedObject | null;
  loading: boolean;
  error: string | null;
  loadWorkspace: (projectId: string) => Promise<void>;
  refreshSnapshot: () => Promise<void>;
  startAutoRefresh: () => void;
  stopAutoRefresh: () => void;
  setStageAutomation: (
    stageKey: StageKey,
    patch: Partial<Omit<StageAutomation, "stage_key">>,
  ) => Promise<void>;
  setActiveModule: (module: WorkbenchModule) => void;
  selectObject: (value: SelectedObject | null) => void;
  clearError: () => void;
}

let loadSequence = 0;
let workspaceGeneration = 0;
let refreshInFlight = false;
let autoRefreshTimer: ReturnType<typeof setInterval> | null = null;

const AUTO_REFRESH_INTERVAL_MS = 3000;

interface PendingStageMutation {
  patch: Partial<Omit<StageAutomation, "stage_key">>;
  resolve: () => void;
  reject: (error: unknown) => void;
}

interface StageMutationQueue {
  projectId: string;
  generation: number;
  stageKey: StageKey;
  confirmed: StageAutomation;
  pending: PendingStageMutation[];
  running: boolean;
}

const stageMutationQueues = new Map<StageKey, StageMutationQueue>();

function optimisticAutomation(queue: StageMutationQueue): StageAutomation {
  return queue.pending.reduce<StageAutomation>(
    (value, mutation) => ({
      ...value,
      ...mutation.patch,
      stage_key: queue.stageKey,
    }),
    queue.confirmed,
  );
}

function isCurrentQueue(queue: StageMutationQueue): boolean {
  return (
    stageMutationQueues.get(queue.stageKey) === queue &&
    workspaceGeneration === queue.generation &&
    useWorkspaceStore.getState().projectId === queue.projectId
  );
}

function renderQueue(queue: StageMutationQueue, error: string | null) {
  if (!isCurrentQueue(queue)) return;
  const snapshot = useWorkspaceStore.getState().snapshot;
  if (!snapshot) return;
  const automation = optimisticAutomation(queue);
  useWorkspaceStore.setState({
    error,
    snapshot: {
      ...snapshot,
      stages: snapshot.stages.map((stage) =>
        stage.stage_key === queue.stageKey
          ? { ...stage, automation }
          : stage,
      ),
    },
  });
}

/**
 * Apply a freshly-fetched snapshot while preserving any pending optimistic
 * stage-automation mutations, so in-flight user edits are not lost when the
 * snapshot is refreshed during production. Only the `snapshot` slice is
 * touched; the loading/error state established by loadWorkspace is left intact.
 */
function applyRefreshedSnapshot(nextSnapshot: WorkspaceSnapshot) {
  let stages = nextSnapshot.stages;
  if (stageMutationQueues.size > 0) {
    stages = stages.map((stage) => {
      const queue = stageMutationQueues.get(stage.stage_key);
      if (queue && isCurrentQueue(queue)) {
        return { ...stage, automation: optimisticAutomation(queue) };
      }
      return stage;
    });
  }
  useWorkspaceStore.setState({
    snapshot: { ...nextSnapshot, stages },
  });
}

function hasActiveJobs(snapshot: WorkspaceSnapshot | null): boolean {
  return Boolean(snapshot && snapshot.active_jobs > 0);
}

/**
 * Start or stop background snapshot polling based on whether there are active
 * jobs in the latest snapshot. Self-regulating: each polled refresh re-runs
 * this reconciliation, so polling automatically stops once all jobs complete.
 */
function reconcileAutoRefresh(snapshot: WorkspaceSnapshot | null) {
  if (hasActiveJobs(snapshot)) {
    startAutoRefreshTimer();
  } else {
    stopAutoRefreshTimer();
  }
}

function startAutoRefreshTimer() {
  if (autoRefreshTimer) return;
  autoRefreshTimer = setInterval(() => {
    void useWorkspaceStore.getState().refreshSnapshot();
  }, AUTO_REFRESH_INTERVAL_MS);
}

function stopAutoRefreshTimer() {
  if (!autoRefreshTimer) return;
  clearInterval(autoRefreshTimer);
  autoRefreshTimer = null;
}

async function drainStageQueue(queue: StageMutationQueue) {
  if (queue.running) return;
  queue.running = true;
  while (queue.pending.length > 0) {
    const mutation = queue.pending[0];
    const requestValue: StageAutomation = {
      ...queue.confirmed,
      ...mutation.patch,
      stage_key: queue.stageKey,
    };
    try {
      queue.confirmed = await workspaceApi.updateStageAutomation(
        queue.projectId,
        queue.stageKey,
        requestValue,
      );
      queue.pending.shift();
      renderQueue(queue, null);
      mutation.resolve();
    } catch (error) {
      queue.pending.shift();
      renderQueue(queue, "保存自动生产设置失败，请重试");
      mutation.reject(error);
    }
  }
  queue.running = false;
  if (stageMutationQueues.get(queue.stageKey) === queue) {
    stageMutationQueues.delete(queue.stageKey);
  }
}

function enqueueStageMutation(
  stageKey: StageKey,
  patch: Partial<Omit<StageAutomation, "stage_key">>,
): Promise<void> {
  const state = useWorkspaceStore.getState();
  const stage = state.snapshot?.stages.find((candidate) => candidate.stage_key === stageKey);
  if (!state.snapshot || !stage) return Promise.resolve();

  let queue = stageMutationQueues.get(stageKey);
  if (
    !queue ||
    queue.projectId !== state.projectId ||
    queue.generation !== workspaceGeneration
  ) {
    queue = {
      projectId: state.projectId,
      generation: workspaceGeneration,
      stageKey,
      confirmed: stage.automation,
      pending: [],
      running: false,
    };
    stageMutationQueues.set(stageKey, queue);
  }

  const result = new Promise<void>((resolve, reject) => {
    queue!.pending.push({ patch, resolve, reject });
  });
  renderQueue(queue, null);
  void drainStageQueue(queue);
  return result;
}

export const useWorkspaceStore = create<WorkspaceStore>((set, get) => ({
  projectId: "",
  snapshot: null,
  activeModule: "总览",
  selectedObject: null,
  loading: false,
  error: null,

  loadWorkspace: async (projectId) => {
    const requestToken = ++loadSequence;
    workspaceGeneration += 1;
    stageMutationQueues.clear();
    stopAutoRefreshTimer();
    set({ projectId, snapshot: null, loading: true, error: null });
    try {
      const nextSnapshot = await workspaceApi.getSnapshot(projectId);
      if (requestToken !== loadSequence || get().projectId !== projectId) return;
      set({ snapshot: nextSnapshot, loading: false, error: null });
      reconcileAutoRefresh(nextSnapshot);
    } catch (error) {
      if (requestToken !== loadSequence || get().projectId !== projectId) return;
      set({ loading: false, error: userMessage(error) });
    }
  },

  refreshSnapshot: async () => {
    const projectId = get().projectId;
    if (!projectId || refreshInFlight) return;
    const requestToken = loadSequence;
    refreshInFlight = true;
    try {
      const nextSnapshot = await workspaceApi.getSnapshot(projectId);
      if (requestToken !== loadSequence || get().projectId !== projectId) return;
      applyRefreshedSnapshot(nextSnapshot);
      reconcileAutoRefresh(nextSnapshot);
    } catch {
      // Best-effort refresh: never clobber the loading/error state established
      // by loadWorkspace. The next poll/SSE tick will retry.
    } finally {
      refreshInFlight = false;
    }
  },

  startAutoRefresh: () => startAutoRefreshTimer(),
  stopAutoRefresh: () => stopAutoRefreshTimer(),

  setStageAutomation: enqueueStageMutation,

  setActiveModule: (activeModule) => set({ activeModule }),
  selectObject: (selectedObject) => set({ selectedObject }),
  clearError: () => set({ error: null }),
}));

/**
 * Standalone entry point for refreshing the workspace snapshot, intended to be
 * called from jobStore when an SSE job event arrives. Safe to call when no
 * project is loaded; overlapping calls are coalesced via an in-flight guard so
 * bursty SSE traffic does not flood the API.
 */
export async function refreshWorkspaceSnapshot(): Promise<void> {
  if (!useWorkspaceStore.getState().projectId) return;
  await useWorkspaceStore.getState().refreshSnapshot();
}

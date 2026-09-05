import { create } from "zustand";

import { ApiError, userMessage } from "@/api/client";
import { timelineApi } from "@/api/timeline";
import type {
  TimelineDraft,
  TimelineExportResult,
  TimelineMutationResult,
  TimelineOperation,
  TimelineOutputProfile,
  TimelinePreflight,
  TimelineQcStatus,
  TimelineSnapshot,
} from "@/types/timeline";

const SAVE_DEBOUNCE_MS = 200;

interface PendingOperation {
  operation: TimelineOperation;
}

interface TimelineStore {
  projectId: string;
  timelineId: string;
  draft: TimelineDraft | null;
  preflight: TimelinePreflight | null;
  snapshots: TimelineSnapshot[];
  selectedSnapshotId: string | null;
  qcBySnapshot: Record<string, TimelineQcStatus>;
  exportBySnapshot: Record<string, TimelineExportResult>;
  loading: boolean;
  pendingSave: boolean;
  conflict: boolean;
  error: string | null;
  loadProject: (projectId: string) => Promise<void>;
  scheduleOperation: (operation: TimelineOperation) => void;
  flushPending: () => Promise<void>;
  commitCritical: (operation: TimelineOperation) => Promise<TimelineMutationResult | null>;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
  createSnapshot: () => Promise<TimelineSnapshot | null>;
  runQc: (snapshotId: string) => Promise<void>;
  exportSnapshot: (snapshotId: string, profile: TimelineOutputProfile) => Promise<TimelineExportResult | null>;
  selectSnapshot: (snapshotId: string) => void;
  clearConflict: () => void;
}

let loadGeneration = 0;
let saveTimer: ReturnType<typeof setTimeout> | null = null;
let pendingOperations: PendingOperation[] = [];
let flushPromise: Promise<void> | null = null;

function initialState() {
  return {
    projectId: "",
    timelineId: "",
    draft: null,
    preflight: null,
    snapshots: [] as TimelineSnapshot[],
    selectedSnapshotId: null as string | null,
    qcBySnapshot: {} as Record<string, TimelineQcStatus>,
    exportBySnapshot: {} as Record<string, TimelineExportResult>,
    loading: false,
    pendingSave: false,
    conflict: false,
    error: null as string | null,
  };
}

function isRevisionConflict(error: unknown): error is ApiError {
  if (!(error instanceof ApiError) || error.status !== 409) return false;
  const detail = error.detail;
  return Boolean(detail && typeof detail === "object" && "code" in detail && (detail as { code?: unknown }).code === "TIMELINE_REVISION_CONFLICT");
}

async function listSnapshotsOrEmpty(timelineId: string): Promise<TimelineSnapshot[]> {
  try {
    const snapshots = await Promise.resolve(timelineApi.listSnapshots(timelineId));
    return Array.isArray(snapshots) ? snapshots : [];
  } catch {
    return [];
  }
}

async function loadQcStatuses(snapshots: TimelineSnapshot[]): Promise<Record<string, TimelineQcStatus>> {
  const entries = await Promise.all(snapshots.map(async (snapshot) => {
    try {
      const status = await timelineApi.getQc(snapshot.id);
      return [snapshot.id, status] as const;
    } catch {
      return [snapshot.id, { snapshot_id: snapshot.id, effective_status: "not_run", attempts: [] } satisfies TimelineQcStatus] as const;
    }
  }));
  return Object.fromEntries(entries);
}

async function recoverRevisionConflict(timelineId: string) {
  const authoritative = await timelineApi.getDraft(timelineId);
  if (useTimelineStore.getState().timelineId !== timelineId) return;
  pendingOperations = [];
  useTimelineStore.setState({
    draft: authoritative,
    pendingSave: false,
    conflict: true,
    error: "时间线已更新，请基于最新版本重新执行该操作",
  });
}

async function flushPendingInternal(): Promise<void> {
  if (saveTimer) {
    clearTimeout(saveTimer);
    saveTimer = null;
  }
  if (flushPromise) return flushPromise;
  flushPromise = (async () => {
    while (pendingOperations.length > 0) {
      const state = useTimelineStore.getState();
      const timelineId = state.timelineId;
      const currentDraft = state.draft;
      if (!timelineId || !currentDraft) {
        pendingOperations = [];
        useTimelineStore.setState({ pendingSave: false });
        return;
      }
      const next = pendingOperations.shift()!;
      try {
        const result = await timelineApi.applyOperation(timelineId, {
          expected_revision: currentDraft.revision,
          operation: next.operation,
        });
        if (useTimelineStore.getState().timelineId !== timelineId) continue;
        useTimelineStore.setState({
          draft: result.draft,
          preflight: result.preflight,
          conflict: false,
          error: null,
        });
      } catch (error) {
        if (isRevisionConflict(error)) {
          await recoverRevisionConflict(timelineId);
          return;
        }
        pendingOperations = [];
        useTimelineStore.setState({ pendingSave: false, error: userMessage(error) });
        throw error;
      }
    }
    useTimelineStore.setState({ pendingSave: false });
  })().finally(() => {
    flushPromise = null;
  });
  return flushPromise;
}

export const useTimelineStore = create<TimelineStore>((set, get) => ({
  ...initialState(),

  loadProject: async (projectId) => {
    if (get().timelineId && get().projectId && get().projectId !== projectId) {
      await flushPendingInternal();
    }
    const generation = ++loadGeneration;
    set({ ...initialState(), projectId, loading: true });
    try {
      let summary;
      try {
        summary = await timelineApi.getProjectTimeline(projectId);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          const created = await timelineApi.initialize(projectId);
          if (generation !== loadGeneration || get().projectId !== projectId) return;
          const snapshots = await listSnapshotsOrEmpty(created.timeline_id);
          const qcBySnapshot = await loadQcStatuses(snapshots);
          if (generation !== loadGeneration || get().projectId !== projectId) return;
          set({
            timelineId: created.timeline_id,
            draft: created,
            snapshots,
            selectedSnapshotId: snapshots.length ? snapshots[snapshots.length - 1].id : null,
            qcBySnapshot,
            loading: false,
            error: null,
          });
          return;
        }
        throw error;
      }
      if (generation !== loadGeneration || get().projectId !== projectId) return;
      const nextDraft = await timelineApi.getDraft(summary.timeline_id);
      if (generation !== loadGeneration || get().projectId !== projectId) return;
      const snapshots = await listSnapshotsOrEmpty(summary.timeline_id);
      const qcBySnapshot = await loadQcStatuses(snapshots);
      if (generation !== loadGeneration || get().projectId !== projectId) return;
      set({
        timelineId: summary.timeline_id,
        draft: nextDraft,
        snapshots,
        selectedSnapshotId: snapshots.length ? snapshots[snapshots.length - 1].id : null,
        qcBySnapshot,
        loading: false,
        error: null,
      });
    } catch (error) {
      if (generation !== loadGeneration || get().projectId !== projectId) return;
      set({ loading: false, error: userMessage(error) });
    }
  },

  scheduleOperation: (operation) => {
    if (operation.type === "MOVE_CLIP") {
      const previous = pendingOperations[pendingOperations.length - 1];
      if (previous?.operation.type === "MOVE_CLIP" && previous.operation.clip_id === operation.clip_id) {
        pendingOperations[pendingOperations.length - 1] = { operation };
      } else {
        pendingOperations.push({ operation });
      }
    } else {
      pendingOperations.push({ operation });
    }
    set({ pendingSave: true, conflict: false });
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      void flushPendingInternal().catch(() => undefined);
    }, SAVE_DEBOUNCE_MS);
  },

  flushPending: flushPendingInternal,

  commitCritical: async (operation) => {
    await flushPendingInternal();
    const state = get();
    if (!state.timelineId || !state.draft) return null;
    try {
      const result = await timelineApi.applyOperation(state.timelineId, {
        expected_revision: state.draft.revision,
        operation,
      });
      if (get().timelineId === state.timelineId) {
        set({ draft: result.draft, preflight: result.preflight, conflict: false, error: null });
      }
      return result;
    } catch (error) {
      if (isRevisionConflict(error)) {
        await recoverRevisionConflict(state.timelineId);
        return null;
      }
      set({ error: userMessage(error) });
      throw error;
    }
  },

  undo: async () => {
    await flushPendingInternal();
    const state = get();
    if (!state.timelineId || !state.draft) return;
    const result = await timelineApi.undo(state.timelineId, state.draft.revision);
    if (get().timelineId === state.timelineId) set({ draft: result.draft, preflight: result.preflight, conflict: false });
  },

  redo: async () => {
    await flushPendingInternal();
    const state = get();
    if (!state.timelineId || !state.draft) return;
    const result = await timelineApi.redo(state.timelineId, state.draft.revision);
    if (get().timelineId === state.timelineId) set({ draft: result.draft, preflight: result.preflight, conflict: false });
  },

  createSnapshot: async () => {
    await flushPendingInternal();
    const timelineId = get().timelineId;
    if (!timelineId) return null;
    const snapshot = await timelineApi.createSnapshot(timelineId);
    if (get().timelineId === timelineId) {
      set((state) => ({
        snapshots: [...state.snapshots.filter((item) => item.id !== snapshot.id), snapshot],
        selectedSnapshotId: snapshot.id,
        qcBySnapshot: {
          ...state.qcBySnapshot,
          [snapshot.id]: { snapshot_id: snapshot.id, effective_status: "not_run", attempts: [] },
        },
      }));
    }
    return snapshot;
  },

  runQc: async (snapshotId) => {
    await flushPendingInternal();
    await timelineApi.runQc(snapshotId);
    const status = await timelineApi.getQc(snapshotId);
    set((state) => ({ qcBySnapshot: { ...state.qcBySnapshot, [snapshotId]: status } }));
  },

  exportSnapshot: async (snapshotId, profile) => {
    await flushPendingInternal();
    const result = await timelineApi.exportSnapshot(snapshotId, profile);
    set((state) => ({ exportBySnapshot: { ...state.exportBySnapshot, [snapshotId]: result } }));
    return result;
  },

  selectSnapshot: (snapshotId) => set({ selectedSnapshotId: snapshotId }),
  clearConflict: () => set({ conflict: false, error: null }),
}));

export function resetTimelineStoreForTests(): void {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = null;
  pendingOperations = [];
  flushPromise = null;
  loadGeneration += 1;
  useTimelineStore.setState(initialState());
}

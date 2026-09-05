import { request } from "@/api/client";
import type {
  TimelineDraft,
  TimelineExportResult,
  TimelineMutationResult,
  TimelineOperationRequest,
  TimelineOutputProfile,
  TimelineQcRun,
  TimelineQcStatus,
  TimelineSnapshot,
  TimelineSummary,
  WaveformEnvelope,
} from "@/types/timeline";

const projectPath = (projectId: string) => `/projects/${encodeURIComponent(projectId)}/timeline`;
const timelinePath = (timelineId: string) => `/timelines/${encodeURIComponent(timelineId)}`;
const snapshotPath = (snapshotId: string) => `/timeline-snapshots/${encodeURIComponent(snapshotId)}`;

export const timelineApi = {
  getProjectTimeline: (projectId: string): Promise<TimelineSummary> => request<TimelineSummary>(projectPath(projectId)),
  initialize: (projectId: string): Promise<TimelineDraft> => request<TimelineDraft>(`${projectPath(projectId)}/initialize`, { method: "POST" }),
  getDraft: (timelineId: string): Promise<TimelineDraft> => request<TimelineDraft>(`${timelinePath(timelineId)}/draft`),
  applyOperation: (timelineId: string, value: TimelineOperationRequest): Promise<TimelineMutationResult> =>
    request<TimelineMutationResult>(`${timelinePath(timelineId)}/operations`, {
      method: "POST",
      body: JSON.stringify(value),
    }),
  undo: (timelineId: string, expectedRevision: number): Promise<TimelineMutationResult> =>
    request<TimelineMutationResult>(`${timelinePath(timelineId)}/undo`, {
      method: "POST",
      body: JSON.stringify({ expected_revision: expectedRevision }),
    }),
  redo: (timelineId: string, expectedRevision: number): Promise<TimelineMutationResult> =>
    request<TimelineMutationResult>(`${timelinePath(timelineId)}/redo`, {
      method: "POST",
      body: JSON.stringify({ expected_revision: expectedRevision }),
    }),
  createSnapshot: (timelineId: string): Promise<TimelineSnapshot> =>
    request<TimelineSnapshot>(`${timelinePath(timelineId)}/snapshots`, { method: "POST" }),
  listSnapshots: (timelineId: string): Promise<TimelineSnapshot[]> =>
    request<TimelineSnapshot[]>(`${timelinePath(timelineId)}/snapshots`),
  runQc: (snapshotId: string): Promise<TimelineQcRun> =>
    request<TimelineQcRun>(`${snapshotPath(snapshotId)}/qc`, { method: "POST" }),
  getQc: (snapshotId: string): Promise<TimelineQcStatus> =>
    request<TimelineQcStatus>(`${snapshotPath(snapshotId)}/qc`),
  exportSnapshot: (snapshotId: string, outputProfile: TimelineOutputProfile): Promise<TimelineExportResult> =>
    request<TimelineExportResult>(`${snapshotPath(snapshotId)}/export`, {
      method: "POST",
      body: JSON.stringify({ output_profile: outputProfile }),
    }),
  getWaveform: (timelineId: string, artifactId: number, bins = 512): Promise<WaveformEnvelope> =>
    request<WaveformEnvelope>(`${timelinePath(timelineId)}/artifacts/${artifactId}/waveform?bins=${bins}`),
};

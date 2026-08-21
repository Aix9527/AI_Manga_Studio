// History management API client

import { request } from "@/api/client";

export interface HistoryStats {
  total_jobs: number;
  total_artifacts: number;
  total_steps: number;
  total_projects: number;
  storage_bytes: number;
  db_path: string;
}

export interface ClearHistoryResponse {
  project_id: string;
  cleared_jobs: number;
  cleared_artifacts: number;
  cleared_steps: number;
  cleared_files: number;
  freed_bytes: number;
  message: string;
}

export const historyApi = {
  getStats: () => request<HistoryStats>("/history/stats"),

  clearProject: (projectId: string, clearOutputs = true) =>
    request<ClearHistoryResponse>(
      `/history/${encodeURIComponent(projectId)}?clear_outputs=${clearOutputs}`,
      { method: "DELETE" },
    ),

  clearAll: (clearOutputs = true) =>
    request<ClearHistoryResponse>(
      `/history/all?clear_outputs=${clearOutputs}`,
      { method: "DELETE" },
    ),
};

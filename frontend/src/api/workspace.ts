import { request } from "@/api/client";
import type { JobDetail } from "@/types/jobs";
import type {
  AssetFilters,
  ProjectAsset,
  StageAutomation,
  StageKey,
  WorkspaceSnapshot,
} from "@/workbench/types";

export const workspaceApi = {
  getSnapshot: (projectId: string) =>
    request<WorkspaceSnapshot>(`/workspace/${encodeURIComponent(projectId)}`),

  updateStageAutomation: (
    projectId: string,
    stageKey: StageKey,
    value: StageAutomation,
  ) =>
    request<StageAutomation>(
      `/workspace/${encodeURIComponent(projectId)}/automation/${stageKey}`,
      {
        method: "PUT",
        body: JSON.stringify(value),
      },
    ),

  listAssets: (projectId: string, filters: AssetFilters = {}) => {
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
    const suffix = query.size > 0 ? `?${query.toString()}` : "";
    return request<ProjectAsset[]>(
      `/workspace/${encodeURIComponent(projectId)}/assets${suffix}`,
    );
  },

  regenerateAsset: (projectId: string, assetId: number) =>
    request<JobDetail>(
      `/workspace/${encodeURIComponent(projectId)}/assets/${assetId}/regenerate`,
      { method: "POST" },
    ),
};

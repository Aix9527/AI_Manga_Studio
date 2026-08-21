import { request } from "@/api/client";

export interface ShotInfo {
  shot_id: string;
  shot_number: number;
  description: string;
  narration: string;
  duration: number;
  camera: string;
  positive_prompt: string;
  negative_prompt: string;
  seed: number;
  transition: string;
  has_keyframe: boolean;
  keyframe_url: string;
  has_ai_video: boolean;
  ai_video_url: string;
  ai_video_status: string;
}

export interface CreatorProject {
  project_id: string;
  title: string;
  total_shots: number;
  shots: ShotInfo[];
  settings: Record<string, unknown>;
}

export interface ComfyUIStatus {
  available: boolean;
  url: string;
  message?: string;
  system?: Record<string, unknown>;
}

export interface RegenerateImageParams {
  prompt?: string;
  negative_prompt?: string;
  seed?: number;
  width?: number;
  height?: number;
}

export interface GenerateVideoParams {
  motion_bucket_id?: number;
  motion_level?: number;
  frames?: number;
  fps?: number;
  use_ai_video?: boolean;
}

export interface CreatorSettings {
  motion_bucket_id: number;
  motion_level: number;
  video_frames: number;
  ai_video: boolean;
  character_consistency: boolean;
  provider: string;
}

export const creatorApi = {
  getProject: (projectId: string) =>
    request<CreatorProject>(`/creator/${encodeURIComponent(projectId)}`),

  regenerateImage: (projectId: string, shotId: string, params: RegenerateImageParams) =>
    request<{ status: string; shot_id: string; message: string }>(
      `/creator/${encodeURIComponent(projectId)}/shots/${shotId}/regenerate-image`,
      { method: "POST", body: JSON.stringify(params) },
    ),

  generateVideo: (projectId: string, shotId: string, params: GenerateVideoParams) =>
    request<{ status: string; shot_id: string; message: string; method?: string; file_size?: number }>(
      `/creator/${encodeURIComponent(projectId)}/shots/${shotId}/generate-video`,
      { method: "POST", body: JSON.stringify(params) },
    ),

  generateAllVideos: (projectId: string) =>
    request<{
      status: string;
      project_id: string;
      total: number;
      succeeded: number;
      failed: number;
      skipped: { shot_id: string; reason: string }[];
      results: { shot_id: string; status: string; message: string }[];
      message: string;
    }>(
      `/creator/${encodeURIComponent(projectId)}/generate-all-videos`,
      { method: "POST", body: JSON.stringify({}) },
    ),

  updateSettings: (projectId: string, settings: CreatorSettings) =>
    request<{ status: string; settings: Record<string, unknown> }>(
      `/creator/${encodeURIComponent(projectId)}/settings`,
      { method: "PUT", body: JSON.stringify(settings) },
    ),

  getComfyUIStatus: (projectId: string) =>
    request<ComfyUIStatus>(`/creator/${encodeURIComponent(projectId)}/comfyui-status`),
};

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { userMessage } from "@/api/client";
import { creatorApi, type ShotInfo, type ComfyUIStatus, type CreatorSettings } from "@/api/creator";
import { workspaceApi } from "@/api/workspace";
import { useWorkspaceStore } from "@/state/workspaceStore";
import type { ProjectAsset } from "@/workbench/types";

const VIDEO_STATUS_LABELS: Record<string, string> = {
  pending: "待生成",
  ready: "可生成",
  completed: "已完成",
};

function motionBucketToLabel(bucket: number): string {
  if (bucket <= 40) return "静止";
  if (bucket <= 80) return "微动";
  if (bucket <= 127) return "标准";
  if (bucket <= 180) return "动感";
  return "激烈";
}

const MOTION_LEVELS: { level: number; label: string; hint: string }[] = [
  { level: 0, label: "0 静态", hint: "低 denoise，适合空镜/远景" },
  { level: 1, label: "1 微动", hint: "呼吸/发丝级细微动作" },
  { level: 2, label: "2 标准", hint: "常规肢体动作与表情" },
  { level: 3, label: "3 动感", hint: "行走/挥手等明显动作" },
  { level: 4, label: "4 激烈", hint: "打斗/奔跑等强动作" },
];

function motionLevelToHint(level: number): string {
  return MOTION_LEVELS.find(m => m.level === level)?.hint ?? "常规肢体动作与表情";
}

interface ShotCardProps {
  shot: ShotInfo;
  projectId: string;
  assetMap: Map<string, ProjectAsset>;
  onRegenerate: (shot: ShotInfo) => void;
  onGenerateVideo: (shot: ShotInfo) => void;
  busy: boolean;
}

function ShotCard({ shot, projectId, assetMap, onRegenerate, onGenerateVideo, busy }: ShotCardProps) {
  const imageAsset = assetMap.get(`image-${shot.shot_id}`);
  const videoAsset = assetMap.get(`video-${shot.shot_id}`);

  const imageUrl = imageAsset?.media_url
    ? `/api/workspace/${encodeURIComponent(projectId)}/assets/${imageAsset.id}/media`
    : "";
  // Use workspace asset URL if available, otherwise fall back to direct file endpoint
  const videoUrl = videoAsset?.media_url
    ? `/api/workspace/${encodeURIComponent(projectId)}/assets/${videoAsset.id}/media`
    : shot.has_ai_video
      ? `/api/creator/${encodeURIComponent(projectId)}/shots/${shot.shot_id}/video-file`
      : "";

  return (
    <article className="creator-shot-card" data-status={shot.ai_video_status}>
      <header className="creator-shot-card__header">
        <span className="creator-shot-card__number">#{shot.shot_number}</span>
        <span className="creator-shot-card__id">{shot.shot_id}</span>
        <span className={`creator-shot-card__badge creator-shot-card__badge--${shot.ai_video_status}`}>
          {VIDEO_STATUS_LABELS[shot.ai_video_status] ?? shot.ai_video_status}
        </span>
      </header>

      <div className="creator-shot-card__previews">
        <div className="creator-shot-card__preview creator-shot-card__preview--image">
          {imageUrl ? (
            <img src={imageUrl} alt={shot.shot_id} loading="lazy" />
          ) : (
            <div className="creator-shot-card__placeholder">
              <span>暂无关键帧</span>
            </div>
          )}
          <span className="creator-shot-card__preview-label">关键帧</span>
        </div>
        <div className="creator-shot-card__preview creator-shot-card__preview--video">
          {videoUrl ? (
            <video src={videoUrl} controls preload="metadata" />
          ) : (
            <div className="creator-shot-card__placeholder">
              <span>暂无AI视频</span>
            </div>
          )}
          <span className="creator-shot-card__preview-label">AI视频</span>
        </div>
      </div>

      <div className="creator-shot-card__info">
        <p className="creator-shot-card__desc">{shot.description || "无描述"}</p>
        <p className="creator-shot-card__narration">{shot.narration || "无旁白"}</p>
        <dl className="creator-shot-card__meta">
          <div><dt>镜头</dt><dd>{shot.camera || "—"}</dd></div>
          <div><dt>时长</dt><dd>{shot.duration}s</dd></div>
          <div><dt>转场</dt><dd>{shot.transition}</dd></div>
          <div><dt>种子</dt><dd>{shot.seed}</dd></div>
        </dl>
      </div>

      <details className="creator-shot-card__prompt">
        <summary>提示词</summary>
        <div className="creator-shot-card__prompt-body">
          <p className="creator-shot-card__prompt-positive">{shot.positive_prompt}</p>
          {shot.negative_prompt ? (
            <p className="creator-shot-card__prompt-negative">{shot.negative_prompt}</p>
          ) : null}
        </div>
      </details>

      <div className="creator-shot-card__actions">
        <button
          type="button"
          className="creator-btn creator-btn--secondary"
          disabled={busy}
          onClick={() => onRegenerate(shot)}
        >
          重新生成关键帧
        </button>
        <button
          type="button"
          className="creator-btn creator-btn--primary"
          disabled={busy || !shot.has_keyframe}
          onClick={() => onGenerateVideo(shot)}
        >
          {busy ? "生成中..." : "生成AI视频"}
        </button>
      </div>
    </article>
  );
}

const DEFAULT_SETTINGS: CreatorSettings = {
  motion_bucket_id: 127,
  motion_level: 1,
  video_frames: 33,
  ai_video: false,
  character_consistency: false,
  provider: "ltx23",
};

const AICreatorStudio: React.FC = () => {
  const snapshot = useWorkspaceStore((state) => state.snapshot);
  const workspaceProjectId = useWorkspaceStore((state) => state.projectId);
  const projectId = snapshot?.project_id || workspaceProjectId || "default";

  const [shots, setShots] = useState<ShotInfo[]>([]);
  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const [comfyStatus, setComfyStatus] = useState<ComfyUIStatus | null>(null);
  const [settings, setSettings] = useState<CreatorSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyShot, setBusyShot] = useState<string | null>(null);
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchProgress, setBatchProgress] = useState<{ current: number; total: number } | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const loadSeq = useRef(0);

  const buildAssetMap = useCallback((assetList: ProjectAsset[]): Map<string, ProjectAsset> => {
    const map = new Map<string, ProjectAsset>();
    for (const a of assetList) {
      if (a.shot_id) {
        const key = `${a.kind}-${a.shot_id}`;
        const existing = map.get(key);
        if (!existing || (a.active && !existing.active) || a.id > existing.id) {
          map.set(key, a);
        }
      }
    }
    return map;
  }, []);

  useEffect(() => {
    const token = ++loadSeq.current;
    setLoading(true);
    setError(null);

    Promise.all([
      creatorApi.getProject(projectId),
      workspaceApi.listAssets(projectId, {}),
      creatorApi.getComfyUIStatus(projectId),
    ]).then(([project, assetList, comfy]) => {
      if (token !== loadSeq.current) return;
      setShots(project.shots);
      setAssets(assetList);
      setComfyStatus(comfy);

      const s = project.settings as Record<string, unknown>;
      setSettings({
        motion_bucket_id: typeof s?.motion_bucket_id === "number" ? s.motion_bucket_id : DEFAULT_SETTINGS.motion_bucket_id,
        motion_level: typeof s?.motion_level === "number" ? s.motion_level : DEFAULT_SETTINGS.motion_level,
        video_frames: typeof s?.video_frames === "number" ? s.video_frames : DEFAULT_SETTINGS.video_frames,
        ai_video: typeof s?.ai_video === "boolean" ? s.ai_video : DEFAULT_SETTINGS.ai_video,
        character_consistency: typeof s?.character_consistency === "boolean" ? s.character_consistency : DEFAULT_SETTINGS.character_consistency,
        provider: typeof s?.provider === "string" ? s.provider : DEFAULT_SETTINGS.provider,
      });
    }).catch((err: unknown) => {
      if (token !== loadSeq.current) return;
      setError(userMessage(err));
    }).finally(() => {
      if (token === loadSeq.current) setLoading(false);
    });
  }, [projectId, reloadToken]);

  const assetMap = buildAssetMap(assets);

  const handleRegenerate = useCallback(async (shot: ShotInfo) => {
    setBusyShot(shot.shot_id);
    setFeedback(null);
    try {
      const result = await creatorApi.regenerateImage(projectId, shot.shot_id, {
        prompt: shot.positive_prompt,
        negative_prompt: shot.negative_prompt,
        seed: shot.seed,
      });
      setFeedback(result.message);
    } catch (err: unknown) {
      setFeedback(userMessage(err));
    } finally {
      setBusyShot(null);
    }
  }, [projectId]);

  const handleGenerateVideo = useCallback(async (shot: ShotInfo) => {
    setBusyShot(shot.shot_id);
    setFeedback(null);
    try {
      const result = await creatorApi.generateVideo(projectId, shot.shot_id, {
        motion_bucket_id: settings.motion_bucket_id,
        motion_level: settings.motion_level,
        frames: settings.video_frames,
        fps: 24,
        use_ai_video: true,
      });
      setFeedback(result.message);
      // Reload to show the generated video
      setReloadToken(v => v + 1);
    } catch (err: unknown) {
      setFeedback(userMessage(err));
    } finally {
      setBusyShot(null);
    }
  }, [projectId, settings]);

  const handleGenerateAllVideos = useCallback(async () => {
    setBatchBusy(true);
    setFeedback(null);
    setBatchProgress(null);
    try {
      const result = await creatorApi.generateAllVideos(projectId);
      setFeedback(result.message);
      // Reload to show all generated videos
      setReloadToken(v => v + 1);
    } catch (err: unknown) {
      setFeedback(userMessage(err));
    } finally {
      setBatchBusy(false);
      setBatchProgress(null);
    }
  }, [projectId]);

  const handleSaveSettings = useCallback(async () => {
    setFeedback(null);
    try {
      await creatorApi.updateSettings(projectId, settings);
      setFeedback("设置已保存");
    } catch (err: unknown) {
      setFeedback(userMessage(err));
    }
  }, [projectId, settings]);

  const keyframeCount = shots.filter(s => s.has_keyframe).length;
  const videoCount = shots.filter(s => s.has_ai_video).length;
  const pendingCount = shots.filter(s => s.has_keyframe && !s.has_ai_video).length;

  return (
    <section className="workspace-page creator-page" aria-labelledby="creator-title">
      <header className="workspace-page__header">
        <div>
          <p className="workspace-eyebrow">AI 创意工坊</p>
          <h1 id="creator-title">AI Creator Studio</h1>
        </div>
        <div className="workspace-actions">
          <Link to="/director">返回导演台</Link>
          <button type="button" onClick={() => setReloadToken(v => v + 1)}>刷新</button>
        </div>
      </header>

      {error ? <p className="workspace-error" role="alert">{error}</p> : null}
      {feedback ? <p className="workspace-feedback" role="status">{feedback}</p> : null}

      <dl className="overview-metrics">
        <div><dt>分镜总数</dt><dd>{shots.length}</dd></div>
        <div><dt>已有关键帧</dt><dd>{keyframeCount}</dd></div>
        <div><dt>已有AI视频</dt><dd>{videoCount}</dd></div>
        <div>
          <dt>ComfyUI</dt>
          <dd className={comfyStatus?.available ? "creator-status--ok" : "creator-status--off"}>
            {comfyStatus?.available ? "在线" : "离线"}
          </dd>
        </div>
        <div>
          <dt>整体进度</dt>
          <dd>{snapshot ? `${Math.round(snapshot.progress * 100)}%` : "0%"}</dd>
        </div>
        <div>
          <dt>AI视频生成</dt>
          <dd>{settings.ai_video ? "已启用" : "未启用"}</dd>
        </div>
      </dl>

      <section className="workspace-panel creator-settings-panel">
        <h2>生成参数</h2>
        <div className="creator-settings-grid">
          <label>
            运动强度
            <select
              value={settings.motion_bucket_id}
              onChange={(e) => setSettings(s => ({ ...s, motion_bucket_id: Number(e.target.value) }))}
            >
              <option value={40}>静止 (40)</option>
              <option value={80}>微动 (80)</option>
              <option value={127}>标准 (127)</option>
              <option value={180}>动感 (180)</option>
              <option value={240}>激烈 (240)</option>
            </select>
            <span className="creator-settings-hint">{motionBucketToLabel(settings.motion_bucket_id)}</span>
          </label>
          <label>
            运动档位 (0-4)
            <select
              value={settings.motion_level}
              onChange={(e) => setSettings(s => ({ ...s, motion_level: Number(e.target.value) }))}
            >
              {MOTION_LEVELS.map(m => (
                <option key={m.level} value={m.level}>{m.label}</option>
              ))}
            </select>
            <span className="creator-settings-hint">{motionLevelToHint(settings.motion_level)}</span>
          </label>
          <label>
            视频帧数
            <select
              value={settings.video_frames}
              onChange={(e) => setSettings(s => ({ ...s, video_frames: Number(e.target.value) }))}
            >
              <option value={17}>17帧 (约0.7s)</option>
              <option value={33}>33帧 (约1.4s)</option>
              <option value={49}>49帧 (约2.0s)</option>
              <option value={81}>81帧 (约3.4s)</option>
            </select>
          </label>
          <label>
            AI视频生成
            <button
              type="button"
              role="switch"
              aria-checked={settings.ai_video}
              onClick={() => setSettings(s => ({ ...s, ai_video: !s.ai_video }))}
              className={settings.ai_video ? "creator-switch--on" : ""}
            >
              <span className="creator-switch-indicator" />
              <span>{settings.ai_video ? "已启用" : "未启用"}</span>
            </button>
          </label>
          <label>
            角色一致性
            <button
              type="button"
              role="switch"
              aria-checked={settings.character_consistency}
              onClick={() => setSettings(s => ({ ...s, character_consistency: !s.character_consistency }))}
              className={settings.character_consistency ? "creator-switch--on" : ""}
            >
              <span className="creator-switch-indicator" />
              <span>{settings.character_consistency ? "已启用" : "未启用"}</span>
            </button>
          </label>
          <label>
            生成引擎
            <select
              value={settings.provider}
              onChange={(e) => setSettings(s => ({ ...s, provider: e.target.value }))}
            >
              <option value="ltx23">LTX-23</option>
              <option value="wan22">Wan2.2</option>
              <option value="flux">FLUX</option>
            </select>
          </label>
          <div className="creator-settings-actions">
            <button type="button" className="creator-btn creator-btn--primary" onClick={handleSaveSettings}>
              保存设置
            </button>
          </div>
        </div>

        {/* One-click batch generation */}
        <div className="creator-batch-bar">
          <div className="creator-batch-info">
            <span className="creator-batch-stat">
              待生成: <strong>{pendingCount}</strong>
            </span>
            <span className="creator-batch-stat">
              已完成: <strong>{videoCount}</strong> / {keyframeCount}
            </span>
            {comfyStatus ? (
              <span className={`creator-batch-stat ${comfyStatus.available ? "creator-status--ok" : "creator-status--off"}`}>
                ComfyUI: {comfyStatus.available ? "在线" : "离线"}
                {!comfyStatus.available ? " (已禁用Ken Burns兜底)" : ""}
              </span>
            ) : null}
          </div>
          <button
            type="button"
            className="creator-btn creator-btn--primary creator-btn--batch"
            disabled={batchBusy || pendingCount === 0}
            onClick={handleGenerateAllVideos}
          >
            {batchBusy ? "正在批量生成..." : `一键生成全部AI视频 (${pendingCount})`}
          </button>
        </div>
      </section>

      {!comfyStatus?.available ? (
        <div className="creator-comfyui-warning">
          <strong>ComfyUI 未运行</strong>
          <p>AI 视频生成将失败（Ken Burns 定帧兜底已禁用）。请启动 ComfyUI (端口 8188) 后重试，才能产出真正的 AI 漫剧动态视频。</p>
        </div>
      ) : null}

      {loading ? <p className="workspace-feedback" role="status">正在加载分镜数据...</p> : null}

      {!loading && shots.length > 0 ? (
        <div className="creator-shot-grid">
          {shots.map(shot => (
            <ShotCard
              key={shot.shot_id}
              shot={shot}
              projectId={projectId}
              assetMap={assetMap}
              onRegenerate={handleRegenerate}
              onGenerateVideo={handleGenerateVideo}
              busy={busyShot === shot.shot_id}
            />
          ))}
        </div>
      ) : null}

      {!loading && shots.length === 0 && !error ? (
        <div className="workspace-empty-state">
          <strong>暂无分镜数据</strong>
          <p>请先在分镜导演台规划分镜，生成关键帧后将在此处进行AI视频创作。</p>
          <Link to="/director" className="workspace-primary-link">前往分镜导演台</Link>
        </div>
      ) : null}
    </section>
  );
};

export default AICreatorStudio;

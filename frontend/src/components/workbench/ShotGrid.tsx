import React from "react";

import type { SceneData } from "@/api/story";

const SHOT_TYPES: Record<string, string> = {
  wide: "远景",
  medium: "中景",
  "close-up": "特写",
  "extreme-close-up": "大特写",
  long: "全景",
  panorama: "横移全景",
};

const PRODUCTION_STATUS: Record<string, string> = {
  pending: "待生产",
  queued: "排队中",
  running: "生产中",
  ready: "已就绪",
  completed: "已完成",
  failed: "生产失败",
};

const QUALITY_STATUS: Record<string, string> = {
  unreviewed: "未质检",
  pending: "待质检",
  reviewing: "质检中",
  approved: "已通过",
  rejected: "未通过",
};

export function shotNumber(index: number): string {
  return String(index + 1).padStart(2, "0");
}

function validThumbnail(value: string): boolean {
  return /^(https?:|data:)/i.test(value);
}

interface ShotGridProps {
  scenes: SceneData[];
  selectedSceneId: string | null;
  selectedShotId: string | null;
  selectedShotIds: string[];
  onSelectScene: (sceneId: string) => void;
  onSelectShot: (shotId: string) => void;
  onToggleBatch: (shotId: string) => void;
}

const ShotGrid: React.FC<ShotGridProps> = ({
  scenes,
  selectedSceneId,
  selectedShotId,
  selectedShotIds,
  onSelectScene,
  onSelectShot,
  onToggleBatch,
}) => {
  const scene = scenes.find((candidate) => candidate.id === selectedSceneId) ?? scenes[0];

  if (!scene) return null;

  return (
    <section className="director-grid-panel" aria-labelledby="director-grid-heading">
      <div className="director-section-heading">
        <div>
          <h2 id="director-grid-heading">镜头网格</h2>
          <p>{scene.location || scene.description || `场景 ${scene.index + 1}`}</p>
        </div>
        <label className="director-scene-select">
          <span>场景</span>
          <select
            aria-label="选择场景"
            value={scene.id}
            onChange={(event) => onSelectScene(event.target.value)}
          >
            {scenes.map((candidate) => (
              <option key={candidate.id} value={candidate.id}>
                场景 {candidate.index + 1} · {candidate.location || candidate.description || "未命名场景"}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="director-shot-grid">
        {scene.shots.map((shot) => {
          const number = shotNumber(shot.index);
          const selected = selectedShotId === shot.id;
          const batchSelected = selectedShotIds.includes(shot.id);
          const characterCopy = shot.character_ids.length
            ? `${shot.character_ids.length} 个人物 · ${shot.character_ids.join("、")}`
            : "无人物";
          return (
            <article className="director-shot-card" key={shot.id} data-selected={selected}>
              <button
                type="button"
                className="director-shot-card__main"
                aria-label={`选择镜头 ${number}`}
                aria-pressed={selected}
                onClick={() => onSelectShot(shot.id)}
              >
                <span className="director-shot-card__media">
                  {validThumbnail(shot.thumbnail_url) ? (
                    <img src={shot.thumbnail_url} alt={`镜头 ${number} 缩略图`} />
                  ) : (
                    <span>尚未生成关键帧</span>
                  )}
                </span>
                <span className="director-shot-card__topline">
                  <strong>镜头 {number}</strong>
                  <span>{SHOT_TYPES[shot.shot_type] ?? "未知景别"}</span>
                  <span>{shot.duration} 秒</span>
                </span>
                <span className="director-shot-card__description">{shot.description || "暂无镜头描述"}</span>
                <span className="director-shot-card__meta">{characterCopy}</span>
                <span className="director-shot-card__statuses">
                  <span>{PRODUCTION_STATUS[shot.production_status] ?? "未知生产状态"}</span>
                  <span>{QUALITY_STATUS[shot.quality_status] ?? "未知质检状态"}</span>
                </span>
              </button>
              <label className="director-batch-check">
                <input
                  type="checkbox"
                  checked={batchSelected}
                  onChange={() => onToggleBatch(shot.id)}
                />
                <span>加入批量生成：镜头 {number}</span>
              </label>
            </article>
          );
        })}
      </div>
    </section>
  );
};

export default ShotGrid;

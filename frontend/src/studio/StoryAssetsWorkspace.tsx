import React, { useEffect, useMemo, useState } from "react";

import { userMessage } from "@/api/client";
import { workspaceApi } from "@/api/workspace";
import { useJobStore } from "@/state/jobStore";
import { useWorkspaceStore } from "@/state/workspaceStore";
import type { ProjectAsset } from "@/workbench/types";

const CATEGORIES = [
  { key: "character", label: "角色", aliases: ["character", "character_ref", "portrait"] },
  { key: "location", label: "场景", aliases: ["location", "scene", "environment", "background"] },
  { key: "prop", label: "道具", aliases: ["prop", "object"] },
  { key: "voice", label: "声音", aliases: ["voice", "audio", "speech"] },
  { key: "style", label: "风格", aliases: ["style", "reference", "keyframe", "image"] },
] as const;

type CategoryKey = (typeof CATEGORIES)[number]["key"];

function categoryFor(asset: ProjectAsset): CategoryKey {
  const kind = (asset.kind || "").toLowerCase();
  const matched = CATEGORIES.find((category) => category.aliases.some((alias) => kind.includes(alias)));
  return matched?.key ?? "style";
}

function assetTitle(asset: ProjectAsset): string {
  if (asset.shot_id) return asset.shot_id;
  if (asset.scene_id) return asset.scene_id;
  const filename = asset.path.split(/[\\/]/).pop();
  return filename || `${asset.kind} #${asset.id}`;
}

const StoryAssetsWorkspace: React.FC = () => {
  const snapshot = useWorkspaceStore((state) => state.snapshot);
  const projectId = snapshot?.project_id || useWorkspaceStore.getState().projectId || "default";
  const { jobs } = useJobStore();
  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const [category, setCategory] = useState<CategoryKey>("character");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    void workspaceApi.listAssets(projectId)
      .then((items) => {
        if (!alive) return;
        setAssets(items);
        setSelectedId(items[0]?.id ?? null);
      })
      .catch((reason) => alive && setError(userMessage(reason)))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [projectId]);

  const visible = useMemo(
    () => assets.filter((asset) => categoryFor(asset) === category),
    [assets, category],
  );
  const selected = assets.find((asset) => asset.id === selectedId) ?? null;
  const selectedJob = selected?.job_id ? jobs.get(selected.job_id) : undefined;
  const firstReviewStep = selectedJob?.steps.find((step) => step.status === "waiting_review");
  const canRegenerate = Boolean(
    selected?.active
      && selectedJob?.status === "waiting_review"
      && firstReviewStep?.id === selected.step_id,
  );

  const regenerateSelected = () => {
    if (!selected || !canRegenerate) return;
    void workspaceApi.regenerateAsset(projectId, selected.id);
  };

  return (
    <div className="studio-workspace studio-three-pane">
      <aside className="studio-panel studio-left-pane">
        <div className="studio-panel__header"><div><strong>故事结构</strong><span>Episode → Scene → Shot</span></div></div>
        <div className="inspector-section">
          <h3>{snapshot?.title || "当前项目"}</h3>
          <div className="story-list">
            <button type="button" className="is-active">第 1 集 · 当前制作</button>
            {snapshot?.stages.map((stage, index) => (
              <button key={stage.stage_key} type="button">
                {String(index + 1).padStart(2, "0")} · {stage.stage_key} · {Math.round(stage.progress * 100)}%
              </button>
            ))}
          </div>
        </div>
        <div className="inspector-section">
          <h3>生产原则</h3>
          <p className="subtle">角色、场景、道具、声音与风格作为项目级资产复用；镜头只引用资产，不重复创建孤立副本。</p>
        </div>
      </aside>

      <section className="studio-center-pane">
        <header className="studio-workspace__header">
          <div><h1>故事 · 资产台</h1><p>统一管理故事结构与可复用制作资产</p></div>
        </header>
        <section className="studio-panel">
          <div className="studio-panel__header">
            <div><strong>资产库</strong><span>{assets.length} 个本地资产</span></div>
          </div>
          <div className="inspector-section">
            <div className="asset-tabs" role="tablist" aria-label="资产类别">
              {CATEGORIES.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={`asset-tab${category === item.key ? " is-active" : ""}`}
                  onClick={() => setCategory(item.key)}
                >{item.label}</button>
              ))}
            </div>
          </div>
          <div className="inspector-section">
            {loading ? <div className="studio-empty">正在读取本地资产…</div> : null}
            {error ? <div className="studio-empty" role="status">{error}</div> : null}
            {!loading && !error && visible.length === 0 ? (
              <div className="studio-empty">当前类别暂无资产。完成故事拆解或生成后会自动归档到这里。</div>
            ) : null}
            <div className="asset-grid">
              {visible.map((asset) => (
                <article key={asset.id} className="asset-card" onClick={() => setSelectedId(asset.id)}>
                  <div className="asset-card__media">
                    {asset.media_url && asset.kind.includes("video") ? <video src={asset.media_url} muted preload="metadata" /> : null}
                    {asset.media_url && !asset.kind.includes("video") && !asset.kind.includes("audio") ? <img src={asset.media_url} alt={assetTitle(asset)} loading="lazy" /> : null}
                    {!asset.media_url || asset.kind.includes("audio") ? <span>{asset.kind}</span> : null}
                  </div>
                  <div className="asset-card__body">
                    <strong>{assetTitle(asset)}</strong>
                    <span>{asset.kind} · v{asset.version} · {asset.quality_status || "未质检"}</span>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>
      </section>

      <aside className="studio-panel studio-right-pane">
        <div className="studio-panel__header"><div><strong>资产检查器</strong><span>选中项详情</span></div></div>
        {selected ? (
          <>
            <div className="inspector-section">
              <h3>{assetTitle(selected)}</h3>
              <p className="subtle">{selected.path}</p>
            </div>
            <div className="inspector-section">
              <div className="inspector-field"><label>类型</label><input value={selected.kind} readOnly /></div>
              <div className="inspector-field"><label>场景</label><input value={selected.scene_id || "项目级"} readOnly /></div>
              <div className="inspector-field"><label>镜头</label><input value={selected.shot_id || "未绑定"} readOnly /></div>
              <div className="inspector-field"><label>版本</label><input value={`v${selected.version}`} readOnly /></div>
              <div className="inspector-field"><label>质检状态</label><input value={selected.quality_status || "未质检"} readOnly /></div>
            </div>
            <div className="inspector-section">
              <button type="button" className="studio-secondary-button" disabled={!canRegenerate} onClick={regenerateSelected}>重新生成此资产</button>
            </div>
          </>
        ) : <div className="studio-empty">选择一个资产查看详情</div>}
      </aside>
    </div>
  );
};

export default StoryAssetsWorkspace;

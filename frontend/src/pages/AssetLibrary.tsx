import React, { useEffect, useMemo, useRef, useState } from "react";

import { userMessage } from "@/api/client";
import { workspaceApi } from "@/api/workspace";
import { useWorkspaceStore } from "@/state/workspaceStore";
import type { AssetFilters, ProjectAsset } from "@/workbench/types";

const STAGE_LABELS: Record<string, string> = {
  import: "小说导入",
  story: "故事结构",
  character: "角色设定",
  storyboard: "分镜制作",
  keyframe: "关键帧",
  video: "视频生成",
  audio: "音频制作",
  compose: "合成",
  export: "成片导出",
};

const KIND_LABELS: Record<string, string> = {
  image: "图片",
  video: "视频",
  audio: "音频",
  text: "文本",
  subtitle: "字幕",
};

const QUALITY_LABELS: Record<string, string> = {
  unreviewed: "未质检",
  reviewing: "质检中",
  passed: "质检通过",
  failed: "质检未通过",
};

const DEFAULT_FILTERS = {
  kind: "",
  stageKey: "",
  sceneId: "",
  shotId: "",
  version: "current",
  qualityStatus: "",
};

type FilterState = typeof DEFAULT_FILTERS;

function safePath(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  if (/^[A-Za-z]:\//.test(normalized) || normalized.startsWith("/")) {
    const parts = normalized.split("/").filter(Boolean);
    return parts[parts.length - 1] ?? "未知文件";
  }
  return normalized;
}

function assetName(asset: ProjectAsset): string {
  const parts = safePath(asset.path).split("/");
  return parts[parts.length - 1] || "未知文件";
}

function previewLabel(asset: ProjectAsset): string {
  return `素材 ${assetName(asset)} 版本 ${asset.version}`;
}

function AssetPreview({ asset }: { asset: ProjectAsset }) {
  const [failed, setFailed] = useState(false);
  const name = assetName(asset);
  if (!asset.media_url || failed) {
    return <p className="asset-preview-error" role="alert">素材加载失败：{name}</p>;
  }
  if (asset.kind === "image") {
    return <img src={asset.media_url} alt={previewLabel(asset)} onError={() => setFailed(true)} />;
  }
  if (asset.kind === "video") {
    return (
      <video
        src={asset.media_url}
        controls
        preload="metadata"
        aria-label={previewLabel(asset)}
        onError={() => setFailed(true)}
      />
    );
  }
  if (asset.kind === "audio") {
    return (
      <audio
        src={asset.media_url}
        controls
        preload="metadata"
        aria-label={previewLabel(asset)}
        onError={() => setFailed(true)}
      />
    );
  }
  return (
    <a
      href={asset.media_url}
      target="_blank"
      rel="noreferrer"
      aria-label={`打开素材 ${name} 版本 ${asset.version}`}
    >
      打开素材
    </a>
  );
}

function options(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))].sort((left, right) => left.localeCompare(right, "zh-CN"));
}

export const AssetLibrary: React.FC = () => {
  const projectId = useWorkspaceStore((state) => state.snapshot?.project_id ?? "");
  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const [catalogAssets, setCatalogAssets] = useState<ProjectAsset[]>([]);
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const listRequestSequence = useRef(0);
  const catalogRequestSequence = useRef(0);

  const apiFilters = useMemo<AssetFilters>(() => ({
    ...(filters.version === "current" ? { active: true } : {}),
    ...(filters.kind ? { kind: filters.kind } : {}),
    ...(filters.stageKey ? { stage_key: filters.stageKey } : {}),
    ...(filters.sceneId ? { scene_id: filters.sceneId } : {}),
    ...(filters.shotId ? { shot_id: filters.shotId } : {}),
    ...(filters.qualityStatus ? { quality_status: filters.qualityStatus } : {}),
  }), [filters]);

  useEffect(() => {
    listRequestSequence.current += 1;
    catalogRequestSequence.current += 1;
    setAssets([]);
    setCatalogAssets([]);
    setFilters(DEFAULT_FILTERS);
    setError(null);
    if (!projectId) {
      setLoading(false);
      return undefined;
    }
    return undefined;
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return undefined;
    const token = ++catalogRequestSequence.current;
    setCatalogAssets([]);
    void workspaceApi.listAssets(projectId, {}).then((result) => {
      if (token !== catalogRequestSequence.current) return;
      setCatalogAssets(result);
    }).catch(() => {
      if (token !== catalogRequestSequence.current) return;
      setCatalogAssets([]);
    });
    return () => { catalogRequestSequence.current += 1; };
  }, [projectId, reloadToken]);

  useEffect(() => {
    if (!projectId) return undefined;
    const token = ++listRequestSequence.current;
    setLoading(true);
    setError(null);
    void workspaceApi.listAssets(projectId, apiFilters).then((result) => {
      if (token !== listRequestSequence.current) return;
      setAssets(result);
    }).catch((reason: unknown) => {
      if (token !== listRequestSequence.current) return;
      setAssets([]);
      setError(userMessage(reason));
    }).finally(() => {
      if (token === listRequestSequence.current) setLoading(false);
    });
    return () => { listRequestSequence.current += 1; };
  }, [projectId, apiFilters, reloadToken]);

  const hasFilters = Object.entries(filters).some(([key, value]) => (
    key === "version" ? value !== "current" : value !== ""
  ));
  const kinds = options(catalogAssets.map((asset) => asset.kind));
  const stages = options(catalogAssets.map((asset) => asset.stage_key ?? ""));
  const scenes = options(catalogAssets.map((asset) => asset.scene_id));
  const shots = options(catalogAssets.map((asset) => asset.shot_id));

  const setFilter = <K extends keyof FilterState>(key: K, value: FilterState[K]) => {
    setFilters((current) => ({ ...current, [key]: value }));
  };

  return (
    <section className="workspace-page asset-library" aria-labelledby="asset-library-title">
      <header className="workspace-page__header">
        <div>
          <p className="workspace-eyebrow">当前项目媒体与版本</p>
          <h1 id="asset-library-title">素材库</h1>
        </div>
      </header>

      <div className="asset-filters" aria-label="素材筛选">
        <label>媒体类型
          <select value={filters.kind} onChange={(event) => setFilter("kind", event.target.value)}>
            <option value="">全部</option>
            {kinds.map((kind) => <option key={kind} value={kind}>{KIND_LABELS[kind] ?? kind}</option>)}
          </select>
        </label>
        <label>制作阶段
          <select value={filters.stageKey} onChange={(event) => setFilter("stageKey", event.target.value)}>
            <option value="">全部</option>
            {stages.map((stage) => <option key={stage} value={stage}>{STAGE_LABELS[stage] ?? stage}</option>)}
          </select>
        </label>
        <label>场景
          <select value={filters.sceneId} onChange={(event) => setFilter("sceneId", event.target.value)}>
            <option value="">全部</option>
            {scenes.map((scene) => <option key={scene} value={scene}>{scene}</option>)}
          </select>
        </label>
        <label>镜头
          <select value={filters.shotId} onChange={(event) => setFilter("shotId", event.target.value)}>
            <option value="">全部</option>
            {shots.map((shot) => <option key={shot} value={shot}>{shot}</option>)}
          </select>
        </label>
        <label>版本
          <select value={filters.version} onChange={(event) => setFilter("version", event.target.value)}>
            <option value="current">当前版本</option>
            <option value="all">全部版本</option>
          </select>
        </label>
        <label>质检状态
          <select value={filters.qualityStatus} onChange={(event) => setFilter("qualityStatus", event.target.value)}>
            <option value="">全部</option>
            {Object.entries(QUALITY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
      </div>

      {loading ? <p className="workspace-feedback" role="status">正在加载素材</p> : null}
      {error ? (
        <div className="asset-library-error" role="alert">
          <p>{error}</p>
          <button type="button" onClick={() => setReloadToken((value) => value + 1)}>重新加载</button>
        </div>
      ) : null}
      {!loading && !error && assets.length === 0 ? (
        <div className="asset-empty">
          <p>当前筛选条件下暂无素材</p>
          {hasFilters ? <button type="button" onClick={() => setFilters(DEFAULT_FILTERS)}>清除筛选</button> : null}
        </div>
      ) : null}

      {!error && assets.length > 0 ? (
        <div className="asset-grid">
          {assets.map((item) => {
            const path = safePath(item.path);
            const name = assetName(item);
            return (
              <article className={`asset-card${item.active ? "" : " asset-card--historical"}`} key={item.id}>
                <div className="asset-card__preview"><AssetPreview asset={item} /></div>
                <div className="asset-card__body">
                  <h2>{name}</h2>
                  <dl>
                    <div><dt>类型</dt><dd>{KIND_LABELS[item.kind] ?? item.kind}</dd></div>
                    <div><dt>阶段</dt><dd>{item.stage_key ? (STAGE_LABELS[item.stage_key] ?? item.stage_key) : "未标注"}</dd></div>
                    <div><dt>场景 / 镜头</dt><dd>{item.scene_id || "未标注"} / {item.shot_id || "未标注"}</dd></div>
                    <div><dt>版本</dt><dd>版本 v{item.version}</dd></div>
                    <div><dt>版本状态</dt><dd>{item.active ? "当前版本" : "历史版本"}</dd></div>
                    <div><dt>质检</dt><dd>{QUALITY_LABELS[item.quality_status] ?? item.quality_status}</dd></div>
                    <div><dt>创建时间</dt><dd>{new Date(item.created_at).toLocaleString("zh-CN")}</dd></div>
                    <div><dt>路径</dt><dd>{path}</dd></div>
                  </dl>
                </div>
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
};

export default AssetLibrary;

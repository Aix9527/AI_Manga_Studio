import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { userMessage } from "@/api/client";
import { workspaceApi } from "@/api/workspace";
import { useWorkspaceStore } from "@/state/workspaceStore";
import type { ProjectAsset } from "@/workbench/types";

function formatTimestamp(iso: string): string {
  if (!iso) return "未知时间";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function inferFormat(path: string): string {
  const lower = path.toLowerCase();
  if (lower.endsWith(".mp4")) return "MP4";
  if (lower.endsWith(".webm")) return "WebM";
  if (lower.endsWith(".mov")) return "MOV";
  if (lower.endsWith(".avi")) return "AVI";
  if (lower.endsWith(".mkv")) return "MKV";
  return "视频";
}

function inferSize(metadata: Record<string, unknown>): string {
  const size = metadata?.file_size ?? metadata?.size;
  if (typeof size === "number" && size > 0) {
    if (size >= 1073741824) return `${(size / 1073741824).toFixed(2)} GB`;
    if (size >= 1048576) return `${(size / 1048576).toFixed(1)} MB`;
    if (size >= 1024) return `${(size / 1024).toFixed(0)} KB`;
    return `${size} B`;
  }
  return "未知";
}

function inferDuration(metadata: Record<string, unknown>): string {
  const duration = metadata?.duration ?? metadata?.total_duration;
  if (typeof duration === "number" && duration > 0) {
    const mins = Math.floor(duration / 60);
    const secs = Math.round(duration % 60);
    return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  return "未知";
}

function inferResolution(metadata: Record<string, unknown>): string {
  const w = metadata?.width ?? metadata?.resolution_width;
  const h = metadata?.height ?? metadata?.resolution_height;
  if (typeof w === "number" && typeof h === "number") return `${w}×${h}`;
  const aspect = metadata?.aspect_ratio;
  if (typeof aspect === "string") return aspect;
  return "未知";
}

const ExportStudio: React.FC = () => {
  const snapshot = useWorkspaceStore((state) => state.snapshot);
  const workspaceProjectId = useWorkspaceStore((state) => state.projectId);
  const projectId = snapshot?.project_id ?? workspaceProjectId ?? "default";

  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [compareId, setCompareId] = useState<number | null>(null);
  const loadToken = useRef(0);

  useEffect(() => {
    loadToken.current += 1;
    setSelectedId(null);
    setCompareId(null);
    setError(null);
    setAssets([]);
    setLoading(false);

    const token = loadToken.current;
    const loadAssets = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await workspaceApi.listAssets(projectId, {
          kind: "video",
          stage_key: "export",
        });
        if (token !== loadToken.current) return;
        setAssets(result);
        const firstActive = result.find((a) => a.active);
        if (firstActive) setSelectedId(firstActive.id);
        else if (result.length > 0) setSelectedId(result[0].id);
      } catch (err) {
        if (token !== loadToken.current) return;
        setError(userMessage(err));
      } finally {
        if (token === loadToken.current) setLoading(false);
      }
    };

    void loadAssets();
    return () => { loadToken.current += 1; };
  }, [projectId]);

  const exportStage = snapshot?.stages.find((s) => s.stage_key === "export");
  const composeStage = snapshot?.stages.find((s) => s.stage_key === "compose");

  const selectedAsset = assets.find((a) => a.id === selectedId) ?? null;
  const compareAsset = assets.find((a) => a.id === compareId) ?? null;

  const handleDownload = (asset: ProjectAsset) => {
    const url = `/api/workspace/${encodeURIComponent(projectId)}/assets/${asset.id}/media`;
    const a = document.createElement("a");
    a.href = url;
    a.download = asset.path.split(/[\\/]/).pop() ?? "export.mp4";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const exportReady = exportStage?.status === "completed" || (assets.length > 0 && selectedAsset);

  return (
    <section className="workspace-page export-page" aria-labelledby="export-title">
      <header className="workspace-page__header">
        <div>
          <p className="workspace-eyebrow">最终成片与导出</p>
          <h1 id="export-title">成片与导出</h1>
        </div>
        <div className="workspace-actions">
          <Link to="/director">返回制作</Link>
          {selectedAsset ? (
            <button type="button" onClick={() => handleDownload(selectedAsset)}>
              下载当前版本
            </button>
          ) : null}
        </div>
      </header>

      {error ? <p className="workspace-error" role="alert">{error}</p> : null}

      <dl className="overview-metrics">
        <div><dt>导出阶段</dt><dd>{exportStage?.status === "completed" ? "已完成" : exportStage?.status === "running" ? "导出中" : exportStage?.status === "pending" ? "等待中" : exportStage?.status ?? "未开始"}</dd></div>
        <div><dt>合成阶段</dt><dd>{composeStage?.status === "completed" ? "已完成" : composeStage?.status === "running" ? "合成中" : composeStage?.status === "pending" ? "等待中" : composeStage?.status ?? "未开始"}</dd></div>
        <div><dt>可用版本</dt><dd>{assets.length} 个</dd></div>
        <div><dt>活跃版本</dt><dd>{assets.filter((a) => a.active).length > 0 ? `v${String(assets.find((a) => a.active)?.version ?? 1).padStart(2, "0")}` : "暂无"}</dd></div>
        <div><dt>质检状态</dt><dd>{selectedAsset?.quality_status === "passed" ? "已通过" : selectedAsset?.quality_status === "pending" ? "待审核" : selectedAsset?.quality_status === "failed" ? "未通过" : "暂无"}</dd></div>
        <div><dt>整体进度</dt><dd>{snapshot ? `${Math.round(snapshot.progress * 100)}%` : "0%"}</dd></div>
      </dl>

      {!exportReady && !loading ? (
        <div className="workspace-empty-state">
          <strong>暂无导出成片</strong>
          <p>完成合成阶段后，最终成片将在此处展示。您也可以在分镜导演台检查制作进度。</p>
          <Link to="/director" className="workspace-primary-link">前往分镜导演台</Link>
        </div>
      ) : null}

      {loading ? <p className="workspace-muted">正在加载导出版本...</p> : null}

      {exportReady && selectedAsset ? (
        <div className="export-layout">
          <div className="export-player-section">
            <section className="workspace-panel export-player-panel">
              <h2>视频播放器</h2>
              <div className="export-video-wrapper">
                <video
                  key={selectedAsset.id}
                  controls
                  preload="metadata"
                  className="export-video"
                  src={`/api/workspace/${encodeURIComponent(projectId)}/assets/${selectedAsset.id}/media`}
                >
                  您的浏览器不支持视频播放。
                </video>
              </div>
              <div className="export-video-info">
                <div>
                  <span className="export-info-label">文件</span>
                  <span className="export-info-value">{selectedAsset.path.split(/[\\/]/).pop() ?? "未知文件"}</span>
                </div>
                <div>
                  <span className="export-info-label">格式</span>
                  <span className="export-info-value">{inferFormat(selectedAsset.path)}</span>
                </div>
                <div>
                  <span className="export-info-label">时长</span>
                  <span className="export-info-value">{inferDuration(selectedAsset.metadata)}</span>
                </div>
                <div>
                  <span className="export-info-label">分辨率</span>
                  <span className="export-info-value">{inferResolution(selectedAsset.metadata)}</span>
                </div>
                <div>
                  <span className="export-info-label">大小</span>
                  <span className="export-info-value">{inferSize(selectedAsset.metadata)}</span>
                </div>
                <div>
                  <span className="export-info-label">创建时间</span>
                  <span className="export-info-value">{formatTimestamp(selectedAsset.created_at)}</span>
                </div>
              </div>
              <div className="export-actions">
                <button type="button" onClick={() => handleDownload(selectedAsset)}>
                  下载此版本
                </button>
                {selectedAsset.active ? (
                  <span className="export-active-badge">当前活跃版本</span>
                ) : null}
              </div>
            </section>

            {compareAsset ? (
              <section className="workspace-panel export-compare-panel">
                <div className="export-compare-header">
                  <h2>版本对比</h2>
                  <button type="button" className="export-close-compare" onClick={() => setCompareId(null)}>
                    关闭对比
                  </button>
                </div>
                <div className="export-compare-grid">
                  <div className="export-compare-col">
                    <span className="export-compare-label">版本 v{String(selectedAsset.version).padStart(2, "0")}</span>
                    <video
                      key={selectedAsset.id}
                      controls
                      preload="metadata"
                      className="export-video export-video--small"
                      src={`/api/workspace/${encodeURIComponent(projectId)}/assets/${selectedAsset.id}/media`}
                    />
                    <dl className="export-compare-meta">
                      <div><dt>格式</dt><dd>{inferFormat(selectedAsset.path)}</dd></div>
                      <div><dt>时长</dt><dd>{inferDuration(selectedAsset.metadata)}</dd></div>
                      <div><dt>分辨率</dt><dd>{inferResolution(selectedAsset.metadata)}</dd></div>
                      <div><dt>大小</dt><dd>{inferSize(selectedAsset.metadata)}</dd></div>
                      <div><dt>时间</dt><dd>{formatTimestamp(selectedAsset.created_at)}</dd></div>
                    </dl>
                  </div>
                  <div className="export-compare-col">
                    <span className="export-compare-label">版本 v{String(compareAsset.version).padStart(2, "0")}</span>
                    <video
                      key={compareAsset.id}
                      controls
                      preload="metadata"
                      className="export-video export-video--small"
                      src={`/api/workspace/${encodeURIComponent(projectId)}/assets/${compareAsset.id}/media`}
                    />
                    <dl className="export-compare-meta">
                      <div><dt>格式</dt><dd>{inferFormat(compareAsset.path)}</dd></div>
                      <div><dt>时长</dt><dd>{inferDuration(compareAsset.metadata)}</dd></div>
                      <div><dt>分辨率</dt><dd>{inferResolution(compareAsset.metadata)}</dd></div>
                      <div><dt>大小</dt><dd>{inferSize(compareAsset.metadata)}</dd></div>
                      <div><dt>时间</dt><dd>{formatTimestamp(compareAsset.created_at)}</dd></div>
                    </dl>
                  </div>
                </div>
              </section>
            ) : null}
          </div>

          <aside className="export-versions-panel">
            <section className="workspace-panel">
              <h2>版本列表</h2>
              {assets.length === 0 ? (
                <p className="workspace-empty-copy">暂无导出版本</p>
              ) : (
                <ul className="export-version-list">
                  {assets.map((asset) => (
                    <li key={asset.id}>
                      <button
                        type="button"
                        className="export-version-item"
                        aria-pressed={asset.id === selectedId}
                        onClick={() => setSelectedId(asset.id)}
                      >
                        <span className="export-version-name">
                          版本 v{String(asset.version).padStart(2, "0")}
                          {asset.active ? <em className="export-version-active">活跃</em> : null}
                        </span>
                        <span className="export-version-meta">
                          {inferFormat(asset.path)} · {inferSize(asset.metadata)}
                        </span>
                        <span className="export-version-date">{formatTimestamp(asset.created_at)}</span>
                        <div className="export-version-actions">
                          <button
                            type="button"
                            className="export-version-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              setCompareId(asset.id === compareId ? null : asset.id);
                            }}
                          >
                            {asset.id === compareId ? "取消对比" : "对比"}
                          </button>
                          <button
                            type="button"
                            className="export-version-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDownload(asset);
                            }}
                          >
                            下载
                          </button>
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="workspace-panel export-checklist-panel">
              <h2>导出检查项</h2>
              <ul className="export-checklist">
                <li>
                  <span className={selectedAsset ? "export-check--ok" : "export-check--pending"}>
                    {selectedAsset ? "✓" : "○"}
                  </span>
                  视频文件可播放
                </li>
                <li>
                  <span className={selectedAsset?.quality_status === "passed" ? "export-check--ok" : "export-check--pending"}>
                    {selectedAsset?.quality_status === "passed" ? "✓" : "○"}
                  </span>
                  质检已通过
                </li>
                <li>
                  <span className={composeStage?.status === "completed" ? "export-check--ok" : "export-check--pending"}>
                    {composeStage?.status === "completed" ? "✓" : "○"}
                  </span>
                  合成已完成
                </li>
                <li>
                  <span className={exportStage?.status === "completed" ? "export-check--ok" : "export-check--pending"}>
                    {exportStage?.status === "completed" ? "✓" : "○"}
                  </span>
                  导出已完成
                </li>
              </ul>
            </section>
          </aside>
        </div>
      ) : null}
    </section>
  );
};

export default ExportStudio;

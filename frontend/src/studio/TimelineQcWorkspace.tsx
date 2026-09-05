import React, { useEffect, useMemo, useState } from "react";
import { CheckCircleOutlined, ExportOutlined, ReloadOutlined, SafetyCertificateOutlined } from "@ant-design/icons";

import { userMessage } from "@/api/client";
import { workspaceApi } from "@/api/workspace";
import { jobStoreActions, useJobStore } from "@/state/jobStore";
import { useTimelineStore } from "@/state/timelineStore";
import { useWorkspaceStore } from "@/state/workspaceStore";
import TimelineEditor from "@/studio/timeline/TimelineEditor";
import TimelineSnapshotPanel from "@/studio/timeline/TimelineSnapshotPanel";
import "@/styles/timeline.css";
import type { JobDetail } from "@/types/jobs";
import type { ProjectAsset } from "@/workbench/types";

interface TimelineItem {
  id: number;
  label: string;
  selectable: boolean;
}

const TimelineQcWorkspace: React.FC = () => {
  const snapshot = useWorkspaceStore((state) => state.snapshot);
  const projectId = snapshot?.project_id || useWorkspaceStore.getState().projectId || "default";
  const jobStore = useJobStore();
  const actions = jobStoreActions();
  const timelineDraft = useTimelineStore((state) => state.draft);
  const timelineId = useTimelineStore((state) => state.timelineId);
  const timelinePreflight = useTimelineStore((state) => state.preflight);
  const timelineSnapshots = useTimelineStore((state) => state.snapshots);
  const selectedSnapshotId = useTimelineStore((state) => state.selectedSnapshotId);
  const qcBySnapshot = useTimelineStore((state) => state.qcBySnapshot);
  const exportBySnapshot = useTimelineStore((state) => state.exportBySnapshot);
  const timelineLoading = useTimelineStore((state) => state.loading);
  const timelinePendingSave = useTimelineStore((state) => state.pendingSave);
  const timelineError = useTimelineStore((state) => state.error);
  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedTimelineClipId, setSelectedTimelineClipId] = useState<string | null>(null);
  const [playheadTick, setPlayheadTick] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const [exportBusy, setExportBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    setSelectedTimelineClipId(null);
    setPlayheadTick(0);
    void useTimelineStore.getState().loadProject(projectId);
    void workspaceApi.listAssets(projectId)
      .then((items) => {
        if (!alive) return;
        setAssets(items);
        const preview = items.find((item) => item.media_url && (item.kind.includes("video") || item.kind.includes("image")));
        setSelectedId(preview?.id ?? null);
      })
      .catch((error) => alive && setMessage(userMessage(error)));
    return () => { alive = false; };
  }, [projectId]);

  const selected = assets.find((asset) => asset.id === selectedId) ?? null;
  const mediaAssets = useMemo(
    () => assets.filter((asset) => asset.kind.includes("video") || asset.kind.includes("image") || asset.kind.includes("composition")),
    [assets],
  );
  const timelineItems = useMemo<TimelineItem[]>(() => mediaAssets.map((asset, index) => ({
    id: asset.id,
    label: asset.shot_id || asset.scene_id || `镜头 ${index + 1}`,
    selectable: true,
  })), [mediaAssets]);
  const jobs = jobStore.recentIds
    .map((id) => jobStore.jobs.get(id))
    .filter((job): job is JobDetail => Boolean(job));
  const problemJobs = jobs.filter((job) => job.status === "failed" || job.status === "waiting_review" || job.status === "retry_wait");
  const qcPassed = assets.filter((asset) => asset.quality_status === "passed" || asset.quality_status === "pass").length;
  const qcFailed = assets.filter((asset) => asset.quality_status === "failed" || asset.quality_status === "fail").length;
  const qcPending = Math.max(0, assets.length - qcPassed - qcFailed);

  const artifactUpgrades = useMemo(() => {
    if (!timelineDraft) return {};
    const result: Record<string, { artifact_id: number; version: number }> = {};
    const activeAssets = assets.filter((asset) => asset.active);
    for (const clip of timelineDraft.tracks.flatMap((track) => track.clips)) {
      if (!clip.shot_id || clip.artifact_version == null) continue;
      const newer = activeAssets
        .filter((asset) => asset.shot_id === clip.shot_id && asset.version > clip.artifact_version)
        .sort((a, b) => b.version - a.version || b.id - a.id)[0];
      if (newer) result[clip.id] = { artifact_id: newer.id, version: newer.version };
    }
    return result;
  }, [assets, timelineDraft]);

  const exportAsset = assets.find((asset) => (
    asset.active
    && asset.stage_key === "export"
    && (asset.kind.includes("video") || asset.kind.includes("composition"))
  )) ?? null;
  const exportJob = jobs.find((job) => job.current_stage === "export" || job.current_stage === "compose") ?? null;
  const legacyExportLabel = exportAsset
    ? "下载成片"
    : exportJob?.status === "retry_wait" || exportJob?.status === "failed" || exportJob?.status === "paused"
      ? "恢复导出"
      : exportJob?.status === "queued" || exportJob?.status === "running"
        ? "导出进行中"
        : exportJob?.status === "waiting_review"
          ? "等待审核"
          : "导出成片";
  const legacyExportDisabled = Boolean(
    exportBusy
    || qcFailed > 0
    || qcPending > 0
    || (!exportAsset && !exportJob)
    || (!exportAsset && ["queued", "running", "waiting_review", "completed"].includes(exportJob?.status ?? "")),
  );
  const legacyExportReason = qcFailed > 0
    ? "存在未通过 QC 的资产，必须修复后才能导出。"
    : qcPending > 0
      ? "仍有未完成 QC 的资产，全部通过后才能导出。"
      : exportAsset
        ? "QC 已通过，可下载当前激活导出版本。"
        : !exportJob
          ? "当前没有可恢复的 compose/export 任务。"
          : exportJob.status === "queued" || exportJob.status === "running"
            ? "compose/export 任务正在运行，无需重复提交。"
            : exportJob.status === "waiting_review"
              ? "当前生产任务正在等待审核，时间线不会自动绕过审核门禁。"
              : "恢复现有 compose/export 任务，不会创建重复的全流程 Job。";

  const downloadAsset = (asset: ProjectAsset) => {
    const anchor = document.createElement("a");
    anchor.href = asset.media_url;
    anchor.download = asset.path.split(/[\\/]/).pop() || "export.mp4";
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  };

  const handleLegacyExport = async () => {
    if (legacyExportDisabled) return;
    if (exportAsset) {
      downloadAsset(exportAsset);
      setMessage("已请求下载当前激活成片版本");
      return;
    }
    if (!exportJob) return;
    setExportBusy(true);
    try {
      if (exportJob.status === "paused") {
        await actions.resumeJob(exportJob.id);
      } else if (exportJob.status === "failed" || exportJob.status === "retry_wait") {
        await actions.retryJob(exportJob.id);
      } else {
        return;
      }
      setMessage(`已恢复导出任务 · ${exportJob.id.slice(0, 8)}`);
    } catch (error) {
      setMessage(userMessage(error));
    } finally {
      setExportBusy(false);
    }
  };

  return (
    <div className="studio-workspace timeline-workspace">
      <section className="timeline-stack">
        <header className="studio-workspace__header">
          <div><h1>时间线 · 质检 · 导出</h1><p>持久化 NLE、多轨剪辑、Snapshot QC 与确定性导出集中在一个工作区</p></div>
          {timelinePendingSave ? <span className="nle-pending">正在保存剪辑…</span> : null}
        </header>

        <section className="timeline-main-preview">
          {selected?.media_url && selected.kind.includes("video") ? <video src={selected.media_url} controls preload="metadata" /> : null}
          {selected?.media_url && !selected.kind.includes("video") ? <img src={selected.media_url} alt={selected.shot_id || selected.kind} /> : null}
          {!selected?.media_url ? <span>选择时间线镜头预览</span> : null}
        </section>

        <section className="studio-panel">
          <div className="studio-panel__header"><div><strong>媒体产物</strong><span>{mediaAssets.length} 个可预览素材</span></div></div>
          <div className="inspector-section">
            {timelineItems.length ? (
              <div className="timeline-track">
                {timelineItems.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`timeline-block${selectedId === item.id ? " is-active" : ""}`}
                    disabled={!item.selectable}
                    onClick={() => item.selectable && setSelectedId(item.id)}
                  >{item.label}</button>
                ))}
              </div>
            ) : <div className="studio-empty">当前没有可预览媒体产物</div>}
          </div>
        </section>

        {timelineDraft ? (
          <TimelineEditor
            draft={timelineDraft}
            playheadTick={playheadTick}
            selectedClipId={selectedTimelineClipId}
            artifactUpgrades={artifactUpgrades}
            onPlayheadChange={setPlayheadTick}
            onScheduleOperation={(operation) => useTimelineStore.getState().scheduleOperation(operation)}
            onCriticalOperation={(operation) => useTimelineStore.getState().commitCritical(operation)}
            onSelectClip={(clip) => {
              setSelectedTimelineClipId(clip.id);
              if (clip.artifact_id != null) setSelectedId(clip.artifact_id);
            }}
          />
        ) : timelineLoading ? (
          <div className="nle-empty">正在加载持久化时间线…</div>
        ) : (
          <div className="nle-empty">当前项目尚未建立可编辑时间线</div>
        )}
        {timelineError ? <p className="nle-load-error">{timelineError}</p> : null}
        {message ? <p className="studio-feedback" role="status">{message}</p> : null}
      </section>

      <aside className="studio-right-pane">
        <section className="studio-panel qc-summary-card">
          <h2><SafetyCertificateOutlined /> 素材 QC</h2>
          <div className="qc-grid">
            <div className="qc-item is-ok">通过 <strong>{qcPassed}</strong></div>
            <div className={qcFailed ? "qc-item is-warn" : "qc-item is-ok"}>失败 <strong>{qcFailed}</strong></div>
            <div className="qc-item">待检测 <strong>{qcPending}</strong></div>
            <div className="qc-item is-ok">Snapshot QC 独立门禁</div>
          </div>
        </section>

        <section className="studio-panel">
          <div className="studio-panel__header"><div><strong>待处理问题</strong><span>{problemJobs.length} 个</span></div></div>
          <div className="task-queue-list">
            {problemJobs.length === 0 ? <div className="studio-empty"><CheckCircleOutlined /> 当前没有阻塞生产的问题</div> : problemJobs.map((job) => (
              <article key={job.id} className="task-card">
                <div className="task-card__title"><strong>{job.current_shot || job.current_stage || job.id.slice(0, 8)}</strong><span className={`status-chip status-chip--${job.status}`}>{job.status}</span></div>
                <p>{job.message || "需要处理的生产任务"}</p>
                <div className="task-card__actions">
                  {job.status === "failed" || job.status === "retry_wait" ? <button type="button" onClick={() => void actions.retryJob(job.id)}><ReloadOutlined /> 重试</button> : null}
                  {job.status === "waiting_review" ? <button type="button" onClick={() => void actions.reviewJob(job.id, "approve", "在统一时间线工作区批准")}>批准</button> : null}
                </div>
              </article>
            ))}
          </div>
        </section>

        {timelineDraft && timelineId ? (
          <TimelineSnapshotPanel
            draft={timelineDraft}
            preflight={timelinePreflight}
            snapshots={timelineSnapshots}
            selectedSnapshotId={selectedSnapshotId}
            qcBySnapshot={qcBySnapshot}
            exportBySnapshot={exportBySnapshot}
            pendingSave={timelinePendingSave}
            onSelectSnapshot={(snapshotId) => useTimelineStore.getState().selectSnapshot(snapshotId)}
            onFlush={() => useTimelineStore.getState().flushPending()}
            onCreateSnapshot={() => useTimelineStore.getState().createSnapshot()}
            onRunQc={(snapshotId) => useTimelineStore.getState().runQc(snapshotId)}
            onExportSnapshot={(snapshotId, profile) => useTimelineStore.getState().exportSnapshot(snapshotId, profile)}
          />
        ) : (
          <section className="studio-panel export-box">
            <strong><ExportOutlined /> 兼容导出</strong>
            <p>当前项目没有 Timeline，继续使用 v0.9 既有 compose/export 任务，不阻塞一键生产。</p>
            <p className="subtle">{legacyExportReason}</p>
            <button type="button" className="studio-primary-button" disabled={legacyExportDisabled} onClick={() => void handleLegacyExport()}>
              {exportBusy ? "正在恢复…" : legacyExportLabel}
            </button>
          </section>
        )}
      </aside>
    </div>
  );
};

export default TimelineQcWorkspace;

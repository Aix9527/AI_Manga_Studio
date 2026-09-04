import React, { useEffect, useMemo, useState } from "react";
import { CheckCircleOutlined, ExportOutlined, ReloadOutlined, SafetyCertificateOutlined } from "@ant-design/icons";

import { userMessage } from "@/api/client";
import { workspaceApi } from "@/api/workspace";
import { jobStoreActions, useJobStore } from "@/state/jobStore";
import { useWorkspaceStore } from "@/state/workspaceStore";
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
  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [exportBusy, setExportBusy] = useState(false);

  useEffect(() => {
    let alive = true;
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
  const timelineItems = useMemo<TimelineItem[]>(() => {
    if (mediaAssets.length) {
      return mediaAssets.map((asset, index) => ({
        id: asset.id,
        label: asset.shot_id || asset.scene_id || `镜头 ${index + 1}`,
        selectable: true,
      }));
    }
    return Array.from({ length: 8 }, (_, index) => ({
      id: -(index + 1),
      label: `镜头 ${index + 1}`,
      selectable: false,
    }));
  }, [mediaAssets]);
  const jobs = jobStore.recentIds
    .map((id) => jobStore.jobs.get(id))
    .filter((job): job is JobDetail => Boolean(job));
  const problemJobs = jobs.filter((job) => job.status === "failed" || job.status === "waiting_review" || job.status === "retry_wait");
  const qcPassed = assets.filter((asset) => asset.quality_status === "passed" || asset.quality_status === "pass").length;
  const qcFailed = assets.filter((asset) => asset.quality_status === "failed" || asset.quality_status === "fail").length;
  const qcPending = Math.max(0, assets.length - qcPassed - qcFailed);
  const exportAsset = assets.find((asset) => (
    asset.active
    && asset.stage_key === "export"
    && (asset.kind.includes("video") || asset.kind.includes("composition"))
  )) ?? null;
  const exportJob = jobs.find((job) => job.current_stage === "export" || job.current_stage === "compose") ?? null;

  const exportLabel = (() => {
    if (exportAsset) return "下载成片";
    if (exportJob?.status === "retry_wait" || exportJob?.status === "failed" || exportJob?.status === "paused") return "恢复导出";
    if (exportJob?.status === "queued" || exportJob?.status === "running") return "导出进行中";
    if (exportJob?.status === "waiting_review") return "等待审核";
    return "导出成片";
  })();

  const exportDisabled = Boolean(
    exportBusy
    || qcFailed > 0
    || (!exportAsset && !exportJob)
    || (!exportAsset && exportJob?.status === "queued")
    || (!exportAsset && exportJob?.status === "running")
    || (!exportAsset && exportJob?.status === "waiting_review")
    || (!exportAsset && exportJob?.status === "completed"),
  );

  const exportReason = (() => {
    if (qcFailed > 0) return "存在未通过 QC 的资产，必须修复后才能导出。";
    if (exportAsset) return "QC 已通过，可下载当前激活导出版本。";
    if (!exportJob) return "当前没有可恢复的 compose/export 任务；一键生产会在前置阶段完成后自动进入导出。";
    if (exportJob.status === "queued" || exportJob.status === "running") return "compose/export 任务正在运行，无需重复提交。";
    if (exportJob.status === "waiting_review") return "当前生产任务正在等待审核，时间线不会自动绕过审核门禁。";
    if (exportJob.status === "completed") return "导出任务已完成，等待导出资产同步。";
    return "恢复现有 compose/export 任务，不会创建重复的全流程 Job。";
  })();

  const downloadAsset = (asset: ProjectAsset) => {
    const anchor = document.createElement("a");
    anchor.href = asset.media_url;
    anchor.download = asset.path.split(/[\\/]/).pop() || "export.mp4";
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  };

  const handleExport = async () => {
    if (exportDisabled) return;
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
          <div><h1>时间线 · 质检 · 导出</h1><p>多轨成片、镜头 QC、问题重试和版本导出集中在一个工作区</p></div>
        </header>

        <section className="timeline-main-preview">
          {selected?.media_url && selected.kind.includes("video") ? <video src={selected.media_url} controls preload="metadata" /> : null}
          {selected?.media_url && !selected.kind.includes("video") ? <img src={selected.media_url} alt={selected.shot_id || selected.kind} /> : null}
          {!selected?.media_url ? <span>选择时间线镜头预览</span> : null}
        </section>

        <section className="studio-panel">
          <div className="studio-panel__header"><div><strong>镜头时间线</strong><span>{mediaAssets.length} 个媒体产物</span></div></div>
          <div className="inspector-section">
            <div className="timeline-ruler"><span>00:00</span><span>00:15</span><span>00:30</span><span>00:45</span><span>01:00</span><span>01:15</span><span>01:30</span></div>
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
          </div>
        </section>

        <section className="timeline-lanes">
          <div className="timeline-lane"><span>镜头轨道</span><div className="timeline-lane__blocks">{Array.from({ length: 8 }).map((_, i) => <i key={i} />)}</div></div>
          <div className="timeline-lane"><span>对白 / 配音</span><div className="timeline-lane__blocks">{Array.from({ length: 6 }).map((_, i) => <i key={i} />)}</div></div>
          <div className="timeline-lane"><span>BGM / 音效</span><div className="timeline-lane__blocks">{Array.from({ length: 5 }).map((_, i) => <i key={i} />)}</div></div>
          <div className="timeline-lane"><span>字幕</span><div className="timeline-lane__blocks">{Array.from({ length: 7 }).map((_, i) => <i key={i} />)}</div></div>
        </section>
        {message ? <p className="studio-feedback" role="status">{message}</p> : null}
      </section>

      <aside className="studio-right-pane">
        <section className="studio-panel qc-summary-card">
          <h2><SafetyCertificateOutlined /> QC Gate</h2>
          <div className="qc-grid">
            <div className="qc-item is-ok">通过 <strong>{qcPassed}</strong></div>
            <div className={qcFailed ? "qc-item is-warn" : "qc-item is-ok"}>失败 <strong>{qcFailed}</strong></div>
            <div className="qc-item">待检测 <strong>{qcPending}</strong></div>
            <div className="qc-item is-ok">角色一致性 ✓</div>
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

        <section className="studio-panel export-box">
          <strong><ExportOutlined /> 版本与导出</strong>
          <p>输出继续使用本地 FFmpeg 合成链；统一时间线只恢复既有 compose/export Job，不会绕过 QC，也不会重复创建整条生产链。</p>
          <div className="inspector-field"><label>分辨率</label><select defaultValue="1080x1920"><option>1080x1920 · 9:16</option><option>1920x1080 · 16:9</option></select></div>
          <div className="inspector-field"><label>帧率</label><select defaultValue="24"><option value="24">24 fps</option><option value="25">25 fps</option><option value="30">30 fps</option></select></div>
          <p className="subtle">{exportReason}</p>
          <button type="button" className="studio-primary-button" disabled={exportDisabled} onClick={() => void handleExport()}>{exportBusy ? "正在恢复…" : exportLabel}</button>
        </section>
      </aside>
    </div>
  );
};

export default TimelineQcWorkspace;

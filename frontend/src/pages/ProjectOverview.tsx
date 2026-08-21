import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { userMessage } from "@/api/client";
import { api } from "@/api/jobs";
import ClearHistoryButton from "@/components/settings/ClearHistoryButton";
import { useCharacterStore } from "@/state/characterStore";
import { jobStoreActions, useJobStore } from "@/state/jobStore";
import { useStoryStore } from "@/state/storyStore";
import { useWorkspaceStore } from "@/state/workspaceStore";
import type { JobStatus } from "@/types/jobs";
import type { StageKey } from "@/workbench/types";

const STAGE_LABELS: Record<StageKey, string> = {
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

const STAGE_ROUTES: Record<StageKey, string> = {
  import: "/overview#import",
  story: "/story",
  character: "/story",
  storyboard: "/director",
  keyframe: "/director",
  video: "/director",
  audio: "/director",
  compose: "/export",
  export: "/export",
};

const JOB_STATUS_LABELS: Record<JobStatus, string> = {
  draft: "草稿",
  queued: "排队中",
  running: "运行中",
  waiting_review: "等待审核",
  retry_wait: "等待重试",
  failed: "失败",
  paused: "已暂停",
  completed: "已完成",
  cancelled: "已取消",
};

const ACTIVE_JOB_STATUSES = new Set<JobStatus>(["queued", "running", "waiting_review", "retry_wait"]);

export const ProjectOverview: React.FC = () => {
  const snapshot = useWorkspaceStore((state) => state.snapshot);
  const workspaceProjectId = useWorkspaceStore((state) => state.projectId);
  const projectId = snapshot?.project_id ?? workspaceProjectId;
  const jobStore = useJobStore();
  const parseStory = useStoryStore((state) => state.parseStory);
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthResult, setHealthResult] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<string | null>(null);
  const [uploadedPath, setUploadedPath] = useState<string | null>(null);
  const [creatingJob, setCreatingJob] = useState(false);
  const [jobResult, setJobResult] = useState<string | null>(null);
  const healthRequest = useRef(0);
  const importRequest = useRef(0);

  useEffect(() => {
    healthRequest.current += 1;
    importRequest.current += 1;
    setHealthLoading(false);
    setHealthResult(null);
    setImporting(false);
    setImportResult(null);
    useStoryStore.getState().invalidateRequests();
    return () => {
      healthRequest.current += 1;
      importRequest.current += 1;
      useStoryStore.getState().invalidateRequests();
    };
  }, [projectId]);

  const currentStage = snapshot?.stages.find((stage) => stage.status !== "completed");
  const stageText = !snapshot
    ? "尚未开始"
    : currentStage
      ? STAGE_LABELS[currentStage.stage_key]
      : "全部阶段已完成";
  const databaseOk = snapshot?.system_health.database === "ok" || snapshot?.system_health.database === true;

  const projectJobs = useMemo(
    () => jobStore.recentIds
      .map((id) => jobStore.jobs.get(id))
      .filter((job): job is NonNullable<typeof job> => Boolean(job && job.project_id === projectId)),
    [jobStore.jobs, jobStore.recentIds, projectId],
  );
  const currentJob = projectJobs.find((job) => job && ACTIVE_JOB_STATUSES.has(job.status));
  const artifacts = projectJobs.flatMap((job) => job?.artifacts ?? []);

  const checkHealth = async () => {
    const requestToken = ++healthRequest.current;
    setHealthLoading(true);
    setHealthResult(null);
    try {
      const result = await api.health();
      if (requestToken !== healthRequest.current) return;
      setHealthResult(`本地服务正常 · 版本 ${result.version}`);
    } catch (error) {
      if (requestToken !== healthRequest.current) return;
      setHealthResult(userMessage(error));
    } finally {
      if (requestToken === healthRequest.current) setHealthLoading(false);
    }
  };

  const importNovel = async () => {
    if (!file) {
      setImportResult("请选择小说文件");
      return;
    }
    if (!snapshot?.project_id) {
      setImportResult("请先载入当前项目");
      return;
    }
    const requestToken = ++importRequest.current;
    const importProjectId = snapshot.project_id;
    setImporting(true);
    setImportResult(null);
    try {
      const text = await file.text();
      if (requestToken !== importRequest.current) return;
      const uploadResp = await api.uploadInput(file, importProjectId);
      if (requestToken !== importRequest.current) return;
      setUploadedPath(uploadResp.path);
      await parseStory(text, importProjectId);
      if (requestToken !== importRequest.current) return;
      const storyError = useStoryStore.getState().parseError;
      if (storyError) throw new Error(storyError);
      setImportResult("故事解析完成，正在提取角色…");
      await useCharacterStore.getState().extractFromText({ text, novel_id: importProjectId });
      if (requestToken !== importRequest.current) return;
      const charError = useCharacterStore.getState().error;
      if (charError) throw new Error(charError);
      const charCount = useCharacterStore.getState().characters.length;
      setImportResult(`小说已上传并完成解析，已提取 ${charCount} 个角色`);
    } catch (error) {
      if (requestToken !== importRequest.current) return;
      setImportResult(userMessage(error));
    } finally {
      if (requestToken === importRequest.current) setImporting(false);
    }
  };

  const startProduction = async () => {
    if (!snapshot?.project_id) {
      setJobResult("请先载入当前项目");
      return;
    }
    if (!uploadedPath) {
      setJobResult("请先上传小说文件");
      return;
    }
    setCreatingJob(true);
    setJobResult(null);
    try {
      const actions = jobStoreActions();
      const job = await actions.createJob({
        project_id: snapshot.project_id,
        input_path: uploadedPath,
        mode: "automatic",
        shot_duration: 5.0,
        width: 1080,
        height: 1920,
        fps: 24,
        options: { style: "anime" },
      });
      actions.subscribeSSE(job.id);
      setJobResult(`生产任务已创建（${job.id}），正在自动生成中…`);
    } catch (error) {
      setJobResult(userMessage(error));
    } finally {
      setCreatingJob(false);
    }
  };

  const canStartProduction = Boolean(uploadedPath && !importing);

  const metrics = [
    ["整体进度", snapshot ? `${Math.round(snapshot.progress * 100)}%` : "0%"],
    ["当前阶段", stageText],
    ["待审核", String(snapshot?.pending_reviews ?? 0)],
    ["活动任务", String(snapshot?.active_jobs ?? 0)],
    ["预计完成", snapshot?.estimated_minutes == null ? "暂无估算" : `${snapshot.estimated_minutes} 分钟`],
    ["系统状态", databaseOk ? "数据库正常" : "数据库异常"],
  ];

  return (
    <section className="workspace-page overview-page" aria-labelledby="overview-title">
      <header className="workspace-page__header">
        <div>
          <p className="workspace-eyebrow">当前项目驾驶舱</p>
          <h1 id="overview-title">项目总览</h1>
        </div>
        <div className="workspace-actions">
          <button type="button" disabled={healthLoading} onClick={() => void checkHealth()}>
            {healthLoading ? "正在检查" : "运行环境预检"}
          </button>
          <Link className="workspace-primary-link" to="/director">继续制作</Link>
          {(snapshot?.pending_reviews ?? 0) > 0 ? <Link to="/quality">处理待审核</Link> : null}
        </div>
      </header>
      {healthResult ? <p className="workspace-feedback" role="status">{healthResult}</p> : null}

      <dl className="overview-metrics">
        {metrics.map(([label, value]) => (
          <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
        ))}
      </dl>

      <div className="overview-grid">
        <section className="workspace-panel" aria-labelledby="current-job-title">
          <h2 id="current-job-title">当前任务</h2>
          {currentJob ? (
            <div className="overview-job">
              <strong>{JOB_STATUS_LABELS[currentJob.status]}</strong>
              <span>{currentJob.message || STAGE_LABELS[currentJob.current_stage as StageKey] || "任务处理中"}</span>
              <span>{Math.round(currentJob.progress * 100)}%</span>
            </div>
          ) : <p className="workspace-empty-copy">暂无运行任务</p>}
        </section>
        <section className="workspace-panel" aria-labelledby="artifact-title">
          <h2 id="artifact-title">最近产物</h2>
          {artifacts.length ? (
            <div className="overview-artifact-gallery">
              {artifacts.map((artifact, index) => {
                const key = `${artifact.path}-${index}`;
                const label = artifact.shot_id || artifact.stage_key || artifact.kind;
                if (artifact.kind === "video" && artifact.media_url) {
                  return (
                    <div key={key} className="overview-artifact-item">
                      <video src={artifact.media_url} controls preload="metadata" />
                      <span>{label}</span>
                    </div>
                  );
                }
                if (artifact.kind === "composition" && artifact.media_url) {
                  return (
                    <div key={key} className="overview-artifact-item">
                      <video src={artifact.media_url} controls preload="metadata" />
                      <span>{label}</span>
                    </div>
                  );
                }
                if (artifact.kind === "image" && artifact.media_url) {
                  return (
                    <div key={key} className="overview-artifact-item">
                      <img src={artifact.media_url} alt={label} loading="lazy" />
                      <span>{label}</span>
                    </div>
                  );
                }
                if (artifact.kind === "audio" && artifact.media_url) {
                  return (
                    <div key={key} className="overview-artifact-item">
                      <audio src={artifact.media_url} controls preload="metadata" />
                      <span>{label}</span>
                    </div>
                  );
                }
                return (
                  <div key={key} className="overview-artifact-item">
                    <span>{artifact.path}</span>
                  </div>
                );
              })}
            </div>
          ) : <p className="workspace-empty-copy">暂无产物</p>}
        </section>
        <section className="workspace-panel" aria-labelledby="next-title">
          <h2 id="next-title">下一步建议</h2>
          {currentStage ? (
            <Link to={STAGE_ROUTES[currentStage.stage_key]}>继续{STAGE_LABELS[currentStage.stage_key]}</Link>
          ) : <p className="workspace-empty-copy">当前没有待推进阶段</p>}
        </section>
      </div>

      <section id="import" className="workspace-panel import-panel" aria-labelledby="import-title">
        <div className="workspace-section-heading">
          <div>
            <h2 id="import-title">小说导入</h2>
            <p>支持 TXT、Markdown、XML 与 Fountain 文本。</p>
          </div>
        </div>
        <div className="workspace-form-row">
          <label htmlFor="novel-file">选择小说文件</label>
          <input
            id="novel-file"
            type="file"
            accept=".txt,.md,.xml,.fountain"
            disabled={importing}
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setImportResult(null);
            }}
          />
          <button type="button" disabled={importing} onClick={() => void importNovel()}>
            {importing ? "正在上传并解析" : "上传并解析小说"}
          </button>
        </div>
        {importResult ? <p className="workspace-feedback" role="status">{importResult}</p> : null}
        {canStartProduction ? (
          <div className="workspace-form-row" style={{ marginTop: 12 }}>
            <button
              type="button"
              className="workspace-primary-button"
              disabled={creatingJob}
              onClick={() => void startProduction()}
            >
              {creatingJob ? "正在创建生产任务…" : "开始生产"}
            </button>
            <Link className="workspace-primary-link" to="/story">查看故事与角色</Link>
            <Link to="/tasks">前往任务队列</Link>
          </div>
        ) : null}
        {jobResult ? <p className="workspace-feedback" role="status">{jobResult}</p> : null}
      </section>

      <section className="workspace-panel" aria-labelledby="history-title">
        <h2 id="history-title">历史记录管理</h2>
        <ClearHistoryButton />
      </section>
    </section>
  );
};

export default ProjectOverview;

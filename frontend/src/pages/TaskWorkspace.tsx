import React, { useEffect, useMemo, useRef, useState } from "react";

import { userMessage } from "@/api/client";
import { api } from "@/api/jobs";
import { useJobStore } from "@/state/jobStore";
import { useWorkspaceStore } from "@/state/workspaceStore";
import type { ArtifactInfo, JobDetail, JobStatus, StepInfo } from "@/types/jobs";

const STATUS_LABELS: Record<JobStatus, string> = {
  draft: "草稿",
  queued: "排队中",
  running: "生产中",
  waiting_review: "待审核",
  retry_wait: "等待重试",
  failed: "失败",
  paused: "已暂停",
  completed: "已完成",
  cancelled: "已取消",
};

const STAGE_LABELS: Record<string, string> = {
  load_input: "小说导入",
  planning: "故事解析",
  visual_generate: "关键帧生成",
  audio_tts: "旁白生成",
  audio_sfx: "音效生成",
  composition_compose: "成片合成",
  export: "成片导出",
  import: "小说导入",
  story: "故事解析",
  character: "角色定妆",
  storyboard: "分镜规划",
  keyframe: "关键帧",
  video: "视频",
  audio: "音频",
  compose: "合成",
};

const ERROR_SUMMARIES: Record<string, string> = {
  GPU_OOM: "显存不足，请降低分辨率或释放显存后重试",
  MODEL_NOT_FOUND: "所需模型不存在，请检查模型配置",
  COMFYUI_UNAVAILABLE: "ComfyUI 无法连接，请确认服务已启动",
  INVALID_OUTPUT: "生成结果无效，请检查工作流和输出节点",
  MEDIA_CORRUPT: "媒体文件损坏，请重新生成该步骤",
};

const ACTIVE_CANCEL = new Set<JobStatus>(["queued", "running", "retry_wait", "paused"]);

function shotLabel(value: string | null): string {
  if (!value) return "未绑定镜头";
  const match = value.match(/(\d+)$/);
  return match ? `镜头 ${match[1].padStart(2, "0")}` : value;
}

function artifactLabel(asset: ArtifactInfo): string {
  const kinds: Record<string, string> = { image: "图片", video: "视频", audio: "音频", subtitle: "字幕", text: "文本" };
  return `版本 ${asset.version} · ${kinds[asset.kind] ?? asset.kind}`;
}

function TaskActions({ job }: { job: JobDetail }) {
  const { pauseJob, resumeJob, retryJob, cancelJob, reviewJob } = useJobStore();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ jobId: string; invalidated: string[] } | null>(null);
  const reviewStep = job.steps.find((step) => step.status === "waiting_review");

  const run = async (operation: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await operation();
    } catch (reason) {
      setError(userMessage(reason));
    } finally {
      setBusy(false);
    }
  };

  const loadRollback = async () => {
    if (!reviewStep) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.rollbackPreview(job.id, reviewStep.id);
      setPreview({ jobId: job.id, invalidated: result.invalidated_step_ids });
    } catch (reason) {
      setError(userMessage(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="task-actions" aria-label="任务操作">
      <h2>任务操作</h2>
      <div className="task-actions__buttons">
        {job.status === "running" ? <button type="button" disabled={busy} aria-label={`暂停任务 ${job.id}`} onClick={() => void run(() => pauseJob(job.id))}>暂停</button> : null}
        {job.status === "paused" ? <button type="button" disabled={busy} aria-label={`恢复任务 ${job.id}`} onClick={() => void run(() => resumeJob(job.id))}>恢复</button> : null}
        {job.status === "failed" ? <button type="button" disabled={busy} aria-label={`重试任务 ${job.id}`} onClick={() => void run(() => retryJob(job.id, reviewStep?.id))}>重试</button> : null}
        {job.status === "waiting_review" ? (
          <>
            <button type="button" disabled={busy} aria-label={`批准任务 ${job.id}`} onClick={() => void run(() => reviewJob(job.id, "approve"))}>批准</button>
            <button type="button" disabled={busy} aria-label={`重新生成任务 ${job.id}`} onClick={() => void run(() => reviewJob(job.id, "retry"))}>重新生成</button>
            <button type="button" disabled={busy || !reviewStep} aria-label={`回滚任务 ${job.id}`} onClick={() => void loadRollback()}>回滚</button>
          </>
        ) : null}
        {(ACTIVE_CANCEL.has(job.status) || job.status === "failed") ? <button type="button" disabled={busy} aria-label={`取消任务 ${job.id}`} onClick={() => void run(() => cancelJob(job.id))}>取消</button> : null}
      </div>
      {preview?.jobId === job.id ? (
        <div className="task-rollback" role="status">
          <p>将影响 {preview.invalidated.length} 个后续步骤</p>
          {preview.invalidated.length > 0 ? <ul>{preview.invalidated.map((id) => <li key={id}>{id}</li>)}</ul> : <p>没有后续步骤会失效</p>}
          <button type="button" disabled={busy} aria-label={`确认回滚任务 ${job.id}`} onClick={() => void run(async () => { await reviewJob(job.id, "rollback"); setPreview(null); })}>确认回滚</button>
          <button type="button" disabled={busy} onClick={() => setPreview(null)}>取消回滚</button>
        </div>
      ) : null}
      {error ? <p className="workspace-error" role="alert">{error}</p> : null}
    </aside>
  );
}

function StepRow({ step }: { step: StepInfo }) {
  return (
    <li className="task-step" data-status={step.status}>
      <div><strong>{STAGE_LABELS[step.ui_stage_key || step.stage_key] ?? STAGE_LABELS[step.stage_key] ?? step.stage_key}</strong><span>{shotLabel(step.shot_id)}</span></div>
      <div><span>{STATUS_LABELS[step.status as JobStatus] ?? step.status}</span><span>{Math.round(step.progress * 100)}%</span><span>第 {step.attempt} 次尝试</span></div>
    </li>
  );
}

function TaskDetail({ job }: { job: JobDetail }) {
  const failedStep = job.steps.find((step) => step.status === "failed");
  const errorCode = failedStep?.error_code ?? "";
  const technical = failedStep?.error_message || job.message;
  return (
    <section className="task-detail" aria-labelledby="task-detail-title">
      <header>
        <div><p className="workspace-eyebrow">任务详情</p><h2 id="task-detail-title">{job.id}</h2></div>
        <strong>{STATUS_LABELS[job.status]}</strong>
      </header>
      <dl className="task-detail__summary">
        <div><dt>当前阶段</dt><dd>{STAGE_LABELS[job.current_stage] ?? (job.current_stage || "尚未开始")}</dd></div>
        <div><dt>当前镜头</dt><dd>{shotLabel(job.current_shot)}</dd></div>
        <div><dt>整体进度</dt><dd>{Math.round(job.progress * 100)}%</dd></div>
      </dl>
      {job.status === "failed" ? (
        <section className="task-error" aria-labelledby="task-error-title">
          <h3 id="task-error-title">失败原因</h3>
          <p>{ERROR_SUMMARIES[errorCode] ?? "任务执行失败，请查看技术详情后重试"}</p>
          {errorCode ? <p>错误码：{errorCode}</p> : null}
          {technical ? <details><summary>原始技术详情</summary><pre>{technical}</pre></details> : null}
        </section>
      ) : null}
      <section><h3>制作步骤</h3><ol className="task-step-list">{job.steps.map((step) => <StepRow key={step.id} step={step} />)}</ol></section>
      <section><h3>任务产物</h3>{job.artifacts.length > 0 ? <ul className="task-artifacts">{job.artifacts.map((asset, index) => <li key={asset.id ?? `${asset.kind}-${index}`}><strong>{artifactLabel(asset)}</strong><span>{shotLabel(asset.shot_id)}</span></li>)}</ul> : <p className="workspace-muted">尚无产物</p>}</section>
    </section>
  );
}

interface TaskWorkspaceProps {
  manageLifecycle?: boolean;
}

export const TaskWorkspace: React.FC<TaskWorkspaceProps> = ({ manageLifecycle = true }) => {
  const projectId = useWorkspaceStore((state) => state.snapshot?.project_id ?? state.projectId);
  const selectObject = useWorkspaceStore((state) => state.selectObject);
  const {
    jobs,
    recentIds,
    loadingProjectId,
    loadError,
    loadProjectJobs,
    retryProjectJobs,
    subscribeActiveJobs,
  } = useJobStore();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [stageFilter, setStageFilter] = useState("");
  const lifecycleCleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!projectId || !manageLifecycle) return undefined;
    let cancelled = false;
    void loadProjectJobs(projectId).then((loaded) => {
      if (cancelled) return;
      lifecycleCleanupRef.current?.();
      lifecycleCleanupRef.current = subscribeActiveJobs();
      setSelectedId((current) => current && loaded.some((item) => item.id === current) ? current : loaded[0]?.id ?? null);
    }).catch(() => undefined);
    return () => {
      cancelled = true;
      lifecycleCleanupRef.current?.();
      lifecycleCleanupRef.current = null;
    };
  }, [loadProjectJobs, manageLifecycle, projectId, subscribeActiveJobs]);

  const retryLoad = async () => {
    await retryProjectJobs();
    if (manageLifecycle) {
      lifecycleCleanupRef.current?.();
      lifecycleCleanupRef.current = subscribeActiveJobs();
    }
  };

  const list = useMemo(
    () => recentIds
      .map((id) => jobs.get(id))
      .filter((item): item is JobDetail => Boolean(item && item.project_id === projectId)),
    [jobs, projectId, recentIds],
  );
  const stages = useMemo(() => [...new Set(list.map((item) => item.current_stage).filter(Boolean))], [list]);
  const filtered = list.filter((item) => (!statusFilter || item.status === statusFilter) && (!stageFilter || item.current_stage === stageFilter));
  const selectedJob = filtered.find((item) => item.id === selectedId) ?? filtered[0];

  useEffect(() => {
    const nextId = selectedJob?.id ?? null;
    if (selectedId !== nextId) setSelectedId(nextId);
    const current = useWorkspaceStore.getState().selectedObject;
    if (nextId) {
      if (current?.type !== "任务" || current.id !== nextId) {
        selectObject({ type: "任务", id: nextId });
      }
    } else if (current?.type === "任务") {
      selectObject(null);
    }
  }, [projectId, selectObject, selectedId, selectedJob?.id]);

  const selectJob = (id: string) => {
    setSelectedId(id);
    selectObject({ type: "任务", id });
  };

  return (
    <section className="workspace-page task-workspace-page" aria-labelledby="task-workspace-title">
      <header className="workspace-page__header"><div><p className="workspace-eyebrow">当前项目持久任务队列</p><h1 id="task-workspace-title">生成任务</h1></div></header>
      <div className="task-filters" aria-label="任务筛选">
        <label>任务状态<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">全部状态</option>{Object.entries(STATUS_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
        <label>制作阶段<select value={stageFilter} onChange={(event) => setStageFilter(event.target.value)}><option value="">全部阶段</option>{stages.map((value) => <option value={value} key={value}>{STAGE_LABELS[value] ?? value}</option>)}</select></label>
      </div>
      {loadingProjectId === projectId ? <p className="workspace-feedback" role="status">正在加载任务</p> : null}
      {loadError ? (
        <div className="workspace-error" role="alert">
          <p>{userMessage(loadError)}</p>
          <button type="button" onClick={() => void retryLoad().catch(() => undefined)}>重新加载任务</button>
        </div>
      ) : null}
      <div className="task-workspace">
        <nav className="task-list" aria-label="任务列表">
          {filtered.length === 0 ? <p className="workspace-muted">当前筛选条件下暂无任务</p> : filtered.map((item) => (
            <button type="button" key={item.id} aria-label={`选择任务 ${item.id}，${STATUS_LABELS[item.status]}`} aria-pressed={selectedJob?.id === item.id} onClick={() => selectJob(item.id)}>
              <span><strong>{item.id}</strong><span>{STATUS_LABELS[item.status]}</span></span>
              <span>{STAGE_LABELS[item.current_stage] ?? (item.current_stage || "尚未开始")} · {Math.round(item.progress * 100)}%</span>
            </button>
          ))}
        </nav>
        {selectedJob ? <TaskDetail job={selectedJob} /> : <section className="task-detail"><p className="workspace-muted">请选择任务查看详情</p></section>}
        {selectedJob ? <TaskActions key={selectedJob.id} job={selectedJob} /> : <aside className="task-actions" aria-label="任务操作"><p className="workspace-muted">选择任务后显示可用操作</p></aside>}
      </div>
    </section>
  );
};

export default TaskWorkspace;

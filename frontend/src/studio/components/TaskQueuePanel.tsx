import React from "react";

import { jobStoreActions, useJobStore } from "@/state/jobStore";
import type { JobDetail, JobStatus } from "@/types/jobs";

const STATUS_LABEL: Record<JobStatus, string> = {
  draft: "草稿",
  queued: "排队中",
  running: "运行中",
  waiting_review: "待审核",
  retry_wait: "等待重试",
  failed: "失败",
  paused: "已暂停",
  completed: "已完成",
  cancelled: "已取消",
};

function shotLabel(job: JobDetail): string {
  if (job.current_shot) return job.current_shot;
  if (job.current_stage) return job.current_stage;
  return job.id.slice(0, 8);
}

const TaskQueuePanel: React.FC = () => {
  const store = useJobStore();
  const jobs = store.recentIds
    .map((id) => store.jobs.get(id))
    .filter((job): job is JobDetail => Boolean(job))
    .slice(0, 7);

  const counts = jobs.reduce(
    (acc, job) => {
      if (job.status === "running") acc.running += 1;
      else if (job.status === "queued" || job.status === "retry_wait") acc.queued += 1;
      else if (job.status === "completed") acc.completed += 1;
      else if (job.status === "failed") acc.failed += 1;
      return acc;
    },
    { running: 0, queued: 0, completed: 0, failed: 0 },
  );

  return (
    <aside className="studio-panel task-queue-panel" aria-label="任务队列">
      <div className="studio-panel__header">
        <div><strong>任务队列</strong><span>{jobs.length || 0} 个任务</span></div>
      </div>
      <div className="task-queue-summary">
        <span><b>{counts.running}</b>运行中</span>
        <span><b>{counts.queued}</b>排队中</span>
        <span><b>{counts.completed}</b>已完成</span>
        <span><b>{counts.failed}</b>失败</span>
      </div>
      <div className="task-queue-list">
        {jobs.length === 0 ? (
          <div className="studio-empty">暂无任务。导入小说后可直接开始一键生产。</div>
        ) : jobs.map((job) => (
          <article key={job.id} className="task-card">
            <div className="task-card__title">
              <strong>{shotLabel(job)}</strong>
              <span className={`status-chip status-chip--${job.status}`}>{STATUS_LABEL[job.status]}</span>
            </div>
            <p>{job.message || "本地生产任务"}</p>
            <div className="task-card__progress-row">
              <div className="studio-progress"><i style={{ width: `${Math.round(job.progress * 100)}%` }} /></div>
              <span>{Math.round(job.progress * 100)}%</span>
            </div>
            <div className="task-card__actions">
              {job.status === "running" ? (
                <button type="button" onClick={() => void jobStoreActions().pauseJob(job.id)}>暂停</button>
              ) : null}
              {job.status === "paused" ? (
                <button type="button" onClick={() => void jobStoreActions().resumeJob(job.id)}>继续</button>
              ) : null}
              {job.status === "failed" ? (
                <button type="button" onClick={() => void jobStoreActions().retryJob(job.id)}>重试</button>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </aside>
  );
};

export default TaskQueuePanel;

import React from "react";

import GlobalTaskBar from "@/components/layout/GlobalTaskBar";
import ClearHistoryButton from "@/components/settings/ClearHistoryButton";
import { useWorkspaceStore } from "@/state/workspaceStore";
import "@/styles/clear-history.css";

function percent(value: number): number {
  const normalized = value <= 1 ? value * 100 : value;
  return Math.round(Math.max(0, Math.min(100, normalized)));
}

function databaseLabel(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  const healthy =
    value === true ||
    (typeof value === "string" && ["ok", "healthy", "ready", "available"].includes(value.toLowerCase()));
  return healthy ? "数据库正常" : "数据库异常";
}

const ProjectHeader: React.FC = () => {
  const snapshot = useWorkspaceStore((state) => state.snapshot);
  const loading = useWorkspaceStore((state) => state.loading);
  const error = useWorkspaceStore((state) => state.error);
  const projectTitle = snapshot?.title ?? (error ? "项目尚未载入" : "正在载入项目");
  const saveStatus = error ? "尚未同步" : snapshot ? "已自动保存" : "正在同步";
  const database = databaseLabel(snapshot?.system_health.database);
  const healthJobCount = snapshot?.system_health.jobs;

  return (
    <header className="wb-header">
      <div className="wb-header__identity">
        <span className="wb-header__brand">AI 漫画工作台</span>
        <span className="wb-header__divider" aria-hidden="true" />
        <div className="wb-header__project">
          <strong title={projectTitle}>{projectTitle}</strong>
          <div className="wb-header__project-meta">
            <span>{snapshot?.version ? `版本 ${snapshot.version}` : "版本尚未载入"}</span>
            <span aria-hidden="true"> · </span>
            <span>{loading ? "正在同步" : saveStatus}</span>
          </div>
        </div>
      </div>

      <div className="wb-header__metrics" aria-label="项目进度摘要">
        <span>整体进度 {snapshot ? `${percent(snapshot.progress)}%` : "暂无数据"}</span>
        <span>待审核 {snapshot ? snapshot.pending_reviews : "暂无数据"}</span>
        <span>{snapshot?.estimated_minutes == null ? "暂无估算" : `预计 ${snapshot.estimated_minutes} 分钟`}</span>
      </div>

      <div className="wb-header__right">
        {snapshot && (database || typeof healthJobCount === "number") ? (
          <div className="wb-header__health" aria-label="系统状态">
            {database ? <span data-health={database === "数据库正常" ? "ok" : "error"}>{database}</span> : null}
            {typeof healthJobCount === "number" ? <span>{healthJobCount} 个任务</span> : null}
          </div>
        ) : null}
        <ClearHistoryButton compact />
        <GlobalTaskBar />
      </div>

      {error ? <p className="wb-header__error" role="alert">{error}</p> : null}
    </header>
  );
};

export default ProjectHeader;

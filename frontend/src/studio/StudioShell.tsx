import React, { useEffect, useLayoutEffect, useRef } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { CloudServerOutlined, SettingOutlined } from "@ant-design/icons";

import { STUDIO_NAVIGATION } from "@/studio/studioNavigation";
import { useProjectStore } from "@/state/projectStore";
import { jobStoreActions, useJobStore } from "@/state/jobStore";
import { useWorkspaceStore } from "@/state/workspaceStore";

const StudioShell: React.FC = () => {
  const legacyProjectId = useProjectStore((state) => state.project?.id);
  const projectIdFromWorkspace = useWorkspaceStore((state) => state.projectId);
  const snapshot = useWorkspaceStore((state) => state.snapshot);
  const loading = useWorkspaceStore((state) => state.loading);
  const { loadedProjectId, loadRevision } = useJobStore();
  const projectId = legacyProjectId || projectIdFromWorkspace || "default";
  const resetRef = useRef<string | null>(null);

  useLayoutEffect(() => {
    if (resetRef.current === projectId) return;
    resetRef.current = projectId;
    jobStoreActions().resetProjectJobs(projectId);
  }, [projectId]);

  useEffect(() => {
    const state = useWorkspaceStore.getState();
    const sameProject = state.snapshot?.project_id === projectId;
    if (!sameProject && !(state.loading && state.projectId === projectId)) {
      void state.loadWorkspace(projectId).catch(() => undefined);
    }
  }, [projectId]);

  useEffect(() => {
    if (snapshot?.project_id !== projectId) return;
    void jobStoreActions().loadProjectJobs(projectId).catch(() => undefined);
  }, [projectId, snapshot?.project_id]);

  useEffect(() => {
    if (snapshot?.project_id !== projectId || loadedProjectId !== projectId) return undefined;
    return jobStoreActions().subscribeActiveJobs();
  }, [loadedProjectId, loadRevision, projectId, snapshot?.project_id]);

  return (
    <div className="studio-shell">
      <header className="studio-topbar">
        <div className="studio-brand" aria-label="AI Manga Studio">
          <span className="studio-brand__mark">A</span>
          <span>AI Manga Studio</span>
        </div>
        <nav className="studio-nav" aria-label="制作工作台导航">
          {STUDIO_NAVIGATION.map(({ path, label, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              className={({ isActive }) => `studio-nav__item${isActive ? " is-active" : ""}`}
            >
              <Icon />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="studio-topbar__status">
          <span className="studio-local-badge"><i />本地模式</span>
          <button type="button" className="studio-icon-button" aria-label="工作区设置"><SettingOutlined /></button>
        </div>
      </header>

      <div className="studio-subbar">
        <div>
          <strong>{snapshot?.title || "当前项目"}</strong>
          <span>{snapshot?.source_path || `项目 ${projectId}`}</span>
        </div>
        <div className="studio-subbar__meta">
          <span><CloudServerOutlined /> {loading ? "正在连接本地服务" : "本地服务已就绪"}</span>
          <span>版本 {snapshot?.version || "—"}</span>
          <span>进度 {Math.round((snapshot?.progress || 0) * 100)}%</span>
        </div>
      </div>

      <main className="studio-main">
        <Outlet />
      </main>

      <footer className="studio-statusbar">
        <span><i className="status-dot" /> 项目自动保存</span>
        <span>数据本地存储 · 任务可观察 · 版本可回退</span>
        <span>ComfyUI / Wan / Flux / CosyVoice / FFmpeg</span>
      </footer>
    </div>
  );
};

export default StudioShell;

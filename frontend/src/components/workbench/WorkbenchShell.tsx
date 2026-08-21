import React, { useEffect, useLayoutEffect, useRef } from "react";
import { Outlet } from "react-router-dom";

import InspectorPanel from "@/components/workbench/InspectorPanel";
import ProjectHeader from "@/components/workbench/ProjectHeader";
import StageRail from "@/components/workbench/StageRail";
import WorkspaceSidebar from "@/components/workbench/WorkspaceSidebar";
import { jobStoreActions, useJobStore } from "@/state/jobStore";
import { useProjectStore } from "@/state/projectStore";
import { useWorkspaceStore } from "@/state/workspaceStore";
import "@/styles/workbench.css";

const WorkbenchShell: React.FC = () => {
  const legacyProjectId = useProjectStore((state) => state.project?.id);
  const workspaceProjectId = useWorkspaceStore((state) => state.projectId);
  const snapshotProjectId = useWorkspaceStore((state) => state.snapshot?.project_id);
  const { loadedProjectId, loadRevision } = useJobStore();
  const projectId = legacyProjectId || workspaceProjectId || "default";
  const resetProjectRef = useRef<string | null>(null);

  useLayoutEffect(() => {
    if (resetProjectRef.current === projectId) return;
    resetProjectRef.current = projectId;
    jobStoreActions().resetProjectJobs(projectId);
  }, [projectId]);

  useEffect(() => {
    const currentWorkspace = useWorkspaceStore.getState();
    const hasMatchingSnapshot = currentWorkspace.snapshot?.project_id === projectId;
    const isLoadingTarget =
      currentWorkspace.loading && currentWorkspace.projectId === projectId;
    if (!hasMatchingSnapshot && !isLoadingTarget) {
      void useWorkspaceStore.getState().loadWorkspace(projectId).catch(() => undefined);
    }
  }, [projectId, snapshotProjectId, workspaceProjectId]);

  useEffect(() => {
    if (snapshotProjectId !== projectId) return;

    const actions = jobStoreActions();
    void actions.loadProjectJobs(projectId).catch(() => undefined);
  }, [projectId, snapshotProjectId]);

  useEffect(() => {
    if (snapshotProjectId !== projectId || loadedProjectId !== projectId) return undefined;
    return jobStoreActions().subscribeActiveJobs();
  }, [loadedProjectId, loadRevision, projectId, snapshotProjectId]);

  return (
    <div className="wb-shell">
      <ProjectHeader />
      <div className="wb-shell__body">
        <WorkspaceSidebar />
        <section className="wb-shell__workspace" aria-label="当前项目制作区">
          <StageRail />
          <main className="wb-shell__content">
            <Outlet />
          </main>
        </section>
        <InspectorPanel />
      </div>
    </div>
  );
};

export default WorkbenchShell;

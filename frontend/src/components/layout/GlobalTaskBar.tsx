import React from "react";
import { Link } from "react-router-dom";
import { ThunderboltOutlined } from "@ant-design/icons";

import { useJobStore } from "@/state/jobStore";
import { useProjectStore } from "@/state/projectStore";
import { useWorkspaceStore } from "@/state/workspaceStore";

const ACTIVE_STATUSES = new Set(["queued", "running", "waiting_review", "retry_wait"]);

const GlobalTaskBar: React.FC = () => {
  const { jobs, recentIds } = useJobStore();
  const legacyProjectId = useProjectStore((state) => state.project?.id);
  const workspaceProjectId = useWorkspaceStore((state) => state.projectId);
  const snapshotProjectId = useWorkspaceStore((state) => state.snapshot?.project_id);
  const targetProjectId = legacyProjectId || workspaceProjectId || "default";
  const activeCount = recentIds.reduce((count, id) => {
    const job = jobs.get(id);
    return snapshotProjectId === targetProjectId &&
      job?.project_id === snapshotProjectId &&
      ACTIVE_STATUSES.has(job.status)
      ? count + 1
      : count;
  }, 0);
  const status = activeCount > 0 ? `${activeCount} 个运行中` : "暂无运行任务";

  return (
    <Link className="wb-task-shortcut" to="/tasks" aria-label={`生成任务 ${status}`}>
      <ThunderboltOutlined aria-hidden="true" />
      <span>生成任务</span>
      <span className="wb-task-shortcut__status">
        {status}
      </span>
    </Link>
  );
};

export default GlobalTaskBar;

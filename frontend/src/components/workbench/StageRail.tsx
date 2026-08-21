import React from "react";
import { NavLink } from "react-router-dom";

import { useWorkspaceStore } from "@/state/workspaceStore";
import { STAGE_KEYS, type StageKey, type StageSummary } from "@/workbench/types";

const stageMetadata: Record<StageKey, { label: string; route: string }> = {
  import: { label: "导入", route: "/overview" },
  story: { label: "故事解析", route: "/story" },
  character: { label: "角色定妆", route: "/story" },
  storyboard: { label: "分镜规划", route: "/director" },
  keyframe: { label: "关键帧", route: "/director" },
  video: { label: "视频", route: "/creator" },
  audio: { label: "音频", route: "/director" },
  compose: { label: "合成", route: "/director" },
  export: { label: "导出", route: "/export" },
};

const statusLabels: Record<string, string> = {
  pending: "未开始",
  queued: "排队中",
  running: "生产中",
  retry_wait: "等待重试",
  waiting_review: "待审核",
  failed: "失败",
  completed: "已完成",
  invalidated: "需要更新",
  cancelled: "已取消",
};

function progressValue(stage?: StageSummary): number {
  if (!stage) return 0;
  const normalized = stage.progress <= 1 ? stage.progress * 100 : stage.progress;
  return Math.round(Math.max(0, Math.min(100, normalized)));
}

const StageRail: React.FC = () => {
  const snapshot = useWorkspaceStore((state) => state.snapshot);
  const stageByKey = new Map(snapshot?.stages.map((stage) => [stage.stage_key, stage]) ?? []);

  const toggleAutomation = (stageKey: StageKey, current: boolean) => {
    void useWorkspaceStore
      .getState()
      .setStageAutomation(stageKey, { auto_produce: !current })
      .catch(() => undefined);
  };

  return (
    <section className="wb-stage-rail" aria-label="制作阶段">
      <ol className="wb-stage-rail__list">
        {STAGE_KEYS.map((stageKey) => {
          const stage = stageByKey.get(stageKey);
          const metadata = stageMetadata[stageKey];
          const progress = progressValue(stage);
          const automation = stage?.automation.auto_produce ?? false;
          const disabledDescription = `${stageKey}-automation-description`;
          const status = stage ? statusLabels[stage.status] ?? "状态未知" : "未开始";
          return (
            <li className="wb-stage" data-status={stage?.status ?? "pending"} key={stageKey}>
              <div className="wb-stage__topline">
                <NavLink to={metadata.route}>{metadata.label}</NavLink>
                <span className="wb-stage__progress">{progress}%</span>
              </div>
              <div className="wb-stage__status">
                <span>{status}</span>
                {stage && stage.waiting_review > 0 ? <span>待审 {stage.waiting_review}</span> : null}
              </div>
              <div className="wb-stage__bar" aria-hidden="true">
                <span style={{ width: `${progress}%` }} />
              </div>
              <button
                type="button"
                role="switch"
                aria-label={`${metadata.label}自动生产`}
                aria-checked={automation}
                aria-describedby={!stage ? disabledDescription : undefined}
                disabled={!stage}
                onClick={() => stage && toggleAutomation(stageKey, automation)}
              >
                <span className="wb-stage__switch-indicator" aria-hidden="true" />
                <span>{automation ? "自动" : "手动确认"}</span>
              </button>
              {!stage ? (
                <span className="wb-visually-hidden" id={disabledDescription}>
                  项目载入后可设置自动生产
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
};

export default StageRail;

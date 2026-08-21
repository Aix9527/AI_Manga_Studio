import React from "react";
import type { ReactNode } from "react";

export interface PipelineStepProps {
  index: number;
  title: string;
  description: string;
  status: "completed" | "running" | "waiting";
  progress?: number;
  icon: ReactNode;
}

const STATUS_LABELS = {
  completed: "已完成",
  running: "生成中",
  waiting: "等待中",
};

const PipelineStep: React.FC<PipelineStepProps> = ({
  index,
  title,
  description,
  status,
  progress = 0,
  icon,
}) => (
  <article className={`pipeline-step pipeline-step--${status}`}>
    <div className="pipeline-step__heading">
      <span>{index}</span>
      <strong>{title}</strong>
    </div>
    <div className="pipeline-step__icon">{icon}</div>
    <p>{description}</p>
    <div className="pipeline-step__footer">
      <span className="pipeline-step__status">{STATUS_LABELS[status]}</span>
      {status === "running" ? <span>{Math.round(progress * 100)}%</span> : null}
    </div>
    {status === "running" ? (
      <div className="studio-progress"><i style={{ width: `${Math.round(progress * 100)}%` }} /></div>
    ) : null}
  </article>
);

export default PipelineStep;

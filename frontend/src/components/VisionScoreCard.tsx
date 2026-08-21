import React from "react";

import RegenerateButton from "@/components/RegenerateButton";

export interface VisionScore {
  key: string;
  label: string;
  score: number;
}

interface VisionScoreCardProps {
  assetId: number;
  version: number;
  shotId: string;
  title: string;
  overallScore: number | null;
  scores: VisionScore[];
  passed: boolean | null;
  issues: string[];
  suggestions: string[];
  qualityAttempt: number;
  hasReport: boolean;
  preview: React.ReactNode;
  disabled?: boolean;
  disabledReason?: string;
  isRegenerating?: boolean;
  onRegenerate?: () => void;
}

function scoreText(score: number): string {
  return `${(score * 10).toFixed(1)} / 10`;
}

export const VisionScoreCard: React.FC<VisionScoreCardProps> = ({
  assetId,
  version,
  shotId,
  title,
  overallScore,
  scores,
  passed,
  issues,
  suggestions,
  qualityAttempt,
  hasReport,
  preview,
  disabled = false,
  disabledReason,
  isRegenerating = false,
  onRegenerate,
}) => (
  <article className="quality-card" data-quality-status={passed === null ? "unknown" : passed ? "passed" : "failed"}>
    <header className="quality-card__header">
      <div>
        <h2>{title}</h2>
        <p>自动重试 {qualityAttempt} / 2</p>
      </div>
      {hasReport ? (
        <div className="quality-card__summary">
          {overallScore !== null ? <strong>{scoreText(overallScore)}</strong> : null}
          <span>{passed === null ? "未给出结论" : passed ? "质检通过" : "质检未通过"}</span>
        </div>
      ) : null}
    </header>
    <div className="quality-card__body">
      <div className="quality-card__preview">{preview}</div>
      <div className="quality-card__report">
        {!hasReport ? <p className="quality-card__empty">尚无质检报告</p> : null}
        {scores.length > 0 ? (
          <dl className="quality-score-list">
            {scores.map((score) => (
              <div key={score.key}>
                <dt>{score.label}</dt>
                <dd>{scoreText(score.score)}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        {issues.length > 0 ? (
          <section><h3>质检问题</h3><ul>{issues.map((issue) => <li key={issue}>{issue}</li>)}</ul></section>
        ) : null}
        {suggestions.length > 0 ? (
          <section><h3>修改建议</h3><ul>{suggestions.map((item) => <li key={item}>{item}</li>)}</ul></section>
        ) : null}
      </div>
    </div>
    {onRegenerate ? (
      <RegenerateButton
        assetId={assetId}
        version={version}
        shotId={shotId}
        disabled={disabled}
        disabledReason={disabledReason}
        isRegenerating={isRegenerating}
        feedbackActions={[]}
        onRegenerate={onRegenerate}
      />
    ) : null}
  </article>
);

export default VisionScoreCard;

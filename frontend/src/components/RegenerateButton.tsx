import { ReloadOutlined } from "@ant-design/icons";
import React, { useId } from "react";

interface RegenerateButtonProps {
  assetId: number;
  version: number;
  shotId: string;
  disabled?: boolean;
  disabledReason?: string;
  isRegenerating?: boolean;
  feedbackActions?: string[];
  onRegenerate: () => void;
}

export const RegenerateButton: React.FC<RegenerateButtonProps> = ({
  assetId,
  version,
  shotId,
  disabled = false,
  disabledReason,
  isRegenerating = false,
  feedbackActions = [],
  onRegenerate,
}) => {
  const reasonId = useId();
  const unavailableReason = isRegenerating ? "正在提交版本重生请求" : disabledReason;
  return (
    <div className="quality-regenerate" data-asset-id={assetId} data-version={version} data-shot-id={shotId}>
      <button
        type="button"
        className="quality-regenerate__button"
        onClick={onRegenerate}
        disabled={disabled || isRegenerating}
        aria-label={isRegenerating ? "正在根据质检建议重新生成" : "根据质检建议重新生成"}
        aria-busy={isRegenerating}
        aria-describedby={unavailableReason ? reasonId : undefined}
      >
        <ReloadOutlined aria-hidden="true" />
        {isRegenerating ? "正在重新生成…" : "根据质检建议重新生成"}
      </button>
      {unavailableReason ? <p id={reasonId} className="quality-regenerate__reason">{unavailableReason}</p> : null}
      {feedbackActions.length > 0 ? (
        <details className="quality-regenerate__details">
          <summary>查看本次质检建议</summary>
          <ul>{feedbackActions.map((action) => <li key={action}>{action}</li>)}</ul>
        </details>
      ) : null}
    </div>
  );
};

export default RegenerateButton;

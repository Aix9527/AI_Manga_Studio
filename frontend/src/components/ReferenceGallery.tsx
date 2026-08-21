import { DeleteOutlined } from "@ant-design/icons";
import React from "react";

export interface ReferenceImage {
  id: string;
  url: string;
  label: string;
  characterId: string;
}

interface ReferenceGalleryProps {
  characterId: string;
  characterName: string;
  references: ReferenceImage[];
  onAddReference?: () => void;
  onDeleteReference?: (id: string) => void;
  selectedId?: string;
  onSelect?: (ref: ReferenceImage) => void;
}

const LABELS: Record<string, string> = {
  front: "正面",
  side: "侧面",
  action: "动作",
  expression: "表情",
};

function referenceLabel(label: string): string {
  return LABELS[label.toLowerCase()] ?? "补充参考";
}

export const ReferenceGallery: React.FC<ReferenceGalleryProps> = ({
  characterId,
  characterName,
  references,
  onAddReference,
  onDeleteReference,
  selectedId,
  onSelect,
}) => (
  <div className="workspace-reference-gallery" data-character-id={characterId}>
    <div className="workspace-section-heading">
      <div>
        <h4>{characterName}</h4>
        <p>参考图库 · {references.length} 张</p>
      </div>
      {onAddReference ? (
        <button type="button" className="workspace-primary-button" onClick={onAddReference}>
          添加参考图
        </button>
      ) : null}
    </div>

    {references.length === 0 ? (
      <p className="workspace-empty-copy">尚无参考图，请添加正面、侧面、动作或表情参考。</p>
    ) : (
      <div className="workspace-reference-grid">
        {references.map((reference) => {
          const label = referenceLabel(reference.label);
          return (
            <div className="workspace-reference-card" key={reference.id}>
              <button
                type="button"
                className="workspace-reference-select"
                aria-label={`选择参考图：${label}`}
                aria-pressed={reference.id === selectedId}
                onClick={() => onSelect?.(reference)}
              >
                <span className="workspace-reference-image">
                  {reference.url ? (
                    <img src={reference.url} alt={`${characterName}：${label}`} />
                  ) : (
                    <span>缺少图像</span>
                  )}
                </span>
                <span>{label}</span>
              </button>
              {onDeleteReference ? (
                <button
                  type="button"
                  className="workspace-reference-delete"
                  aria-label={`删除参考图：${label}`}
                  onClick={() => onDeleteReference(reference.id)}
                >
                  <DeleteOutlined aria-hidden="true" />
                </button>
              ) : null}
            </div>
          );
        })}
      </div>
    )}
  </div>
);

export default ReferenceGallery;

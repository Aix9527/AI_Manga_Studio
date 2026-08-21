import React from "react";

import ShotInspector from "@/components/workbench/ShotInspector";
import { useStoryStore } from "@/state/storyStore";
import { useWorkspaceStore } from "@/state/workspaceStore";

const InspectorPanel: React.FC = () => {
  const selectedObject = useWorkspaceStore((state) => state.selectedObject);
  const selectedShotId = useStoryStore((state) => state.selectedShotId);
  const showingShot = selectedObject
    ? selectedObject.type === "镜头"
    : Boolean(selectedShotId);

  return (
    <aside
      className="wb-inspector"
      aria-label={showingShot ? "镜头参数" : "属性检查器"}
      data-collapsed={showingShot ? "false" : "true"}
    >
      <div className="wb-inspector__heading">
        <span>{showingShot ? "镜头参数" : "属性检查器"}</span>
        <span>当前选择</span>
      </div>
      {showingShot && selectedShotId ? (
        <ShotInspector />
      ) : selectedObject?.type === "镜头" ? (
        <div className="wb-inspector__selection">
          <p className="wb-inspector__object" title={`${selectedObject.type} · ${selectedObject.id}`}>
            {selectedObject.type} · {selectedObject.id}
          </p>
          <ShotInspector />
        </div>
      ) : !selectedObject ? (
        <div className="wb-inspector__empty">
          <strong>尚未选择对象</strong>
          <p>选择角色、镜头、素材或任务后，在这里查看属性与生成参数。</p>
        </div>
      ) : (
        <div className="wb-inspector__selection">
          <p className="wb-inspector__object" title={`${selectedObject.type} · ${selectedObject.id}`}>
            {selectedObject.type} · {selectedObject.id}
          </p>
        </div>
      )}
    </aside>
  );
};

export default InspectorPanel;

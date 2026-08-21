import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import * as pipelineApi from "@/api/pipeline";
import ShotGrid from "@/components/workbench/ShotGrid";
import ShotTimeline from "@/components/workbench/ShotTimeline";
import { useProjectStore } from "@/state/projectStore";
import { useStoryStore } from "@/state/storyStore";
import { useWorkspaceStore } from "@/state/workspaceStore";
import "@/styles/director.css";

const StoryboardDirector: React.FC = () => {
  const legacyNovelId = useProjectStore((state) => state.project?.novel_id);
  const snapshotProjectId = useWorkspaceStore((state) => state.snapshot?.project_id);
  const novelId = legacyNovelId || snapshotProjectId || "";
  const scenes = useStoryStore((state) => state.scenes);
  const shots = useStoryStore((state) => state.shots);
  const storyboardNovelId = useStoryStore((state) => state.storyboardNovelId);
  const loading = useStoryStore((state) => state.loading);
  const loadError = useStoryStore((state) => state.error);
  const selectedShotId = useStoryStore((state) => state.selectedShotId);
  const selectedShotIds = useStoryStore((state) => state.selectedShotIds);
  const loadStoryboard = useStoryStore((state) => state.loadStoryboard);
  const invalidateRequests = useStoryStore((state) => state.invalidateRequests);
  const selectShotInStore = useStoryStore((state) => state.selectShot);
  const toggleShotSelection = useStoryStore((state) => state.toggleShotSelection);
  const selectObject = useWorkspaceStore((state) => state.selectObject);
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null);
  const [batchFeedback, setBatchFeedback] = useState<string | null>(null);
  const [batchCompiling, setBatchCompiling] = useState(false);
  const batchOperationRef = useRef(0);
  const mountedRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      batchOperationRef.current += 1;
    };
  }, []);

  useEffect(() => {
    batchOperationRef.current += 1;
    setBatchCompiling(false);
    setBatchFeedback(null);
    if (!novelId) return undefined;
    selectObject(null);
    void loadStoryboard(novelId);
    return () => {
      batchOperationRef.current += 1;
      invalidateRequests();
    };
  }, [invalidateRequests, loadStoryboard, novelId, selectObject]);

  useEffect(() => {
    setSelectedSceneId((current) => {
      if (current && scenes.some((scene) => scene.id === current)) return current;
      return scenes[0]?.id ?? null;
    });
  }, [scenes]);

  const selectedShotsInOrder = useMemo(() => {
    const ids = new Set(selectedShotIds);
    return shots.filter((shot) => ids.has(shot.id));
  }, [selectedShotIds, shots]);

  const selectShot = (shotId: string) => {
    selectShotInStore(shotId);
    selectObject({ type: "镜头", id: shotId });
  };

  const selectScene = (sceneId: string) => {
    setSelectedSceneId(sceneId);
    const targetScene = scenes.find((scene) => scene.id === sceneId);
    if (selectedShotId && !targetScene?.shots.some((shot) => shot.id === selectedShotId)) {
      selectShotInStore(null);
      if (useWorkspaceStore.getState().selectedObject?.type === "镜头") {
        selectObject(null);
      }
    }
  };

  const compileSelected = async () => {
    if (!selectedShotsInOrder.length) return;
    const operationToken = ++batchOperationRef.current;
    const operationNovelId = novelId;
    const isCurrentOperation = () => {
      const projectNovelId = useProjectStore.getState().project?.novel_id;
      const workspaceProjectId = useWorkspaceStore.getState().snapshot?.project_id;
      const currentNovelId = projectNovelId || workspaceProjectId || "";
      return mountedRef.current
        && batchOperationRef.current === operationToken
        && currentNovelId === operationNovelId;
    };
    setBatchCompiling(true);
    setBatchFeedback(null);
    let succeeded = 0;
    let failed = 0;
    for (let index = 0; index < selectedShotsInOrder.length; index += 1) {
      if (!isCurrentOperation()) return;
      setBatchFeedback(`正在编译 ${index + 1}/${selectedShotsInOrder.length}`);
      try {
        await pipelineApi.compileSingleShot(selectedShotsInOrder[index]);
        if (!isCurrentOperation()) return;
        succeeded += 1;
      } catch {
        if (!isCurrentOperation()) return;
        failed += 1;
      }
    }
    if (!isCurrentOperation()) return;
    setBatchFeedback(`编译完成：成功 ${succeeded} 个，失败 ${failed} 个`);
    setBatchCompiling(false);
  };

  const loaded = storyboardNovelId === novelId;

  return (
    <div className="workspace-page director-page">
      <div className="workspace-page__header director-header">
        <div>
          <p className="workspace-eyebrow">全片制作视图</p>
          <h1>分镜导演台</h1>
        </div>
      </div>

      <div className="director-batch-bar">
        <strong>已选择 {selectedShotIds.length} 个镜头</strong>
        <button
          type="button"
          disabled={!selectedShotIds.length || batchCompiling}
          onClick={() => void compileSelected()}
        >
          编译所选镜头提示词
        </button>
        {batchFeedback ? <span role="status">{batchFeedback}</span> : null}
      </div>

      {loading && !loaded ? <p className="workspace-feedback" role="status">正在恢复分镜…</p> : null}
      {loadError && (!loaded || scenes.length === 0) ? (
        <div className="workspace-load-error" role="alert">
          <p>{loadError}</p>
          <button type="button" onClick={() => void loadStoryboard(novelId)}>重试加载分镜</button>
        </div>
      ) : null}
      {!loading && loaded && scenes.length === 0 ? (
        <section className="workspace-empty-state">
          <h2>此项目尚未生成分镜</h2>
          <p className="workspace-empty-copy">请先在故事与角色模块生成 canonical 故事结构。</p>
          <Link to="/story">返回故事与角色</Link>
        </section>
      ) : null}
      {scenes.length > 0 ? (
        <>
          <ShotGrid
            scenes={scenes}
            selectedSceneId={selectedSceneId}
            selectedShotId={selectedShotId}
            selectedShotIds={selectedShotIds}
            onSelectScene={selectScene}
            onSelectShot={selectShot}
            onToggleBatch={toggleShotSelection}
          />
          <ShotTimeline shots={shots} selectedShotId={selectedShotId} onSelectShot={selectShot} />
        </>
      ) : null}
    </div>
  );
};

export default StoryboardDirector;

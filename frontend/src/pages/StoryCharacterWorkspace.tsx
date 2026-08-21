import React, { useEffect, useState } from "react";

import CharacterBiblePanel from "@/pages/CharacterStudio";
import StoryStructurePanel from "@/pages/StoryGraphViewer";
import { useCharacterStore } from "@/state/characterStore";
import { useProjectStore } from "@/state/projectStore";
import { useStoryStore } from "@/state/storyStore";
import { useWorkspaceStore } from "@/state/workspaceStore";

type WorkspaceTab = "story" | "characters";

export const StoryCharacterWorkspace: React.FC = () => {
  const [tab, setTab] = useState<WorkspaceTab>("story");
  const snapshotProjectId = useWorkspaceStore((state) => state.snapshot?.project_id);
  const legacyNovelId = useProjectStore((state) => state.project?.novel_id);
  const novelId = legacyNovelId || snapshotProjectId || "";
  const storyError = useStoryStore((state) => state.error);
  const characterError = useCharacterStore((state) => state.error);
  const loadGraph = useStoryStore((state) => state.loadGraph);
  const loadCharacters = useCharacterStore((state) => state.loadCharacters);
  const invalidateStoryRequests = useStoryStore((state) => state.invalidateRequests);
  const invalidateCharacterRequests = useCharacterStore((state) => state.invalidateRequests);

  const reload = () => {
    if (!novelId) return;
    void Promise.all([loadGraph(novelId), loadCharacters(novelId)]);
  };

  useEffect(() => {
    reload();
    return () => {
      invalidateStoryRequests();
      invalidateCharacterRequests();
    };
  }, [novelId]);

  return (
    <section className="workspace-page story-character-page" aria-labelledby="story-character-title">
      <header className="workspace-page__header">
        <div>
          <p className="workspace-eyebrow">故事结构与角色圣经</p>
          <h1 id="story-character-title">故事与角色</h1>
        </div>
      </header>
      <div className="workspace-tabs" role="tablist" aria-label="故事与角色视图">
        <button
          type="button"
          id="story-tab"
          role="tab"
          aria-selected={tab === "story"}
          aria-controls="story-panel"
          onClick={() => setTab("story")}
        >
          故事结构
        </button>
        <button
          type="button"
          id="characters-tab"
          role="tab"
          aria-selected={tab === "characters"}
          aria-controls="characters-panel"
          onClick={() => setTab("characters")}
        >
          角色圣经
        </button>
      </div>

      {tab === "story" ? (
        <div id="story-panel" role="tabpanel" aria-labelledby="story-tab" className="workspace-tab-panel">
          {storyError ? (
            <div className="workspace-load-error" role="alert">
              <p>{storyError}</p>
              <button type="button" onClick={reload}>重试加载</button>
            </div>
          ) : <StoryStructurePanel />}
        </div>
      ) : (
        <div id="characters-panel" role="tabpanel" aria-labelledby="characters-tab" className="workspace-tab-panel">
          {characterError ? (
            <div className="workspace-load-error" role="alert">
              <p>{characterError}</p>
              <button type="button" onClick={reload}>重试加载</button>
            </div>
          ) : <CharacterBiblePanel />}
        </div>
      )}
    </section>
  );
};

export default StoryCharacterWorkspace;

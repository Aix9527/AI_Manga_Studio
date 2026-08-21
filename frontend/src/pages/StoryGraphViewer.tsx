import { DownOutlined, RightOutlined } from "@ant-design/icons";
import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import type { StoryEdge, StoryNode } from "@/api/story";
import { useStoryStore } from "@/state/storyStore";
import { useWorkspaceStore } from "@/state/workspaceStore";

interface StoryNodeButtonProps {
  expanded: boolean;
  onClick: () => void;
  children: React.ReactNode;
}

const ExpandButton: React.FC<StoryNodeButtonProps> = ({ expanded, onClick, children }) => (
  <button
    type="button"
    className="story-tree__toggle"
    aria-expanded={expanded}
    onClick={onClick}
  >
    {expanded ? <DownOutlined aria-hidden="true" /> : <RightOutlined aria-hidden="true" />}
    {children}
    <span className="story-tree__toggle-copy">{expanded ? "收起" : "展开"}</span>
  </button>
);

function relationCount(edges: StoryEdge[], nodeId: string): number {
  return edges.filter((edge) => edge.source === nodeId || edge.target === nodeId).length;
}

const SceneBranch: React.FC<{
  scene: StoryNode;
  shots: StoryNode[];
  edges: StoryEdge[];
}> = ({ scene, shots, edges }) => {
  const [expanded, setExpanded] = useState(false);
  const selectObject = useWorkspaceStore((state) => state.selectObject);
  const selectShot = useStoryStore((state) => state.selectShot);

  return (
    <li className="story-tree__scene">
      <ExpandButton expanded={expanded} onClick={() => setExpanded((value) => !value)}>
        <span>第 {scene.index + 1} 场</span>
        <strong>{scene.label}</strong>
        <span>{shots.length} 个镜头</span>
        {relationCount(edges, scene.id) > 0 ? (
          <span>{relationCount(edges, scene.id)} 条关联</span>
        ) : null}
      </ExpandButton>
      {expanded ? (
        <ol className="story-tree__shots">
          {shots.map((shot) => {
            const count = relationCount(edges, shot.id);
            return (
              <li key={shot.id}>
                <button
                  type="button"
                  className="story-tree__shot"
                  onClick={() => {
                    selectShot(shot.id);
                    selectObject({ type: "镜头", id: shot.id });
                  }}
                >
                  <span>第 {shot.index + 1} 镜</span>
                  <strong>{shot.label}</strong>
                  <span>{count} 条关联</span>
                </button>
              </li>
            );
          })}
        </ol>
      ) : null}
    </li>
  );
};

const ChapterBranch: React.FC<{
  chapter: StoryNode;
  scenes: StoryNode[];
  shots: StoryNode[];
  edges: StoryEdge[];
}> = ({ chapter, scenes, shots, edges }) => {
  const [expanded, setExpanded] = useState(true);
  return (
    <li className="story-tree__chapter">
      <ExpandButton expanded={expanded} onClick={() => setExpanded((value) => !value)}>
        <span>第 {chapter.index + 1} 章</span>
        <strong>{chapter.label}</strong>
        <span>{scenes.length} 个场景</span>
      </ExpandButton>
      {expanded ? (
        <ol className="story-tree__scenes">
          {scenes.map((scene) => (
            <SceneBranch
              key={scene.id}
              scene={scene}
              shots={shots.filter((shot) => shot.parent_id === scene.id)}
              edges={edges}
            />
          ))}
        </ol>
      ) : null}
    </li>
  );
};

export const StoryStructurePanel: React.FC = () => {
  const graph = useStoryStore((state) => state.graph);
  const grouped = useMemo(() => {
    const nodes = graph?.nodes ?? [];
    return {
      chapters: nodes.filter((node) => node.type === "chapter").sort((a, b) => a.index - b.index),
      scenes: nodes.filter((node) => node.type === "scene").sort((a, b) => a.index - b.index),
      shots: nodes.filter((node) => node.type === "shot").sort((a, b) => a.index - b.index),
    };
  }, [graph]);

  if (!graph || graph.nodes.length === 0) {
    return (
      <div className="workspace-empty-state">
        <h2>尚未生成故事结构</h2>
        <p>导入小说后可生成章节、场景与镜头层级。</p>
        <Link to="/overview#import">导入并解析小说</Link>
      </div>
    );
  }

  return (
    <section className="story-structure" aria-labelledby="story-structure-title">
      <div className="workspace-section-heading">
        <div>
          <h2 id="story-structure-title">{graph.title}</h2>
          <p>{graph.nodes.length} 个节点 · {graph.edges.length} 条关系</p>
        </div>
      </div>
      <ol className="story-tree">
        {grouped.chapters.map((chapter) => (
          <ChapterBranch
            key={chapter.id}
            chapter={chapter}
            scenes={grouped.scenes.filter((scene) => scene.parent_id === chapter.id)}
            shots={grouped.shots}
            edges={graph.edges}
          />
        ))}
      </ol>
    </section>
  );
};

export default StoryStructurePanel;

import React, { useCallback, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Node,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import {
  DEFAULT_PRODUCTION_EDGES,
  DEFAULT_PRODUCTION_NODES,
  type ProductionNodeData,
} from "@/studio/canvas/defaultFlow";

const LIBRARY = [
  ["输入", ["小说文本", "文件读取", "素材导入"]],
  ["解析", ["文本解析", "场景拆解", "角色识别"]],
  ["资产", ["角色Bible", "场景库", "道具库"]],
  ["分镜", ["分镜脚本", "镜头语言", "参考帧"]],
  ["生图", ["文生图", "图生图", "高清修复"]],
  ["生视频", ["TI2V视频生成", "图生视频", "视频延展"]],
  ["配音", ["角色配音", "音效生成", "字幕生成"]],
  ["合成", ["视频合成", "转场特效", "调色处理"]],
  ["质检", ["画面质检", "音频质检", "一致性检测"]],
  ["导出", ["成片导出", "工程打包"]],
] as const;

type ProductionNode = Node<ProductionNodeData>;

const AdvancedCanvasWorkspace: React.FC = () => {
  const [selectedNode, setSelectedNode] = useState<ProductionNode | null>(DEFAULT_PRODUCTION_NODES[5] ?? null);
  const [notice, setNotice] = useState("专业精修 / 本地可控 / 节点可回放");

  const selectNode: NodeMouseHandler<ProductionNode> = useCallback((_event, node) => {
    setSelectedNode(node);
  }, []);

  return (
    <div className="studio-workspace canvas-workspace">
      <aside className="studio-panel canvas-library">
        <div className="studio-panel__header"><div><strong>节点库</strong><span>本地生产能力</span></div></div>
        {LIBRARY.map(([group, items]) => (
          <section key={group}>
            <h3>{group}</h3>
            {items.map((item) => <button key={item} type="button">{item}</button>)}
          </section>
        ))}
      </aside>

      <section className="studio-center-pane">
        <header className="studio-workspace__header">
          <div><h1>高级画布 / 精修工作台</h1><p>{notice}</p></div>
          <div className="asset-tabs">
            <button type="button" className="studio-primary-button" onClick={() => setNotice(`运行选中节点：${selectedNode?.data.label || "未选择"}`)}>运行选中节点</button>
            <button type="button" className="studio-secondary-button" onClick={() => setNotice(`从 ${selectedNode?.data.label || "当前节点"} 继续执行`)}>从当前节点继续</button>
            <button type="button" className="studio-secondary-button" onClick={() => setNotice("当前流程已保存为本地模板")}>保存为模板</button>
            <button type="button" className="studio-secondary-button" onClick={() => setNotice("当前流程已设为一键成片专业模板")}>发布到一键成片</button>
          </div>
        </header>
        <div className="canvas-stage" aria-label="高级生产节点画布">
          <ReactFlow<ProductionNode>
            nodes={DEFAULT_PRODUCTION_NODES}
            edges={DEFAULT_PRODUCTION_EDGES}
            onNodeClick={selectNode}
            fitView
            minZoom={0.55}
            maxZoom={1.6}
          >
            <Background gap={22} size={1} />
            <Controls />
            <MiniMap pannable zoomable />
          </ReactFlow>
        </div>
        <section className="studio-panel">
          <div className="studio-panel__header"><div><strong>执行说明</strong><span>高级模式不会改变普通用户的一键生产入口</span></div></div>
          <div className="inspector-section"><p className="subtle">默认流程：小说文本 → 场景拆解 → 角色Bible → 分镜脚本 → 关键帧 → TI2V视频生成 → 配音/字幕 → 合成导出。节点级执行按钮当前只改变精修工作台状态；实际 Provider 执行继续由现有本地编排与 ComfyUI 工作流负责。</p></div>
        </section>
      </section>

      <aside className="studio-panel studio-right-pane">
        <div className="studio-panel__header"><div><strong>节点设置</strong><span>{selectedNode?.data.label || "未选择"}</span></div></div>
        {selectedNode ? (
          <>
            <div className="inspector-section">
              <h3>{selectedNode.data.label}</h3>
              <p className="subtle">{selectedNode.data.subtitle}</p>
            </div>
            <div className="inspector-section">
              <div className="inspector-field"><label>执行引擎</label><select defaultValue={selectedNode.data.group === "video" ? "Wan 2.2" : selectedNode.data.group === "audio" ? "CosyVoice" : "FLUX / Local"}><option>Wan 2.2</option><option>MiniMax H3</option><option>FLUX / Local</option><option>CosyVoice</option></select></div>
              <div className="inspector-field"><label>批次大小</label><input type="number" min="1" max="8" defaultValue="1" /></div>
              <div className="inspector-field"><label>失败重试</label><select defaultValue="2"><option value="0">不重试</option><option value="1">1 次</option><option value="2">2 次</option><option value="3">3 次</option></select></div>
              <div className="inspector-field"><label>缓存策略</label><select defaultValue="精确匹配"><option>精确匹配</option><option>允许相似复用</option><option>禁用缓存</option></select></div>
            </div>
            <div className="inspector-section">
              <h3>节点可观察性</h3>
              <div className="qc-grid"><div className="qc-item is-ok">输入已绑定</div><div className="qc-item is-ok">本地执行</div><div className="qc-item">可回放</div><div className="qc-item">可重试</div></div>
            </div>
          </>
        ) : <div className="studio-empty">点击节点查看参数</div>}
      </aside>
    </div>
  );
};

export default AdvancedCanvasWorkspace;

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { userMessage } from "@/api/client";
import {
  getProductionTemplate,
  listProductionTemplates,
  publishProductionTemplate,
  saveProductionTemplate,
} from "@/api/productionTemplates";
import { jobStoreActions, useJobStore } from "@/state/jobStore";
import { useWorkspaceStore } from "@/state/workspaceStore";
import type { JobDetail, StageExecutionMode } from "@/types/jobs";
import type { ProductionTemplateVersion } from "@/types/productionTemplates";
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

const EXECUTABLE_JOB_STATES = new Set<JobDetail["status"]>([
  "paused",
  "failed",
  "retry_wait",
  "completed",
]);

type ProductionNode = Node<ProductionNodeData>;

type StoredCanvas = {
  nodes?: ProductionNode[];
  edges?: Edge[];
};

function freshDefaultNodes(): ProductionNode[] {
  return DEFAULT_PRODUCTION_NODES.map((node) => ({
    ...node,
    position: { ...node.position },
    data: { ...node.data },
  }));
}

function freshDefaultEdges(): Edge[] {
  return DEFAULT_PRODUCTION_EDGES.map((edge) => ({ ...edge }));
}

function parseStoredCanvas(version: ProductionTemplateVersion): StoredCanvas {
  const parsed = JSON.parse(version.content_json) as { canvas?: StoredCanvas };
  return parsed.canvas ?? {};
}

const AdvancedCanvasWorkspace: React.FC = () => {
  const workspace = useWorkspaceStore((state) => state.snapshot);
  const projectId = workspace?.project_id || useWorkspaceStore.getState().projectId || "default";
  const jobStore = useJobStore();
  const actions = jobStoreActions();
  const [nodes, setNodes] = useState<ProductionNode[]>(freshDefaultNodes);
  const [edges, setEdges] = useState<Edge[]>(freshDefaultEdges);
  const [selectedNode, setSelectedNode] = useState<ProductionNode | null>(DEFAULT_PRODUCTION_NODES[5] ?? null);
  const [selectedShotId, setSelectedShotId] = useState("");
  const [notice, setNotice] = useState("专业精修 / 正式 Job 控制 / 节点可回放");
  const [busy, setBusy] = useState(false);
  const [templateBusy, setTemplateBusy] = useState(true);
  const [templateDirty, setTemplateDirty] = useState(true);
  const [savedVersion, setSavedVersion] = useState<number | null>(null);
  const [publishedVersion, setPublishedVersion] = useState<number | null>(null);
  const [templateVersions, setTemplateVersions] = useState<ProductionTemplateVersion[]>([]);
  const [historyVersion, setHistoryVersion] = useState<number | null>(null);

  const jobs = useMemo(
    () => jobStore.recentIds
      .map((id) => jobStore.jobs.get(id))
      .filter((job): job is JobDetail => Boolean(job && job.project_id === projectId)),
    [jobStore.jobs, jobStore.recentIds, projectId],
  );
  const productionJob = jobs[0] ?? null;

  useEffect(() => {
    let cancelled = false;
    setTemplateBusy(true);
    setSavedVersion(null);
    setPublishedVersion(null);
    setTemplateVersions([]);
    setHistoryVersion(null);
    setNodes(freshDefaultNodes());
    setEdges(freshDefaultEdges());
    setTemplateDirty(true);

    void (async () => {
      try {
        const listing = await listProductionTemplates(projectId);
        if (cancelled) return;
        setTemplateVersions(listing.versions);
        setPublishedVersion(listing.published_version);
        if (listing.latest_version > 0) {
          const latest = await getProductionTemplate(projectId, listing.latest_version);
          if (cancelled) return;
          const canvas = parseStoredCanvas(latest);
          if (Array.isArray(canvas.nodes)) setNodes(canvas.nodes);
          if (Array.isArray(canvas.edges)) setEdges(canvas.edges);
          setSavedVersion(latest.version);
          setHistoryVersion(latest.version);
          setTemplateDirty(false);
        }
      } catch (error) {
        if (!cancelled) setNotice(`模板状态读取失败：${userMessage(error)}`);
      } finally {
        if (!cancelled) setTemplateBusy(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const shotOptions = useMemo(() => {
    if (!productionJob || !selectedNode?.data.shotScoped) return [];
    return Array.from(new Set(
      productionJob.steps
        .filter((step) => step.stage_key === selectedNode.data.stageKey && Boolean(step.shot_id))
        .map((step) => step.shot_id as string),
    ));
  }, [productionJob, selectedNode]);

  useEffect(() => {
    if (!selectedNode?.data.shotScoped) {
      setSelectedShotId("");
      return;
    }
    setSelectedShotId((current) => shotOptions.includes(current) ? current : (shotOptions[0] ?? ""));
  }, [selectedNode, shotOptions]);

  const selectNode: NodeMouseHandler<ProductionNode> = useCallback((_event, node) => {
    setSelectedNode(node);
    setNotice(`已选择：${node.data.label} · ${node.data.stageKey}`);
  }, []);

  const blockedReason = (() => {
    if (!selectedNode?.data.stageKey) return "当前节点没有经过验证的编排阶段映射。";
    if (!productionJob) return "当前项目没有可执行的 Production Job。";
    if (productionJob.status === "waiting_review") return "当前任务正在等待审核；高级画布不能绕过 Review Gate。";
    if (productionJob.status === "running" || productionJob.status === "queued") return "当前任务正在执行；请先进入稳定状态后再回退节点。";
    if (!EXECUTABLE_JOB_STATES.has(productionJob.status)) return `当前任务状态 ${productionJob.status} 不允许节点回退执行。`;
    if (selectedNode.data.shotScoped && !selectedShotId) return "该节点按镜头执行，但当前没有可解析的 shot_id。";
    return "";
  })();

  const execute = async (mode: StageExecutionMode) => {
    if (!selectedNode || !productionJob || blockedReason) {
      setNotice(blockedReason || "无法提交节点执行命令。");
      return;
    }
    setBusy(true);
    try {
      const updated = await actions.executeFromStage(productionJob.id, {
        stage_key: selectedNode.data.stageKey,
        shot_id: selectedNode.data.shotScoped ? selectedShotId : undefined,
        mode,
      });
      setNotice(
        `${mode === "rerun_node" ? "已提交单节点重跑" : "已从节点继续"}：${selectedNode.data.label}`
        + `${selectedShotId ? ` · ${selectedShotId}` : ""} · Job ${updated.id.slice(0, 8)} · ${updated.status}`,
      );
    } catch (error) {
      setNotice(userMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const saveTemplate = async () => {
    setTemplateBusy(true);
    try {
      const saved = await saveProductionTemplate(projectId, {
        name: "高级画布生产模板",
        schema_version: 1,
        canvas: {
          nodes: nodes as unknown as Array<Record<string, unknown>>,
          edges: edges as unknown as Array<Record<string, unknown>>,
        },
        production: {
          shot_duration: 5,
          width: 1080,
          height: 1920,
          fps: 24,
          options: { style: "anime", local_first: true },
        },
        stage_policy: { stages: [] },
      });
      setSavedVersion(saved.version);
      setHistoryVersion(saved.version);
      setTemplateDirty(false);
      setTemplateVersions((current) => [saved, ...current.filter((item) => item.version !== saved.version)]);
      setNotice(`已保存模板 v${saved.version}；当前生产${publishedVersion ? `仍使用 v${publishedVersion}` : "尚未发布模板"}。`);
    } catch (error) {
      setNotice(`模板保存失败：${userMessage(error)}`);
    } finally {
      setTemplateBusy(false);
    }
  };

  const publishVersion = async (version: number) => {
    setTemplateBusy(true);
    try {
      const published = await publishProductionTemplate(projectId, version);
      setPublishedVersion(published.version);
      setTemplateVersions((current) => current.map((item) => (
        item.version === published.version ? published : item
      )));
      setNotice(`v${published.version} 已发布；后续新建的一键成片任务将使用该版本，现有任务不变。`);
    } catch (error) {
      setNotice(`模板发布失败：${userMessage(error)}`);
    } finally {
      setTemplateBusy(false);
    }
  };

  const markNodePosition = useCallback((_event: unknown, node: ProductionNode) => {
    setNodes((current) => current.map((item) => item.id === node.id ? { ...item, position: { ...node.position } } : item));
    setTemplateDirty(true);
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
          <div><h1>高级画布 / 精修工作台</h1><p role="status">{notice}</p></div>
          <div className="asset-tabs">
            <button type="button" className="studio-primary-button" disabled={busy || Boolean(blockedReason)} onClick={() => void execute("rerun_node")}>{busy ? "提交中…" : "运行选中节点"}</button>
            <button type="button" className="studio-secondary-button" disabled={busy || Boolean(blockedReason)} onClick={() => void execute("continue")}>从当前节点继续</button>
            <button type="button" className="studio-secondary-button" disabled={templateBusy} onClick={() => void saveTemplate()}>{templateBusy ? "模板处理中…" : "保存为模板"}</button>
            <button type="button" className="studio-secondary-button" disabled={templateBusy || templateDirty || savedVersion === null} onClick={() => savedVersion !== null && void publishVersion(savedVersion)}>发布到一键成片</button>
          </div>
        </header>
        <div className="inspector-section" aria-label="生产模板状态">
          <p className="subtle">最新保存：{savedVersion === null ? "未保存" : `v${savedVersion}`} · 当前发布：{publishedVersion === null ? "未发布" : `v${publishedVersion}`} · 画布：{templateDirty ? "有未保存修改" : "已保存"} · Schema v1</p>
          {templateVersions.length ? (
            <div className="inspector-field">
              <label htmlFor="template-history-version">模板历史版本</label>
              <select
                id="template-history-version"
                aria-label="模板历史版本"
                value={historyVersion ?? ""}
                onChange={(event) => setHistoryVersion(Number(event.target.value))}
              >
                {templateVersions.map((item) => <option key={item.id} value={item.version}>v{item.version}{item.version === publishedVersion ? " · 当前发布" : ""}</option>)}
              </select>
              <button type="button" className="studio-secondary-button" disabled={templateBusy || historyVersion === null} onClick={() => historyVersion !== null && void publishVersion(historyVersion)}>发布历史版本</button>
            </div>
          ) : null}
        </div>
        {blockedReason ? <p className="studio-feedback">{blockedReason}</p> : null}
        <div className="canvas-stage" aria-label="高级生产节点画布">
          <ReactFlow<ProductionNode>
            nodes={nodes}
            edges={edges}
            onNodeClick={selectNode}
            onNodeDragStop={markNodePosition}
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
          <div className="studio-panel__header"><div><strong>执行说明</strong><span>高级模式复用一键生产的正式 Job</span></div></div>
          <div className="inspector-section"><p className="subtle">默认流程：小说文本 → 场景拆解 → 角色Bible → 分镜脚本 → 关键帧 → TI2V视频生成 → 配音/字幕 → 合成导出。高级画布只发出正式 stage rewind 命令；Worker、Provider、QC、Review Gate、SSE 与资产版本仍由原生产编排链统一管理。</p></div>
        </section>
      </section>

      <aside className="studio-panel studio-right-pane">
        <div className="studio-panel__header"><div><strong>节点设置</strong><span>{selectedNode?.data.label || "未选择"}</span></div></div>
        {selectedNode ? (
          <>
            <div className="inspector-section">
              <h3>{selectedNode.data.label}</h3>
              <p className="subtle">{selectedNode.data.subtitle}</p>
              <p className="subtle">正式阶段：{selectedNode.data.stageKey}</p>
              <p className="subtle">执行任务：{productionJob ? `${productionJob.id.slice(0, 8)} · ${productionJob.status}` : "未绑定"}</p>
            </div>
            {selectedNode.data.shotScoped ? (
              <div className="inspector-section">
                <div className="inspector-field">
                  <label>目标镜头</label>
                  <select aria-label="目标镜头" value={selectedShotId} onChange={(event) => setSelectedShotId(event.target.value)}>
                    {shotOptions.length === 0 ? <option value="">无可用镜头</option> : null}
                    {shotOptions.map((shotId) => <option key={shotId} value={shotId}>{shotId}</option>)}
                  </select>
                </div>
              </div>
            ) : null}
            <div className="inspector-section">
              <h3>执行参数来源</h3>
              <div className="inspector-field"><label>执行引擎</label><input value="继承正式 Job / Provider 路由" readOnly disabled /></div>
              <div className="inspector-field"><label>批次大小</label><input value="继承 Job 设置" readOnly disabled /></div>
              <div className="inspector-field"><label>失败重试</label><input value="继承编排器重试策略" readOnly disabled /></div>
              <div className="inspector-field"><label>缓存策略</label><input value="继承正式运行时策略" readOnly disabled /></div>
              <p className="subtle">这些参数不会在画布里临时覆盖正式 Job，因此选择节点执行不会静默改变 Wan / H3 / FLUX / CosyVoice 路由。</p>
            </div>
            <div className="inspector-section">
              <h3>节点可观察性</h3>
              <div className="qc-grid"><div className="qc-item is-ok">输入已绑定</div><div className="qc-item is-ok">正式 Job</div><div className="qc-item">可回放</div><div className="qc-item">可重试</div></div>
            </div>
          </>
        ) : <div className="studio-empty">点击节点查看参数</div>}
      </aside>
    </div>
  );
};

export default AdvancedCanvasWorkspace;

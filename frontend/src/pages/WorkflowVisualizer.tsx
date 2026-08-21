/**
 * Production Workflow Visualizer（GPT 优化 v1.2，工业电影控制台风格）。
 *
 * 端到端流水线 + Stage Heatmap + EP 进度条 + 阶段完成率 + 集筛选 +
 * 阶段详情 Drawer。5 秒回答：生产到哪里 / 卡在哪里 / 下一步谁处理。
 */

import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Alert, Card, Col, Drawer, Input, Progress, Row, Select, Space, Statistic, Tag, Typography,
} from "antd";
import { ApartmentOutlined, BarChartOutlined, ControlOutlined, ExperimentOutlined, LinkOutlined } from "@ant-design/icons";

import { teamFlow, teamStats, type FlowView, type TeamStats } from "@/api/team";
import { kgSearch } from "@/api/knowledgeGraph";
import { producerPlan } from "@/api/producerAgent";
import { userMessage } from "@/api/client";

const { Title, Text } = Typography;

const STAGE_ORDER = ["planning", "script", "storyboard", "assets", "generation", "qc", "editing", "sound", "final"];
const STAGE_LABELS: Record<string, string> = {
  planning: "策划", script: "编剧", storyboard: "分镜", assets: "资产",
  generation: "生成", qc: "质检", editing: "剪辑", sound: "声音", final: "成片",
};
const STAGE_DESC: Record<string, string> = {
  planning: "集规划与留存结构", script: "剧本 / 对白 / 旁白", storyboard: "镜头语言与导演指令",
  assets: "角色 / 场景 / 道具资产", generation: "TaskQueue / Worker 生成", qc: "质量 / 身份 / 规则评审",
  editing: "时间线 / 节奏 / 转场", sound: "配音 / BGM / 混音", final: "成片锁定 / 人工审批",
};
// 工业控制台状态色（GPT 配色）
const STATUS_HEX: Record<string, string> = {
  done: "#22C55E", in_progress: "#3B82F6", assigned: "#60A5FA", review: "#F59E0B",
  approved: "#22C55E", escalated: "#A855F7", blocked: "#EF4444", rework: "#F59E0B",
  failed: "#EF4444", cancelled: "#64748B", planned: "#475569",
};
const STATUS_LABEL: Record<string, string> = {
  done: "完成", in_progress: "进行中", assigned: "已分派", review: "评审中",
  approved: "已批准", escalated: "等待人工", blocked: "阻塞", rework: "返工",
  failed: "失败", cancelled: "取消", planned: "待分派",
};
const STATUS_ORDER = ["blocked", "escalated", "review", "rework", "in_progress", "assigned", "approved", "done"];

const WorkflowVisualizer: React.FC = () => {
  const [searchParams] = useSearchParams();
  const [flow, setFlow] = useState<FlowView | null>(null);
  const [stats, setStats] = useState<TeamStats | null>(null);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState(searchParams.get("episode") ?? "");
  const [drawer, setDrawer] = useState<{ episode: string; stage: string; status: string; role: string } | null>(null);
  const [kgNodes, setKgNodes] = useState<Array<{ id: string; label: string; type: string }>>([]);
  const [explain, setExplain] = useState<Array<{ priority: number; action: string; detail: string }>>([]);
  const [error, setError] = useState("");

  const load = async () => {
    const [f, s] = await Promise.all([
      teamFlow("guixu2"), teamStats(),
    ]).catch((err: unknown) => {
      setError(userMessage(err));
      return [null, null];
    });
    setFlow(f ?? null);
    setStats(s ?? null);
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 阶段完成率（每阶段 done 占比）
  const stageCompletion = useMemo(() => {
    const totals: Record<string, number> = {};
    const dones: Record<string, number> = {};
    for (const ep of flow?.episodes ?? []) {
      for (const stage of STAGE_ORDER) {
        totals[stage] = (totals[stage] ?? 0) + 1;
        if (ep.stages[stage]?.status === "done") dones[stage] = (dones[stage] ?? 0) + 1;
      }
    }
    return STAGE_ORDER.map((stage) => ({
      stage,
      pct: totals[stage] ? Math.round((dones[stage] ?? 0) / totals[stage] * 100) : 0,
      done: dones[stage] ?? 0,
      total: totals[stage] ?? 0,
    }));
  }, [flow]);

  // 瓶颈阶段（完成率最低的非 100% 阶段）
  const bottleneck = useMemo(() => {
    const sorted = [...stageCompletion].sort((a, b) => a.pct - b.pct);
    return sorted.find((s) => s.pct < 100) ?? null;
  }, [stageCompletion]);

  const filteredEpisodes = useMemo(() => {
    let rows = flow?.episodes ?? [];
    if (filter === "blocked") rows = rows.filter((e) => Object.values(e.stages).some((s) => s.status === "blocked"));
    if (filter === "waiting") rows = rows.filter((e) => e.waiting_human > 0);
    if (filter === "active") rows = rows.filter((e) => Object.values(e.stages).some((s) => s.status === "in_progress"));
    if (search) {
      const q = search.trim().toLowerCase();
      rows = rows.filter((e) => e.episode_id.toLowerCase().includes(q));
    }
    return rows;
  }, [flow, filter, search]);

  const doneCount = stats?.by_status?.done ?? 0;
  const totalCount = stats?.assignments ?? 0;
  const progressPct = totalCount ? Math.round((doneCount / totalCount) * 100) : 0;
  const blockedCount = stats?.by_status?.blocked ?? 0;
  const waitingCount = stats?.by_status?.escalated ?? 0;
  const activeCount = (stats?.by_status?.in_progress ?? 0) + (stats?.by_status?.assigned ?? 0);

  const openDrawer = async (episode: string, stage: string, status: string, role: string) => {
    setDrawer({ episode, stage, status, role });
    setKgNodes([]);
    setExplain([]);
    kgSearch(episode, 5).then((r) => setKgNodes(r.results.map((n) => ({ id: n.id, label: n.label, type: n.type }))))
      .catch(() => undefined);
    if (stage === "generation" || stage === "qc") {
      producerPlan().then((r) => setExplain(r.steps.map((s) => ({ priority: s.priority, action: s.action, detail: s.detail }))))
        .catch(() => undefined);
    }
  };

  const episodeProgress = (ep: FlowView["episodes"][number]) => {
    const done = STAGE_ORDER.filter((s) => ep.stages[s]?.status === "done").length;
    return { done, pct: Math.round(done / STAGE_ORDER.length * 100) };
  };

  return (
    <div className="page-container" style={{ background: "#0B1020", minHeight: "100vh", padding: 16, color: "#E2E8F0" }}>
      {/* Production Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          <Title level={3} style={{ marginBottom: 0, color: "#E2E8F0" }}>
            <ApartmentOutlined /> Production Workflow <Text style={{ color: "#94A3B8" }}>工作流可视化</Text>
          </Title>
          <Text style={{ color: "#64748B", fontSize: 12 }}>
            《归墟第二部》· Season 1 · 100 Episodes · 1000 Shots
          </Text>
        </div>
        <Space>
          <Tag style={{ background: "#0F172A", color: "#22C55E", borderColor: "#22C55E" }}>🟢 Running</Tag>
          <Tag style={{ background: "#0F172A", color: "#3B82F6", borderColor: "#3B82F6" }}>GPU 82%</Tag>
          <Tag style={{ background: "#0F172A", color: "#EF4444", borderColor: "#EF4444" }}>Risk {blockedCount + waitingCount}</Tag>
        </Space>
      </div>

      {/* Health Banner */}
      <Card size="small" style={{ marginBottom: 12, background: "#0F172A", borderColor: "#1E293B" }} styles={{ body: { padding: 12 } }}>
        <div style={{ display: "flex", alignItems: "center", gap: 24, flexWrap: "wrap" }}>
          <div style={{ minWidth: 200 }}>
            <div style={{ color: "#94A3B8", fontSize: 12, marginBottom: 4 }}>Production Health</div>
            <Progress percent={progressPct} strokeColor="#22C55E" trailColor="#1E293B" size={{ height: 10 }} />
            <Text style={{ color: "#E2E8F0", fontSize: 13 }}>{progressPct}% · {doneCount}/{totalCount} tasks</Text>
          </div>
          <Statistic title={<span style={{ color: "#94A3B8", fontSize: 12 }}>Completed Episodes</span>} value={doneCount} valueStyle={{ color: "#22C55E", fontSize: 20 }} />
          <Statistic title={<span style={{ color: "#94A3B8", fontSize: 12 }}>Active</span>} value={activeCount} valueStyle={{ color: "#3B82F6", fontSize: 20 }} />
          <Statistic title={<span style={{ color: "#94A3B8", fontSize: 12 }}>Blocked</span>} value={blockedCount} valueStyle={{ color: "#EF4444", fontSize: 20 }} />
          <Statistic title={<span style={{ color: "#94A3B8", fontSize: 12 }}>Need Review</span>} value={waitingCount} valueStyle={{ color: "#A855F7", fontSize: 20 }} />
          <Statistic title={<span style={{ color: "#94A3B8", fontSize: 12 }}>Audit</span>} value={`${stats ? (stats.audit_coverage * 100).toFixed(0) : "…"}%`} valueStyle={{ color: "#22C55E", fontSize: 20 }} />
          <a href="#/command-center" style={{ color: "#3B82F6", fontSize: 12 }}>
            审批入口 → Command Center（{waitingCount} 待审）
          </a>
        </div>
      </Card>

      {/* 瓶颈 + 阶段完成率 */}
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
        <Col span={12}>
          <Card size="small" title={<span style={{ color: "#E2E8F0", fontSize: 13 }}><BarChartOutlined /> Pipeline Stage Analytics</span>}
                style={{ background: "#0F172A", borderColor: "#1E293B" }}>
            <Space direction="vertical" style={{ width: "100%" }}>
              {stageCompletion.map((s) => (
                <div key={s.stage}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#94A3B8", marginBottom: 2 }}>
                    <span>{STAGE_LABELS[s.stage]}</span><span>{s.done}/{s.total} · {s.pct}%</span>
                  </div>
                  <Progress percent={s.pct} strokeColor={s.pct === 100 ? "#22C55E" : s.pct < 70 ? "#EF4444" : "#F59E0B"} trailColor="#1E293B" size={{ height: 8 }} showInfo={false} />
                </div>
              ))}
            </Space>
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title={<span style={{ color: "#E2E8F0", fontSize: 13 }}><ControlOutlined /> 当前瓶颈 / 生产状态</span>}
                style={{ background: "#0F172A", borderColor: "#1E293B", height: "100%" }}>
            {bottleneck ? (
              <div>
                <Tag color="red" style={{ marginBottom: 8 }}>瓶颈：{STAGE_LABELS[bottleneck.stage]}（{bottleneck.pct}%）</Tag>
                <div style={{ color: "#94A3B8", fontSize: 13, marginBottom: 8 }}>{STAGE_DESC[bottleneck.stage]}</div>
                <div style={{ fontSize: 12, color: "#64748B" }}>
                  下一步：优先处理 <Text style={{ color: "#F59E0B" }}>{STAGE_LABELS[bottleneck.stage]}</Text> 待办任务
                  {waitingCount > 0 ? `；另有 ${waitingCount} 项等待人工审批` : ""}
                </div>
              </div>
            ) : <Text style={{ color: "#64748B" }}>无显著瓶颈（全部阶段 100%）</Text>}
          </Card>
        </Col>
      </Row>

      {/* Pipeline + 联动 + 筛选 */}
      <Card size="small" style={{ marginBottom: 12, background: "#0F172A", borderColor: "#1E293B" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
          <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
            <Tag style={{ background: "#1E293B", color: "#60A5FA", border: 0 }}>📜 剧本</Tag>
            {STAGE_ORDER.map((stage, i) => (
              <React.Fragment key={stage}>
                <Text style={{ color: "#475569" }}>→</Text>
                <Tag style={{ background: "#1E293B", color: "#E2E8F0", border: 0 }}>{STAGE_LABELS[stage]}</Tag>
              </React.Fragment>
            ))}
            <Text style={{ color: "#475569" }}>→</Text>
            <Tag style={{ background: "#1E293B", color: "#F59E0B", border: 0 }}>✅ 人工审批</Tag>
          </div>
          <Space wrap>
            <Tag style={{ background: "#1E293B", color: "#94A3B8", border: 0, fontSize: 11 }}>
              SOP：剧本→资产→分镜→生成→剪辑→发布
            </Tag>
            <Select value={filter} onChange={setFilter} style={{ width: 150 }}
                    options={[
                      { value: "all", label: "全部集" },
                      { value: "active", label: "进行中" },
                      { value: "blocked", label: "阻塞" },
                      { value: "waiting", label: "等待人工" },
                    ]} />
            <Input placeholder="搜索集（如 EP023）" value={search} onChange={(e) => setSearch(e.target.value)}
                   style={{ width: 160, background: "#0B1020", borderColor: "#1E293B", color: "#E2E8F0" }} />
            <Space size={4} style={{ fontSize: 12, color: "#64748B" }}>
              <LinkOutlined /> <a href="#/command-center" style={{ color: "#3B82F6" }}>Command Center</a>
              <a href="#/digital-twin" style={{ color: "#3B82F6" }}>Digital Twin</a>
              <a href="#/knowledge-graph" style={{ color: "#3B82F6" }}>KG</a>
            </Space>
          </Space>
        </div>
      </Card>

      {/* Stage Heatmap + EP 进度条 */}
      <Card size="small" title={<span style={{ color: "#E2E8F0", fontSize: 13 }}>Episode Production Board（Stage Heatmap）</span>}
            style={{ background: "#0F172A", borderColor: "#1E293B" }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr>
                <th style={{ padding: "6px 10px", textAlign: "left", color: "#94A3B8", minWidth: 90 }}>集 / 进度</th>
                {STAGE_ORDER.map((stage) => (
                  <th key={stage} style={{ padding: "6px 6px", textAlign: "center", color: "#94A3B8", minWidth: 56 }}>
                    {STAGE_LABELS[stage]}
                    <div style={{ fontSize: 10, fontWeight: "normal", color: "#64748B" }}>{STAGE_DESC[stage]}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredEpisodes.map((ep) => {
                const prog = episodeProgress(ep);
                return (
                  <tr key={ep.episode_id} style={{ borderTop: "1px solid #1E293B", cursor: "pointer" }}
                      onClick={() => { window.location.hash = `#/production-studio-v1?episode=${ep.episode_id}`; }}
                      title="点击跳转 Production Studio">
                    <td style={{ padding: "4px 10px" }}>
                      <div style={{ color: "#3B82F6", fontWeight: 600 }}>{ep.episode_id} ↗</div>
                      <div style={{ fontSize: 10, color: "#64748B" }}>{prog.done}/9 · {prog.pct}%</div>
                      <Progress percent={prog.pct} strokeColor={prog.pct === 100 ? "#22C55E" : "#3B82F6"} trailColor="#1E293B" size={{ height: 4 }} showInfo={false} />
                    </td>
                    {STAGE_ORDER.map((stage) => {
                      const view = ep.stages[stage];
                      const status = view?.status ?? "planned";
                      const color = STATUS_HEX[status] ?? "#475569";
                      return (
                        <td key={stage} style={{ padding: "4px 6px", textAlign: "center" }}>
                          <div
                            onClick={() => openDrawer(ep.episode_id, stage, status, view?.role ?? "")}
                            title={`${ep.episode_id} · ${STAGE_LABELS[stage]} · ${STATUS_LABEL[status]}`}
                            style={{
                              height: 22, borderRadius: 4, cursor: "pointer",
                              background: status === "planned" ? "#1E293B" : `${color}33`,
                              border: `1px solid ${status === "planned" ? "#1E293B" : color}`,
                              display: "flex", alignItems: "center", justifyContent: "center",
                              fontSize: 10, color,
                            }}
                          >
                            {STATUS_LABEL[status]}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
              {filteredEpisodes.length === 0 ? (
                <tr><td colSpan={10} style={{ padding: 16, textAlign: "center", color: "#64748B" }}>无匹配数据</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </Card>

      {/* 阶段详情 Drawer */}
      <Drawer
        title={`${drawer?.episode ?? ""} / ${drawer ? STAGE_LABELS[drawer.stage] : ""}`}
        open={!!drawer}
        onClose={() => setDrawer(null)}
        width={340}
        styles={{ body: { background: "#0B1020", color: "#E2E8F0" }, header: { background: "#0B1020", color: "#E2E8F0" } }}
      >
        {drawer && (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Tag color={STATUS_HEX[drawer.status] === "#EF4444" ? "red" : drawer.status === "escalated" ? "purple" : drawer.status === "done" ? "green" : "blue"}>
              {STATUS_LABEL[drawer.status]}
            </Tag>
            <div><Text style={{ color: "#94A3B8" }}>阶段：</Text><Text style={{ color: "#E2E8F0" }}>{STAGE_LABELS[drawer.stage]}</Text></div>
            <div><Text style={{ color: "#94A3B8" }}>职责：</Text><Text style={{ color: "#E2E8F0" }}>{STAGE_DESC[drawer.stage]}</Text></div>
            <div><Text style={{ color: "#94A3B8" }}>负责人：</Text><Text style={{ color: "#E2E8F0" }}>{drawer.role || "—"}</Text></div>
            <div style={{ color: "#64748B", fontSize: 12 }}>
              状态含义：{STATUS_LABEL[drawer.status]}。点击对应系统查看详情（Command Center / Digital Twin）。
            </div>
            {kgNodes.length > 0 ? (
              <div>
                <Text style={{ color: "#94A3B8" }}>关联 KG 节点：</Text>
                <Space wrap size={4}>
                  {kgNodes.map((n) => <Tag key={n.id} color="geekblue">{n.label || n.id}</Tag>)}
                </Space>
              </div>
            ) : null}
            {explain.length > 0 ? (
              <div>
                <Text style={{ color: "#94A3B8" }}>AI 制片人建议：</Text>
                {explain.map((s) => (
                  <div key={s.action} style={{ fontSize: 12, color: "#E2E8F0", marginTop: 4 }}>
                    P{s.priority} · {s.action}：{s.detail}
                  </div>
                ))}
              </div>
            ) : null}
          </Space>
        )}
      </Drawer>

      {error ? <Alert style={{ marginTop: 12 }} type="error" showIcon message={error} /> : null}
    </div>
  );
};

export default WorkflowVisualizer;

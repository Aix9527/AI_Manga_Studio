/**
 * Production Digital Twin (Phase 14.2, GPT spec).
 *
 * mode=simulation_and_visibility_only / auto_control=false：
 * Runtime 状态镜像 / Episode 甘特图 / Resource Heatmap / Queue Simulation /
 * Risk Prediction（RiskCandidate 仅建议，不自动干预）。
 */

import React, { useEffect, useState } from "react";
import {
  Alert, Button, Card, Col, Progress, Row, Space, Statistic, Table, Tag, Typography,
} from "antd";
import { BarChartOutlined, DashboardOutlined, ExperimentOutlined, FundOutlined, ThunderboltOutlined } from "@ant-design/icons";

import {
  dtDismissRisk, dtHeatmap, dtOverview, dtPredict, dtRiskCandidates, dtSimulate, dtTimeline,
  type DTHeatmap, type DTRiskCandidate, type DTSimulationRow, type DTTimeline,
} from "@/api/digitalTwin";
import { userMessage } from "@/api/client";

const { Title, Text } = Typography;

const RISK_COLORS: Record<string, string> = {
  schedule: "blue", episode: "purple", quality: "red", asset: "orange", budget: "gold",
};
const SEVERITY_COLORS: Record<string, string> = { low: "default", medium: "orange", high: "red" };
const STATUS_COLORS: Record<string, string> = {
  done: "success", in_progress: "processing", assigned: "blue", review: "orange",
  approved: "green", escalated: "magenta", blocked: "warning", rework: "purple",
  failed: "red", cancelled: "default", planned: "default",
};
const STAGE_LABELS: Record<string, string> = {
  planning: "策划", script: "编剧", storyboard: "分镜", assets: "资产",
  generation: "生成", qc: "质检", editing: "剪辑", sound: "声音", final: "成片",
};

const DigitalTwin: React.FC = () => {
  const [mode, setMode] = useState<{ mode: string; auto_control: boolean } | null>(null);
  const [timeline, setTimeline] = useState<DTTimeline | null>(null);
  const [heatmap, setHeatmap] = useState<DTHeatmap | null>(null);
  const [simRows, setSimRows] = useState<DTSimulationRow[]>([]);
  const [risks, setRisks] = useState<DTRiskCandidate[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    const [o, tl, hm, rk] = await Promise.all([
      dtOverview(), dtTimeline(), dtHeatmap(), dtRiskCandidates(),
    ]).catch((err: unknown) => {
      setError(userMessage(err));
      return [null, null, null, null];
    });
    setMode(o ? { mode: o.mode, auto_control: o.auto_control } : null);
    setTimeline(tl ?? null);
    setHeatmap(hm ?? null);
    setRisks(rk?.candidates ?? []);
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onSimulate = async () => {
    setBusy(true);
    setError("");
    try {
      const r = await dtSimulate();
      setSimRows(r.results);
    } catch (e) {
      setError(userMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const onPredict = async () => {
    setBusy(true);
    setError("");
    try {
      await dtPredict({ actor: "human", reason: "例行风险预测" });
      const r = await dtRiskCandidates();
      setRisks(r.candidates);
    } catch (e) {
      setError(userMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const onDismiss = async (id: string) => {
    try {
      await dtDismissRisk(id, { actor: "human", reason: "人工驳回风险" });
      const r = await dtRiskCandidates();
      setRisks(r.candidates);
    } catch (e) {
      setError(userMessage(e));
    }
  };

  const simColumns = [
    { title: "场景", dataIndex: "label", key: "label" },
    { title: "预计完成", dataIndex: "eta_hours", key: "eta", render: (v: number) => `${v}h` },
    { title: "成本", dataIndex: "cost", key: "cost", render: (v: number) => `¥${v}` },
    { title: "瓶颈", dataIndex: "bottleneck", key: "bottleneck", render: (v: string) => <Tag color="orange">{v}</Tag> },
  ];

  const riskColumns = [
    { title: "风险", dataIndex: "risk_type", key: "type", render: (v: string) => <Tag color={RISK_COLORS[v]}>{v}</Tag> },
    { title: "目标", dataIndex: "target_id", key: "target", render: (v: string, r: DTRiskCandidate) => `${r.target_type}: ${v}` },
    { title: "严重度", dataIndex: "severity", key: "severity", render: (v: string) => <Tag color={SEVERITY_COLORS[v]}>{v}</Tag> },
    { title: "建议", dataIndex: "suggestion", key: "suggestion" },
    { title: "状态", dataIndex: "status", key: "status", render: (v: string) => <Tag>{v}</Tag> },
    {
      title: "操作", key: "ops",
      render: (_: unknown, r: DTRiskCandidate) => r.status === "proposed"
        ? <Button size="small" onClick={() => onDismiss(r.id)}>驳回</Button>
        : "-",
    },
  ];

  return (
    <div className="page-container">
      <div className="page-header">
        <Title level={3} style={{ marginBottom: 4 }}>
          <DashboardOutlined /> Production Digital Twin <Text type="secondary">生产数字孪生</Text>
        </Title>
        <Text type="secondary">
          Runtime Mirror · Episode 甘特图 · Resource Heatmap · Queue Simulation · Risk Prediction（仅模拟与可见性）
        </Text>
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message={`模式：${mode?.mode ?? "…"} / auto_control=${mode?.auto_control ?? "…"}`}
        description="数字孪生是 KG + Runtime + Analytics 的实时模拟层，不是新的生产系统；模拟与风险候选绝不自动修改生产状态。"
      />

      {timeline && (
        <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
          <Col span={4}><Card size="small"><Statistic title="活跃任务" value={timeline.episodes.reduce((n, e) => n + e.stages.filter((s) => ["in_progress", "assigned"].includes(s.status)).length, 0)} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="阻塞" value={timeline.blocked_total} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="返工" value={timeline.rework_total} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="等待人工" value={timeline.waiting_human_total} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="并行集" value={heatmap?.production.parallel_episodes ?? 0} /></Card></Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="GPU 使用率" value={heatmap ? Math.round(heatmap.gpu.usage * 100) : 0} suffix="%" />
              <Progress percent={heatmap ? Math.round(heatmap.gpu.usage * 100) : 0} size="small" />
            </Card>
          </Col>
        </Row>
      )}

      <Card size="small" title={<span><ThunderboltOutlined /> Episode 甘特图（Timeline）</span>} style={{ marginBottom: 12 }}>
        <Table
          size="small"
          rowKey={(row) => row.episode_id}
          pagination={{ pageSize: 8 }}
          dataSource={timeline?.episodes ?? []}
          columns={[
            { title: "集", dataIndex: "episode_id", key: "ep", width: 80, render: (v: string) => <Text strong>{v}</Text> },
            {
              title: "阶段流水线",
              key: "stages",
              render: (_: unknown, row: DTTimeline["episodes"][number]) => (
                <Space wrap>
                  {row.stages.map((s) => (
                    <Tag key={s.stage} color={STATUS_COLORS[s.status] ?? "default"}>
                      {STAGE_LABELS[s.stage] ?? s.stage}:{s.status}
                      {s.duration_s != null ? `(${(s.duration_s / 60).toFixed(0)}m)` : ""}
                    </Tag>
                  ))}
                </Space>
              ),
            },
            { title: "阻塞", dataIndex: "blocked_count", key: "blocked", width: 70 },
            { title: "返工", dataIndex: "rework_count", key: "rework", width: 70 },
            { title: "等人工", dataIndex: "waiting_human", key: "waiting", width: 70 },
          ]}
        />
      </Card>

      <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
        <Col span={12}>
          <Card size="small" title={<span><FundOutlined /> Resource Heatmap</span>}>
            {heatmap ? (
              <Space direction="vertical" style={{ width: "100%" }}>
                <Space wrap>
                  <Tag color="blue">GPU 队列 {heatmap.gpu.queue_length}</Tag>
                  <Tag color="blue">活跃任务 {heatmap.gpu.active_tasks}</Tag>
                  <Tag color="blue">Worker 空闲 {(heatmap.gpu.worker_idle_rate * 100).toFixed(0)}%</Tag>
                  <Tag color="blue">VRAM ~{heatmap.gpu.vram_mb}MB</Tag>
                </Space>
                <div>
                  <Text strong>Retry 热点：</Text>
                  {Object.entries(heatmap.production.retry_hotspots).map(([stage, n]) => (
                    <Tag key={stage} color="purple">{STAGE_LABELS[stage] ?? stage}: {n}</Tag>
                  ))}
                </div>
                <div>
                  <Text strong>阶段密度：</Text>
                  {Object.entries(heatmap.production.stage_density).map(([stage, n]) => (
                    <Tag key={stage}>{STAGE_LABELS[stage] ?? stage}: {n}</Tag>
                  ))}
                </div>
              </Space>
            ) : <Text type="secondary">暂无数据</Text>}
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title={<span><ExperimentOutlined /> Queue Simulation（≥3 场景）</span>} extra={<Button size="small" type="primary" loading={busy} onClick={onSimulate}>运行模拟</Button>}>
            {simRows.length > 0 ? (
              <Table size="small" rowKey="scenario" pagination={false} dataSource={simRows} columns={simColumns} />
            ) : (
              <Text type="secondary">点击「运行模拟」生成基线 / 20 集 / GPU-50% / 速度-30% / 返工+10% 场景预测</Text>
            )}
          </Card>
        </Col>
      </Row>

      <Card size="small" title={<span><BarChartOutlined /> Risk Prediction（RiskCandidate，仅建议）</span>} extra={<Button size="small" type="primary" loading={busy} onClick={onPredict}>生成风险候选</Button>}>
        <Table size="small" rowKey="id" pagination={{ pageSize: 8 }} dataSource={risks} columns={riskColumns} />
      </Card>

      {error ? <Alert style={{ marginTop: 12 }} type="error" showIcon message={error} /> : null}
    </div>
  );
};

export default DigitalTwin;

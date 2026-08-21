/**
 * Production Command Center (Phase 14.3, GPT spec).
 *
 * 三系统融合层：当前生产态（Digital Twin）/ 未来预测（Simulation）/
 * 风险（Risk）+ 优化建议（Production Intelligence）/ 人工审批入口。
 * Control Suggestion ≠ Auto Control。
 */

import React, { useEffect, useState } from "react";
import {
  Alert, Card, Col, Progress, Row, Space, Statistic, Table, Tag, Typography,
} from "antd";
import { ControlOutlined, FundOutlined, RadarChartOutlined, RocketOutlined } from "@ant-design/icons";

import { ccOverview, type CommandCenterOverview } from "@/api/commandCenter";
import { userMessage } from "@/api/client";

const { Title, Text } = Typography;

const RISK_COLORS: Record<string, string> = {
  schedule: "blue", episode: "purple", quality: "red", asset: "orange", budget: "gold",
};
const SEVERITY_COLORS: Record<string, string> = { low: "default", medium: "orange", high: "red" };

const CommandCenter: React.FC = () => {
  const [overview, setOverview] = useState<CommandCenterOverview | null>(null);
  const [error, setError] = useState("");

  const load = async () => {
    ccOverview().then(setOverview).catch((e: Error) => setError(userMessage(e)));
  };

  useEffect(() => {
    load();
  }, []);

  const predictionColumns = [
    { title: "场景", dataIndex: "label", key: "label" },
    { title: "预计完成", dataIndex: "eta_hours", key: "eta", render: (v: number) => `${v}h` },
    { title: "成本", dataIndex: "cost", key: "cost", render: (v: number) => `¥${v}` },
    { title: "瓶颈", dataIndex: "bottleneck", key: "bottleneck", render: (v: string) => <Tag color="orange">{v}</Tag> },
  ];

  const riskColumns = [
    { title: "风险", dataIndex: "risk_type", key: "type", render: (v: string) => <Tag color={RISK_COLORS[v]}>{v}</Tag> },
    { title: "目标", dataIndex: "target_id", key: "target" },
    { title: "严重度", dataIndex: "severity", key: "severity", render: (v: string) => <Tag color={SEVERITY_COLORS[v]}>{v}</Tag> },
    { title: "建议", dataIndex: "suggestion", key: "suggestion" },
  ];

  return (
    <div className="page-container">
      <div className="page-header">
        <Title level={3} style={{ marginBottom: 4 }}>
          <ControlOutlined /> Production Command Center <Text type="secondary">生产指挥中心</Text>
        </Title>
        <Text type="secondary">
          Knowledge Graph + Digital Twin + Production Intelligence 三系统融合层
        </Text>
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="Control Suggestion ≠ Auto Control"
        description={`${overview?.note ?? ""} 当前模式：${overview?.mode ?? "…"} / auto_control=${overview?.governance?.auto_control ?? "…"}`}
      />

      {overview && (
        <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
          <Col span={4}><Card size="small"><Statistic title="任务总量" value={overview.production_state.task_total} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="活跃任务" value={overview.production_state.active_tasks} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="Worker" value={overview.production_state.worker_count} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="等待人工" value={overview.production_state.waiting_human} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="KG 节点" value={overview.knowledge_graph.nodes} /></Card></Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="GPU 使用率" value={Math.round(overview.production_state.gpu_usage * 100)} suffix="%" />
              <Progress percent={Math.round(overview.production_state.gpu_usage * 100)} size="small" />
            </Card>
          </Col>
        </Row>
      )}

      <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
        <Col span={8}>
          <Card size="small" title={<span><FundOutlined /> 生产态 + 时间线摘要</span>}>
            {overview && (
              <Space direction="vertical">
                <Tag>队列深度 {overview.production_state.queue_depth}</Tag>
                <Tag>并行集 {overview.timeline_summary.parallel_episodes}</Tag>
                <Tag color="warning">阻塞 {overview.timeline_summary.blocked_total}</Tag>
                <Tag color="purple">返工 {overview.timeline_summary.rework_total}</Tag>
                <Tag color="magenta">等待人工 {overview.timeline_summary.waiting_human_total}</Tag>
              </Space>
            )}
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small" title={<span><RocketOutlined /> 预测（Queue Simulation）</span>}>
            {overview ? (
              <Table size="small" rowKey="scenario" pagination={false}
                     dataSource={overview.prediction} columns={predictionColumns} />
            ) : null}
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small" title={<span><RadarChartOutlined /> 审批入口（人工）</span>}>
            {overview && (
              <Space direction="vertical">
                <Statistic title="等待人工任务" value={overview.approvals_pending.waiting_human} />
                <Statistic title="优化候选待审" value={overview.approvals_pending.pi_candidates} />
                <Statistic title="风险候选待审" value={overview.approvals_pending.risk_candidates} />
                <Text type="secondary">审计覆盖率 {(overview.audit_coverage * 100).toFixed(0)}%</Text>
              </Space>
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[12, 12]}>
        <Col span={12}>
          <Card size="small" title="风险候选（RiskCandidate，仅建议）">
            <Table size="small" rowKey={(r) => String(r.id)} pagination={{ pageSize: 6 }}
                   dataSource={overview?.risks ?? []} columns={riskColumns} />
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title="优化候选（Production Intelligence，人工审批）">
            <Table
              size="small"
              rowKey={(r) => String(r.id)}
              pagination={{ pageSize: 6 }}
              dataSource={overview?.intelligence.pi_candidates ?? []}
              columns={[
                { title: "ID", dataIndex: "id", key: "id" },
                { title: "目标", dataIndex: "target_type", key: "tt", render: (v: string, r: Record<string, unknown>) => `${v}: ${r.target_id}` },
                { title: "原因", dataIndex: "reason", key: "reason" },
                { title: "状态", dataIndex: "status", key: "status", render: (v: string) => <Tag>{v}</Tag> },
              ]}
            />
          </Card>
        </Col>
      </Row>

      {error ? <Alert style={{ marginTop: 12 }} type="error" showIcon message={error} /> : null}
    </div>
  );
};

export default CommandCenter;

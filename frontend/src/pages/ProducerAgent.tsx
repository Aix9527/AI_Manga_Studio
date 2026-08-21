/**
 * AI Producer Agent workbench (Phase 14.4, GPT spec).
 *
 * 负责：项目规划 / 资源建议 / 风险解释 / 制作报告；
 * 不负责：自动批准 / 自动调度（所有输出仅建议，人工审批后生效）。
 */

import React, { useEffect, useState } from "react";
import { Alert, Button, Card, Col, Row, Space, Table, Tag, Typography } from "antd";
import { FileTextOutlined, FundOutlined, ProfileOutlined, ThunderboltOutlined } from "@ant-design/icons";

import {
  producerPlan, producerReport, producerResource,
  type ProducerPlan, type ProducerReport, type ResourceSuggestion,
} from "@/api/producerAgent";
import { userMessage } from "@/api/client";

const { Title, Text } = Typography;

const ProducerAgent: React.FC = () => {
  const [plan, setPlan] = useState<ProducerPlan | null>(null);
  const [resource, setResource] = useState<ResourceSuggestion | null>(null);
  const [report, setReport] = useState<ProducerReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    const [p, r, rep] = await Promise.all([
      producerPlan(), producerResource(), producerReport(),
    ]).catch((err: unknown) => {
      setError(userMessage(err));
      return [null, null, null];
    });
    setPlan(p ?? null);
    setResource(r ?? null);
    setReport(rep ?? null);
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onRefresh = async () => {
    setBusy(true);
    setError("");
    try {
      await load();
    } finally {
      setBusy(false);
    }
  };

  const stepColumns = [
    { title: "优先级", dataIndex: "priority", key: "p", width: 70, render: (v: number) => <Tag color={v === 1 ? "red" : v === 2 ? "orange" : "default"}>{v}</Tag> },
    { title: "动作", dataIndex: "action", key: "action" },
    { title: "说明", dataIndex: "detail", key: "detail" },
  ];

  return (
    <div className="page-container">
      <div className="page-header">
        <Title level={3} style={{ marginBottom: 4 }}>
          <ProfileOutlined /> AI Producer Agent <Text type="secondary">AI 制片人</Text>
        </Title>
        <Text type="secondary">
          项目规划 · 资源建议 · 风险解释 · 制作报告（不自动批准 / 不自动调度）
        </Text>
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="Producer 是建议层，不是决策者"
        description="基于 Executive Producer + Analytics + Digital Twin + KG；发布 / 预算 / 路由变更 / 成片锁定仍需人工审批（auto_approve=false / auto_schedule=false）。"
      />

      {plan && (
        <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
          <Col span={4}><Card size="small"><Text strong>活跃任务</Text><div>{plan.summary.active_tasks}</div></Card></Col>
          <Col span={4}><Card size="small"><Text strong>等待人工</Text><div><Tag color={plan.summary.waiting_human > 0 ? "magenta" : "default"}>{plan.summary.waiting_human}</Tag></div></Card></Col>
          <Col span={4}><Card size="small"><Text strong>阻塞</Text><div><Tag color={plan.summary.blocked > 0 ? "warning" : "default"}>{plan.summary.blocked}</Tag></div></Card></Col>
          <Col span={4}><Card size="small"><Text strong>并行集</Text><div>{plan.summary.parallel_episodes}</div></Card></Col>
          <Col span={8}>
            <Card size="small">
              <Text strong>治理门禁</Text>
              <div><Tag color="green">auto_approve=false</Tag><Tag color="green">auto_schedule=false</Tag></div>
            </Card>
          </Col>
        </Row>
      )}

      <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
        <Col span={12}>
          <Card size="small" title={<span><ThunderboltOutlined /> 项目规划建议（Producer Plan）</span>} extra={<Button size="small" type="primary" loading={busy} onClick={onRefresh}>刷新</Button>}>
            {plan ? (
              <Table size="small" rowKey="action" pagination={false} dataSource={plan.steps} columns={stepColumns} />
            ) : <Text type="secondary">加载中…</Text>}
            {plan?.note ? <Text type="secondary" style={{ fontSize: 12 }}>{plan.note}</Text> : null}
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title={<span><FundOutlined /> 资源建议（Resource Suggestion）</span>}>
            {resource && resource.suggestions.length > 0 ? (
              <Space direction="vertical">
                {resource.suggestions.map((s, i) => (
                  <Alert key={i} type={s.kind === "risk" ? "warning" : "info"} showIcon message={s.suggestion} />
                ))}
                <Text type="secondary" style={{ fontSize: 12 }}>{resource.note}</Text>
              </Space>
            ) : (
              <Text type="secondary">当前负载下无显著容量缺口建议（可运行 Queue Simulation 复核）</Text>
            )}
          </Card>
        </Col>
      </Row>

      <Card size="small" title={<span><FileTextOutlined /> 制作报告（Producer Report）</span>}>
        {report && (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Space wrap>
              <Tag>任务 {String(report.production_state.task_total)}</Tag>
              <Tag>活跃 {String(report.production_state.active_tasks)}</Tag>
              <Tag>Worker {String(report.production_state.worker_count)}</Tag>
              <Tag color="warning">阻塞 {String(report.timeline_summary.blocked_total)}</Tag>
              <Tag color="purple">返工 {String(report.timeline_summary.rework_total)}</Tag>
              <Tag color="magenta">等待人工 {String(report.approvals_pending.waiting_human)}</Tag>
              <Tag>KG 节点 {String(report.knowledge_graph.nodes)}</Tag>
              <Tag>风险 {report.risks.length}</Tag>
              <Tag>优化候选 {report.optimization_candidates.length}</Tag>
            </Space>
            <Text type="secondary" style={{ fontSize: 12 }}>{report.note}</Text>
          </Space>
        )}
      </Card>

      {error ? <Alert style={{ marginTop: 12 }} type="error" showIcon message={error} /> : null}
    </div>
  );
};

export default ProducerAgent;

/**
 * Team Collaboration panel (Phase 13.5-C, GPT spec).
 *
 * Episode 流水线泳道（策划｜编剧｜分镜｜资产｜生成｜质检｜剪辑｜声音｜成片）、
 * 负责人 / 状态 / 返工次数 / 等待人工项、审计时间线，以及人工审批操作
 * （开始 / 通过评审 / 完成任务 / 升级重试；final 与升级操作要求 approval_id）。
 */

import React, { useEffect, useState } from "react";
import { Alert, Button, Card, Col, Input, Row, Select, Space, Statistic, Table, Tag, Typography } from "antd";

import {
  completeAssignment,
  escalateAssignment,
  listAssignments,
  reviewAssignment,
  startAssignment,
  teamAudit,
  teamFlow,
  teamStats,
  type FlowView,
  type TeamAssignment,
  type TeamAuditRow,
  type TeamStats,
} from "@/api/team";
import { userMessage } from "@/api/client";

const { Title, Text } = Typography;

const STAGE_ORDER = ["planning", "script", "storyboard", "assets", "generation", "qc", "editing", "sound", "final"];
const STAGE_LABELS: Record<string, string> = {
  planning: "策划", script: "编剧", storyboard: "分镜", assets: "资产",
  generation: "生成", qc: "质检", editing: "剪辑", sound: "声音", final: "成片",
};

const STATUS_COLORS: Record<string, string> = {
  planned: "default", assigned: "blue", in_progress: "processing", review: "orange",
  approved: "green", done: "success", rework: "purple", blocked: "warning",
  failed: "red", escalated: "magenta", cancelled: "default",
};

const STATUS_LABELS: Record<string, string> = {
  planned: "待分派", assigned: "已分派", in_progress: "进行中", review: "评审中",
  approved: "已批准", done: "完成", rework: "返工", blocked: "阻塞",
  failed: "失败", escalated: "已升级", cancelled: "已取消",
};

const TeamCollaboration: React.FC<{ projectId: string }> = ({ projectId }) => {
  const [stats, setStats] = useState<TeamStats | null>(null);
  const [flow, setFlow] = useState<FlowView | null>(null);
  const [assignments, setAssignments] = useState<TeamAssignment[]>([]);
  const [auditRows, setAuditRows] = useState<TeamAuditRow[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [approvalId, setApprovalId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    const [s, f, a, au] = await Promise.all([
      teamStats(), teamFlow(projectId), listAssignments({ project_id: projectId }), teamAudit(projectId),
    ]).catch((err: unknown) => {
      setError(userMessage(err));
      return [null, null, null, null];
    });
    setStats(s ?? null);
    setFlow(f ?? null);
    setAssignments(a?.assignments ?? []);
    setAuditRows(au?.audit ?? []);
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const selected = assignments.find((a) => a.id === selectedId) ?? null;

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      await load();
    } catch (e) {
      setError(userMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const onStart = () => selected && run(() => startAssignment(selected.id, { actor: "human", reason: "开始任务" }));
  const onApprove = () => selected && run(() => reviewAssignment(selected.id, {
    reviewer_role: selected.role, reviewer_id: "human", verdict: "approve",
    evidence: { frontend_manual: true }, actor: "human", reason: "人工通过评审",
    approval_id: selected.stage === "final" ? approvalId : "",
  }));
  const onComplete = () => selected && run(() => completeAssignment(selected.id, {
    actor: "human", reason: "任务完成", approval_id: selected.stage === "final" ? approvalId : "",
  }));
  const onRetry = () => selected && run(() => escalateAssignment(selected.id, {
    decision: "retry", approval_id: approvalId, actor: "human", reason: "人工批准重试",
  }));

  const needsApproval = selected ? (selected.status === "escalated" || selected.stage === "final") : false;

  const stageColumns = [
    { title: "集", dataIndex: "episode_id", key: "episode", width: 90, render: (v: string) => <Text strong>{v}</Text> },
    ...STAGE_ORDER.map((stage) => ({
      title: STAGE_LABELS[stage],
      key: stage,
      render: (_: unknown, row: FlowView["episodes"][number]) => {
        const view = row.stages[stage];
        if (!view) return <Text type="secondary">-</Text>;
        return (
          <Space direction="vertical" size={0}>
            <Tag color={STATUS_COLORS[view.status] ?? "default"}>{STATUS_LABELS[view.status] ?? view.status}</Tag>
            <Text type="secondary" style={{ fontSize: 11 }}>{view.role} · 尝试{view.attempt}</Text>
          </Space>
        );
      },
    })),
    { title: "返工", dataIndex: "rework_count", key: "rework", width: 70, render: (v: number) => (v > 0 ? <Tag color="purple">{v}</Tag> : <Text type="secondary">0</Text>) },
    { title: "等人工", dataIndex: "waiting_human", key: "waiting", width: 70, render: (v: number) => (v > 0 ? <Tag color="magenta">{v}</Tag> : <Text type="secondary">0</Text>) },
  ];

  const auditColumns = [
    { title: "时间", dataIndex: "timestamp", key: "ts" },
    { title: "事件", dataIndex: "event", key: "event", render: (v: string) => <Tag>{v}</Tag> },
    { title: "操作人", dataIndex: "actor", key: "actor" },
    { title: "任务", dataIndex: "assignment_id", key: "aid", render: (v: string) => v || "-" },
    { title: "原因", dataIndex: "reason", key: "reason" },
  ];

  return (
    <div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="团队协作 = 编排 + 人工审批门"
        description="分派复用 TaskQueue（新建队列 0）；每次状态迁移写审计（覆盖率 100%）；返工定向路由且禁止无限返工；升级处理与最终成片锁定必须 approval_id。"
      />
      {stats && (
        <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
          <Col span={4}><Card size="small"><Statistic title="任务数" value={stats.assignments} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="审计覆盖率" value={stats.audit_coverage} precision={2} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="新建队列" value={stats.new_queue_count} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="非法迁移" value={stats.illegal_transitions} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="无限返工" value={stats.infinite_rework} /></Card></Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="治理门禁" value={stats.governance.human_approval ? "开启" : "关闭"} />
              <Text type="secondary">auto_apply=false</Text>
            </Card>
          </Col>
        </Row>
      )}

      <Card size="small" title="Episode 流水线泳道" style={{ marginBottom: 12 }}>
        <Table
          rowKey="episode_id"
          size="small"
          pagination={false}
          dataSource={flow?.episodes ?? []}
          columns={stageColumns}
        />
      </Card>

      <Row gutter={[12, 12]}>
        <Col span={12}>
          <Card size="small" title="人工操作台（审批门）">
            <Space direction="vertical" style={{ width: "100%" }}>
              <Select
                style={{ width: "100%" }}
                placeholder="选择进行中的任务"
                value={selectedId || undefined}
                onChange={(v) => { setSelectedId(v); setApprovalId(""); }}
                options={assignments
                  .filter((a) => !["done", "cancelled", "failed"].includes(a.status))
                  .map((a) => ({
                    value: a.id,
                    label: `${a.id} · ${STAGE_LABELS[a.stage] ?? a.stage} · ${STATUS_LABELS[a.status] ?? a.status}`,
                  }))}
              />
              {selected && (
                <Space wrap>
                  <Tag color={STATUS_COLORS[selected.status]}>{STATUS_LABELS[selected.status]}</Tag>
                  <Tag>{STAGE_LABELS[selected.stage] ?? selected.stage}</Tag>
                  <Tag>{selected.role}</Tag>
                  <Tag>返工 {selected.rework_count}</Tag>
                  {selected.task_id ? <Tag>TaskQueue: {selected.task_id}</Tag> : null}
                </Space>
              )}
              {needsApproval && (
                <Input
                  placeholder="approval_id（人工审批门）"
                  value={approvalId}
                  onChange={(e) => setApprovalId(e.target.value)}
                />
              )}
              <Space wrap>
                <Button size="small" type="primary" loading={busy} disabled={!selected || selected.status !== "assigned"} onClick={onStart}>开始</Button>
                <Button size="small" loading={busy} disabled={!selected || selected.status !== "in_progress"} onClick={onApprove}>通过评审</Button>
                <Button size="small" loading={busy} disabled={!selected || selected.status !== "approved"} onClick={onComplete}>完成任务</Button>
                <Button size="small" type="primary" danger loading={busy} disabled={!selected || selected.status !== "escalated"} onClick={onRetry}>升级重试</Button>
              </Space>
              {error ? <Alert type="error" showIcon message={error} /> : null}
            </Space>
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title="审计时间线（append-only）">
            <Table
              rowKey={(row) => row.id}
              size="small"
              pagination={{ pageSize: 6 }}
              dataSource={auditRows}
              columns={auditColumns}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default TeamCollaboration;

/**
 * Director Evolution Center (Phase 12.2, GPT spec).
 *
 * Modules: Policy Performance / Candidate Queue / Approval History /
 * Rollback Center / Director Win Rate, backed by the Director Memory +
 * Controlled Evolution APIs.
 */

import React, { useEffect } from "react";

import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Descriptions,
  Progress,
  Row,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Timeline,
  Typography,
} from "antd";
import {
  AuditOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CloudDownloadOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  HistoryOutlined,
  InboxOutlined,
  LockOutlined,
  RollbackOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
  TrophyOutlined,
} from "@ant-design/icons";

import type { Candidate, HistoryEntry, PolicyPerformanceRow } from "@/api/directorEvolution";
import type { AdaptiveRecommendation } from "@/api/adaptiveRouter";
import type { AuditEntry, ReleaseResult } from "@/api/governance";
import { useDirectorEvolutionStore, type DirectorEvolutionState } from "@/state/directorEvolutionStore";

const { Title, Text } = Typography;

const ROUTE_TAG_COLORS: Record<string, string> = {
  rule: "blue",
  qwen: "purple",
  hybrid: "orange",
};

const ACTION_TAGS: Record<string, string> = {
  approve: "green",
  reject: "red",
  rollback: "orange",
};

const DirectorEvolutionCenter: React.FC = () => {
  const store = useDirectorEvolutionStore();

  useEffect(() => {
    store.refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const source = store.source;
  const candidates = store.candidates?.candidates ?? [];
  const routes = store.stats?.routes ?? {};
  const accumulation = store.accumulation;

  const performanceColumns = [
    { title: "场景类型", dataIndex: "scene_type", key: "scene_type" },
    {
      title: "导演策略",
      dataIndex: "director",
      key: "director",
      render: (director: string) => (
        <Tag color={ROUTE_TAG_COLORS[director.replace("-v2", "")] ?? "default"}>{director}</Tag>
      ),
    },
    { title: "样本数", dataIndex: "shots", key: "shots" },
    {
      title: "平均质量分",
      dataIndex: "avg_score",
      key: "avg_score",
      render: (v: number | null) => (v === null ? "-" : v),
    },
    {
      title: "平均成本",
      dataIndex: "avg_cost",
      key: "avg_cost",
      render: (v: number | null) => (v === null ? "-" : `${v}s`),
    },
    {
      title: "平均生成时间",
      dataIndex: "avg_generation_time",
      key: "avg_generation_time",
      render: (v: number | null) => (v === null ? "-" : `${v}s`),
    },
    {
      title: "平均人工分",
      dataIndex: "avg_human_score",
      key: "avg_human_score",
      render: (v: number | null) => (v === null ? "-" : v),
    },
    { title: "重做次数", dataIndex: "revisions", key: "revisions" },
  ];

  const winRateColumns = [
    { title: "场景类型", dataIndex: "scene_type", key: "scene_type" },
    {
      title: "胜出策略",
      dataIndex: "winner",
      key: "winner",
      render: (winner: string) => (
        <Tag color={ROUTE_TAG_COLORS[winner.replace("-v2", "")] ?? "gold"}>
          <TrophyOutlined /> {winner}
        </Tag>
      ),
    },
    { title: "平均分", dataIndex: "avg_score", key: "avg_score" },
    { title: "样本数", dataIndex: "shots", key: "shots" },
  ];

  const historyColumns = [
    { title: "动作", dataIndex: "action", key: "action", render: (a: string) => <Tag color={ACTION_TAGS[a] ?? "default"}>{a}</Tag> },
    { title: "候选", dataIndex: ["candidate", "scene_type"], key: "scene", render: (_: unknown, row: HistoryEntry) => row.candidate?.scene_type ?? "-" },
    { title: "版本", key: "version", render: (_: unknown, row: HistoryEntry) => `${row.policy_version_before ?? "-"} → ${row.policy_version_after ?? "-"}` },
    { title: "受影响镜数", dataIndex: "affected_shots", key: "shots", render: (v: number | undefined) => v ?? "-" },
    { title: "分数变化", dataIndex: "score_delta", key: "delta", render: (v: number | undefined) => (v === undefined ? "-" : `+${v}`) },
    { title: "操作人", key: "operator", render: (_: unknown, row: HistoryEntry) => row.approved_by ?? row.rejected_by ?? row.rolled_back_by ?? "-" },
    { title: "时间", dataIndex: "created_at", key: "time" },
  ];

  const candidateDiff = (candidate: Candidate) => (
    <Space size={4}>
      <Tag color={ROUTE_TAG_COLORS[candidate.from_director.replace("-v2", "")] ?? "default"}>{candidate.from_director}</Tag>
      <span>→</span>
      <Tag color={ROUTE_TAG_COLORS[candidate.to_director.replace("-v2", "")] ?? "gold"}>{candidate.to_director}</Tag>
    </Space>
  );

  const renderTimeline = () => {
    const entries = [...store.history].reverse();
    if (entries.length === 0) {
      return <Text type="secondary">暂无策略变更记录（数据积累后自动生成）</Text>;
    }
    return (
      <Timeline
        items={entries.map((entry) => ({
          color: entry.action === "approve" ? "green" : entry.action === "reject" ? "red" : "orange",
          children: (
            <Space direction="vertical" size={0}>
              <Text strong>
                {entry.action.toUpperCase()} — {entry.candidate?.scene_type ?? "policy"}
              </Text>
              <Text type="secondary">
                版本 {entry.policy_version_before ?? "-"} → {entry.policy_version_after ?? "-"}
                {entry.affected_shots ? ` · 影响 ${entry.affected_shots} 镜` : ""}
                {entry.score_delta ? ` · Δ +${entry.score_delta}` : ""}
              </Text>
            </Space>
          ),
        }))}
      />
    );
  };

  return (
    <div className="evolution-center" style={{ padding: 24 }}>
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Space align="center" style={{ width: "100%", justifyContent: "space-between" }}>
          <Title level={3} style={{ margin: 0 }}>
            <ExperimentOutlined /> Director Evolution Center
          </Title>
          <Space>
            <Button
              size="small"
              type={source === "production" ? "primary" : "default"}
              onClick={() => store.setSource("production")}
            >
              生产数据
            </Button>
            <Button size="small" type={source === "mock" ? "primary" : "default"} onClick={() => store.setSource("mock")}>
              Mock 演示
            </Button>
            <Button size="small" icon={<CloudDownloadOutlined />} onClick={() => store.seedMock()} disabled={source === "production"}>
              生成 Mock
            </Button>
            <Button size="small" icon={<HistoryOutlined />} onClick={() => store.refresh()}>
              刷新
            </Button>
          </Space>
        </Space>

        {store.error && <Alert type="error" message={store.error} showIcon />}

        <Card size="small" title={`当前策略版本 v${store.stats?.policy_version ?? "-"}`}>
          <Row gutter={16}>
            <Col span={6}>
              <Statistic title="已生成镜头" value={accumulation?.shots ?? 0} suffix={`/ ${accumulation?.targets.shots ?? 500}`} />
              <Progress
                percent={Math.min(100, Math.round(((accumulation?.shots ?? 0) / (accumulation?.targets.shots ?? 500)) * 100))}
                size="small"
              />
            </Col>
            <Col span={6}>
              <Statistic title="项目数" value={accumulation?.projects ?? 0} suffix={`/ ${accumulation?.targets.projects ?? 3}`} />
            </Col>
            <Col span={6}>
              <Statistic title="反馈记录" value={accumulation?.feedback_records ?? 0} suffix={`/ ${accumulation?.targets.feedback_records ?? 1000}`} />
            </Col>
            <Col span={6}>
              <Statistic title="重做次数" value={accumulation?.revisions ?? 0} />
            </Col>
          </Row>
          <Descriptions size="small" style={{ marginTop: 12 }} column={4}>
            {Object.entries(routes).map(([sceneType, route]) => (
              <Descriptions.Item key={sceneType} label={sceneType}>
                <Tag color={ROUTE_TAG_COLORS[route] ?? "default"}>{route}</Tag>
              </Descriptions.Item>
            ))}
          </Descriptions>
        </Card>

        <Tabs
          items={[
            {
              key: "performance",
              label: "Policy Performance",
              children: (
                <Table<PolicyPerformanceRow>
                  rowKey={(row) => `${row.scene_type}|${row.director}`}
                  columns={performanceColumns}
                  dataSource={store.performance}
                  pagination={{ pageSize: 10 }}
                  size="small"
                />
              ),
            },
            {
              key: "candidates",
              label: (
                <Badge count={candidates.length} size="small" offset={[8, -2]}>
                  Candidate Queue
                </Badge>
              ),
              children: (
                <Space direction="vertical" size={12} style={{ width: "100%" }}>
                  {candidates.length === 0 && <Alert type="info" message="暂无满足阈值（min_samples / confidence）的候选" showIcon />}
                  {candidates.map((candidate) => (
                    <Card
                      key={candidate.id}
                      size="small"
                      title={
                        <Space>
                          <Tag color="geekblue">{candidate.scene_type}</Tag>
                          {candidateDiff(candidate)}
                        </Space>
                      }
                      extra={
                        <Space>
                          <Button size="small" type="primary" icon={<CheckCircleOutlined />} onClick={() => store.approve(candidate.id)}>
                            Approve
                          </Button>
                          <Button size="small" danger icon={<CloseCircleOutlined />} onClick={() => store.reject(candidate.id)}>
                            Reject
                          </Button>
                        </Space>
                      }
                    >
                      <Descriptions size="small" column={4}>
                        <Descriptions.Item label="样本数">{candidate.samples_from} → {candidate.samples_to}</Descriptions.Item>
                        <Descriptions.Item label="平均分">{candidate.avg_from} → {candidate.avg_to}</Descriptions.Item>
                        <Descriptions.Item label="Score Δ">+{candidate.score_delta}</Descriptions.Item>
                        <Descriptions.Item label="Confidence">{candidate.confidence}</Descriptions.Item>
                      </Descriptions>
                    </Card>
                  ))}
                </Space>
              ),
            },
            {
              key: "history",
              label: "Approval History",
              children: (
                <Table<HistoryEntry>
                  rowKey={(row) => row.id}
                  columns={historyColumns}
                  dataSource={store.history}
                  pagination={{ pageSize: 8 }}
                  size="small"
                />
              ),
            },
            {
              key: "rollback",
              label: "Rollback Center",
              children: (
                <Space direction="vertical" size={16} style={{ width: "100%" }}>
                  <Card size="small" title="版本回滚">
                    <Space direction="vertical">
                      <Text>
                        当前版本：<Tag>v{store.stats?.policy_version ?? "-"}</Tag>
                      </Text>
                      <Text type="secondary">回滚将恢复最近一次策略快照（router_policy_vN.yaml），内容回退、版本号保持单调递增，并写入审计日志。</Text>
                      <Button danger icon={<RollbackOutlined />} onClick={() => store.rollback()} loading={store.loading}>
                        回滚到上一版本
                      </Button>
                    </Space>
                  </Card>
                  <Card size="small" title="进化时间线">
                    {renderTimeline()}
                  </Card>
                </Space>
              ),
            },
            {
              key: "adaptive",
              label: (
                <Badge count={store.adaptive?.count ?? 0} size="small" offset={[8, -2]}>
                  Adaptive Router
                </Badge>
              ),
              children: <AdaptiveRouterPanel store={store} />,
            },
            {
              key: "production",
              label: (
                <Badge count={store.auditEntries.length} size="small" offset={[8, -2]}>
                  Production OS
                </Badge>
              ),
              children: <ProductionOSPanel store={store} />,
            },
            {
              key: "winrate",
              label: "Director Win Rate",
              children: (
                <Space direction="vertical" size={16} style={{ width: "100%" }}>
                  <Card size="small">
                    <Row gutter={16}>
                      {Object.entries(store.winRate?.counts ?? {}).map(([strategy, count]) => (
                        <Col span={8} key={strategy}>
                          <Statistic title={`${strategy} 胜出场景数`} value={count} />
                        </Col>
                      ))}
                    </Row>
                  </Card>
                  <Table
                    rowKey={(row) => row.scene_type}
                    columns={winRateColumns}
                    dataSource={store.winRate?.by_scene_type ?? []}
                    pagination={false}
                    size="small"
                  />
                </Space>
              ),
            },
          ]}
        />
      </Space>
    </div>
  );
};


// ---------------------------------------------------------------- Phase 12.6
interface AdaptiveRouterPanelProps {
  store: DirectorEvolutionState;
}

const AdaptiveRouterPanel: React.FC<AdaptiveRouterPanelProps> = ({ store }) => {
  const ab = store.abValidation;
  const recs: AdaptiveRecommendation[] = store.adaptive?.recommendations ?? [];
  const isolation = store.adaptive?.scope_isolation;
  const pvsWeights = store.adaptive?.production_value_weights ?? {};

  const recommendationColumns = [
    {
      title: "Scope 单元格",
      dataIndex: "cell",
      key: "cell",
      render: (cell: string, row: AdaptiveRecommendation) => (
        <Space size={4}>
          <Tag color="geekblue">{row.genre}</Tag>
          <Tag>{row.scene_type}</Tag>
        </Space>
      ),
    },
    {
      title: "角色",
      dataIndex: "role",
      key: "role",
      render: (role: string) => (
        <Tag color={role === "primary" ? "gold" : "purple"}>{role === "primary" ? "Primary" : "Fallback"}</Tag>
      ),
    },
    {
      title: "导演",
      dataIndex: "director",
      key: "director",
      render: (director: string) => (
        <Tag color={ROUTE_TAG_COLORS[director.replace("-v2", "").replace("llm-", "")] ?? "default"}>{director}</Tag>
      ),
    },
    { title: "Production Value", dataIndex: "pvs", key: "pvs" },
    { title: "PVS Δ", dataIndex: "delta_to_next", key: "delta", render: (v: number) => (v === 0 ? "-" : `+${v}`) },
    { title: "样本", dataIndex: "samples", key: "samples" },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (status: string) => (
        <Tag color={status === "approved" ? "green" : status === "rejected" ? "red" : "orange"}>{status}</Tag>
      ),
    },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, row: AdaptiveRecommendation) => (
        <Space>
          <Button
            size="small"
            type="primary"
            icon={<CheckCircleOutlined />}
            disabled={row.status !== "pending"}
            onClick={() => store.approveAdaptive(row.id)}
          >
            Approve
          </Button>
          <Button
            size="small"
            danger
            icon={<CloseCircleOutlined />}
            disabled={row.status !== "pending"}
            onClick={() => store.rejectAdaptive(row.id)}
          >
            Reject
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card
        size="small"
        title={
          <Space>
            <ThunderboltOutlined /> Production Value Score 权重
          </Space>
        }
      >
        <Space size={16}>
          {Object.entries(pvsWeights).map(([key, value]) => (
            <Statistic key={key} title={key} value={value} precision={2} />
          ))}
        </Space>
        <Alert
          style={{ marginTop: 12 }}
          type="info"
          showIcon
          message="选择规则：primary = 创意胜者（per-scope winner），fallback = Production Value Score 最高的非胜者导演。"
        />
      </Card>

      {ab && (
        <Card size="small" title="A/B 验证（≥100 镜：Before 静态 Router vs After Adaptive Router）">
          <Row gutter={16}>
            <Col span={6}>
              <Statistic title="验证镜数" value={ab.shots} />
            </Col>
            <Col span={6}>
              <Statistic
                title="质量提升"
                value={ab.quality_gain_pct}
                precision={1}
                suffix="%"
                valueStyle={{ color: ab.quality_gain_pct >= 0 ? "#3f8600" : "#cf1322" }}
              />
            </Col>
            <Col span={6}>
              <Statistic
                title="成本Δ（正=上升）"
                value={ab.cost_delta_pct}
                precision={1}
                suffix="%"
                valueStyle={{ color: ab.cost_reduction_pct >= 0 ? "#3f8600" : "#cf1322" }}
              />
            </Col>
            <Col span={6}>
              <Statistic
                title="验收"
                value={ab.passed ? "PASS" : "FAIL"}
                valueStyle={{ color: ab.passed ? "#3f8600" : "#cf1322" }}
              />
            </Col>
          </Row>
          <Descriptions size="small" style={{ marginTop: 12 }} column={3}>
            <Descriptions.Item label="Before 平均质量">{ab.before.avg_quality}</Descriptions.Item>
            <Descriptions.Item label="After 平均质量">{ab.after.avg_quality}</Descriptions.Item>
            <Descriptions.Item label="After 平均成本">{ab.after.avg_cost}</Descriptions.Item>
          </Descriptions>
          <Text type="secondary">
            验收门槛：质量提升 ≥ {ab.gate.quality_gain_min}% 或成本下降 ≥ {ab.gate.cost_reduction_min}%
          </Text>
        </Card>
      )}

      <Card
        size="small"
        title={
          <Space>
            <ExperimentOutlined /> Router 推荐
            <Text type="secondary">
              {store.adaptive?.count ?? 0} 条建议（≥30 门）；Scope 隔离：
              {isolation ? (isolation.violations === 0 ? " ✅ 0 污染" : ` ❌ ${isolation.violations}`) : "-"}
            </Text>
          </Space>
        }
        extra={
          <Button size="small" danger icon={<RollbackOutlined />} onClick={() => store.rollbackAdaptive()}>
            回滚 Adaptive 策略
          </Button>
        }
      >
        <Table<AdaptiveRecommendation>
          rowKey={(row) => row.id}
          columns={recommendationColumns}
          dataSource={recs}
          pagination={{ pageSize: 10 }}
          size="small"
        />
      </Card>
    </Space>
  );
};

// ---------------------------------------------------------------- Phase 12.9
interface ProductionOSPanelProps {
  store: DirectorEvolutionState;
}

const AUDIT_TAG_COLORS: Record<string, string> = {
  release_create: "blue",
  release_approve: "green",
  release_rollback: "orange",
  release_certify: "purple",
  production_freeze: "gold",
};

const ProductionOSPanel: React.FC<ProductionOSPanelProps> = ({ store }) => {
  const components = store.registry?.components ?? {};
  const componentRows = Object.entries(components).map(([name, entry]) => ({
    key: name,
    name: entry.name,
    version: entry.version,
    updated_at: entry.updated_at,
  }));
  const auditEntries = [...store.auditEntries].reverse();
  const release = store.lastRelease;
  const certify = store.certify;
  const freeze = store.freeze;

  const componentColumns = [
    { title: "组件", dataIndex: "name", key: "name" },
    {
      title: "版本",
      dataIndex: "version",
      key: "version",
      render: (version: string) => <Tag color="geekblue">{version}</Tag>,
    },
    { title: "更新时间", dataIndex: "updated_at", key: "updated_at" },
  ];

  const auditColumns = [
    {
      title: "动作",
      dataIndex: "action",
      key: "action",
      render: (action: string) => <Tag color={AUDIT_TAG_COLORS[action] ?? "default"}>{action}</Tag>,
    },
    {
      title: "详情",
      dataIndex: "detail",
      key: "detail",
      render: (detail: Record<string, unknown>) => {
        const releaseId = detail?.release_id;
        return releaseId ? (
          <Text code>{String(releaseId)}</Text>
        ) : (
          <Text type="secondary">{Object.keys(detail ?? {}).join(", ") || "-"}</Text>
        );
      },
    },
    { title: "时间", dataIndex: "created_at", key: "time" },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Row gutter={16}>
        <Col span={8}>
          <Card size="small" title={<Space><DatabaseOutlined /> Pipeline Health</Space>}>
            <Statistic title="注册组件" value={componentRows.length} />
            <Statistic title="已发布版本" value={store.registry?.releases ?? 0} />
            <Text type="secondary">统一版本签名：pipeline / director / policy / model / workflow</Text>
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small" title={<Space><LockOutlined /> Director Intelligence</Space>}>
            <Statistic title="最近 Release" value={release?.release_id ?? "-"} valueStyle={{ fontSize: 14 }} />
            <Statistic
              title="Certify 门禁"
              value={certify ? (certify.passed ? "PASS" : "FAIL") : "-"}
              valueStyle={{ color: certify?.passed ? "#3f8600" : "#cf1322" }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small" title={<Space><HistoryOutlined /> Production History</Space>}>
            <Statistic title="审计事件" value={store.auditEntries.length} />
            <Statistic
              title="Freeze 包"
              value={freeze?.root ?? "-"}
              valueStyle={{ fontSize: 14 }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={12}>
          <Card size="small" title="Registry 组件版本">
            <Table
              rowKey={(row) => row.key}
              columns={componentColumns}
              dataSource={componentRows}
              pagination={false}
              size="small"
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card
            size="small"
            title="Release 管理（human approval）"
            extra={
              <Button
                type="primary"
                size="small"
                icon={<CloudDownloadOutlined />}
                loading={store.loading}
                onClick={() => store.createRelease()}
              >
                创建 Release 签名
              </Button>
            }
          >
            <Space direction="vertical" style={{ width: "100%" }}>
              {release ? (
                <>
                  <Space>
                    <Text>Release：</Text>
                    <Tag color="blue">{release.release_id}</Tag>
                    {release.approved ? <Tag color="green">已批准</Tag> : <Tag color="orange">待人工批准</Tag>}
                    {release.rolled_back ? <Tag color="red">已回滚</Tag> : null}
                  </Space>
                  <pre
                    style={{
                      margin: 0,
                      padding: 8,
                      maxHeight: 140,
                      overflow: "auto",
                      background: "#fafafa",
                      fontSize: 12,
                    }}
                  >
                    {JSON.stringify(release.manifest ?? {}, null, 2)}
                  </pre>
                  <Space>
                    <Button
                      size="small"
                      type="primary"
                      icon={<CheckCircleOutlined />}
                      disabled={release.approved || release.rolled_back}
                      onClick={() => store.approveRelease(release.release_id)}
                    >
                      Approve（人工）
                    </Button>
                    <Button
                      size="small"
                      danger
                      icon={<RollbackOutlined />}
                      onClick={() => store.rollbackRelease(release.release_id)}
                    >
                      Rollback
                    </Button>
                  </Space>
                </>
              ) : (
                <Text type="secondary">尚未创建 Release；创建后将生成确定性签名 manifest 并写入审计链。</Text>
              )}
            </Space>
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={12}>
          <Card
            size="small"
            title={<Space><SafetyCertificateOutlined /> Certify 门禁（12.9-C）</Space>}
            extra={
              <Button
                size="small"
                icon={<CheckCircleOutlined />}
                loading={store.loading}
                onClick={() => store.certifyRelease()}
              >
                运行认证
              </Button>
            }
          >
            <Space direction="vertical" style={{ width: "100%" }}>
              {certify ? (
                <Alert
                  type={certify.passed ? "success" : "error"}
                  showIcon
                  message={`认证结果：${certify.passed ? "PASS" : "FAIL"}`}
                  description={
                    <Space direction="vertical" size={4}>
                      {Object.entries(certify.checks ?? {}).map(([check, ok]) => (
                        <Text key={check}>
                          {ok ? "✅" : "❌"} {check}
                        </Text>
                      ))}
                    </Space>
                  }
                />
              ) : (
                <Text type="secondary">门禁：100 镜连续生产 / Council explain 100% / Governance rollback + audit + hash。</Text>
              )}
            </Space>
          </Card>
        </Col>
        <Col span={12}>
          <Card
            size="small"
            title={<Space><InboxOutlined /> Production Freeze（12.9-D）</Space>}
            extra={
              <Button
                size="small"
                icon={<InboxOutlined />}
                loading={store.loading}
                onClick={() => store.freezeRelease()}
              >
                打包冻结
              </Button>
            }
          >
            {freeze ? (
              <Alert
                type="success"
                showIcon
                message="生产冻结包已生成"
                description={
                  <Space direction="vertical" size={4}>
                    <Text code>{freeze.root}</Text>
                    <Text type="secondary">
                      manifest.json + director_decisions / council_votes / policy_history /
                      asset_registry / model_registry（全部 sha256 内容哈希）
                    </Text>
                  </Space>
                }
              />
            ) : (
              <Text type="secondary">将《归墟觉醒·天倾》冻结为可复现发布包，产出 production_release/ 目录。</Text>
            )}
          </Card>
        </Col>
      </Row>

      <Card size="small" title={<Space><AuditOutlined /> Audit 审计时间线</Space>}>
        {auditEntries.length === 0 ? (
          <Text type="secondary">暂无审计记录（append-only 链为空）。</Text>
        ) : (
          <>
            <Table<AuditEntry>
              rowKey={(row) => row.id}
              columns={auditColumns}
              dataSource={auditEntries.slice(0, 20)}
              pagination={{ pageSize: 8 }}
              size="small"
            />
            <Text type="secondary" style={{ marginTop: 8, display: "block" }}>
              append-only：条目只追加、不删除、不修改，保证端到端可审计。
            </Text>
          </>
        )}
      </Card>
    </Space>
  );
};

export default DirectorEvolutionCenter;


/**
 * Knowledge Graph center (GPT Priority 2).
 *
 * 多源图谱（Team / Production Intelligence / Feedback / Prompt OS / Shot DNA）：
 * 统计 / 节点检索 / 邻居 / 路径 / 智能推荐。仅分析与推荐，不自动修改任何资产。
 */

import React, { useEffect, useState } from "react";
import {
  Alert, Button, Card, Col, Descriptions, Input, Row, Select, Space, Statistic, Table, Tag, Typography,
} from "antd";
import { ApartmentOutlined, ReloadOutlined, SearchOutlined } from "@ant-design/icons";

import {
  kgGetNode, kgIngest, kgNeighbors, kgNodes, kgPaths, kgRecommend, kgSearch, kgStats,
  type KGNeighbors, type KGNode, type KGPaths, type KGRecommend, type KGStats,
} from "@/api/knowledgeGraph";
import { userMessage } from "@/api/client";

const { Title, Text } = Typography;

const TYPE_COLORS: Record<string, string> = {
  project: "blue", episode: "green", assignment: "purple", artifact: "orange",
  review: "cyan", production_event: "magenta", feedback: "red", shot_dna: "geekblue",
  shot_design: "gold", candidate: "lime", character: "volcano", world: "geekblue",
};

const TYPE_LABELS: Record<string, string> = {
  project: "项目", season: "季", episode: "集", character: "角色", world: "世界观",
  scene: "场景", prompt_version: "Prompt 版本", shot_dna: "Shot DNA", shot: "镜头",
  shot_design: "ShotDesign", artifact: "Artifact", review: "评审", feedback: "反馈",
  production_event: "生产事件", assignment: "协作任务", candidate: "候选",
};

const KnowledgeGraph: React.FC = () => {
  const [stats, setStats] = useState<KGStats | null>(null);
  const [nodes, setNodes] = useState<KGNode[]>([]);
  const [nodeType, setNodeType] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<KGNode | null>(null);
  const [neighbors, setNeighbors] = useState<KGNeighbors | null>(null);
  const [recommend, setRecommend] = useState<KGRecommend | null>(null);
  const [paths, setPaths] = useState<KGPaths | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadStats = async () => {
    kgStats().then(setStats).catch((e: Error) => setError(userMessage(e)));
  };

  const loadNodes = async (type?: string, q?: string) => {
    const params: Record<string, string> = { limit: "50" };
    if (type) params.node_type = type;
    if (q) params.q = q;
    kgNodes(params).then((r) => setNodes(r.nodes)).catch((e: Error) => setError(userMessage(e)));
  };

  useEffect(() => {
    loadStats();
    loadNodes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onIngest = async () => {
    setBusy(true);
    setError("");
    try {
      await kgIngest({ actor: "human", reason: "重建知识图谱" });
      await Promise.all([loadStats(), loadNodes(nodeType, query)]);
    } catch (e) {
      setError(userMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const onSelect = async (nodeId: string) => {
    setError("");
    try {
      const [node, nbr, rec] = await Promise.all([kgGetNode(nodeId), kgNeighbors(nodeId), kgRecommend(nodeId)]);
      setSelected(node);
      setNeighbors(nbr);
      setRecommend(rec);
      const otherId = rec.recommendations[0]?.node?.id;
      setPaths(otherId ? await kgPaths(nodeId, otherId) : null);
    } catch (e) {
      setError(userMessage(e));
    }
  };

  const columns = [
    { title: "ID", dataIndex: "id", key: "id", width: 200, render: (v: string, row: KGNode) => <Button type="link" onClick={() => onSelect(row.id)}>{v}</Button> },
    { title: "类型", dataIndex: "type", key: "type", width: 110, render: (v: string) => <Tag color={TYPE_COLORS[v] ?? "default"}>{TYPE_LABELS[v] ?? v}</Tag> },
    { title: "标签", dataIndex: "label", key: "label" },
    { title: "项目", dataIndex: "project_id", key: "project", width: 100, render: (v: string) => v || "-" },
  ];

  return (
    <div className="page-container">
      <div className="page-header">
        <Title level={3} style={{ marginBottom: 4 }}>
          <ApartmentOutlined /> Knowledge Graph <Text type="secondary">生产知识图谱</Text>
        </Title>
        <Text type="secondary">
          统一 Episode / Character / World / Prompt / Shot DNA / Artifact / Review / Feedback / Production Event / Assignment
        </Text>
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="图谱只读摄取，智能推荐不改资产"
        description="KG 从 Team / Production Intelligence / Feedback / Prompt OS / Shot DNA 只读摄取；邻居 / 路径 / 推荐仅用于分析与检索（auto_apply=false）。"
      />

      {stats && (
        <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
          <Col span={4}><Card size="small"><Statistic title="节点" value={stats.nodes} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="边" value={stats.edges} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="协作任务" value={stats.by_type.assignment ?? 0} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="生产事件" value={stats.by_type.production_event ?? 0} /></Card></Col>
          <Col span={4}><Card size="small"><Statistic title="评审" value={stats.by_type.review ?? 0} /></Card></Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="数据源" value={Object.keys(stats.by_type).length} />
              <Text type="secondary">5 类源模块</Text>
            </Card>
          </Col>
        </Row>
      )}

      <Card size="small" style={{ marginBottom: 12 }}>
        <Space wrap>
          <Select
            style={{ width: 160 }}
            placeholder="节点类型"
            allowClear
            value={nodeType || undefined}
            onChange={(v) => { setNodeType(v ?? ""); loadNodes(v ?? "", query); }}
            options={Object.entries(TYPE_LABELS).map(([value, label]) => ({ value, label: `${label} (${value})` }))}
          />
          <Input
            style={{ width: 260 }}
            placeholder="搜索节点（ID / 标签）"
            prefix={<SearchOutlined />}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onPressEnter={() => loadNodes(nodeType, query)}
            allowClear
          />
          <Button icon={<SearchOutlined />} onClick={() => loadNodes(nodeType, query)}>搜索</Button>
          <Button icon={<ReloadOutlined />} loading={busy} onClick={onIngest}>重新摄取</Button>
        </Space>
      </Card>

      <Row gutter={[12, 12]}>
        <Col span={10}>
          <Card size="small" title="节点列表">
            <Table rowKey="id" size="small" pagination={{ pageSize: 10 }} dataSource={nodes} columns={columns} />
          </Card>
        </Col>
        <Col span={14}>
          <Card size="small" title="节点详情 · 邻居 · 推荐">
            {selected ? (
              <Space direction="vertical" style={{ width: "100%" }}>
                <Descriptions size="small" bordered column={2}>
                  <Descriptions.Item label="ID">{selected.id}</Descriptions.Item>
                  <Descriptions.Item label="类型">{TYPE_LABELS[selected.type] ?? selected.type}</Descriptions.Item>
                  <Descriptions.Item label="标签" span={2}>{selected.label}</Descriptions.Item>
                  <Descriptions.Item label="项目">{selected.project_id || "-"}</Descriptions.Item>
                </Descriptions>
                {neighbors && (
                  <Space wrap>
                    <Text strong>邻居 {neighbors.count}：</Text>
                    {neighbors.neighbors.slice(0, 8).map((n) => (
                      <Tag key={n.node.id} color={TYPE_COLORS[n.node.type] ?? "default"}>
                        {TYPE_LABELS[n.node.type] ?? n.node.type} · {n.node.id}（{n.edge.type}）
                      </Tag>
                    ))}
                  </Space>
                )}
                {recommend && recommend.recommendations.length > 0 && (
                  <Space wrap>
                    <Text strong>智能推荐：</Text>
                    {recommend.recommendations.map((r) => (
                      <Tag key={r.node.id} color="gold">{r.node.id}（{r.score.toFixed(2)}）</Tag>
                    ))}
                  </Space>
                )}
                {paths && paths.paths.length > 0 && (
                  <div>
                    <Text strong>推荐关联路径：</Text>
                    {paths.paths[0].map((p, i) => (
                      <span key={`${p.id}-${i}`}>
                        <Tag>{p.id}</Tag>
                        {i < paths.paths[0].length - 1 ? <Text type="secondary"> → </Text> : null}
                      </span>
                    ))}
                  </div>
                )}
                <Text type="secondary" style={{ fontSize: 12 }}>{recommend?.note}</Text>
              </Space>
            ) : (
              <Text type="secondary">点击节点 ID 查看邻居 / 路径 / 推荐</Text>
            )}
          </Card>
        </Col>
      </Row>
      {error ? <Alert style={{ marginTop: 12 }} type="error" showIcon message={error} /> : null}
    </div>
  );
};

export default KnowledgeGraph;

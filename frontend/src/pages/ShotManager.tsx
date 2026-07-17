import React, { useEffect, useState, useMemo } from "react";
import {
  Card,
  Table,
  Button,
  Tag,
  Space,
  Image,
  Modal,
  Typography,
  message,
  Descriptions,
  Select,
  Input,
  Row,
  Col,
  Slider,
  Popconfirm,
} from "antd";
import {
  ReloadOutlined,
  EyeOutlined,
  DownloadOutlined,
  DeleteOutlined,
  FilterOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import axios from "axios";

const { Title, Text, Paragraph } = Typography;
const API_BASE = "http://127.0.0.1:8800";

/* ── Types ─────────────────────────────────────── */

interface Shot {
  shot_id: string;
  project_id: string;
  chapter_index: number;
  shot_index: number;
  status: string;
  image_path: string;
  video_path: string;
  final_path: string;
  prompt_positive: string;
  camera_type: string;
  emotion: string;
  motion: string;
  dialogue: string;
  attempts: number;
  quality_score: number;
  created_at: string;
}

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  pending: { color: "default", label: "Pending" },
  generated: { color: "blue", label: "Generated" },
  composed: { color: "cyan", label: "Composed" },
  video: { color: "geekblue", label: "Video" },
  lipsynced: { color: "purple", label: "LipSync" },
  done: { color: "green", label: "Done" },
  failed: { color: "red", label: "Failed" },
  retrying: { color: "orange", label: "Retrying" },
};

/* ── Component ─────────────────────────────────── */

const ShotManager: React.FC = () => {
  const [shots, setShots] = useState<Shot[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedShot, setSelectedShot] = useState<Shot | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [qualityThreshold, setQualityThreshold] = useState(70);

  const fetchShots = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get<{ shots: Shot[] }>(
        `${API_BASE}/api/shots?project_id=demo&limit=200`
      );
      setShots(data.shots || []);
    } catch {
      // demo mode — no backend
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchShots();
  }, []);

  const filteredShots = useMemo(() => {
    return shots.filter((s) => {
      if (statusFilter !== "all" && s.status !== statusFilter) return false;
      if (s.quality_score * 100 < qualityThreshold) return false;
      return true;
    });
  }, [shots, statusFilter, qualityThreshold]);

  const handleRetry = async (shotId: string) => {
    try {
      await axios.post(`${API_BASE}/api/shots/${shotId}/retry`);
      message.success(`Retrying shot ${shotId}`);
      fetchShots();
    } catch {
      message.error("Retry failed");
    }
  };

  const handleDelete = async (shotId: string) => {
    try {
      await axios.delete(`${API_BASE}/api/shots/${shotId}`);
      message.success(`Deleted ${shotId}`);
      fetchShots();
    } catch {
      message.error("Delete failed");
    }
  };

  const columns: ColumnsType<Shot> = [
    {
      title: "Shot",
      dataIndex: "shot_id",
      key: "shot_id",
      width: 140,
      ellipsis: true,
    },
    {
      title: "Preview",
      key: "preview",
      width: 80,
      render: (_: unknown, rec: Shot) =>
        rec.image_path ? (
          <Image
            src={rec.image_path}
            width={48}
            height={27}
            style={{ objectFit: "cover", borderRadius: 4 }}
            preview={{ mask: <EyeOutlined /> }}
            fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
          />
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    { title: "Ch", dataIndex: "chapter_index", key: "ch", width: 50 },
    { title: "#", dataIndex: "shot_index", key: "idx", width: 50 },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => {
        const m = STATUS_MAP[s] ?? { color: "default", label: s };
        return <Tag color={m.color}>{m.label}</Tag>;
      },
    },
    { title: "Camera", dataIndex: "camera_type", key: "camera", width: 100 },
    { title: "Emotion", dataIndex: "emotion", key: "emotion", width: 90 },
    {
      title: "Quality",
      dataIndex: "quality_score",
      key: "quality",
      width: 90,
      render: (v: number) => (
        <Text style={{ color: v >= 0.8 ? "#52c41a" : v >= 0.6 ? "#faad14" : "#ff4d4f" }}>
          {(v * 100).toFixed(0)}%
        </Text>
      ),
    },
    {
      title: "Attempts",
      dataIndex: "attempts",
      key: "attempts",
      width: 70,
    },
    {
      title: "Actions",
      key: "actions",
      width: 160,
      render: (_: unknown, rec: Shot) => (
        <Space size="small">
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => {
              setSelectedShot(rec);
              setPreviewOpen(true);
            }}
          >
            View
          </Button>
          <Popconfirm
            title="Retry this shot?"
            onConfirm={() => handleRetry(rec.shot_id)}
          >
            <Button size="small" icon={<ReloadOutlined />} danger={rec.status === "failed"}>
              Retry
            </Button>
          </Popconfirm>
          <Popconfirm
            title="Delete this shot?"
            onConfirm={() => handleDelete(rec.shot_id)}
          >
            <Button size="small" icon={<DeleteOutlined />} danger />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <Title level={4} style={{ margin: 0 }}>
          Shot Manager
        </Title>
        <Button icon={<ReloadOutlined />} onClick={fetchShots}>
          Refresh
        </Button>
      </div>

      {/* ── Filters ────────────────────────────────── */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={8}>
          <Select
            style={{ width: "100%" }}
            value={statusFilter}
            onChange={setStatusFilter}
            prefix={<FilterOutlined />}
          >
            <Select.Option value="all">All Status</Select.Option>
            {Object.entries(STATUS_MAP).map(([k, v]) => (
              <Select.Option key={k} value={k}>
                {v.label}
              </Select.Option>
            ))}
          </Select>
        </Col>
        <Col xs={24} sm={16}>
          <Text>Min Quality Score: {qualityThreshold}%</Text>
          <Slider
            min={0}
            max={100}
            value={qualityThreshold}
            onChange={setQualityThreshold}
          />
        </Col>
      </Row>

      {/* ── Shot Table ─────────────────────────────── */}
      <Table
        dataSource={filteredShots}
        columns={columns}
        rowKey="shot_id"
        loading={loading}
        pagination={{ pageSize: 20, showSizeChanger: true }}
        size="middle"
        locale={{ emptyText: "No shots found. Start a generation to create shots." }}
      />

      {/* ── Detail Modal ───────────────────────────── */}
      <Modal
        title={`Shot: ${selectedShot?.shot_id ?? ""}`}
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        width={800}
        footer={[
          <Button key="close" onClick={() => setPreviewOpen(false)}>
            Close
          </Button>,
          <Button
            key="download"
            type="primary"
            icon={<DownloadOutlined />}
            onClick={() => {
              if (selectedShot) {
                window.open(
                  `${API_BASE}/api/shots/${selectedShot.shot_id}/download`,
                  "_blank"
                );
              }
            }}
          >
            Download
          </Button>,
        ]}
      >
        {selectedShot && (
          <div>
            {selectedShot.image_path && (
              <Image
                src={selectedShot.image_path}
                style={{ maxHeight: 300, marginBottom: 16, borderRadius: 8 }}
                fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
              />
            )}
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="Status">
                <Tag color={STATUS_MAP[selectedShot.status]?.color}>
                  {STATUS_MAP[selectedShot.status]?.label ?? selectedShot.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Quality">
                {(selectedShot.quality_score * 100).toFixed(0)}%
              </Descriptions.Item>
              <Descriptions.Item label="Camera">
                {selectedShot.camera_type || "—"}
              </Descriptions.Item>
              <Descriptions.Item label="Emotion">
                {selectedShot.emotion || "—"}
              </Descriptions.Item>
              <Descriptions.Item label="Motion">
                {selectedShot.motion || "—"}
              </Descriptions.Item>
              <Descriptions.Item label="Attempts">
                {selectedShot.attempts}
              </Descriptions.Item>
              <Descriptions.Item label="Dialogue" span={2}>
                {selectedShot.dialogue || "—"}
              </Descriptions.Item>
              <Descriptions.Item label="Positive Prompt" span={2}>
                <Paragraph
                  ellipsis={{ rows: 3, expandable: true, symbol: "more" }}
                  style={{ margin: 0 }}
                >
                  {selectedShot.prompt_positive || "—"}
                </Paragraph>
              </Descriptions.Item>
            </Descriptions>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default ShotManager;

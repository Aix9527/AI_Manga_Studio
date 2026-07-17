import React, { useEffect, useState } from "react";
import {
  Card,
  Table,
  Button,
  Tag,
  Typography,
  Space,
  message,
  Input,
  Select,
  Row,
  Col,
} from "antd";
import {
  DownloadOutlined,
  PlayCircleOutlined,
  FileTextOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import axios from "axios";

const { Title, Text } = Typography;
const API_BASE = "http://127.0.0.1:8800";

/* ── Types ─────────────────────────────────────── */

interface VideoOutput {
  id: string;
  project_id: string;
  chapter: number;
  title: string;
  format: string;
  duration_sec: number;
  size_mb: number;
  resolution: string;
  status: string;
  download_url: string;
  created_at: string;
}

/* ── Helpers ───────────────────────────────────── */

const formatDuration = (sec: number): string => {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
};

/* ── Component ─────────────────────────────────── */

const Download: React.FC = () => {
  const [videos, setVideos] = useState<VideoOutput[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [formatFilter, setFormatFilter] = useState<string>("all");

  const fetchVideos = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get<{ videos: VideoOutput[] }>(
        `${API_BASE}/api/shots?project_id=demo&status=done&limit=200`
      );
      // Map shots to video outputs (demo mapping)
      const outputs: VideoOutput[] = (data.videos || []).map((v: VideoOutput, i: number) => ({
        ...v,
        id: v.id || `video-${i}`,
        format: v.format || "mp4",
      }));
      setVideos(outputs);
    } catch {
      // demo mode — no backend
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchVideos();
  }, []);

  const filtered = videos.filter((v) => {
    if (formatFilter !== "all" && v.format !== formatFilter) return false;
    if (search && !v.title.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const handleDownload = async (video: VideoOutput) => {
    try {
      const response = await axios.get(video.download_url, {
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `${video.title}.${video.format}`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      message.success(`Downloading ${video.title}.${video.format}`);
    } catch {
      message.error("Download failed");
    }
  };

  const columns: ColumnsType<VideoOutput> = [
    { title: "Title", dataIndex: "title", key: "title", ellipsis: true },
    { title: "Chapter", dataIndex: "chapter", key: "chapter", width: 80 },
    {
      title: "Format",
      dataIndex: "format",
      key: "format",
      width: 80,
      render: (f: string) => <Tag color="blue">{f.toUpperCase()}</Tag>,
    },
    {
      title: "Duration",
      dataIndex: "duration_sec",
      key: "duration",
      width: 100,
      render: (v: number) => formatDuration(v),
    },
    {
      title: "Size",
      dataIndex: "size_mb",
      key: "size",
      width: 100,
      render: (v: number) => `${v.toFixed(1)} MB`,
    },
    { title: "Resolution", dataIndex: "resolution", key: "res", width: 100 },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => (
        <Tag color={s === "done" ? "green" : s === "processing" ? "processing" : "default"}>
          {s.toUpperCase()}
        </Tag>
      ),
    },
    { title: "Created", dataIndex: "created_at", key: "created", width: 160 },
    {
      title: "Download",
      key: "download",
      width: 120,
      render: (_: unknown, rec: VideoOutput) => (
        <Button
          type="primary"
          icon={<DownloadOutlined />}
          onClick={() => handleDownload(rec)}
          disabled={rec.status !== "done"}
        >
          Download
        </Button>
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
          Video Downloads
        </Title>
        <Button icon={<DownloadOutlined />} onClick={fetchVideos}>
          Refresh
        </Button>
      </div>

      {/* ── Filters ────────────────────────────────── */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={16}>
          <Input
            placeholder="Search by title..."
            prefix={<SearchOutlined />}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            allowClear
          />
        </Col>
        <Col xs={24} sm={8}>
          <Select
            style={{ width: "100%" }}
            value={formatFilter}
            onChange={setFormatFilter}
          >
            <Select.Option value="all">All Formats</Select.Option>
            <Select.Option value="mp4">MP4</Select.Option>
            <Select.Option value="webm">WebM</Select.Option>
            <Select.Option value="mov">MOV</Select.Option>
          </Select>
        </Col>
      </Row>

      {/* ── Summary Cards ──────────────────────────── */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Text type="secondary">Total Files</Text>
            <Title level={4} style={{ margin: 0 }}>
              {filtered.length}
            </Title>
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Text type="secondary">Total Size</Text>
            <Title level={4} style={{ margin: 0 }}>
              {filtered.reduce((sum, v) => sum + v.size_mb, 0).toFixed(1)} MB
            </Title>
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Text type="secondary">Ready</Text>
            <Title level={4} style={{ margin: 0 }}>
              {filtered.filter((v) => v.status === "done").length}
            </Title>
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Text type="secondary">Processing</Text>
            <Title level={4} style={{ margin: 0 }}>
              {filtered.filter((v) => v.status === "processing").length}
            </Title>
          </Card>
        </Col>
      </Row>

      {/* ── Video Table ─────────────────────────────── */}
      <Table
        dataSource={filtered}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 10 }}
        locale={{ emptyText: "No videos generated yet. Complete a generation first." }}
      />
    </div>
  );
};

export default Download;

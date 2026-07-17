import React, { useEffect, useState, useCallback } from "react";
import {
  Card,
  Row,
  Col,
  Statistic,
  Progress,
  Typography,
  Tag,
  Spin,
  Table,
  Divider,
} from "antd";
import {
  ThunderboltOutlined,
  CloudServerOutlined,
  HddOutlined,
  DashboardOutlined,
} from "@ant-design/icons";
import axios from "axios";

const { Title, Text } = Typography;
const API_BASE = "http://127.0.0.1:8800";
const REFRESH_MS = 5000;

/* ── Types ─────────────────────────────────────── */

interface GPUInfo {
  name: string;
  vram_total_mb: number;
  vram_used_mb: number;
  vram_free_mb: number;
  temperature_c: number;
  power_w: number;
  utilization_pct: number;
}

interface CPUInfo {
  model: string;
  cores_physical: number;
  cores_logical: number;
  frequency_mhz: number;
  usage_pct: number;
}

interface RAMInfo {
  total_gb: number;
  used_gb: number;
  free_gb: number;
  usage_pct: number;
}

interface DiskInfo {
  mount: string;
  total_gb: number;
  used_gb: number;
  free_gb: number;
  usage_pct: number;
}

interface Overview {
  gpu: GPUInfo | null;
  cpu: CPUInfo;
  ram: RAMInfo;
  disk: DiskInfo;
  comfyui_queue: number;
  task_queue: number;
  is_ready: boolean;
}

/* ── Helper ────────────────────────────────────── */

const pctColor = (pct: number): string => {
  if (pct > 90) return "#ff4d4f";
  if (pct > 70) return "#faad14";
  return "#52c41a";
};

/* ── Component ─────────────────────────────────── */

const Monitor: React.FC = () => {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchOverview = useCallback(async () => {
    try {
      const { data } = await axios.get<Overview>(`${API_BASE}/api/monitor/overview`);
      setOverview(data);
    } catch {
      // silent fail on refresh
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchOverview();
    const timer = setInterval(fetchOverview, REFRESH_MS);
    return () => clearInterval(timer);
  }, [fetchOverview]);

  if (loading || !overview) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" tip="Connecting..." />
      </div>
    );
  }

  const { gpu, cpu, ram, disk } = overview;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>System Monitor</Title>
        <Tag color={overview.is_ready ? "green" : "red"}>
          {overview.is_ready ? "READY" : "NOT READY"}
        </Tag>
      </div>

      {/* ── GPU ────────────────────────────────── */}
      <Card title={<><ThunderboltOutlined /> GPU</>} style={{ marginBottom: 16 }}>
        {gpu ? (
          <Row gutter={[24, 16]}>
            <Col xs={24} sm={12} md={6}>
              <Statistic title="Model" value={gpu.name} />
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Statistic title="Temperature" value={gpu.temperature_c} suffix="°C" />
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Statistic title="Power" value={gpu.power_w} suffix="W" />
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Statistic title="Utilization" value={gpu.utilization_pct} suffix="%" />
            </Col>
            <Col span={24}>
              <div style={{ marginTop: 8 }}>
                <Text>
                  VRAM: {gpu.vram_used_mb} / {gpu.vram_total_mb} MB
                </Text>
                <Progress
                  percent={Math.round((gpu.vram_used_mb / gpu.vram_total_mb) * 100)}
                  strokeColor={pctColor((gpu.vram_used_mb / gpu.vram_total_mb) * 100)}
                  size="small"
                />
              </div>
            </Col>
          </Row>
        ) : (
          <Text type="secondary">No NVIDIA GPU detected</Text>
        )}
      </Card>

      {/* ── CPU + RAM + Disk ──────────────────── */}
      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}>
          <Card title={<><CloudServerOutlined /> CPU</>}>
            <Statistic title="Model" value={cpu.model} valueStyle={{ fontSize: 14 }} />
            <Statistic title="Utilization" value={cpu.usage_pct} suffix="%" precision={1} />
            <Text type="secondary">
              {cpu.cores_physical}C/{cpu.cores_logical}T @ {cpu.frequency_mhz} MHz
            </Text>
            <Progress
              percent={Math.round(cpu.usage_pct)}
              strokeColor={pctColor(cpu.usage_pct)}
              size="small"
              style={{ marginTop: 8 }}
            />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card title={<><DashboardOutlined /> RAM</>}>
            <Statistic title="Usage" value={ram.usage_pct} suffix="%" precision={1} />
            <Text type="secondary">
              {ram.used_gb.toFixed(1)} / {ram.total_gb.toFixed(1)} GB
            </Text>
            <Progress
              percent={Math.round(ram.usage_pct)}
              strokeColor={pctColor(ram.usage_pct)}
              size="small"
              style={{ marginTop: 8 }}
            />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card title={<><HddOutlined /> Disk</>}>
            <Statistic title={disk.mount} value={disk.usage_pct} suffix="%" precision={1} />
            <Text type="secondary">
              {disk.used_gb.toFixed(1)} / {disk.total_gb.toFixed(1)} GB
            </Text>
            <Progress
              percent={Math.round(disk.usage_pct)}
              strokeColor={pctColor(disk.usage_pct)}
              size="small"
              style={{ marginTop: 8 }}
            />
          </Card>
        </Col>
      </Row>

      {/* ── Queue Status ──────────────────────── */}
      <Divider />
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12}>
          <Card>
            <Statistic
              title="ComfyUI Queue"
              value={overview.comfyui_queue}
              suffix="jobs"
              prefix={<ThunderboltOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12}>
          <Card>
            <Statistic
              title="Task Queue"
              value={overview.task_queue}
              suffix="tasks"
              prefix={<CloudServerOutlined />}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default Monitor;

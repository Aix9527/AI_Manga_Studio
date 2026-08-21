import React from "react";
import {
  ApiOutlined,
  AudioOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";

import type { WorkspaceSnapshot } from "@/workbench/types";

interface Props {
  snapshot: WorkspaceSnapshot | null;
  healthText?: string;
}

const LocalStatusStrip: React.FC<Props> = ({ snapshot, healthText }) => {
  const system = snapshot?.system_health ?? {};
  const databaseOk = system.database === "ok" || system.database === true;
  return (
    <section className="local-status-strip" aria-label="本地环境与模型状态">
      <div><ApiOutlined /><span><strong>ComfyUI</strong><small>{String(system.comfyui || "本地引擎")}</small></span><i /></div>
      <div><ThunderboltOutlined /><span><strong>Wan 2.2 TI2V</strong><small>视频模型</small></span><i /></div>
      <div><DatabaseOutlined /><span><strong>FLUX</strong><small>关键帧模型</small></span><i /></div>
      <div><AudioOutlined /><span><strong>CosyVoice</strong><small>配音与音色</small></span><i /></div>
      <div><DesktopOutlined /><span><strong>GPU 本地执行</strong><small>{healthText || "资源按任务调度"}</small></span><i /></div>
      <div><SafetyCertificateOutlined /><span><strong>本地模式</strong><small>{databaseOk ? "数据库正常 · 数据不出机" : "数据不出机"}</small></span><i /></div>
    </section>
  );
};

export default LocalStatusStrip;

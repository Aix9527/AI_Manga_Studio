import type { Edge, Node } from "@xyflow/react";

export interface ProductionNodeData extends Record<string, unknown> {
  label: string;
  subtitle: string;
  group: "input" | "analysis" | "asset" | "storyboard" | "image" | "video" | "audio" | "export";
  stageKey: string;
  shotScoped: boolean;
}

const positions = [
  [40, 80], [260, 80], [480, 80], [700, 80],
  [700, 280], [480, 280], [260, 280], [40, 280],
] as const;

const definitions: Array<[
  string,
  string,
  string,
  ProductionNodeData["group"],
  string,
  boolean,
]> = [
  ["novel", "小说文本", "chapter_01.txt", "input", "load_input", false],
  ["scene", "场景拆解", "自动拆分场景与情节点", "analysis", "planning", false],
  ["character", "角色Bible", "角色设定与一致性引用", "asset", "character_design", false],
  ["storyboard", "分镜脚本", "镜头、景别、运镜与时长", "storyboard", "planning", false],
  ["keyframe", "关键帧", "FLUX / 参考帧生成", "image", "visual_generate", true],
  ["video", "TI2V视频生成", "Wan 2.2 / MiniMax H3", "video", "video_generate", true],
  ["audio", "配音/字幕", "CosyVoice / TTS / 字幕", "audio", "audio_tts", false],
  ["export", "合成导出", "FFmpeg / QC / 成片", "export", "composition_compose", false],
];

export const DEFAULT_PRODUCTION_NODES: Node<ProductionNodeData>[] = definitions.map((item, index) => ({
  id: item[0],
  position: { x: positions[index][0], y: positions[index][1] },
  data: {
    label: item[1],
    subtitle: item[2],
    group: item[3],
    stageKey: item[4],
    shotScoped: item[5],
  },
  type: "default",
}));

export const DEFAULT_PRODUCTION_EDGES: Edge[] = [
  ["novel", "scene"], ["scene", "character"], ["character", "storyboard"], ["storyboard", "keyframe"],
  ["keyframe", "video"], ["video", "audio"], ["audio", "export"],
].map(([source, target]) => ({ id: `${source}-${target}`, source, target, animated: target === "video" }));

import { describe, expect, it } from "vitest";

import { DEFAULT_PRODUCTION_EDGES, DEFAULT_PRODUCTION_NODES } from "@/studio/canvas/defaultFlow";

describe("default advanced production flow", () => {
  it("contains the complete local production chain", () => {
    expect(DEFAULT_PRODUCTION_NODES.map((node) => node.data.label)).toEqual([
      "小说文本",
      "场景拆解",
      "角色Bible",
      "分镜脚本",
      "关键帧",
      "TI2V视频生成",
      "配音/字幕",
      "合成导出",
    ]);
    expect(DEFAULT_PRODUCTION_EDGES).toHaveLength(7);
  });
});

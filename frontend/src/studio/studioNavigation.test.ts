import { describe, expect, it } from "vitest";

import { LEGACY_ROUTE_REDIRECTS, STUDIO_NAVIGATION } from "@/studio/studioNavigation";

describe("unified studio navigation", () => {
  it("exposes only the five production workspaces", () => {
    expect(STUDIO_NAVIGATION.map((item) => item.path)).toEqual([
      "/project",
      "/story-assets",
      "/director",
      "/canvas",
      "/timeline",
    ]);
    expect(STUDIO_NAVIGATION.map((item) => item.label)).toEqual([
      "项目",
      "故事·资产",
      "分镜导演台",
      "高级画布",
      "时间线·质检",
    ]);
  });

  it("redirects fragmented legacy tools into the unified workspaces", () => {
    expect(LEGACY_ROUTE_REDIRECTS["/overview"]).toBe("/project");
    expect(LEGACY_ROUTE_REDIRECTS["/characters"]).toBe("/story-assets");
    expect(LEGACY_ROUTE_REDIRECTS["/evolution"]).toBe("/director");
    expect(LEGACY_ROUTE_REDIRECTS["/workflow"]).toBe("/canvas");
    expect(LEGACY_ROUTE_REDIRECTS["/quality"]).toBe("/timeline");
    expect(LEGACY_ROUTE_REDIRECTS["/export"]).toBe("/timeline");
  });
});

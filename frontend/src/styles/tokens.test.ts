import { describe, expect, it } from "vitest";
import tokens from "./tokens.css?raw";

describe("工作台主题", () => {
  it("使用合法 CSS 注释并声明核心变量", () => {
    expect(tokens.startsWith("/*")).toBe(true);
    expect(tokens).not.toContain("// Dark theme");
    for (const name of ["--color-bg-primary", "--color-surface", "--color-text", "--color-accent"]) {
      expect(tokens).toContain(name);
    }
  });
});

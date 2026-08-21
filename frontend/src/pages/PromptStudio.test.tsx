import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import PromptStudio from "@/pages/PromptStudio";
import * as promptIntelligence from "@/api/promptIntelligence";

vi.mock("@/api/promptIntelligence", () => ({
  promptStats: vi.fn(),
  listPromptTemplates: vi.fn(),
  createPromptTemplate: vi.fn(),
  createPromptVersion: vi.fn(),
  setPromptVersionStatus: vi.fn(),
  diffPromptVersions: vi.fn(),
  addPromptReview: vi.fn(),
  listPromptReviews: vi.fn(),
  listABTests: vi.fn(),
  createABTest: vi.fn(),
  recordABResult: vi.fn(),
  decideAB: vi.fn(),
  composeCharacter: vi.fn(),
  composeWorld: vi.fn(),
  composeShot: vi.fn(),
}));

const mocked = vi.mocked(promptIntelligence);

function template(overrides: Record<string, unknown> = {}) {
  return {
    id: "PT-1",
    name: "character_portrait",
    kind: "character",
    description: "",
    active_version: "v1",
    created_at: "",
    updated_at: "",
    versions: [
      { template_id: "PT-1", version_id: "v1", parent_version: "", base_template: "portrait of {character_name}", negative_prompt: "low quality", quality_tags: "masterpiece", variables: ["character_name"], notes: "", status: "locked", approved_by: "导演", approved_at: "", content_hash: "abc", created_at: "" },
      { template_id: "PT-1", version_id: "v2", parent_version: "v1", base_template: "portrait of {character_name}, {appearance}", negative_prompt: "low quality", quality_tags: "masterpiece", variables: ["character_name", "appearance"], notes: "", status: "draft", approved_by: "", approved_at: "", content_hash: "def", created_at: "" },
    ],
    ...overrides,
  };
}

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
});

afterAll(() => {
  // @ts-expect-error restore original if defined
  if (window.__originalMatchMedia) Object.defineProperty(window, "matchMedia", { value: window.__originalMatchMedia });
});

describe("PromptStudio", () => {
  beforeEach(() => {
    mocked.promptStats.mockResolvedValue({ templates: 1, versions: 2, by_kind: { character: 1, world: 0, shot: 0, generic: 0 }, approved_versions: 1, locked_versions: 1, reviews: 1, ab_tests: 0 } as never);
    mocked.listPromptTemplates.mockResolvedValue({ templates: [template()] } as never);
    mocked.listABTests.mockResolvedValue({ tests: [] } as never);
    mocked.listPromptReviews.mockResolvedValue({ reviews: [{ id: "RV-1", template_id: "PT-1", version_id: "v1", reviewer: "制片人", status: "approved", comments: "OK", created_at: "", resolved_at: "" }] } as never);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders stats and template versions", async () => {
    render(<PromptStudio />);
    await waitFor(() => expect(screen.getByText("Prompt Studio")).toBeInTheDocument());
    expect(screen.getByText("character_portrait")).toBeInTheDocument();
    expect(screen.getByText("模板库与版本")).toBeInTheDocument();
  });

  it("creates a template via API", async () => {
    mocked.createPromptTemplate.mockResolvedValue(template() as never);
    render(<PromptStudio />);
    await waitFor(() => expect(screen.getByPlaceholderText("模板名，如 character_portrait")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText("模板名，如 character_portrait"), { target: { value: "shot_cinematic" } });
    fireEvent.change(screen.getByPlaceholderText("模板正文，支持 {变量}"), { target: { value: "{prompt_template} with {camera}" } });
    screen.getByRole("button", { name: /创\s*建/ }).click();
    await waitFor(() => expect(mocked.createPromptTemplate).toHaveBeenCalledWith(expect.objectContaining({ name: "shot_cinematic", kind: "character" })));
  });

  it("approves and locks a version", async () => {
    mocked.setPromptVersionStatus.mockResolvedValue(template({ active_version: "v2" }) as never);
    render(<PromptStudio />);
    await waitFor(() => expect(screen.getByText("character_portrait")).toBeInTheDocument());
    const expandIcon = document.querySelector(".ant-table-row-expand-icon");
    if (expandIcon) fireEvent.click(expandIcon);
    await waitFor(() => expect(screen.getByText("v2")).toBeInTheDocument());
    const approveButtons = screen.getAllByRole("button", { name: /审\s*批/ });
    fireEvent.click(approveButtons[approveButtons.length - 1]);
    await waitFor(() => expect(mocked.setPromptVersionStatus).toHaveBeenCalledWith("PT-1", "v2", expect.objectContaining({ status: "approved" })));
  });

  it("runs composer trial and shows compiled prompt", async () => {
    mocked.composeCharacter.mockResolvedValue({
      kind: "character", template: "character_portrait", version_id: "v1",
      positive_prompt: "portrait of 陈夜", negative_prompt: "low quality", source_id: "CH-001",
    } as never);
    render(<PromptStudio />);
    await waitFor(() => expect(screen.getByRole("tab", { name: /提示词试炼/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("tab", { name: /提示词试炼/ }));
    await waitFor(() => expect(screen.getByPlaceholderText("角色ID（Bible）")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText("角色ID（Bible）"), { target: { value: "CH-001" } });
    fireEvent.click(screen.getByRole("button", { name: /生成提示词/ }));
    await waitFor(() => expect(mocked.composeCharacter).toHaveBeenCalledWith(expect.objectContaining({ character_id: "CH-001" })));
    expect(screen.getByText("portrait of 陈夜")).toBeInTheDocument();
  });
});
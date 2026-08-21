import { beforeEach, describe, expect, it, vi } from "vitest";

import * as characterApi from "@/api/character";
import * as storyApi from "@/api/story";

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => vi.restoreAllMocks());

describe("story API 真实 DTO", () => {
  it("parse 返回 canonical 场景，兼容场景路由读取同一组 ID", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(json({
        novel_id: "project-a", graph_id: "graph-1", total_chapters: 1,
        total_scenes: 1, total_shots: 1, chapters: [{ id: "chapter-real", number: 1 }],
        scenes: [{
          id: "scene-real", chapter_id: "chapter-real", number: 1,
          raw_text: "海潮越过长堤", description: "海潮越过长堤", mood: "tense",
          shots: [{
            id: "shot-real", scene_id: "scene-real", index: 0, shot_type: "wide",
            camera_angle: "eye-level", description: "海潮越过长堤", character_ids: [],
          }],
        }],
      }))
      .mockResolvedValueOnce(json({
        scene_count: 1,
        scenes: [{
          id: "scene-real", chapter_id: "chapter-real", number: 1,
          raw_text: "海潮越过长堤", description: "海潮越过长堤", mood: "tense",
          shots: [{
            id: "shot-real", scene_id: "scene-real", index: 0, shot_type: "wide",
            camera_angle: "eye-level", description: "海潮越过长堤", character_ids: [],
          }],
        }],
      }));

    const parsed = await storyApi.parseStory({ text: "正文", novel_id: "project-a" });
    const scenes = await storyApi.parseScenes("正文", "project-a");

    expect(JSON.parse(String(fetchSpy.mock.calls[0][1]?.body))).toEqual({
      text: "正文",
      novel_id: "project-a",
    });
    expect(parsed.scene_data).toEqual([expect.objectContaining({ id: "scene-real", chapter_id: "chapter-real", index: 0 })]);
    expect(parsed.scene_data[0].shots[0].id).toBe("shot-real");
    expect(scenes).toEqual(parsed.scene_data);
    expect(fetchSpy.mock.calls[1][0]).toBe("/api/story/parse/scenes");
    expect(JSON.parse(String(fetchSpy.mock.calls[1][1]?.body))).toEqual({
      text: "正文",
      novel_id: "project-a",
    });
  });

  it("解包并归一化 timeline events", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({
      novel_id: "project-a",
      events: [{
        id: "event-1", character_id: "char-1", chapter_number: 2,
        event_type: "appearance", description: "登场", relative_time: "chapter 2",
      }],
    }));

    await expect(storyApi.getTimeline("project-a")).resolves.toEqual([{
      id: "event-1",
      character_id: "char-1",
      chapter_id: "2",
      chapter_index: 1,
      event_type: "appearance",
      description: "登场",
    }]);
  });

  it("新增 timeline event 发送写模型 novel_id/chapter_number 并归一化返回值", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(json({
      id: "event-2", novel_id: "project-a", chapter_number: 3,
      character_id: "char-1", event_type: "action", description: "拔剑", relative_time: "第三章",
    }));

    await expect(storyApi.addTimelineEvent({
      novel_id: "project-a", chapter_number: 3, character_id: "char-1",
      event_type: "action", description: "拔剑", relative_time: "第三章",
    })).resolves.toEqual(expect.objectContaining({ chapter_id: "3", chapter_index: 2 }));
    expect(JSON.parse(String(fetchSpy.mock.calls[0][1]?.body))).toEqual({
      novel_id: "project-a", chapter_number: 3, character_id: "char-1",
      event_type: "action", description: "拔剑", relative_time: "第三章",
    });
  });
});

describe("character API 真实 DTO", () => {
  it("解析角色 JSON 字段并解包提取响应", async () => {
    const raw = {
      id: "char-1", name: "林默", appearance: "{\"eyes\":\"灰色\"}",
      personality: "{\"traits\":[\"calm\"]}", combat_style: "{}", aliases: "[]",
    };
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(json([raw]))
      .mockResolvedValueOnce(json({ count: 1, characters: [raw] }));

    await expect(characterApi.listCharacters("project-a")).resolves.toEqual([
      expect.objectContaining({ appearance: { eyes: "灰色" }, personality: { traits: ["calm"] } }),
    ]);
    await expect(characterApi.extractCharacters({ text: "正文", novel_id: "project-a" })).resolves.toEqual([
      expect.objectContaining({ id: "char-1", name: "林默" }),
    ]);
  });

  it("归一化图片与关系，并使用后端真实 POST 形态", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(json({ id: "image-1", character_id: "char/1", file_path: "refs/front.png", image_type: "front_view", is_primary: true }))
      .mockResolvedValueOnce(json({ id: "rel-1", character_id: "char/1", related_id: "char-2", related_name: "苏晚", relation_type: "friend" }));

    await expect(characterApi.addCharacterImage("char/1", {
      character_id: "char/1", url: "refs/front.png", label: "front", is_reference: true,
    })).resolves.toEqual(expect.objectContaining({ url: "/api/characters/media/image-1", label: "front", is_reference: true }));
    expect(fetchSpy.mock.calls[0][0]).toBe(
      "/api/characters/images?character_id=char%2F1&image_path=refs%2Ffront.png&image_type=front_view&is_primary=true",
    );
    expect(fetchSpy.mock.calls[0][1]).toMatchObject({ method: "POST" });

    await expect(characterApi.addRelationship("char/1", {
      source_id: "char/1", target_id: "char-2", relation_type: "friend",
    })).resolves.toEqual(expect.objectContaining({
      source_id: "char/1", target_id: "char-2", related_name: "苏晚",
    }));
    expect(fetchSpy.mock.calls[1][0]).toBe("/api/characters/relationships");
    expect(JSON.parse(String(fetchSpy.mock.calls[1][1]?.body))).toEqual({
      character_id: "char/1",
      related_id: "char-2",
      relation_type: "friend",
      description: "",
    });
  });

  it("本地图片使用受约束媒体 URL，远程和 data URL 保持原样", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json([
      { id: "local-1", character_id: "char-1", file_path: "refs/front.png", image_type: "front_view" },
      { id: "remote-1", character_id: "char-1", file_path: "https://cdn.example/ref.png", image_type: "side_view" },
      { id: "data-1", character_id: "char-1", file_path: "data:image/png;base64,AAAA", image_type: "expression" },
    ]));

    await expect(characterApi.listCharacterImages("char-1")).resolves.toEqual([
      expect.objectContaining({ url: "/api/characters/media/local-1" }),
      expect.objectContaining({ url: "https://cdn.example/ref.png" }),
      expect.objectContaining({ url: "data:image/png;base64,AAAA" }),
    ]);
  });

  it("一致性检查使用 GET query 并归一化 consistent/score", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(json({
      character_id: "char/1", consistent: false, score: 0.61, threshold: 0.75,
    }));

    await expect(characterApi.checkCharacterConsistency("char/1", "generated/a b.png")).resolves.toEqual({
      character_id: "char/1", passed: false, similarity: 0.61, threshold: 0.75, message: "",
    });
    expect(fetchSpy.mock.calls[0][0]).toBe(
      "/api/characters/char%2F1/consistency?image_path=generated%2Fa+b.png",
    );
    expect(fetchSpy.mock.calls[0][1]?.method).toBe("GET");
  });
});

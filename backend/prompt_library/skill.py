"""Phase 15.3-C：Prompt Skill 自动书写标准提示词（抖音 MiniMaxH3 工作流核心）.

从 Prompt OS ShotDesign（八层）自动填充 CINEDANCE 15 段骨架，
产出可直接喂给 MiniMaxH3 Director 的标准提示词。"""

from __future__ import annotations

from backend.prompt_library.service import PromptLibrary


class PromptSkill:
    """自动书写标准提示词技能（ShotDesign → CINEDANCE）。"""

    def __init__(self, library: PromptLibrary | None = None):
        self.library = library or PromptLibrary()

    # ------------------------------------------------------------ extract
    def extract_shot_design(self, design: dict) -> dict:
        """从 Prompt OS ShotDesign 八层提取字段。"""
        layers = design.get("layers", {}) or {}
        story = layers.get("story", "") or ""
        director_intent = layers.get("director_intent", "") or ""
        photo = layers.get("photography", {}) or {}
        composition = layers.get("composition", {}) or {}
        action = layers.get("action", {}) or {}
        camera = layers.get("camera_movement", "") or ""
        lighting = layers.get("lighting", {}) or {}
        style = layers.get("style", {}) or {}
        duration = int(design.get("duration_seconds") or 15)
        characters = [c.get("name", c) if isinstance(c, dict) else str(c)
                      for c in layers.get("characters", []) or []]
        return {
            "characters": characters,
            "location": str(layers.get("location", "") or composition.get("name", "")),
            "action": story,
            "duration_s": duration,
            "optics": f"{photo.get('lens', '')} {photo.get('shot', '')} {photo.get('angle', '')}".strip(),
            "camera": str(camera),
            "lighting": f"{lighting.get('name', '')} {lighting.get('effect', '')}".strip(),
            "style_hint": style.get("visual", ""),
            "intent": director_intent,
        }

    # ------------------------------------------------------------ write
    def write(self, design: dict, *, beats: list[str] | None = None) -> str:
        """自动书写标准提示词。"""
        s = self.extract_shot_design(design)
        return self.library.compile_shot(
            characters=s["characters"] or ["主角"],
            location=s["location"] or "场景",
            action=f"{s['action']}。导演意图：{s['intent']}。",
            duration_s=max(5, s["duration_s"]),
            beats=beats or [],
            optics=s["optics"],
            camera=s["camera"],
            lighting=s["lighting"],
        )

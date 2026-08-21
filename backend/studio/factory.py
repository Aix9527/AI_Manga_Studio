"""AI_Manga_Studio v1.0 Phase 4：多模态生产引擎（小说理解 + 镜头工厂 + 集管理）. """

from __future__ import annotations

import json
from pathlib import Path

# 镜头类型库（GPT Shot Factory）
SHOT_TYPES = ["establishing", "wide", "medium", "closeup", "insert", "low_angle", "high_angle", "tracking", "push_in", "reveal"]


class NovelEngine:
    """小说理解引擎：世界观 / 人物 / 冲突。"""

    def analyze(self, *, title: str, content: str, characters: list[str] | None = None) -> dict:
        chars = characters or ["主角"]
        # 简化：按段落/关键词抽取结构
        paragraphs = [p for p in content.split("\n") if p.strip()]
        return {
            "title": title,
            "world": {
                "era": "古代文明",
                "location": "场景待定",
                "rules": ["远古科技", "无现代科技"],
            },
            "characters": chars,
            "main_conflict": paragraphs[0][:50] if paragraphs else "探索真相",
            "chapters": len(paragraphs),
        }


class EpisodeManager:
    """剧集管理器：小说章节 → 集规划。"""

    def plan_season(self, *, title: str, chapters: int = 100, episodes: int = 12) -> dict:
        per = max(1, -(-chapters // episodes))
        return {
            "season": "S1",
            "episodes": [{"id": f"EP{i + 1:02d}", "chapters": list(range(i * per + 1, min(chapters, (i + 1) * per) + 1))} for i in range(episodes)],
            "chapters_per_episode": per,
        }


class ShotFactory:
    """镜头工厂：剧本 → Shot Bible（GPT Phase 4）。"""

    def build_shot_bible(self, *, episode: str, action: str, shot_count: int = 12,
                         duration_per_shot: int = 5) -> dict:
        shots = []
        for i in range(shot_count):
            shot_type = SHOT_TYPES[i % len(SHOT_TYPES)]
            shots.append({
                "id": f"{episode}-{i + 1:03d}",
                "type": shot_type,
                "duration": duration_per_shot,
                "camera": {"type": shot_type, "movement": "slow"},
                "action": action,
            })
        return {"episode": episode, "total": len(shots), "shots": shots}


class AssetFactory:
    """资产工厂：自动生成资产清单（角色/场景/道具）。"""

    def plan_assets(self, *, characters: list[str], locations: list[str], props: list[str]) -> dict:
        return {
            "characters": {c: {"face.png": "", "front.png": "", "side.png": ""} for c in characters},
            "locations": {loc: ["entrance", "main", "detail"] for loc in locations},
            "props": {p: {"base.png": ""} for p in props},
        }


class ProductionFactory:
    """Phase 4 总入口：小说 → 季规划 → 每集镜头圣经 → 资产。"""

    def __init__(self):
        self.novel = NovelEngine()
        self.episodes = EpisodeManager()
        self.shots = ShotFactory()
        self.assets = AssetFactory()

    def produce_season_plan(self, *, title: str, content: str,
                            characters: list[str], locations: list[str],
                            episodes: int = 12, shots_per_episode: int = 60) -> dict:
        universe = self.novel.analyze(title=title, content=content, characters=characters)
        season = self.episodes.plan_season(title=title, chapters=universe["chapters"], episodes=episodes)
        episode_plans = [
            self.shots.build_shot_bible(episode=ep["id"], action=universe["main_conflict"], shot_count=shots_per_episode)
            for ep in season["episodes"]
        ]
        assets = self.assets.plan_assets(characters=characters, locations=locations, props=[])
        return {
            "universe": universe,
            "season": season,
            "total_shots": sum(ep["total"] for ep in episode_plans),
            "assets": assets,
        }

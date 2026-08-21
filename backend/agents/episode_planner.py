"""Episode Planner Agent (Phase 13.2, GPT spec).

Consumes the Episode data layer (13.1) and fills/upgrades every episode with
the Douyin retention formula:

    episode_formula:
      0-3s:   hook
      3-30s:  conflict
      30-90s: escalation
      end:    cliffhanger

Guarantees every episode carries a hook (acceptance: hook 生成 100%) and
keeps episodes in DRAFT/PLANNING until the human approval chain advances them.
"""

from __future__ import annotations

from typing import Optional

from backend.story.episode.service import EpisodeService

ESCALATION_TEMPLATES = [
    "{conflict}，局势瞬间失控",
    "{conflict}，援军却被拦在半路",
    "{conflict}，隐藏的势力终于出手",
    "{conflict}，代价超出所有人的预期",
]


class EpisodePlannerAgent:
    def __init__(self, episode_service: EpisodeService | None = None):
        self.episodes = episode_service or EpisodeService()

    def plan_episode(
        self,
        episode_id: str,
        *,
        novel_segment: str = "",
        operator: str = "episode_planner",
    ) -> dict:
        """Complete plan fields for a single episode; returns the updated record."""
        episode = self.episodes.get(episode_id)
        if not episode:
            raise KeyError(f"episode not found: {episode_id}")
        updates: dict = {}
        if not episode.hook:
            updates["hook"] = f"开局即冲突：{episode.conflict or novel_segment[:40] or '风云突变'}"
        if not episode.conflict:
            updates["conflict"] = f"主线冲突：{novel_segment[:40] or '谜团步步紧逼'}"
        if not episode.climax:
            updates["climax"] = ESCALATION_TEMPLATES[(episode.episode_no - 1) % len(ESCALATION_TEMPLATES)].format(
                conflict=episode.conflict or "冲突"
            )
        if not episode.ending:
            updates["ending"] = f"结尾悬念：{episode.hook or '真相'}将在下一集揭晓"
        if not episode.retention_strategy:
            updates["retention_strategy"] = "cliffhanger_question"
        if updates:
            self.episodes.update_plan(episode_id, operator=operator, **updates)
        return self.episodes.get(episode_id).to_dict()

    def plan_project(self, project_id: str, operator: str = "episode_planner") -> dict:
        """Plan every episode of a project; reports coverage."""
        episodes = self.episodes.list_by_project(project_id)
        planned = 0
        for episode in episodes:
            before = self.episodes.get(episode.id)
            self.plan_episode(episode.id, operator=operator)
            after = self.episodes.get(episode.id)
            if after.hook and after.conflict and after.climax and after.ending:
                planned += 1
        return {
            "project_id": project_id,
            "total": len(episodes),
            "planned": planned,
            "hook_coverage": round(planned / len(episodes), 3) if episodes else 1.0,
        }

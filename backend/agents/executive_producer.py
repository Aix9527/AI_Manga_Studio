"""Executive Producer Agent (Phase 13.2, GPT spec).

Input : novel text + platform + budget + target episodes + target duration
Output: Season/Episode production plan:
    {season, target_episodes, episodes: [{ep, hook, conflict, climax,
      ending, retention_strategy}]}

Deterministic, rule-based beat generation. The plan is written into the
Episode data layer as DRAFT records — the human approval chain decides
whether they ever leave DRAFT (no autonomous deployment).
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.story.episode.service import EpisodeService

# Douyin short-drama retention formula (0-3s hook / 3-30s conflict /
# 30-90s escalation / end cliffhanger).
EPISODE_FORMULA = {
    "0_3s": "hook",
    "3_30s": "conflict",
    "30_90s": "escalation",
    "end": "cliffhanger",
}

HOOK_TEMPLATES = [
    "{hero}撞见{threat}，生死一线",
    "{hero}的身份在众人面前被揭开",
    "{hero}被逼入绝境，退无可退",
    "{hero}发现{secret}，追兵已至",
    "{hero}与{enemy}狭路相逢",
]

CONFLICT_TEMPLATES = [
    "{hero}与{enemy}正面交锋，实力悬殊",
    "{hero}的同伴反目，内忧外患",
    "{hero}的底牌被对手看穿",
    "{hero}为救人必须牺牲什么",
    "{hero}被卷入更大的阴谋",
]

CLIMAX_TEMPLATES = [
    "{hero}觉醒隐藏力量，逆转战局",
    "{hero}做出关键抉择，代价沉重",
    "{hero}揭开真相，敌人现出真身",
    "{hero}以弱胜强，一战成名",
    "{hero}与旧敌联手，共抗强敌",
]

ENDING_TEMPLATES = [
    "{hero}望向远方：更大的风暴正在逼近",
    "{hero}听见那人的名字，瞳孔骤缩",
    "{hero}身后的阴影中，一双眼睛缓缓睁开",
    "{hero}握紧信物：这一切才刚刚开始",
    "黑暗尽头，{enemy}的声音响起：我们又见面了",
]

RETENTION_STRATEGIES = [
    "cliffhanger_question", "identity_reveal", "power_display", "threat_escalation", "betrayal_hook",
]


@dataclass
class ProductionPlan:
    project_id: str
    season: int = 1
    target_episodes: int = 100
    platform: str = "douyin"
    budget: float = 0.0
    target_duration: float = 90.0
    episodes: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _extract_names(text: str) -> dict:
    """Heuristic name extraction for plan templates (hero/enemy/secret)."""
    hero = "少年"
    m = re.search(r"[「《]([\u4e00-\u9fa5]{2,4})[」》]", text)
    if not m:
        m = re.search(r"([\u4e00-\u9fa5]{2,4})[」》]?(?:觉醒|重生|穿越|归来|获得)", text)
    if not m:
        m = re.search(r"主角(?:是|叫|为)?[:：]?([\u4e00-\u9fa5]{2,4})", text)
    if m:
        hero = m.group(1)
    enemy = "宿敌"
    m = re.search(r"(?:反派|敌人|宿敌|对手)[:：]?([\u4e00-\u9fa5]{2,4})", text)
    if m:
        enemy = m.group(1)
    secret = "尘封的秘密"
    m = re.search(r"(?:秘密|真相|遗迹|身世)[:：]?([\u4e00-\u9fa5]{2,6})", text)
    if m:
        secret = m.group(1)
    return {"hero": hero, "enemy": enemy, "secret": secret, "threat": enemy or "危机"}


def _roll(template: str, names: dict, episode_no: int) -> str:
    filled = template.format(**names)
    return f"{filled}（第{episode_no}集）"


class ExecutiveProducerAgent:
    def __init__(self, episode_service: EpisodeService | None = None):
        self.episodes = episode_service or EpisodeService()

    def plan(
        self,
        novel_text: str,
        *,
        project_id: str,
        platform: str = "douyin",
        budget: float = 0.0,
        target_episodes: int = 100,
        target_duration: float = 90.0,
        season: int = 1,
        write_episodes: bool = True,
    ) -> ProductionPlan:
        """Build the season plan; optionally persist DRAFT episodes."""
        names = _extract_names(novel_text)
        episodes: list[dict] = []
        for ep in range(1, target_episodes + 1):
            idx = (ep - 1) % 5
            episodes.append({
                "ep": ep,
                "hook": _roll(HOOK_TEMPLATES[idx], names, ep),
                "conflict": _roll(CONFLICT_TEMPLATES[idx], names, ep),
                "climax": _roll(CLIMAX_TEMPLATES[idx], names, ep),
                "ending": _roll(ENDING_TEMPLATES[idx], names, ep),
                "retention_strategy": RETENTION_STRATEGIES[idx],
            })
        plan = ProductionPlan(
            project_id=project_id,
            season=season,
            target_episodes=target_episodes,
            platform=platform,
            budget=budget,
            target_duration=target_duration,
            episodes=episodes,
            meta={
                "formula": EPISODE_FORMULA,
                "hero": names["hero"],
                "enemy": names["enemy"],
                "source_words": max(0, len(re.sub(r"\s+", "", novel_text or ""))),
            },
        )
        if write_episodes:
            self._persist(plan, operator="executive_producer")
        return plan

    def _persist(self, plan: ProductionPlan, operator: str = "executive_producer") -> None:
        """Write episodes as DRAFT records — never auto-advance (human gate)."""
        for row in plan.episodes:
            episode = self.episodes.create(
                plan.project_id,
                episode_no=row["ep"],
                season=plan.season,
                title=f"第{row['ep']:03d}集",
                operator=operator,
            )
            self.episodes.update_plan(
                episode.id,
                hook=row["hook"],
                conflict=row["conflict"],
                climax=row["climax"],
                ending=row["ending"],
                retention_strategy=row["retention_strategy"],
                script_version="v1",
                operator=operator,
            )

    def plan_pipeline_estimate(self, plan: ProductionPlan) -> dict:
        """Rough production estimate: shots/duration/GPU-hours for the season."""
        shots_per_episode = max(1, int(round(plan.target_duration / 5.0)))
        total_shots = shots_per_episode * plan.target_episodes
        gpu_hours = round(total_shots * 0.05, 1)  # heuristic 3min GPU / shot
        return {
            "season": plan.season,
            "episodes": plan.target_episodes,
            "shots_per_episode": shots_per_episode,
            "total_shots": total_shots,
            "estimated_gpu_hours": gpu_hours,
            "platform": plan.platform,
            "budget": plan.budget,
        }

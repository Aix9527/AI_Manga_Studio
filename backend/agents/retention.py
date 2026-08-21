"""Retention Intelligence Engine (Phase 13.2, GPT spec).

Renamed from "Viral Pattern Analyzer" per GPT: it outputs content-analysis
metrics (hook strength / emotion curve / cliffhanger strength), NOT a promise
of virality.

Output:
    {hook_score, emotion_curve, cliffhanger_score, share_probability}
"""

from __future__ import annotations

import re


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class RetentionIntelligenceEngine:
    def score_episode(
        self,
        *,
        hook: str = "",
        conflict: str = "",
        climax: str = "",
        ending: str = "",
        retention_strategy: str = "",
    ) -> dict:
        """Score one episode against the Douyin retention formula."""
        hook_score = self._hook_strength(hook, conflict)
        emotion_curve = self._emotion_curve(hook, conflict, climax, ending)
        cliffhanger_score = self._cliffhanger_strength(ending, retention_strategy)
        share_probability = _clamp(
            0.25 * hook_score + 0.3 * emotion_curve + 0.3 * cliffhanger_score + 0.15 * (1.0 if retention_strategy else 0.5)
        )
        return {
            "hook_score": round(hook_score, 3),
            "emotion_curve": round(emotion_curve, 3),
            "cliffhanger_score": round(cliffhanger_score, 3),
            "share_probability": round(share_probability, 3),
            "formula_check": self._formula_check(hook, conflict, ending),
        }

    def score_plan(self, episodes: list[dict]) -> dict:
        """Score a whole plan; aggregate + per-episode coverage."""
        results = [self.score_episode(**{k: v for k, v in ep.items() if k in
                                         ("hook", "conflict", "climax", "ending", "retention_strategy")})
                   for ep in episodes]
        if not results:
            return {"episodes": 0, "average": {}, "hook_coverage": 1.0}
        average = {key: round(sum(r[key] for r in results) / len(results), 3)
                   for key in ("hook_score", "emotion_curve", "cliffhanger_score", "share_probability")}
        return {
            "episodes": len(results),
            "average": average,
            "hook_coverage": round(sum(1 for r in results if r["hook_score"] >= 0.5) / len(results), 3),
            "cliffhanger_coverage": round(sum(1 for r in results if r["cliffhanger_score"] >= 0.5) / len(results), 3),
        }

    # ------------------------------------------------------------- helpers
    def _hook_strength(self, hook: str, conflict: str) -> float:
        if not hook:
            return 0.0
        text = f"{hook} {conflict}"
        score = 0.5
        for keyword in ("死", "杀", "追", "危", "秘密", "觉醒", "揭", "陷", "背叛", "消失", "封印", "真相"):
            if keyword in text:
                score += 0.08
        if len(hook) >= 8:
            score += 0.1
        return _clamp(score)

    def _emotion_curve(self, hook: str, conflict: str, climax: str, ending: str) -> float:
        beats = [b for b in (hook, conflict, climax, ending) if b]
        if not beats:
            return 0.0
        # Distinct beat content -> stronger emotional arc.
        unique = len({b[:6] for b in beats})
        return _clamp(0.35 + 0.18 * (unique - 1) + 0.1 * (len(beats) >= 4))

    def _cliffhanger_strength(self, ending: str, retention_strategy: str) -> float:
        if not ending:
            return 0.0
        score = 0.5
        for keyword in ("?" ,"？", "悬念", "揭晓", "逼近", "开始", "响起", "瞳孔", "背后", "下一集"):
            if keyword in ending:
                score += 0.12
        if retention_strategy in ("cliffhanger_question", "threat_escalation", "betrayal_hook"):
            score += 0.2
        return _clamp(score)

    def _formula_check(self, hook: str, conflict: str, ending: str) -> dict:
        return {
            "0_3s_hook": bool(hook),
            "3_30s_conflict": bool(conflict),
            "end_cliffhanger": bool(ending),
        }

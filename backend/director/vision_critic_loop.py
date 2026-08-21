"""Vision Critic Loop (Phase 11.2, GPT approved).

Closed loop per GPT::

    Director -> Generate -> Vision Critic -> Feedback
        -> Director Memory -> Next Shot

The loop plans one shot at a time so the feedback recorded for shot *i* is
available to :meth:`PolicyDirector.apply_memory_feedback` when planning shot
*i+1*. Every critique is written into Director Memory (feedback write rate
= 100%); the acceptance metrics mirror GPT's 11.2 MVP:

- problem detection rate >= 80%
- feedback written to Memory = 100%
- next-shot directive change rate >= 50%
- no regression: Python suite keeps growing (> 135 tests)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from backend.director.hybrid import section_context_for
from backend.director.policy_router import PolicyDirector
from backend.director.vision_critic import VisionCritic
from backend.story.models import Shot

GenerateFn = Callable[[Shot, Any, Path | None], str | Path | None]


class VisionCriticLoop:
    """Drives Director -> Generate -> Critic -> Memory -> Next Shot."""

    def __init__(
        self,
        director: PolicyDirector,
        critic: VisionCritic | None = None,
        generate_fn: GenerateFn | None = None,
    ):
        if director.memory is None:
            raise ValueError("VisionCriticLoop requires a PolicyDirector with memory_root")
        self.director = director
        self.critic = critic or VisionCritic()
        self.generate_fn = generate_fn
        self.last_directives: list[Any] = []

    def run(
        self,
        shots: list[Shot],
        sections: list | None = None,
        *,
        references: dict | None = None,
        workdir: str | Path | None = None,
        gate_reports: dict[str, dict] | None = None,
        seeded: dict[str, list[str]] | None = None,
        project_id: str = "",
        episode: str = "",
    ) -> dict:
        """Run the loop over a shot list.

        ``gate_reports``: shot_id -> {"quality": QualityReport, "identity": IdentityGateReport}
            lets tests/benchmarks inject deterministic gate evidence without a real video.
        ``seeded``: shot_id -> [issue keywords] the critic is expected to detect
            (used to compute the problem detection rate).
        """
        gate_reports = gate_reports or {}
        sections = sections or []
        section_by_scene = {getattr(s, "scene_id", ""): s for s in sections}

        directives: list[Any] = []
        results: list[dict] = []
        previous_shot = ""
        self.last_directives = directives
        for shot in shots:
            context = section_context_for(section_by_scene.get(shot.scene_id, ""))
            directive = self.director.plan_shot(shot, context)
            directive.continuity = dict(directive.continuity or {})
            directive.continuity["previous_shot"] = previous_shot
            self.director.apply_memory_feedback(directive)  # feedback from shot i-1
            directives.append(directive)

            video_path = None
            production_cost = None
            generation_time = None
            if self.generate_fn is not None:
                generated = self.generate_fn(shot, directive, workdir)
                if isinstance(generated, dict):
                    video_path = generated.get("path")
                    production_cost = generated.get("production_cost")
                    generation_time = generated.get("generation_time")
                else:
                    video_path = generated
            reports = gate_reports.get(shot.id, {})
            critique = self.critic.critique(
                shot,
                directive,
                video_path=video_path,
                references=references,
                workdir=workdir,
                quality_report=reports.get("quality"),
                identity_report=reports.get("identity"),
            )
            # Feedback -> Director Memory (always written, per GPT 100% metric)
            self.director.memory.record_quality(
                shot.id, critique.quality_score, critique.to_feedback_dict(),
                production_cost=production_cost, generation_time=generation_time,
            )
            results.append({
                "shot_id": shot.id,
                "directive": directive,
                "critique": critique,
                "video_path": str(video_path) if video_path else None,
                "production_cost": production_cost,
                "generation_time": generation_time,
                "project_id": project_id,
                "episode": episode,
            })
            previous_shot = shot.id

        metrics = self.metrics(results, seeded=seeded or {})
        return {"directives": directives, "results": results, "metrics": metrics}

    # ------------------------------------------------------------- metrics
    def metrics(self, results: list[dict], seeded: dict[str, list[str]]) -> dict:
        n = len(results)
        # 1) problem detection: seeded issue appears in the memory feedback
        seeded_total = sum(len(v) for v in seeded.values())
        detected = 0
        written = 0
        for item in results:
            memory = self.director.memory.shot.get(item["shot_id"]) or {}
            items = (memory.get("feedback") or {}).get("items") or []
            if items:
                written += 1
            got_issues = {str(f.get("issue") or "") for f in items}
            got_categories = {str(f.get("category") or "") for f in items}
            for issue in seeded.get(item["shot_id"], []):
                if issue in got_issues or issue in got_categories:
                    detected += 1
        detection_rate = (detected / seeded_total) if seeded_total else None

        # 2) feedback write rate: every shot recorded quality feedback
        write_rate = (written / n) if n else 0.0

        # 3) next-shot directive change: directives carrying a memory_feedback
        #    note were adjusted because their previous shot produced feedback
        changed = sum(
            1 for d in self.last_directives if (d.continuity or {}).get("memory_feedback")
        )
        change_rate = (changed / max(1, n - 1)) if n > 1 else 0.0

        return {
            "shots": n,
            "seeded_problems": seeded_total,
            "detected_problems": detected,
            "problem_detection_rate": round(detection_rate, 3) if detection_rate is not None else None,
            "feedback_write_rate": round(write_rate, 3),
            "directive_change_rate": round(change_rate, 3),
            "directives_changed": changed,
        }

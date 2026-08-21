"""Asset Feedback Loop service (Phase 13.4-C, GPT spec).

Flow: Critic / Gate / QC → Feedback Event → Asset Candidate Update →
Human Review → Approve → New Version. Locked production assets are never
mutated in place; approved candidates produce new versions / append-only
records. Shot DNA feedback keeps its statistical basis (usage_count /
success_count / failure_count / quality_sum / human_score_sum) and only
recomputes success_rate after a minimum sample threshold.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from backend.characters.bible_v2.service import CharacterBibleService
from backend.feedback.model import (
    AssetCandidate,
    CANDIDATE_STATUSES,
    EVENT_KINDS,
    FeedbackEvent,
    TARGET_TYPES,
)
from backend.feedback.store import FeedbackStore
from backend.prompt_intelligence.service import PromptIntelligenceService
from backend.shot_dna.library import ShotDNALibrary
from backend.world.service import WorldService


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class FeedbackService:
    """Records feedback, proposes candidates, and applies approved updates."""

    def __init__(
        self,
        root: str | Path = "storage/feedback",
        *,
        characters: CharacterBibleService | None = None,
        world: WorldService | None = None,
        shot_dna: ShotDNALibrary | None = None,
        intelligence: PromptIntelligenceService | None = None,
        min_samples: int = 10,
        prior_weight: int = 5,
    ):
        self.store = FeedbackStore(root)
        self.characters = characters or CharacterBibleService()
        self.world = world or WorldService()
        self.shot_dna = shot_dna or ShotDNALibrary()
        self.intelligence = intelligence or PromptIntelligenceService()
        self.min_samples = min_samples
        self.prior_weight = prior_weight

    # ------------------------------------------------------------- events
    def record_event(
        self,
        *,
        kind: str,
        target_type: str,
        target_id: str,
        source: str = "",
        project_id: str = "",
        severity: str = "medium",
        issues: list[str] | None = None,
        metrics: dict | None = None,
    ) -> dict:
        if kind not in EVENT_KINDS:
            raise ValueError(f"invalid event kind: {kind} (allowed: {EVENT_KINDS})")
        if target_type not in TARGET_TYPES:
            raise ValueError(f"invalid target type: {target_type} (allowed: {TARGET_TYPES})")
        event = FeedbackEvent(
            id=_new_id("EV"), kind=kind, source=source, target_type=target_type,
            target_id=target_id, project_id=project_id, severity=severity,
            issues=issues or [], metrics=metrics or {},
        )
        self.store.put_event(event)
        return event.to_dict()

    def list_events(self, **filters) -> list[dict]:
        return [e.to_dict() for e in self.store.list_events(**filters)]

    def stats(self) -> dict:
        events = self.store.list_events()
        by_kind: dict[str, int] = {}
        by_target: dict[str, int] = {}
        for event in events:
            by_kind[event.kind] = by_kind.get(event.kind, 0) + 1
            by_target[event.target_type] = by_target.get(event.target_type, 0) + 1
        candidates = self.store.list_candidates()
        by_status: dict[str, int] = {}
        for candidate in candidates:
            by_status[candidate.status] = by_status.get(candidate.status, 0) + 1
        return {
            "events": len(events),
            "by_kind": by_kind,
            "by_target_type": by_target,
            "candidates": len(candidates),
            "by_status": by_status,
        }

    # ------------------------------------------------------------- shot stats
    def record_shot_outcome(
        self,
        dna_id: str,
        *,
        success: bool | None = None,
        quality: float | None = None,
        human_score: float | None = None,
        source: str = "qc",
    ) -> dict:
        """Append-only statistical basis for a Shot DNA outcome."""
        stats = self.store.shot_stats.get(dna_id) or {
            "usage_count": 0, "success_count": 0, "failure_count": 0,
            "quality_sum": 0.0, "human_score_sum": 0.0, "last_used_at": "",
        }
        stats["usage_count"] = int(stats["usage_count"]) + 1
        if success is True:
            stats["success_count"] = int(stats["success_count"]) + 1
        elif success is False:
            stats["failure_count"] = int(stats["failure_count"]) + 1
        if quality is not None:
            stats["quality_sum"] = float(stats["quality_sum"]) + float(quality)
        if human_score is not None:
            stats["human_score_sum"] = float(stats["human_score_sum"]) + float(human_score)
        stats["last_used_at"] = _now()
        self.store.shot_stats.put(dna_id, stats)
        self.record_event(
            kind="qc", target_type="shot_dna", target_id=dna_id, source=source,
            severity="low", metrics={"success": success, "quality": quality, "human_score": human_score},
        )
        return dict(stats)

    def shot_stats(self, dna_id: str) -> dict:
        raw = self.store.shot_stats.get(dna_id)
        if not raw:
            return {
                "usage_count": 0, "success_count": 0, "failure_count": 0,
                "success_rate": 0.0, "avg_quality": 0.0, "avg_human_score": 0.0,
            }
        usage = int(raw["usage_count"])
        success = int(raw["success_count"])
        prior = self._prior_rate(dna_id)
        smoothed = (prior * self.prior_weight + success) / (self.prior_weight + usage)
        quality_sum = float(raw.get("quality_sum", 0.0))
        human_sum = float(raw.get("human_score_sum", 0.0))
        return {
            "usage_count": usage,
            "success_count": success,
            "failure_count": int(raw.get("failure_count", 0)),
            "success_rate": round(min(1.0, max(0.0, smoothed)), 3),
            "avg_quality": round(quality_sum / usage, 3) if usage else 0.0,
            "avg_human_score": round(human_sum / usage, 3) if usage else 0.0,
            "last_used_at": raw.get("last_used_at", ""),
        }

    def _prior_rate(self, dna_id: str) -> float:
        dna = self.shot_dna.get(dna_id)
        return dna.success_rate if dna else 0.8

    # ------------------------------------------------------------- candidates
    def propose_candidate(
        self,
        *,
        target_type: str,
        target_id: str,
        suggested_changes: dict,
        reason: str = "",
        evidence: dict | None = None,
        project_id: str = "",
    ) -> dict:
        if target_type not in TARGET_TYPES:
            raise ValueError(f"invalid target type: {target_type} (allowed: {TARGET_TYPES})")
        pending = self.store.pending_candidate(target_type, target_id)
        if pending:
            raise ValueError(f"pending candidate already exists: {pending.id}")
        self._validate_target(target_type, target_id)
        candidate = AssetCandidate(
            id=_new_id("CD"), target_type=target_type, target_id=target_id,
            project_id=project_id, suggested_changes=suggested_changes,
            evidence=evidence or {}, reason=reason,
        )
        self.store.put_candidate(candidate)
        return candidate.to_dict()

    def auto_propose(self, min_samples: int | None = None, prior_weight: int | None = None) -> list[dict]:
        """Generate candidates from accumulated feedback (Shot DNA + issues)."""
        min_samples = min_samples or self.min_samples
        prior_weight = prior_weight or self.prior_weight
        created: list[dict] = []

        # Shot DNA statistical candidates
        for dna in self.shot_dna.all():
            raw = self.store.shot_stats.get(dna.id)
            if not raw or int(raw.get("usage_count", 0)) < min_samples:
                continue
            usage = int(raw["usage_count"])
            success = int(raw["success_count"])
            smoothed = (dna.success_rate * prior_weight + success) / (prior_weight + usage)
            try:
                created.append(
                    self.propose_candidate(
                        target_type="shot_dna", target_id=dna.id,
                        suggested_changes={
                            "success_rate": round(min(1.0, max(0.0, smoothed)), 3),
                            "usage_count": usage, "success_count": success,
                        },
                        evidence={"stats": self.shot_stats(dna.id)},
                        reason=f"shot dna feedback >= {min_samples} samples",
                    )
                )
            except ValueError:
                continue  # pending candidate already exists

        # Issue-label candidates (character / world / prompt_template).
        # Threshold = number of feedback samples, not distinct labels.
        issue_map: dict[tuple[str, str], dict] = {}
        for event in self.store.list_events():
            if event.target_type in ("character", "world", "prompt_template") and event.issues:
                key = (event.target_type, event.target_id)
                bucket = issue_map.setdefault(key, {"count": 0, "issues": []})
                bucket["count"] += 1
                bucket["issues"].extend(event.issues)
        for (target_type, target_id), bucket in issue_map.items():
            if bucket["count"] < min_samples:
                continue
            unique_issues = sorted(set(bucket["issues"]))
            try:
                created.append(
                    self.propose_candidate(
                        target_type=target_type, target_id=target_id,
                        suggested_changes={"issues": unique_issues},
                        evidence={"issue_count": len(unique_issues)},
                        reason=f"{target_type} feedback issue aggregation >= {min_samples} labels",
                    )
                )
            except ValueError:
                continue
        return created

    def review_candidate(self, candidate_id: str, decision: str, reviewer: str = "human") -> dict:
        if decision not in ("approve", "reject"):
            raise ValueError("decision must be approve or reject")
        candidate = self.store.get_candidate(candidate_id)
        if not candidate:
            raise KeyError(f"candidate not found: {candidate_id}")
        if candidate.status != "proposed":
            raise ValueError(f"candidate already {candidate.status}")
        candidate.status = "approved" if decision == "approve" else "rejected"
        candidate.reviewer = reviewer
        candidate.decided_at = _now()
        self.store.put_candidate(candidate)
        return candidate.to_dict()

    def apply_candidate(self, candidate_id: str) -> dict:
        candidate = self.store.get_candidate(candidate_id)
        if not candidate:
            raise KeyError(f"candidate not found: {candidate_id}")
        if candidate.status != "approved":
            raise ValueError(f"only approved candidates can apply (status={candidate.status})")
        self._apply(candidate)
        candidate.status = "applied"
        candidate.applied_at = _now()
        self.store.put_candidate(candidate)
        return candidate.to_dict()

    # ------------------------------------------------------------- internal
    def _validate_target(self, target_type: str, target_id: str) -> None:
        if target_type == "character" and not self.characters.get(target_id):
            raise KeyError(f"character bible not found: {target_id}")
        if target_type == "shot_dna" and not self.shot_dna.get(target_id):
            raise KeyError(f"shot dna not found: {target_id}")
        if target_type == "world" and not any(w.id == target_id for w in self.world.list_worlds()):
            raise KeyError(f"world not found: {target_id}")
        if target_type == "prompt_template":
            try:
                self.intelligence.get_template(target_id)
            except KeyError as exc:
                raise KeyError(f"prompt template not found: {target_id}") from exc

    def _apply(self, candidate: AssetCandidate) -> None:
        changes = candidate.suggested_changes
        if candidate.target_type == "shot_dna":
            stats = self.store.shot_stats.get(candidate.target_id) or {}
            self.shot_dna.apply_feedback_stats(
                candidate.target_id,
                success_count=int(stats.get("success_count", 0)),
                usage_count=int(stats.get("usage_count", 0)),
                quality_sum=float(stats.get("quality_sum", 0.0)),
                human_score_sum=float(stats.get("human_score_sum", 0.0)),
                prior_weight=self.prior_weight,
            )
        elif candidate.target_type == "character":
            issues = "；".join(changes.get("issues", []))
            self.characters.add_version(
                candidate.target_id,
                version_id=f"fb-{candidate.id.split('-')[-1]}",
                notes=f"[feedback-{_now()}] {issues or changes.get('notes', '')}",
            )
        elif candidate.target_type == "world":
            issues = "；".join(changes.get("issues", []))
            self.world.note_environment(
                candidate.project_id or "default", kind="feedback_issue",
                content=issues or str(changes), source="feedback_loop",
            )
        elif candidate.target_type == "prompt_template":
            active = self._active_version_text(candidate.target_id)
            issues = "；".join(changes.get("issues", []))
            self.intelligence.create_version(
                candidate.target_id,
                base_template=active,
                notes=f"[feedback-{_now()}] {issues or changes.get('notes', '')}",
            )

    def _active_version_text(self, template_id: str) -> str:
        row = self.intelligence.get_template(template_id)
        versions = row.get("versions", [])
        for version in versions:
            if version.get("status") == "locked":
                return version.get("base_template", "")
        for version in versions:
            if version.get("status") == "approved":
                return version.get("base_template", "")
        return versions[-1].get("base_template", "") if versions else ""
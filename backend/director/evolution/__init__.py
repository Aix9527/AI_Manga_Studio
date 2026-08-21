"""Controlled Director Evolution (Phase 11.3, GPT approved).

Not "AI rewrites itself": every candidate policy change is

1. discovered from Director Memory statistics (PolicyAnalyzer),
2. proposed with samples / confidence / score delta,
3. approved or rejected by a human (manual_approval mode only),
4. versioned as ``router_policy_v{n}.yaml`` and rollback-able.

GPT acceptance: >= 5 auto-discovered opportunities; each proposal carries
sample count + confidence + score delta; approve/reject traceable; policy
version increments; rollback restores the previous policy.
"""

from __future__ import annotations

from pathlib import Path

from backend.director.evolution.policy_analyzer import (
    DIRECTOR_ROUTE,
    PolicyAnalyzer,
)
from backend.director.evolution.policy_candidate import PolicyCandidate
from backend.director.evolution.policy_diff import policy_diff
from backend.director.evolution.rollback import PolicyVersionStore
from backend.director.memory import DirectorMemory, PolicyMemory
from backend.director.policy_router import DEFAULT_POLICY_PATH, DirectorRouter

import yaml


class ControlledEvolution:
    """Facade: analyze -> propose -> approve/reject -> versioned rollback."""

    def __init__(
        self,
        policy_memory: PolicyMemory,
        policy_path: str | Path = DEFAULT_POLICY_PATH,
        versions_dir: str | Path | None = None,
        router: DirectorRouter | None = None,
        director_memory: DirectorMemory | None = None,
    ):
        self.policy_path = Path(policy_path)
        # Phase 12.2: the full DirectorMemory (shots + feedback + production
        # fields) for the dashboard; ``policy_memory`` stays the evolution input.
        self.director_memory = director_memory
        self.router = router or DirectorRouter(self.policy_path)
        self.memory = policy_memory
        self.config = self.router.policy_learning or {}
        self.mode = str(self.config.get("mode") or "manual_approval")
        self.min_samples = int(self.config.get("min_samples") or 20)
        self.confidence_threshold = float(self.config.get("confidence_threshold") or 0.85)
        self.versions = PolicyVersionStore(
            self.policy_path,
            versions_dir=versions_dir,
            rollback_window=int(self.config.get("rollback_window") or 200),
        )
        self.analyzer = PolicyAnalyzer(policy_memory, self.router)

    # ---------------------------------------------------------- analysis
    def analyze(self) -> list[PolicyCandidate]:
        """All opportunities regardless of confidence threshold."""
        return self.analyzer.analyze(
            min_samples=self.min_samples, confidence_threshold=0.0
        )

    def propose(self) -> dict:
        """Valid proposals meeting the policy_learning thresholds."""
        candidates = self.analyzer.analyze(
            min_samples=self.min_samples, confidence_threshold=self.confidence_threshold
        )
        valid = [c for c in candidates if c.is_valid(self.min_samples, self.confidence_threshold)]
        return {"count": len(valid), "candidates": valid, "mode": self.mode}

    # ---------------------------------------------------------- approval
    def approve(self, candidate: PolicyCandidate, approved_by: str = "human") -> dict:
        """Apply a candidate under manual approval; versioned + traceable."""
        if self.mode != "manual_approval":
            raise RuntimeError(f"policy evolution mode is {self.mode!r}, not manual_approval")
        if not candidate.is_valid(self.min_samples, self.confidence_threshold):
            raise ValueError(
                f"candidate {candidate.scene_type} fails thresholds "
                f"(min_samples={self.min_samples}, confidence>={self.confidence_threshold})"
            )
        before = self._policy_dict()
        snapshot = self.versions.snapshot()  # persist the pre-change policy

        route_after = DIRECTOR_ROUTE.get(candidate.to_director)
        if not route_after:
            raise ValueError(f"no route for director {candidate.to_director!r}")
        after = self._apply_change(candidate.scene_type, route_after)

        entry = self.versions.log("approve", {
            "candidate": candidate.to_dict(),
            "policy_version_before": before.get("version", "initial"),
            "policy_version_after": after.get("version"),
            "snapshot_version": snapshot,
            "diff": policy_diff(before, after),
            "affected_shots": self._affected_shots(candidate.scene_type),
            "score_delta": candidate.score_delta,
            "confidence": candidate.confidence,
            "approved_by": approved_by,
        })
        self.router._load()  # refresh route table
        return {"candidate": candidate.to_dict(), "diff": policy_diff(before, after), "log": entry}

    def reject(self, candidate: PolicyCandidate, reason: str = "", rejected_by: str = "human") -> dict:
        """Record a rejection trace; no policy change."""
        return self.versions.log("reject", {
            "candidate": candidate.to_dict(),
            "reason": reason,
            "rejected_by": rejected_by,
        })

    # ---------------------------------------------------------- rollback
    def rollback(self, reason: str = "bad_policy_deployed", rolled_back_by: str = "human") -> dict:
        """Restore the most recent snapshot (undo the last approved change)."""
        version = self.versions.latest_version()
        if version <= 0:
            raise RuntimeError("no policy snapshot to roll back to")
        before = self._policy_dict()
        self.versions.restore(version)
        after = self._policy_dict()
        entry = self.versions.log("rollback", {
            "policy_version_before": before.get("version"),
            "policy_version_after": after.get("version"),
            "diff": policy_diff(before, after),
            "affected_shots": self._affected_shots_all(),
            "reason": reason,
            "rolled_back_by": rolled_back_by,
        })
        self.router._load()
        return {"restored_version": version, "diff": policy_diff(before, after), "log": entry}

    # ---------------------------------------------------------- helpers
    def _policy_dict(self) -> dict:
        if not self.policy_path.exists():
            return {}
        return yaml.safe_load(self.policy_path.read_text(encoding="utf-8")) or {}

    def _apply_change(self, scene_type: str, route_after: str) -> dict:
        data = self._policy_dict()
        routes = dict(data.get("routes") or {})
        routes[scene_type] = route_after
        data["routes"] = routes
        version = data.get("version")
        if isinstance(version, (int, float)):
            data["version"] = round(float(version) + 0.1, 1)
        tmp = self.policy_path.with_suffix(".yaml.tmp")
        tmp.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        tmp.replace(self.policy_path)
        return data

    def _affected_shots(self, scene_type: str) -> int:
        return sum(
            r["shots"] for r in self.memory.stats() if r["scene_type"] == scene_type
        )

    def _affected_shots_all(self) -> int:
        return sum(r["shots"] for r in self.memory.stats())

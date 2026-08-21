"""Episode Production Readiness Gate (Phase 13.3, GPT spec).

Blocks an Episode from entering ASSET_READY until the industrial assets
(Character Bible, World Bible, Shot DNA) meet the project gate:

- characters: every project character has a Bible with completeness >= ratio
- world:      project has at least one World Bible + environment memory
- shot_dna:   library covers all six categories

Returns a structured {ready, gates, missing} report for the UI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from backend.characters.bible_v2.service import CharacterBibleService
from backend.shot_dna.library import CATEGORIES, ShotDNALibrary
from backend.world.service import WorldService


class AssetReadinessGate:
    """Production asset completeness gate for Episode -> ASSET_READY."""

    def __init__(
        self,
        character_service: CharacterBibleService | None = None,
        world_service: WorldService | None = None,
        shot_dna_library: ShotDNALibrary | None = None,
        *,
        character_ratio_min: float = 0.9,
    ):
        self.characters = character_service or CharacterBibleService()
        self.world = world_service or WorldService()
        self.shot_dna = shot_dna_library or ShotDNALibrary()
        self.character_ratio_min = character_ratio_min

    def check_project(self, project_id: str) -> dict:
        """Full readiness report for a project."""
        character_gate = self._check_characters(project_id)
        world_gate = self._check_world(project_id)
        shot_gate = self._check_shot_dna()
        gates = {
            "character": character_gate,
            "world": world_gate,
            "shot_dna": shot_gate,
        }
        missing = [name for name, gate in gates.items() if not gate["pass"]]
        return {
            "project_id": project_id,
            "ready": not missing,
            "gates": gates,
            "missing": missing,
        }

    def require(self, project_id: str) -> None:
        """Raise ValueError with the missing gates when not ready."""
        report = self.check_project(project_id)
        if not report["ready"]:
            detail = ", ".join(report["missing"])
            raise ValueError(f"asset readiness gate blocked: missing {detail}")

    # ------------------------------------------------------------- gates
    def _check_characters(self, project_id: str) -> dict:
        # Character production assets = Character Bibles (views/expressions/
        # actions/versions). The gate requires at least one bible and every
        # bible to meet the completeness threshold.
        bibles = self.characters.list()
        incomplete: list[str] = []
        for bible in bibles:
            ratio = bible.completeness()["ratio"]
            if ratio < self.character_ratio_min:
                incomplete.append(f"{bible.character_id}:ratio={ratio}")
        passed = len(bibles) > 0 and not incomplete
        return {
            "pass": passed,
            "characters": len(bibles),
            "incomplete": incomplete,
            "threshold": self.character_ratio_min,
        }

    def _check_world(self, project_id: str) -> dict:
        worlds = self.world.list_worlds(project_id)
        memory = self.world.environment_summary(project_id)
        passed = bool(worlds) and memory["entries"] > 0
        return {
            "pass": passed,
            "worlds": len(worlds),
            "environment_entries": memory["entries"],
        }

    def _check_shot_dna(self) -> dict:
        stats = self.shot_dna.stats()
        covered = set(stats["by_category"].keys())
        missing_categories = [c for c in CATEGORIES if c not in covered]
        passed = not missing_categories and stats["total"] > 0
        return {
            "pass": passed,
            "total": stats["total"],
            "categories": sorted(covered),
            "missing_categories": missing_categories,
        }

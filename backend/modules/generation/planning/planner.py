
"""Integrated generation planner - orchestrates plan construction."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from backend.modules.generation.domain.plan import (
    GenerationPlan, PlanStatus, ReproducibilityContract,
    ReproducibilityLevel, SeedPlan,
)
from backend.modules.generation.planning.prompt_compiler import (
    PromptCompiler, PromptCompilationResult,
)
from backend.modules.generation.planning.seed_resolver import SeedConfig, SeedResolver
from backend.modules.generation.planning.conflict_resolver import ConflictResolver


@dataclass(slots=True)
class BuildPlanCommand:
    request_id: str
    project_id: str
    generation_type: str
    target_type: str
    target_id: str
    target_snapshot: dict
    character_snapshots: list[dict]
    scene_snapshot: dict | None = None
    shot_snapshot: dict | None = None
    continuity_snapshot: dict | None = None
    user_instruction: str | None = None
    style_fragments: tuple[str, ...] = ()
    quality_fragments: tuple[str, ...] = ()
    seed_config: SeedConfig | None = None
    candidate_count: int = 4


@dataclass(slots=True)
class PlanDto:
    plan_id: str
    request_id: str
    project_id: str
    plan_version: int
    generation_type: str
    target_type: str
    target_id: str
    positive_prompt: str
    negative_prompt: str
    logical_parameters: dict
    seed_plan: dict
    snapshot_hash: str
    status: str
    conflict_count: int
    created_at: str

    @classmethod
    def from_domain(cls, plan: GenerationPlan) -> "PlanDto":
        return cls(
            plan_id=plan.plan_id,
            request_id=plan.request_id,
            project_id=plan.project_id,
            plan_version=plan.plan_version,
            generation_type=plan.generation_type,
            target_type=plan.target_type,
            target_id=plan.target_id,
            positive_prompt=plan.positive_prompt,
            negative_prompt=plan.negative_prompt,
            logical_parameters=plan.logical_parameters,
            seed_plan={
                "strategy": plan.seed_plan.strategy,
                "baseSeed": plan.seed_plan.base_seed,
                "candidateSeeds": list(plan.seed_plan.candidate_seeds),
            },
            snapshot_hash=plan.snapshot_hash,
            status=str(plan.status),
            conflict_count=len(plan.prompt_conflicts),
            created_at=plan.created_at.isoformat() if plan.created_at else "",
        )


class GenerationPlanner:
    """Orchestrates the complete plan construction pipeline."""

    COMPILER_VERSION = "1.0.0"

    def __init__(self):
        self._prompt_compiler = PromptCompiler()
        self._seed_resolver = SeedResolver()
        self._conflict_resolver = ConflictResolver()

    def build_plan(self, cmd: BuildPlanCommand) -> GenerationPlan:
        plan_id = f"genplan_{uuid4().hex[:12]}"

        compiler = self._prompt_compiler
        from backend.modules.generation.planning.prompt_compiler import (
            CharacterSnapshot, SceneSnapshot,
        )

        char_snapshots = [
            CharacterSnapshot(
                character_id=cs["characterId"],
                character_version_id=cs.get("characterVersionId", ""),
                canonical_name=cs.get("canonicalName", ""),
                identity=cs.get("identity", {}),
                appearance=cs.get("appearance", {}),
                signature_traits=tuple(cs.get("signatureTraits", [])),
                negative_identity_traits=tuple(cs.get("negativeIdentityTraits", [])),
                snapshot_hash=cs.get("snapshotHash", ""),
            )
            for cs in cmd.character_snapshots
        ]

        scene_snap = None
        if cmd.scene_snapshot:
            scene_snap = SceneSnapshot(
                scene_id=cmd.scene_snapshot.get("sceneId", ""),
                location_name=cmd.scene_snapshot.get("locationName", ""),
                time_of_day=cmd.scene_snapshot.get("timeOfDay"),
                weather=cmd.scene_snapshot.get("weather"),
                season=cmd.scene_snapshot.get("season"),
                environment_description=cmd.scene_snapshot.get("environmentDescription", ""),
                spatial_anchors=tuple(cmd.scene_snapshot.get("spatialAnchors", [])),
                key_props=tuple(cmd.scene_snapshot.get("keyProps", [])),
                lighting_state=cmd.scene_snapshot.get("lightingState"),
                snapshot_hash=cmd.scene_snapshot.get("snapshotHash", ""),
            )

        compilation: PromptCompilationResult = compiler.compile(
            character_snapshots=char_snapshots,
            scene_snapshot=scene_snap,
            shot_snapshot=cmd.shot_snapshot,
            user_instruction=cmd.user_instruction,
            style_fragments=cmd.style_fragments,
            quality_fragments=cmd.quality_fragments,
        )

        # Conflict detection
        conflicts = self._conflict_resolver.detect_conflicts(
            character_sources=cmd.character_snapshots,
            user_overrides={"user_instruction": cmd.user_instruction} if cmd.user_instruction else {},
            shot_constraints=cmd.shot_snapshot or {},
        )

        # Seed resolution
        seed_config = cmd.seed_config or SeedConfig(candidate_count=cmd.candidate_count)
        seed_plan = self._seed_resolver.resolve(seed_config)

        # Parameters
        logical_params: dict = {
            "width": 1024,
            "height": 1024,
            "aspectRatio": "1:1",
            "candidateCount": cmd.candidate_count,
            "generationType": cmd.generation_type,
        }

        # Snapshot hash
        snapshot_hash = self._compute_plan_hash(
            target_snapshot=cmd.target_snapshot,
            character_snapshots=cmd.character_snapshots,
            scene_snapshot=cmd.scene_snapshot,
            positive_prompt=compilation.positive_prompt,
            negative_prompt=compilation.negative_prompt,
            seed_plan=seed_plan,
            logical_params=logical_params,
        )

        return GenerationPlan(
            plan_id=plan_id,
            request_id=cmd.request_id,
            project_id=cmd.project_id,
            plan_version=1,
            parent_plan_id=None,
            derivation_type=None,
            generation_type=cmd.generation_type,
            target_type=cmd.target_type,
            target_id=cmd.target_id,
            positive_prompt=compilation.positive_prompt,
            negative_prompt=compilation.negative_prompt,
            logical_parameters=logical_params,
            provider_overrides={},
            target_snapshot=cmd.target_snapshot,
            character_snapshots=tuple(cmd.character_snapshots),
            scene_snapshot=cmd.scene_snapshot,
            continuity_snapshot=cmd.continuity_snapshot,
            reference_assets=(),
            seed_plan=seed_plan,
            prompt_sources=tuple(compilation.provenance),
            prompt_conflicts=tuple(conflicts),
            prompt_provenance=tuple(compilation.provenance),
            routing_decision=None,
            reproducibility=ReproducibilityContract(
                level=ReproducibilityLevel.BEST_EFFORT,
                prompt_hash=compilation.prompt_hash,
                target_snapshot_hash=cmd.target_snapshot.get("snapshotHash", ""),
                character_snapshot_hashes=tuple(cs.get("snapshotHash", "") for cs in cmd.character_snapshots),
                continuity_hash=cmd.continuity_snapshot.get("continuityHash", "") if cmd.continuity_snapshot else None,
                workflow_hash=None,
                model_hashes=(),
                input_asset_hashes=(),
                seed_plan=seed_plan,
                compiler_version=self.COMPILER_VERSION,
                provider_adapter_version=None,
            ),
            snapshot_hash=snapshot_hash,
            status=PlanStatus.VALIDATED,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

    @staticmethod
    def diff_plans(old: GenerationPlan, new: GenerationPlan) -> dict:
        prompt_changes = []
        if old.positive_prompt != new.positive_prompt:
            prompt_changes.append({"type": "changed", "key": "positive_prompt",
                                    "from": old.positive_prompt, "to": new.positive_prompt})
        if old.negative_prompt != new.negative_prompt:
            prompt_changes.append({"type": "changed", "key": "negative_prompt",
                                    "from": old.negative_prompt, "to": new.negative_prompt})

        seed_changes = []
        if old.seed_plan.base_seed != new.seed_plan.base_seed:
            seed_changes.append({"from": old.seed_plan.base_seed, "to": new.seed_plan.base_seed})

        return {
            "oldPlanId": old.plan_id,
            "newPlanId": new.plan_id,
            "promptChanges": prompt_changes,
            "characterChanges": [],
            "sceneChanges": [],
            "referenceChanges": [],
            "parameterChanges": [],
            "routingChanges": [],
            "seedChanges": seed_changes,
        }

    @staticmethod
    def _compute_plan_hash(
        target_snapshot: dict,
        character_snapshots: list[dict],
        scene_snapshot: dict | None,
        positive_prompt: str,
        negative_prompt: str,
        seed_plan: SeedPlan,
        logical_params: dict,
    ) -> str:
        payload = {
            "target": target_snapshot,
            "characters": [cs.get("snapshotHash") for cs in character_snapshots],
            "scene": scene_snapshot.get("snapshotHash") if scene_snapshot else None,
            "positive": positive_prompt,
            "negative": negative_prompt,
            "seedBase": seed_plan.base_seed,
            "seedStrategy": seed_plan.strategy,
            "params": logical_params,
            "compiler": "1.0.0",
        }
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()[:20]

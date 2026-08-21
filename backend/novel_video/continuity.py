"""Compile approved H3 reference inputs for a planned shot."""

from collections.abc import Iterable, Mapping
from typing import Any

from backend.novel_video.h3_frames import derive_shot_seed, legal_h3_frames
from backend.novel_video.models import AssetVersion, H3ReferencePackage, ShotRecord, ShotStatus


class ContinuityError(ValueError):
    """Raised when a requested continuity link has no approved source."""


class ContinuityCompiler:
    """Build H3 packages while retaining only approved visual references.

    Callers must provide the AssetVersion records available to a run. Unknown
    IDs cannot become H3 references because approval is checked here.
    """

    def __init__(
        self,
        asset_versions: Iterable[AssetVersion] | Mapping[str, AssetVersion],
    ) -> None:
        if isinstance(asset_versions, Mapping):
            self._assets_by_id = dict(asset_versions)
        else:
            self._assets_by_id = {asset.id: asset for asset in asset_versions}

    def compile(
        self,
        current: ShotRecord,
        previous: ShotRecord | None,
        continuity: str,
    ) -> H3ReferencePackage:
        """Compile a deterministic H3 reference package for ``current``."""
        plan = current.plan
        character_refs = self._approved_plan_references(
            plan, "character_reference_asset_version_ids"
        )
        scene_refs = self._approved_plan_references(
            plan, "scene_reference_asset_version_ids"
        )
        if not scene_refs:
            scene_refs = self._scene_bible_refs(plan)
        tail_id = self._tail_for(continuity, current, previous)
        picture_ids = self._deduplicate([tail_id, *character_refs, *scene_refs])[:3]
        prompt_text = str(plan["prompt"])
        if continuity == "same_action":
            prompt_text = (
                "从 <Picture 1> 的最后状态无缝续接：继承人物、姿势、环境、光线和机位；"
                "继续当前动作，不要重演 <Picture 1> 中已完成的动作。\n"
                f"{prompt_text}"
            )
        elif continuity == "same_character_new_scene" and tail_id:
            prompt_text = (
                "以 <Picture 1> 为人物与服装连续性锚点进入新场景；继承角色身份，"
                "从新的场景状态继续，不要重演 <Picture 1> 中已完成的动作。\n"
                f"{prompt_text}"
            )

        locked_seed = plan.get("locked_seed")
        effective_seed = (
            int(locked_seed)
            if locked_seed is not None
            else derive_shot_seed(int(plan["base_seed"]), current.sequence)
        )
        duration_seconds = float(plan["duration_seconds"])

        return H3ReferencePackage(
            shot_id=current.id,
            prompt_version=str(plan.get("prompt_version", plan["workflow_version"])),
            prompt_text=prompt_text,
            negative_prompt=str(plan["negative_prompt"]),
            base_seed=int(plan["base_seed"]),
            effective_seed=effective_seed,
            duration_seconds=duration_seconds,
            legal_frame_count=legal_h3_frames(duration_seconds),
            width=int(plan["width"]),
            height=int(plan["height"]),
            aspect_ratio=plan["aspect_ratio"],
            megapixel_profile=float(plan["megapixel_profile"]),
            multiple=int(plan["multiple"]),
            picture_asset_version_ids=picture_ids,
            video_reference_asset_version_ids=self._approved_plan_references(
                plan, "video_reference_asset_version_ids"
            ),
            audio_reference_asset_version_ids=self._approved_plan_references(
                plan, "audio_reference_asset_version_ids"
            ),
            workflow_version=str(plan["workflow_version"]),
            model_registry_ids=dict(plan["model_registry_ids"]),
            continuity_reason=continuity,
        )

    def _tail_for(
        self,
        continuity: str,
        current: ShotRecord,
        previous: ShotRecord | None,
    ) -> str | None:
        if continuity == "same_action":
            if previous is None or previous.status is not ShotStatus.APPROVED:
                raise ContinuityError("same_action requires an approved previous shot")
            tail_id = previous.approved_tail_asset_id
            if not tail_id or not self._is_approved(tail_id):
                raise ContinuityError("same_action requires an approved tail asset")
            return tail_id
        if continuity == "same_character_new_scene":
            if not current.plan.get("inherit_tail"):
                return None
            if previous is None or previous.status is not ShotStatus.APPROVED:
                raise ContinuityError(
                    "inherited new scene requires an approved tail asset"
                )
            tail_id = previous.approved_tail_asset_id
            if tail_id and self._is_approved(tail_id):
                return tail_id
            raise ContinuityError(
                "inherited new scene requires an approved tail asset"
            )
        if continuity in {"time_jump", "location_jump"}:
            return None
        raise ContinuityError(f"unsupported continuity mode: {continuity}")

    def _approved_plan_references(self, plan: Mapping[str, Any], key: str) -> list[str]:
        return [reference_id for reference_id in self._id_list(plan[key]) if self._is_approved(reference_id)]

    def _scene_bible_refs(self, plan: Mapping[str, Any]) -> list[str]:
        """Fall back to approved scene-bible images for the shot's scene.

        Bible assets are generated before the run and carry their scene id in
        metadata, so a compiled shot always has an authoritative reference
        even when the plan version predates bible generation.
        """
        scene_id = plan.get("scene_id")
        if not scene_id:
            return []
        matches = [
            asset.id
            for asset in self._assets_by_id.values()
            if asset.kind == "scene"
            and asset.state == "approved"
            and asset.metadata.get("scene_id") == scene_id
        ]
        return matches[:1]

    def _is_approved(self, asset_id: str) -> bool:
        asset = self._assets_by_id.get(asset_id)
        return asset is not None and asset.state == "approved"

    @staticmethod
    def _id_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return [str(item) for item in value]

    @staticmethod
    def _deduplicate(reference_ids: Iterable[str | None]) -> list[str]:
        result: list[str] = []
        for reference_id in reference_ids:
            if reference_id and reference_id not in result:
                result.append(reference_id)
        return result

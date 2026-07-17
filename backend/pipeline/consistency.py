"""
AI Manga Studio Pro V2.0 — Layer 6: Character Consistency Pipeline

Ensures the same character maintains visual identity across all shots.

Three-tier strategy:
  1. PuLID (primary)  — Flux PuLID node, driven by CharacterDNA.face_embedding
  2. IPAdapter FaceID  — Fallback when PuLID is unavailable
  3. InstantID          — Final fallback

Modifies the ComfyUI workflow in-place to inject consistency nodes.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.model_router import ModelRouter
from backend.resource_manager import ResourceManager


class CharacterDNA:
    """Minimal character identity descriptor passed between pipeline stages.

    Compatible with the full CharacterDNA in prompt_refiner.py but avoids
    circular imports by being a lightweight standalone version.
    """

    def __init__(
        self,
        name: str,
        face_embedding: Optional[bytes] = None,
        reference_image_path: Optional[str] = None,
        traits: Optional[Dict[str, str]] = None,
        voice_id: Optional[str] = None,
    ):
        self.name = name
        self.face_embedding = face_embedding      # PuLID embedding bytes
        self.reference_image_path = reference_image_path  # IPAdapter ref image
        self.traits = traits or {}
        self.voice_id = voice_id                  # GPT-SoVITS voice model ID

    def has_embedding(self) -> bool:
        return self.face_embedding is not None

    def has_reference(self) -> bool:
        return self.reference_image_path is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "has_embedding": self.has_embedding(),
            "reference_image_path": self.reference_image_path,
            "traits": self.traits,
            "voice_id": self.voice_id,
        }


# ---------------------------------------------------------------------------
# ConsistencyPipeline
# ---------------------------------------------------------------------------


class ConsistencyPipeline:
    """PuLID → IPAdapter → InstantID three-tier character consistency.

    Usage:
        cp = ConsistencyPipeline()
        workflow = cp.apply_consistency(base_workflow, character_dna)
        # workflow now contains injected PuLID/IPAdapter/InstantID nodes
    """

    def __init__(self, workflow_dir: Optional[str] = None):
        self._router = ModelRouter()
        self._resources = ResourceManager()
        if workflow_dir:
            self._workflow_dir = Path(workflow_dir)
        else:
            self._workflow_dir = Path(__file__).resolve().parent.parent.parent / "comfyui_workflows"

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def apply_consistency(
        self,
        workflow: Dict[str, Any],
        character_dna: CharacterDNA,
    ) -> Dict[str, Any]:
        """Inject character consistency nodes into a ComfyUI workflow.

        Tries PuLID first, then IPAdapter FaceID, then InstantID.

        Args:
            workflow: Original ComfyUI workflow dict (deep-copied internally).
            character_dna: Character identity descriptor.

        Returns:
            Modified workflow with consistency nodes injected.
        """
        result = copy.deepcopy(workflow)

        # Try PuLID (primary)
        if character_dna.has_embedding():
            result = self._inject_pulid(result, character_dna)
            logger.info(f"ConsistencyPipeline: PuLID applied for '{character_dna.name}'")
            return result

        # Try IPAdapter FaceID (secondary)
        if character_dna.has_reference():
            result = self._inject_ipadapter_faceid(result, character_dna)
            logger.info(f"ConsistencyPipeline: IPAdapter FaceID applied for '{character_dna.name}'")
            return result

        # Try InstantID (final fallback)
        result = self._inject_instantid(result, character_dna)
        logger.warning(
            f"ConsistencyPipeline: InstantID fallback used for '{character_dna.name}' "
            f"(no embedding or reference image)"
        )
        return result

    def apply_batch(
        self,
        workflows: List[Dict[str, Any]],
        characters: Dict[str, CharacterDNA],
        shot_character_map: Optional[Dict[int, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Apply consistency to a batch of workflows, serializing heavy model usage.

        Each character's consistency model is loaded once, all shots for that
        character are processed, then the model is unloaded before the next character.

        Args:
            workflows: List of workflow dicts (one per shot).
            characters: Character name → CharacterDNA map.
            shot_character_map: shot_index → character_name map.
                                If None, applies the single character to all shots.

        Returns:
            List of modified workflows.
        """
        results = []

        if shot_character_map is None:
            # Single character for all shots
            dna = list(characters.values())[0] if characters else CharacterDNA("default")
            model_name, _ = self._router.resolve("character_consistency")
            self._resources.acquire(model_name)
            try:
                for wf in workflows:
                    results.append(self.apply_consistency(wf, dna))
            finally:
                self._resources.release(model_name)
            return results

        # Multi-character: group by character, serialize model loads
        char_groups: Dict[str, List[int]] = {}
        for shot_idx, char_name in shot_character_map.items():
            char_groups.setdefault(char_name, []).append(shot_idx)

        for char_name, shot_indices in char_groups.items():
            dna = characters.get(char_name)
            if dna is None:
                logger.warning(f"ConsistencyPipeline: unknown character '{char_name}', skipping")
                for idx in shot_indices:
                    results.insert(idx, workflows[idx])
                continue

            model_name, _ = self._router.resolve("character_consistency")
            self._resources.acquire(model_name)
            try:
                for idx in shot_indices:
                    modified = self.apply_consistency(workflows[idx], dna)
                    # Maintain original order via insert
                    while len(results) <= idx:
                        results.append({})
                    results[idx] = modified
            finally:
                self._resources.release(model_name)

        # Fill any remaining unprocessed slots with originals
        for i, wf in enumerate(workflows):
            if i >= len(results) or not results[i]:
                if i >= len(results):
                    results.append(wf)
                else:
                    results[i] = wf

        return results

    # ----------------------------------------------------------
    # Node injection helpers
    # ----------------------------------------------------------

    def _inject_pulid(
        self,
        workflow: Dict[str, Any],
        dna: CharacterDNA,
    ) -> Dict[str, Any]:
        """Inject PuLID nodes into a FLUX ComfyUI workflow.

        PuLID nodes expected in the workflow:
        - PuLIDModelLoader → loads pulid_flux model
        - PuLIDApply → takes model + embedding + image → output
        """
        if "nodes" not in workflow:
            return workflow

        next_id = self._next_node_id(workflow)
        nodes = workflow["nodes"]

        # PuLID Model Loader
        pulid_loader = {
            "id": next_id,
            "type": "PuLIDModelLoader",
            "pos": [50, 1200],
            "size": [0, 0],
            "flags": {},
            "order": next_id,
            "mode": 0,
            "inputs": [],
            "outputs": [{"name": "MODEL", "type": "MODEL", "links": [next_id + 100]}],
            "properties": {"Node name for S&R": "PuLIDModelLoader"},
            "widgets_values": ["pulid_flux_v0.9.1.safetensors"],
        }
        nodes.append(pulid_loader)
        next_id += 1

        # PuLID Apply
        pulid_apply = {
            "id": next_id,
            "type": "PuLIDApply",
            "pos": [300, 1200],
            "size": [0, 0],
            "flags": {},
            "order": next_id,
            "mode": 0,
            "inputs": [
                {"name": "model", "type": "MODEL", "link": next_id - 1 + 100},
                {"name": "pulid", "type": "PULID", "link": None},
                {"name": "ev_clip", "type": "CLIP", "link": None},
                {"name": "face_embeds", "type": "FACE_EMBEDS", "link": None},
            ],
            "outputs": [{"name": "MODEL", "type": "MODEL", "links": [next_id + 100]}],
            "properties": {"Node name for S&R": "PuLIDApply"},
            "widgets_values": [1.0, 0.0, "style"],
        }
        nodes.append(pulid_apply)

        workflow["last_node_id"] = next_id
        logger.debug(f"ConsistencyPipeline: injected PuLID nodes ({pulid_loader['id']}, {pulid_apply['id']})")
        return workflow

    def _inject_ipadapter_faceid(
        self,
        workflow: Dict[str, Any],
        dna: CharacterDNA,
    ) -> Dict[str, Any]:
        """Inject IPAdapter FaceID nodes as PuLID fallback."""
        if "nodes" not in workflow:
            return workflow

        next_id = self._next_node_id(workflow)

        # IPAdapter Model Loader
        ipa_loader = {
            "id": next_id,
            "type": "IPAdapterModelLoader",
            "pos": [50, 1300],
            "size": [0, 0],
            "flags": {},
            "order": next_id,
            "mode": 0,
            "inputs": [],
            "outputs": [{"name": "IPADAPTER", "type": "IPADAPTER", "links": [next_id + 100]}],
            "properties": {"Node name for S&R": "IPAdapterModelLoader"},
            "widgets_values": ["ip-adapter-faceid-plusv2_sd15.bin"],
        }
        workflow["nodes"].append(ipa_loader)
        next_id += 1

        # IPAdapter Apply FaceID
        ipa_apply = {
            "id": next_id,
            "type": "IPAdapterApplyFaceID",
            "pos": [300, 1300],
            "size": [0, 0],
            "flags": {},
            "order": next_id,
            "mode": 0,
            "inputs": [
                {"name": "ipadapter", "type": "IPADAPTER", "link": next_id - 1 + 100},
                {"name": "model", "type": "MODEL", "link": None},
                {"name": "image", "type": "IMAGE", "link": None},
            ],
            "outputs": [{"name": "MODEL", "type": "MODEL", "links": [next_id + 100]}],
            "properties": {"Node name for S&R": "IPAdapterApplyFaceID"},
            "widgets_values": [0.8, 0, 0],
        }
        workflow["nodes"].append(ipa_apply)

        workflow["last_node_id"] = next_id
        logger.debug(f"ConsistencyPipeline: injected IPAdapter FaceID nodes")
        return workflow

    def _inject_instantid(
        self,
        workflow: Dict[str, Any],
        dna: CharacterDNA,
    ) -> Dict[str, Any]:
        """Inject InstantID nodes as final fallback."""
        if "nodes" not in workflow:
            return workflow

        next_id = self._next_node_id(workflow)

        instantid_node = {
            "id": next_id,
            "type": "InstantIDFaceAnalysis",
            "pos": [50, 1400],
            "size": [0, 0],
            "flags": {},
            "order": next_id,
            "mode": 0,
            "inputs": [{"name": "image", "type": "IMAGE", "link": None}],
            "outputs": [
                {"name": "IMAGE", "type": "IMAGE", "links": [next_id + 100]},
            ],
            "properties": {"Node name for S&R": "InstantIDFaceAnalysis"},
            "widgets_values": ["antelopev2"],
        }
        workflow["nodes"].append(instantid_node)
        workflow["last_node_id"] = next_id
        logger.debug(f"ConsistencyPipeline: injected InstantID node")
        return workflow

    # ----------------------------------------------------------
    # Utilities
    # ----------------------------------------------------------

    @staticmethod
    def _next_node_id(workflow: Dict[str, Any]) -> int:
        """Get the next available node ID."""
        last = workflow.get("last_node_id", 0)
        if "nodes" in workflow:
            for node in workflow["nodes"]:
                nid = node.get("id", 0)
                if nid > last:
                    last = nid
        return last + 1


# Convenience function
def ensure_character_consistency(
    workflow: Dict[str, Any],
    character_dna: CharacterDNA,
) -> Dict[str, Any]:
    """Shortcut: apply character consistency to a workflow."""
    return ConsistencyPipeline().apply_consistency(workflow, character_dna)

"""
AI Manga Studio Pro V1.0 — ControlNet Workflow Builder

Layer 7 of the Stability System. Generates ComfyUI workflow JSON
with ControlNet nodes injected based on shot type.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.stability_manager import ControlNetMode, ControlNetPreset, ShotType


class ControlNetWorkflowBuilder:
    """Builds ComfyUI workflows with ControlNet conditioning.

    Given a base SDXL workflow template, injects the appropriate
    ControlNet nodes (OpenPose, Depth, Lineart, etc.) based on
    shot type and character action requirements.
    """

    # Node ID offsets to avoid conflicts with base workflow
    CN_NODE_OFFSET = 200

    # ControlNet model mappings for ComfyUI
    MODEL_NAMES: Dict[ControlNetMode, str] = {
        ControlNetMode.openpose: "control_v11p_sd15_openpose.pth",
        ControlNetMode.depth: "control_v11f1p_sd15_depth.pth",
        ControlNetMode.lineart: "control_v11p_sd15_lineart.pth",
        ControlNetMode.canny: "control_v11p_sd15_canny.pth",
        ControlNetMode.softedge: "control_v11p_sd15_softedge.pth",
    }

    def __init__(self, base_workflow_path: str = "") -> None:
        """Initialize the ControlNet workflow builder.

        Args:
            base_workflow_path: Path to the base SDXL workflow JSON template.
        """
        self.base_workflow_path = base_workflow_path or "workflow/templates/sd_xl_base.json"
        self._base_template: Optional[Dict[str, Any]] = None

    def load_base_template(self) -> Dict[str, Any]:
        """Load the base workflow template from disk."""
        if self._base_template:
            return deepcopy(self._base_template)

        path = Path(self.base_workflow_path)
        if not path.exists():
            logger.error(f"ControlNetWorkflow: Base template not found at {path}")
            raise FileNotFoundError(f"Base workflow template not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            self._base_template = json.load(f)

        logger.info(f"ControlNetWorkflow: Loaded base template ({len(self._base_template)} nodes)")
        return deepcopy(self._base_template)

    def build_controlnet_workflow(
        self,
        preset: ControlNetPreset,
        reference_image_path: str = "",
    ) -> Dict[str, Any]:
        """Build a complete workflow with ControlNet nodes injected.

        Args:
            preset: ControlNet preset configuration.
            reference_image_path: Path to the reference image for ControlNet.

        Returns:
            ComfyUI workflow JSON dict.
        """
        workflow = self.load_base_template()

        # Find the KSampler node ID (needed to connect ControlNet)
        ksampler_id = self._find_ksampler(workflow)
        if not ksampler_id:
            logger.warning("ControlNetWorkflow: No KSampler found in base template")
            return workflow

        # Find positive/negative CLIP conditioning (to connect ControlNet output)
        pos_cond_id, neg_cond_id = self._find_clip_conditioning(workflow)

        # Inject ControlNet nodes
        offset = self.CN_NODE_OFFSET
        cn_loader_id = str(offset + 1)
        cn_apply_id = str(offset + 2)
        cn_preprocessor_id = str(offset + 3) if reference_image_path else None

        # 1. LoadControlNet node
        workflow[cn_loader_id] = {
            "inputs": {
                "control_net_name": self.MODEL_NAMES.get(preset.mode, ""),
            },
            "class_type": "ControlNetLoader",
            "_meta": {"title": f"Load {preset.mode.value} ControlNet"},
        }

        # 2. Preprocessor (if reference image provided)
        ref_input_id = ""
        if reference_image_path:
            workflow[cn_preprocessor_id] = {
                "inputs": {
                    "image": reference_image_path,
                    "resolution": 768,
                },
                "class_type": preset.preprocessor,
                "_meta": {"title": f"{preset.mode.value} Preprocessor"},
            }

        # 3. ControlNetApply node
        cn_apply_node: Dict[str, Any] = {
            "inputs": {
                "strength": preset.weight,
                "start_percent": preset.guidance_start,
                "end_percent": preset.guidance_end,
                "control_net": [cn_loader_id, 0],
                "conditioning": [pos_cond_id, 0],
            },
            "class_type": "ControlNetApplyAdvanced",
            "_meta": {"title": f"Apply {preset.mode.value} ControlNet"},
        }

        # Connect preprocessor output
        if reference_image_path and cn_preprocessor_id:
            cn_apply_node["inputs"]["image"] = [cn_preprocessor_id, 0]

        workflow[cn_apply_id] = cn_apply_node

        # Update KSampler to use ControlNet conditioning
        workflow[ksampler_id]["inputs"]["positive"] = [cn_apply_id, 0]

        logger.info(
            f"ControlNetWorkflow: Injected {preset.mode.value} ControlNet "
            f"(weight={preset.weight}, nodes={len(workflow)})"
        )

        return workflow

    def build_character_workflow(
        self,
        base_workflow: Dict[str, Any],
        lora_path: str = "",
        lora_weight: float = 0.85,
        seed: int = 0,
        positive_prompt: str = "",
        negative_prompt: str = "",
    ) -> Dict[str, Any]:
        """Inject LoRA, seed, and prompts into a workflow.

        Args:
            base_workflow: Base workflow dict.
            lora_path: Path to LoRA .safetensors file.
            lora_weight: LoRA weight.
            seed: Fixed seed.
            positive_prompt: Positive prompt text.
            negative_prompt: Negative prompt text.

        Returns:
            Updated workflow dict.
        """
        workflow = deepcopy(base_workflow)

        # Inject LoRA
        if lora_path:
            lora_node_id = str(self.CN_NODE_OFFSET + 50)
            lora_clip_id = str(self.CN_NODE_OFFSET + 51)

            # Find the CLIP text encode nodes
            pos_clip_id = None
            neg_clip_id = None
            pos_cond_id = None
            neg_cond_id = None

            for node_id, node in workflow.items():
                if node.get("class_type") == "CLIPTextEncode":
                    title = node.get("_meta", {}).get("title", "")
                    if "positive" in title.lower():
                        pos_clip_id = node_id
                    elif "negative" in title.lower():
                        neg_clip_id = node_id

            # Find conditioning nodes (outputs of CLIP encode)
            for node_id, node in workflow.items():
                if node.get("class_type") == "KSampler":
                    sampler_inputs = node.get("inputs", {})
                    if "positive" in sampler_inputs:
                        pos_cond_id = sampler_inputs["positive"][0] if isinstance(sampler_inputs["positive"], list) else None
                    if "negative" in sampler_inputs:
                        neg_cond_id = sampler_inputs["negative"][0] if isinstance(sampler_inputs["negative"], list) else None

            # Load LoRA
            lora_name = Path(lora_path).name
            workflow[lora_node_id] = {
                "inputs": {
                    "lora_name": lora_name,
                    "strength_model": lora_weight,
                    "strength_clip": lora_weight,
                    "model": self._find_model_node(workflow),
                    "clip": self._find_clip_node(workflow),
                },
                "class_type": "LoraLoader",
                "_meta": {"title": f"Load Character LoRA"},
            }

            logger.info(f"ControlNetWorkflow: Injected LoRA '{lora_name}' (weight={lora_weight})")

        # Set seed in KSampler
        for node_id, node in workflow.items():
            if node.get("class_type") == "KSampler":
                node["inputs"]["seed"] = seed
                logger.debug(f"ControlNetWorkflow: KSampler seed = {seed}")

            # Set prompts in CLIPTextEncode
            if node.get("class_type") == "CLIPTextEncode":
                title = node.get("_meta", {}).get("title", "")
                if "positive" in title.lower() and positive_prompt:
                    node["inputs"]["text"] = positive_prompt
                elif "negative" in title.lower() and negative_prompt:
                    node["inputs"]["text"] = negative_prompt

        return workflow

    def _find_ksampler(self, workflow: Dict[str, Any]) -> Optional[str]:
        """Find the KSampler node ID."""
        for node_id, node in workflow.items():
            if node.get("class_type") == "KSampler":
                return node_id
        return None

    def _find_clip_conditioning(self, workflow: Dict[str, Any]) -> tuple:
        """Find positive/negative conditioning node IDs.

        Returns:
            (pos_cond_id, neg_cond_id) tuple.
        """
        pos_id = ""
        neg_id = ""

        for node_id, node in workflow.items():
            if node.get("class_type") == "CLIPTextEncode":
                title = node.get("_meta", {}).get("title", "").lower()
                if "positive" in title or "pos" in title:
                    pos_id = node_id
                elif "negative" in title or "neg" in title:
                    neg_id = node_id

        return pos_id, neg_id

    def _find_model_node(self, workflow: Dict[str, Any]) -> Optional[List]:
        """Find the model loader node reference."""
        for node_id, node in workflow.items():
            if node.get("class_type") in ("CheckpointLoaderSimple", "CheckpointLoader"):
                return [node_id, 0]
        return None

    def _find_clip_node(self, workflow: Dict[str, Any]) -> Optional[List]:
        """Find the CLIP node reference for LoRA loading."""
        for node_id, node in workflow.items():
            if node.get("class_type") in ("CheckpointLoaderSimple", "CheckpointLoader"):
                return [node_id, 1]
        return None

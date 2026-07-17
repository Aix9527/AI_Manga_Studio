"""
AI Manga Studio Pro V1.0 — Workflow Runner

Loads, validates, and executes ComfyUI JSON workflows. Acts as the
bridge between the backend pipeline logic and the ComfyUI API.

Each workflow JSON in the ../workflow/ directory corresponds to a
stage in the manga generation pipeline:

  001_parse_novel      → Novel text → structured JSON
  002_character        → Character prompt → character image
  003_character_face   → Character face close-up → FaceID reference
  004_scene            → Scene prompt → background layout
  005_background       → Scene background generation
  006_compose          → Char + BG → composed final image
  007_upscale          → Image upscaling (4x / 8x)
  008_i2v              → Image → animated video
  009_lipsync          → WAV + Image → lip-synced video
  010_voice            → Text → TTS voice audio
  011_subtitle         → Text → styled subtitles on video
  012_bgm              → Add background music
  013_merge            → Merge all tracks into final video
  014_quality          → Quality inspection pass
  015_export           → Export to final format
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.comfyui_client import ComfyUIClient


# ============================================================
# Workflow Runner
# ============================================================

class WorkflowRunner:
    """Loads and executes ComfyUI workflow JSON files.

    Each workflow is a JSON file describing a ComfyUI node graph.
    The runner loads the JSON, substitutes dynamic parameters
    (seed, prompt, image paths, etc.), and submits the workflow
    to ComfyUI via the API client.
    """

    # Workflow name → file mapping
    WORKFLOW_FILES: Dict[str, str] = {
        "parse_novel": "001_parse_novel.json",
        "character": "002_character.json",
        "character_face": "003_character_face.json",
        "scene": "004_scene.json",
        "background": "005_background.json",
        "compose": "006_compose.json",
        "upscale": "007_upscale.json",
        "i2v": "008_i2v.json",
        "lipsync": "009_lipsync.json",
        "voice": "010_voice.json",
        "subtitle": "011_subtitle.json",
        "bgm": "012_bgm.json",
        "merge": "013_merge.json",
        "quality": "014_quality.json",
        "export": "015_export.json",
    }

    # Parameter keys that can be injected into workflows
    PARAM_KEYS: Dict[str, List[str]] = {
        "character": ["seed", "prompt_positive", "prompt_negative", "output_path"],
        "compose": ["seed", "prompt_positive", "prompt_negative", "character_image", "background_image", "output_path"],
        "upscale": ["input_image", "output_path", "scale_factor"],
        "i2v": ["input_image", "output_path", "motion_scale", "num_frames", "fps"],
        "lipsync": ["input_image", "audio_path", "output_path"],
        "voice": ["text", "voice_id", "output_path"],
        "subtitle": ["text", "video_path", "output_path"],
        "bgm": ["video_path", "audio_path", "output_path"],
        "merge": ["video_paths", "output_path"],
    }

    def __init__(
        self,
        workflow_dir: str = "",
        client: Optional[ComfyUIClient] = None,
        comfyui_url: str = "",
    ) -> None:
        """Initialize the Workflow Runner.

        Args:
            workflow_dir: Directory containing workflow JSON files.
            client: ComfyUIClient instance.
            comfyui_url: ComfyUI API base URL.
        """
        # Determine workflow directory
        if workflow_dir:
            self.workflow_dir = Path(workflow_dir)
        else:
            # Default: sibling workflow/ directory
            self.workflow_dir = Path(__file__).parent.parent / "workflow"

        self.client = client or ComfyUIClient(base_url=comfyui_url)
        self.workflow_cache: Dict[str, Dict] = {}

        logger.info(f"WorkflowRunner: Initialized (dir={self.workflow_dir})")

    # ----------------------------------------------------------
    # Public API — Per-Stage Runners
    # ----------------------------------------------------------

    def run_character(
        self,
        prompt_positive: str,
        prompt_negative: str,
        seed: int = -1,
        output_path: str = "",
    ) -> str:
        """Run character generation workflow.

        Args:
            prompt_positive: Positive prompt.
            prompt_negative: Negative prompt.
            seed: Random seed (-1 for random).
            output_path: Output path for generated image.

        Returns:
            Path to generated image.
        """
        params = {
            "seed": seed if seed >= 0 else int(time.time() * 1000) % (2**32),
            "prompt_positive": prompt_positive,
            "prompt_negative": prompt_negative,
            "output_path": output_path,
        }
        return self._run_workflow("character", params, output_path)

    def run_compose(
        self,
        prompt_positive: str,
        prompt_negative: str,
        shot_index: int = 0,
        chapter_index: int = 0,
        output_dir: str = "",
    ) -> str:
        """Run image composition workflow.

        Args:
            prompt_positive: Positive prompt.
            prompt_negative: Negative prompt.
            shot_index: Shot index.
            chapter_index: Chapter index.
            output_dir: Output directory.

        Returns:
            Path to composed image.
        """
        output_path = os.path.join(
            output_dir, f"compose_ch{chapter_index:03d}_shot{shot_index:04d}.png"
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        params = {
            "seed": int(time.time() * 1000) % (2**32),
            "prompt_positive": prompt_positive,
            "prompt_negative": prompt_negative,
            "output_path": output_path,
        }
        return self._run_workflow("compose", params, output_path)

    def run_i2v(
        self,
        image_path: str,
        shot_index: int = 0,
        chapter_index: int = 0,
        output_dir: str = "",
        motion_scale: float = 1.0,
        num_frames: int = 24,
        fps: int = 8,
    ) -> str:
        """Run image-to-video workflow.

        Args:
            image_path: Input image path.
            shot_index: Shot index.
            chapter_index: Chapter index.
            output_dir: Output directory.
            motion_scale: Motion intensity.
            num_frames: Number of frames to generate.
            fps: Frames per second.

        Returns:
            Path to generated video.
        """
        output_path = os.path.join(
            output_dir, f"video_ch{chapter_index:03d}_shot{shot_index:04d}.mp4"
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        params = {
            "input_image": image_path,
            "output_path": output_path,
            "motion_scale": motion_scale,
            "num_frames": num_frames,
            "fps": fps,
        }
        return self._run_workflow("i2v", params, output_path)

    def run_upscale(
        self,
        input_image: str,
        output_path: str = "",
        scale_factor: int = 4,
    ) -> str:
        """Run image upscaling workflow.

        Args:
            input_image: Input image path.
            output_path: Output image path.
            scale_factor: Upscaling factor (2, 4, 8).

        Returns:
            Path to upscaled image.
        """
        params = {
            "input_image": input_image,
            "output_path": output_path,
            "scale_factor": scale_factor,
        }
        return self._run_workflow("upscale", params, output_path)

    def run_voice(
        self,
        text: str,
        voice_id: str = "default",
        output_path: str = "",
    ) -> str:
        """Run TTS voice generation workflow.

        Args:
            text: Text to synthesize.
            voice_id: Voice ID.
            output_path: Output WAV path.

        Returns:
            Path to generated WAV.
        """
        params = {
            "text": text,
            "voice_id": voice_id,
            "output_path": output_path,
        }
        return self._run_workflow("voice", params, output_path)

    # ----------------------------------------------------------
    # Generic Workflow Runner
    # ----------------------------------------------------------

    def _run_workflow(
        self,
        workflow_name: str,
        params: Dict[str, Any],
        output_path: str,
    ) -> str:
        """Load, parameterize, and execute a workflow.

        Args:
            workflow_name: Name of the workflow stage.
            params: Parameter overrides.
            output_path: Expected output path.

        Returns:
            Output path (may be placeholder if ComfyUI unavailable).
        """
        # Load workflow JSON
        workflow = self.load_workflow(workflow_name)

        if not workflow:
            logger.warning(
                f"WorkflowRunner: Workflow '{workflow_name}' not found, "
                f"returning output placeholder"
            )
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            return output_path

        # Inject parameters
        workflow = self.inject_params(workflow, params)

        # Submit to ComfyUI
        try:
            result = self.client.submit_workflow(workflow, wait=True)
            if result and "output" in result:
                return result["output"]
        except Exception as e:
            logger.error(f"WorkflowRunner: ComfyUI submission failed: {e}")

        return output_path

    # ----------------------------------------------------------
    # Workflow Loading
    # ----------------------------------------------------------

    def load_workflow(self, workflow_name: str) -> Optional[Dict]:
        """Load a workflow JSON from disk.

        Args:
            workflow_name: Stage name (e.g., 'compose', 'i2v') or filename.

        Returns:
            Parsed workflow dict or None.
        """
        # Check cache
        if workflow_name in self.workflow_cache:
            return dict(self.workflow_cache[workflow_name])

        # Resolve filename
        filename = self.WORKFLOW_FILES.get(workflow_name, workflow_name)
        if not filename.endswith(".json"):
            filename += ".json"

        file_path = self.workflow_dir / filename

        if not file_path.exists():
            logger.warning(f"WorkflowRunner: File not found → {file_path}")
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                workflow = json.load(f)

            self.workflow_cache[workflow_name] = workflow
            logger.info(f"WorkflowRunner: Loaded '{workflow_name}' ({len(workflow.get('nodes', []))} nodes)")

            return dict(workflow)
        except Exception as e:
            logger.error(f"WorkflowRunner: Failed to load {file_path}: {e}")
            return None

    def load_all_workflows(self) -> Dict[str, Dict]:
        """Load all available workflows.

        Returns:
            Dict of workflow_name → workflow_dict.
        """
        workflows: Dict[str, Dict] = {}
        for name in self.WORKFLOW_FILES:
            wf = self.load_workflow(name)
            if wf:
                workflows[name] = wf
        return workflows

    # ----------------------------------------------------------
    # Parameter Injection
    # ----------------------------------------------------------

    def inject_params(
        self,
        workflow: Dict,
        params: Dict[str, Any],
    ) -> Dict:
        """Inject dynamic parameters into a workflow.

        Locates known parameter node types and replaces their
        widget values with the provided parameters.

        Args:
            workflow: Workflow dict.
            params: Parameter overrides.

        Returns:
            Modified workflow dict.
        """
        # Deep copy
        wf = json.loads(json.dumps(workflow))

        nodes = wf.get("nodes", [])

        for node in nodes:
            node_type = node.get("type", "")
            widgets = node.get("widgets_values", [])

            # Seed node
            if "seed" in params and "Seed" in node_type:
                if widgets:
                    widgets[0] = params["seed"]

            # Checkpoint / Model loader
            if "model" in params and "CheckpointLoader" in node_type:
                if widgets:
                    widgets[0] = params["model"]

            # CLIPTextEncode (Positive)
            if "prompt_positive" in params and "CLIPTextEncode" in node_type:
                title = node.get("title", "").lower()
                is_positive = "positive" in title or "pos" in title
                if is_positive and widgets:
                    widgets[0] = params["prompt_positive"]
                elif not title and widgets:
                    # First CLIPTextEncode is usually positive
                    pass  # Handle cautiously

            # CLIPTextEncode (Negative)
            if "prompt_negative" in params and "CLIPTextEncode" in node_type:
                title = node.get("title", "").lower()
                is_negative = "negative" in title or "neg" in title
                if is_negative and widgets:
                    widgets[0] = params["prompt_negative"]

            # LoadImage node
            if "input_image" in params and "LoadImage" in node_type:
                if widgets:
                    widgets[0] = os.path.basename(params["input_image"])

            # VHS (Video Helper Suite) / Save nodes
            if "output_path" in params and "Save" in node_type:
                if "filename_prefix" in [w for w in widgets if isinstance(w, str)]:
                    for i, w in enumerate(widgets):
                        if isinstance(w, str) and "filename" in w.lower():
                            widgets[i] = os.path.splitext(
                                os.path.basename(params["output_path"])
                            )[0]

        return wf

    # ----------------------------------------------------------
    # Validation
    # ----------------------------------------------------------

    def validate_workflow(self, workflow: Dict) -> List[str]:
        """Validate a workflow for common issues.

        Args:
            workflow: Workflow dict.

        Returns:
            List of validation error messages (empty = valid).
        """
        errors: List[str] = []

        if "nodes" not in workflow:
            errors.append("Missing 'nodes' key")
            return errors

        nodes = workflow.get("nodes", [])
        links = workflow.get("links", [])

        # Check for duplicate node IDs
        node_ids = [n.get("id") for n in nodes]
        if len(node_ids) != len(set(node_ids)):
            errors.append("Duplicate node IDs detected")

        # Check links reference valid nodes
        node_id_set = set(node_ids)
        for link in links:
            if isinstance(link, list) and len(link) >= 4:
                from_node = link[0]
                to_node = link[2]
                if from_node not in node_id_set:
                    errors.append(f"Link references unknown source node: {from_node}")
                if to_node not in node_id_set:
                    errors.append(f"Link references unknown target node: {to_node}")

        # Check for essential nodes
        required_node_types = {"CheckpointLoaderSimple", "CLIPTextEncode", "KSampler", "VAEDecode", "SaveImage"}
        present_types = {n.get("type", "") for n in nodes}

        for req in required_node_types:
            if not any(req in t for t in present_types):
                errors.append(f"Missing essential node type: {req}")

        return errors

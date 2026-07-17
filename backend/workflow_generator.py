"""
AI Manga Studio Pro V1.0 鈥?ComfyUI Workflow Generator

Reads a UnifiedShot JSON and produces a complete ComfyUI API-format workflow.
This is the bridge between the unified schema and ComfyUI's node graph.

All prompt assembly, parameter injection, and node wiring lives here.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from backend.unified_shot import (
    UnifiedShot, Camera, Emotion, Weather, TimeOfDay, Lighting,
)

# ============================================================
# Helper 鈥?safe Enum/string value extraction
# ============================================================

def _val(field: Any) -> str:
    """Return the string value of a field, whether it's an Enum or plain string."""
    return getattr(field, "value", field)

# ============================================================
# Template Paths
# ============================================================

WORKFLOW_TEMPLATES_DIR = Path(__file__).parent.parent / "workflow" / "templates"
DEFAULT_TEMPLATE = "sd_xl_base.json"

# Maximum safe resolution for single-pass generation.
# Diffusion models lose global coherence above ~2048px 鈥?body parts fragment.
# For 4K (3840x2160), we MUST generate at a safe base resolution and then upscale.
# SDXL native training resolution: ~1MP (1024脳1024).
# For 16:9 aspect ratio, the area-equivalent safe resolution is ~1344脳768.
# Generating >1536px in any dimension triggers severe anatomy fragmentation.
# We clamp to 1344脳768 for 16:9, upscaling afterwards if 4K is requested.
MAX_SAFE_WIDTH = 1344
MAX_SAFE_HEIGHT = 1344


# ============================================================
# Prompt Builders
# ============================================================

def _get_style_from_config() -> str:
    """Read the generation style from config, falling back to 'anime'."""
    try:
        from backend.config import get_config
        cfg = get_config()
        style = getattr(getattr(cfg, 'generation', None), 'default_style', None)
        if style:
            return style
    except Exception:
        pass
    return "anime"


def _get_composition_directive(shot: UnifiedShot) -> str:
    """Build a strong composition directive to prevent body fragmentation.

    This is the single most critical fix: large resolutions cause diffusion
    models to lose global coherence and fragment the subject. We inject a
    strong composition anchor at the very beginning of the prompt.
    """
    camera = _val(shot.camera)

    composition_map = {
        "close": "single person, close-up portrait, one complete face, head and shoulders, centered, no duplicates, no fragmented body parts",
        "medium": "single person, waist-up portrait, one complete upper body, centered standing, solo, no overlapping figures, no body fragments",
        "wide": "single person, full body shot, one complete figure standing, centered, solo, clean simple composition, no duplicates, no fragmented limbs",
        "drone": "single person, aerial view, one complete figure, centered, solo, no duplicates",
        "pov": "single person, POV perspective, one complete figure, centered, solo, no overlapping",
        "tracking": "single person, dynamic action, one complete figure, solo, centered, no fragments",
        "dutch": "single person, dramatic angle, one complete figure, solo, centered, no fragments",
        "overhead": "single person, overhead view, one complete figure, solo, centered, no fragments",
    }

    return composition_map.get(camera, "single person, one complete figure, solo, centered, no duplicates, no fragmented body parts")


def _build_positive_prompt(shot: UnifiedShot) -> str:
    """Assemble the positive prompt from shot fields."""
    parts: List[str] = []

    # Composition directive 鈥?CRITICAL for preventing body fragmentation
    # Must come early in the prompt for maximum weight
    composition_directive = _get_composition_directive(shot)
    parts.append(composition_directive)

    # Subject
    if shot.characters:
        parts.append(", ".join(shot.characters))

    # Background
    if shot.background:
        parts.append(f"in {shot.background}")

    # Weather & Time
    env = []
    weather_val = _val(shot.weather)
    if weather_val != Weather.clear.value:
        env.append(weather_val)
    time_val = _val(shot.time_of_day)
    if time_val != TimeOfDay.noon.value:
        env.append(time_val)
    if env:
        parts.append(", ".join(env))

    # Lighting
    light_val = _val(shot.lighting)
    if light_val != Lighting.natural.value:
        parts.append(f"{light_val} lighting")
    if shot.light_source:
        parts.append(f"light from {shot.light_source}")

    # Camera
    camera_val = _val(shot.camera)
    camera_tags = {
        "close": "close-up portrait, detailed face, single person, head and shoulders",
        "medium": "medium shot, waist-up, single person, upper body portrait, cinematic framing",
        "wide": "wide shot, full body, single person standing, landscape composition",
        "drone": "drone shot, aerial view, single person, top-down perspective",
        "pov": "POV shot, first-person view, single person",
        "tracking": "tracking shot, single person, dynamic motion",
        "dutch": "dutch angle, single person, tilted composition",
        "overhead": "overhead shot, single person, bird's eye view",
    }
    if camera_val in camera_tags:
        parts.append(camera_tags[camera_val])
    if shot.camera_angle:
        parts.append(shot.camera_angle)
    if shot.camera_motion:
        parts.append(shot.camera_motion)
    if shot.focal_length:
        parts.append(f"{shot.focal_length} lens")

    # Emotion
    emotion_val = _val(shot.emotion)
    emotion_tags = {
        "neutral": "neutral expression",
        "happy": "smiling, joyful expression, bright eyes",
        "sad": "sad expression, melancholic, downcast eyes",
        "angry": "angry expression, furious, glaring",
        "surprised": "surprised expression, wide eyes, shocked",
        "fearful": "fearful expression, terrified, trembling",
        "calm": "calm expression, serene, peaceful",
        "excited": "excited expression, energetic, enthusiastic",
        "determined": "determined expression, resolute, focused",
    }
    if emotion_val in emotion_tags:
        parts.append(emotion_tags[emotion_val])

    # Atmosphere
    if shot.atmosphere:
        parts.append(f"{shot.atmosphere} atmosphere")
    if shot.color_palette:
        parts.append(f"{shot.color_palette} color palette")

    # Style from config (not hardcoded 'anime')
    style = _get_style_from_config()
    style_tags = {
        "anime": "anime style, vibrant colors, clean lineart, cel shading",
        "manga": "manga style, black and white, screentone, crosshatching",
        "realistic": "photorealistic, detailed skin texture, subsurface scattering, realistic human proportions",
        "semi_realistic": "semi-realistic anime, detailed rendering, soft shading",
        "cinematic": "cinematic film grain, anamorphic lens, color grading, film still",
    }
    style_modifier = style_tags.get(style, "anime style")

    # Quality tags
    parts.extend([
        "masterpiece",
        "best quality",
        "highly detailed",
        "8k",
        style_modifier,
        "perfect composition",
        "clean composition",
        "simple background",
    ])

    return ", ".join(p for p in parts if p)


def _build_negative_prompt(shot: UnifiedShot) -> str:
    """Assemble the negative prompt.

    Targeted anatomy negatives are CRITICAL for SDXL 鈥?the model
    frequently produces long necks, extra fingers, and distorted
    proportions at high CFG or out-of-native resolutions.
    """
    base_negatives = [
        "low quality",
        "worst quality",
        "blurry",
        "watermark",
        "text",
        "signature",
        "deformed",
        "bad anatomy",
        "extra limbs",
        "missing fingers",
        "cropped",
        "jpeg artifacts",
        "ugly",
        # Anatomy-specific (high priority for SDXL)
        "long neck",
        "too long neck",
        "extra fingers",
        "six fingers",
        "missing ear",
        "missing ears",
        "broad shoulders",
        "detached limbs",
        "dislocated joints",
        "mutated anatomy",
        "fused body parts",
        "asymmetric face",
        "twisted neck",
        "elongated torso",
        "wrong proportions",
        "grotesque proportions",
        "alien proportions",
        # Anti-fragmentation
        "fragmented body parts",
        "dismembered",
        "body horror",
        "collage",
        "overlapping bodies",
        "mosaic of body parts",
        "duplicate",
        "multiple heads",
        "multiple faces",
        "extra person",
        "crowd",
        "cluttered composition",
        "busy background",
        "complex scene",
        "twisted body",
        "contorted",
        "merged bodies",
        "fused limbs",
        "tangled",
        "pile of bodies",
        "stacked figures",
    ]

    if shot.negative_prompt:
        base_negatives.append(shot.negative_prompt.strip())

    return ", ".join(base_negatives)


# ============================================================
# Resolution Safety
# ============================================================

def _clamp_resolution(width: int, height: int) -> Tuple[int, int, bool]:
    """Clamp resolution to safe maximum for single-pass generation.

    Returns:
        (safe_width, safe_height, was_clamped) 鈥?True if clamping occurred,
        meaning an upscale step will be needed afterwards.
    """
    was_clamped = False
    safe_w, safe_h = width, height

    if width > MAX_SAFE_WIDTH or height > MAX_SAFE_HEIGHT:
        was_clamped = True
        # Scale down proportionally so the longer side hits the max
        scale = min(MAX_SAFE_WIDTH / width, MAX_SAFE_HEIGHT / height)
        safe_w = int(width * scale)
        safe_h = int(height * scale)
        # Ensure multiples of 64 for latent space compatibility
        safe_w = (safe_w // 64) * 64
        safe_h = (safe_h // 64) * 64
        logger.info(
            f"Resolution clamped: {width}x{height} 鈫?{safe_w}x{safe_h} "
            f"(scale={scale:.2f}, needs upscale={was_clamped})"
        )

    return safe_w, safe_h, was_clamped


# ============================================================
# Workflow Generator
# ============================================================

class WorkflowGenerator:
    """Generate ComfyUI API-format workflow JSON from a UnifiedShot."""

    # Node IDs (fixed for template-based generation)
    # Flux workflow: DualCLIPLoader (CLIP) + UNETLoader (MODEL) + VAELoader (VAE)
    NODE_DUAL_CLIP = 1
    NODE_UNET_LOADER = 2
    NODE_CLIP_POS = 3
    NODE_CLIP_NEG = 4
    NODE_EMPTY_LATENT = 5
    NODE_SAMPLER = 6
    NODE_VAE_LOADER = 7
    NODE_VAE_DECODE = 8
    NODE_SAVE_IMAGE = 9

    def __init__(self, template_name: str = DEFAULT_TEMPLATE, no_llm_refine: bool = False, debug: bool = False):
        self.template_name = template_name
        self.no_llm_refine = no_llm_refine
        self.debug = debug or os.environ.get("AI_MANGA_DEBUG", "") == "1"
        self._template: Optional[Dict[str, Any]] = None

    @property
    def template(self) -> Dict[str, Any]:
        if self._template is None:
            self._load_template()
        return self._template or {}

    def _load_template(self) -> None:
        path = WORKFLOW_TEMPLATES_DIR / self.template_name
        if path.exists():
            with open(path, "r", encoding="utf-8-sig") as f:
                self._template = json.load(f)
            logger.info(f"Loaded workflow template: {path}")
        else:
            logger.warning(f"Template not found: {path} 鈥?using built-in default")
            self._template = self._build_default_template()

    def _build_default_template(self) -> Dict[str, Any]:
        """Built-in minimal template (Flux.1 Schnell 鈥?DualCLIPLoader + UNETLoader + VAELoader)."""
        return {
            "1": {
                "inputs": {
                    "clip_name1": "t5xxl_fp8_e4m3fn.safetensors",
                    "clip_name2": "clip_l.safetensors",
                    "type": "flux",
                },
                "class_type": "DualCLIPLoader",
            },
            "2": {
                "inputs": {
                    "unet_name": "flux1-dev-bnb-nf4-v2.safetensors",
                    "weight_dtype": "default",
                },
                "class_type": "UNETLoader",
            },
            "3": {
                "inputs": {
                    "clip": ["1", 0],
                    "clip_l": "PLACEHOLDER_POSITIVE",
                    "t5xxl": "PLACEHOLDER_POSITIVE",
                    "guidance": 1.0,
                },
                "class_type": "CLIPTextEncodeFlux",
            },
            "4": {
                "inputs": {
                    "clip": ["1", 0],
                    "clip_l": "PLACEHOLDER_NEGATIVE",
                    "t5xxl": "PLACEHOLDER_NEGATIVE",
                    "guidance": 1.0,
                },
                "class_type": "CLIPTextEncodeFlux",
            },
            "5": {
                "inputs": {
                    "width": 1344,
                    "height": 704,
                    "batch_size": 1,
                },
                "class_type": "EmptyLatentImage",
            },
            "6": {
                "inputs": {
                    "seed": 0,
                    "steps": 4,
                    "cfg": 1.0,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "denoise": 1.0,
                    "model": ["2", 0],
                    "positive": ["3", 0],
                    "negative": ["4", 0],
                    "latent_image": ["5", 0],
                },
                "class_type": "KSampler",
            },
            "7": {
                "inputs": {
                    "vae_name": "ae.safetensors",
                },
                "class_type": "VAELoader",
            },
            "8": {
                "inputs": {
                    "samples": ["6", 0],
                    "vae": ["7", 0],
                },
                "class_type": "VAEDecode",
            },
            "9": {
                "inputs": {
                    "filename_prefix": "shot_",
                    "images": ["8", 0],
                },
                "class_type": "SaveImage",
            },
        }

    def generate(self, shot: UnifiedShot) -> Dict[str, Any]:
        """Generate a ComfyUI ready workflow from a UnifiedShot.

        Attempts LLM-based prompt refinement first. Falls back to
        template-based prompt assembly if LLM is unavailable or
        --no-llm-refine is set.

        Args:
            shot: UnifiedShot object (can be a dict if loaded from JSON).

        Returns:
            ComfyUI API-format workflow dict.
        """
        wf = copy.deepcopy(self.template)

        # 鈹€鈹€ LLM Refinement Path 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        pos_prompt: Optional[str] = None
        neg_prompt: Optional[str] = None

        if not self.no_llm_refine:
            try:
                from backend.prompt_refiner import refine_shot_prompts
                refined = refine_shot_prompts(shot)
                if refined:
                    pos_prompt = refined.get("positive_prompt", "")
                    neg_prompt = refined.get("negative_prompt", "")
                    logger.info(
                        f"PromptRefiner: Using LLM-refined prompts for "
                        f"ch{getattr(shot, 'chapter', '?')}/sc{getattr(shot, 'scene', '?')}/sh{getattr(shot, 'shot', '?')}"
                    )
            except Exception as exc:
                logger.warning(
                    f"PromptRefiner: LLM refinement failed ({exc}) 鈥?"
                    f"falling back to template prompts"
                )

        # 鈹€鈹€ Fallback: Template Path 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        if pos_prompt is None:
            pos_prompt = _build_positive_prompt(shot)
        if neg_prompt is None:
            neg_prompt = _build_negative_prompt(shot)

        # Inject background image reference into positive prompt
        bg_path = getattr(shot, 'background_image_path', '')
        bg_name = getattr(shot, 'background', '')
        if bg_path and os.path.exists(bg_path):
            pos_prompt = (
                f"(masterpiece, best quality, detailed background:1.2), "
                f"{pos_prompt}, "
                f"((matching the scene background '{bg_name}':1.1))"
            )

        # Inject into template (Flux CLIPTextEncodeFlux uses clip_l + t5xxl)
        self._inject_node(wf, self.NODE_CLIP_POS, "clip_l", pos_prompt)
        self._inject_node(wf, self.NODE_CLIP_POS, "t5xxl", pos_prompt)
        self._inject_node(wf, self.NODE_CLIP_NEG, "clip_l", neg_prompt)
        self._inject_node(wf, self.NODE_CLIP_NEG, "t5xxl", neg_prompt)

        # Resolution 鈥?clamp to safe maximum to prevent body fragmentation
        safe_w, safe_h, needs_upscale = _clamp_resolution(shot.width, shot.height)
        self._inject_node(wf, self.NODE_EMPTY_LATENT, "width", safe_w)
        self._inject_node(wf, self.NODE_EMPTY_LATENT, "height", safe_h)

        # Sampler params
        seed = shot.seed if shot.seed >= 0 else int(os.urandom(4).hex(), 16) % (2**31)
        self._inject_node(wf, self.NODE_SAMPLER, "seed", seed)
        self._inject_node(wf, self.NODE_SAMPLER, "steps", shot.steps)
        self._inject_node(wf, self.NODE_SAMPLER, "cfg", shot.cfg)

        # SaveImage prefix: project_chapter_scene_shot
        prefix = f"p{shot.chapter:02d}_s{shot.scene:02d}_sh{shot.shot:03d}"
        self._inject_node(wf, self.NODE_SAVE_IMAGE, "filename_prefix", prefix)

        # Store metadata in extra so downstream knows if upscale is needed
        if needs_upscale:
            if not hasattr(shot, "extra"):
                shot.extra = {}
            shot.extra["_needs_upscale"] = True
            shot.extra["_target_width"] = shot.width
            shot.extra["_target_height"] = shot.height
            shot.extra["_base_width"] = safe_w
            shot.extra["_base_height"] = safe_h

        logger.info(
            f"Generated workflow for ch{shot.chapter}/sc{shot.scene}/sh{shot.shot}: "
            f"camera={_val(shot.camera)}, emotion={_val(shot.emotion)}, "
            f"resolution={safe_w}x{safe_h}{' (needs upscale to '+str(shot.width)+'x'+str(shot.height)+')' if needs_upscale else ''}, "
            f"seed={seed}"
        )

        # 鈹€鈹€ Debug mode: save full reproducibility artifacts 鈹€鈹€
        if self.debug:
            self._write_debug_files(
                shot=shot, workflow=wf, pos_prompt=pos_prompt, neg_prompt=neg_prompt,
                seed=seed, cfg=shot.cfg, steps=shot.steps, safe_w=safe_w, safe_h=safe_h,
            )

        # Strip metadata keys 鈥?ComfyUI API rejects nodes dict with non-numeric keys
        return {k: v for k, v in wf.items() if isinstance(v, dict)}

    def generate_file(
        self,
        shot: UnifiedShot,
        output_path: str,
    ) -> str:
        """Generate workflow and save to JSON file.

        Args:
            shot: UnifiedShot to generate from.
            output_path: Where to write the ComfyUI workflow JSON.

        Returns:
            Absolute path to the written file.
        """
        wf = self.generate(shot)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8-sig") as f:
            json.dump(wf, f, indent=2, ensure_ascii=False)
        logger.info(f"Workflow written to: {output_path}")
        return os.path.abspath(output_path)

    @staticmethod
    def _inject_node(wf: Dict[str, Any], node_id: int, key: str, value: Any) -> None:
        """Safely inject a value into a node's inputs."""
        node_key = str(node_id)
        if node_key in wf and "inputs" in wf[node_key]:
            wf[node_key]["inputs"][key] = value

    # 鈹€鈹€ Debug Mode 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _write_debug_files(
        self,
        shot: Any,
        workflow: Dict[str, Any],
        pos_prompt: Optional[str],
        neg_prompt: Optional[str],
        seed: int,
        cfg: float,
        steps: int,
        safe_w: int,
        safe_h: int,
    ) -> None:
        """Write full reproducibility debug artifacts for this shot.

        Saved to: output/debug/chXX_scXX_shXX/
        Controlled by: AI_MANGA_DEBUG=1 env var or --debug CLI flag.
        """
        import json as _json

        ch = getattr(shot, "chapter", 0)
        sc = getattr(shot, "scene", 0)
        sh = getattr(shot, "shot", 0)
        debug_dir = Path("output") / "debug" / f"ch{ch:02d}_sc{sc:02d}_sh{sh:03d}"
        debug_dir.mkdir(parents=True, exist_ok=True)

        # Clean workflow (strip non-dict keys for valid ComfyUI JSON)
        clean_wf = {k: v for k, v in workflow.items() if isinstance(v, dict)}

        # 1. workflow.json 鈥?final ComfyUI-ready workflow
        (debug_dir / "workflow.json").write_text(
            _json.dumps(clean_wf, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # 2. final_prompt.txt 鈥?assembled positive prompt
        (debug_dir / "final_prompt.txt").write_text(
            pos_prompt or "", encoding="utf-8"
        )

        # 3. negative.txt 鈥?assembled negative prompt
        (debug_dir / "negative.txt").write_text(
            neg_prompt or "", encoding="utf-8"
        )

        # 4. seed.txt
        (debug_dir / "seed.txt").write_text(str(seed), encoding="utf-8")

        # 5. cfg.txt
        (debug_dir / "cfg.txt").write_text(str(cfg), encoding="utf-8")

        # 6. sampler.txt 鈥?sampler name + scheduler + steps
        sampler_name = workflow.get(str(self.NODE_SAMPLER), {}).get("inputs", {}).get("sampler_name", "euler")
        scheduler = workflow.get(str(self.NODE_SAMPLER), {}).get("inputs", {}).get("scheduler", "simple")
        (debug_dir / "sampler.txt").write_text(
            f"sampler_name={sampler_name}\nscheduler={scheduler}\nsteps={steps}", encoding="utf-8"
        )

        # 7. checkpoint.txt 鈥?UNET/model name
        unet_name = workflow.get(str(self.NODE_UNET_LOADER), {}).get("inputs", {}).get("unet_name", "?")
        (debug_dir / "checkpoint.txt").write_text(str(unet_name), encoding="utf-8")

        # 8. vae.txt 鈥?VAE model name
        vae_name = workflow.get(str(self.NODE_VAE_LOADER), {}).get("inputs", {}).get("vae_name", "?")
        (debug_dir / "vae.txt").write_text(str(vae_name), encoding="utf-8")

        logger.info(
            f"Debug: Wrote 8 artifact files 鈫?{debug_dir} "
            f"(unet={unet_name}, vae={vae_name}, cfg={cfg}, steps={steps}, seed={seed}, "
            f"resolution={safe_w}x{safe_h})"
        )


# ============================================================
# Convenience
# ============================================================

_workflow_gen: Optional[WorkflowGenerator] = None


def get_workflow_generator(template: str = DEFAULT_TEMPLATE) -> WorkflowGenerator:
    global _workflow_gen
    if _workflow_gen is None:
        _workflow_gen = WorkflowGenerator(template)
    return _workflow_gen






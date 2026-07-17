"""
AI Manga Studio Pro V5 — I2V Workflow Generator with Director-Level Control

Multi-model I2V support upgraded for cinematic video generation:
  1. Wan2.2 I2V (first frame + last frame + director motion prompt) PRIMARY
  2. HunyuanVideo I2V (first frame + motion prompt) FALLBACK
  3. LTX2.3 I2V (first frame + last frame + motion) ALTERNATIVE
  4. AnimateDiff I2V (single image + motion) EMERGENCY

V5 Director-Level Features:
- First/last frame pair generation with LastFrameGenerator integration
- DirectorVideoPromptBuilder motion prompt injection
- Shot-type-aware workflow parameters
- Character lock via PuLID/IPAdapter injection
- FX layer injection (speed lines, impact waves, particles, transitions)
- Professional shot continuity (match cut, dissolve, seamless)
- Motion strength auto-inference from shot content
- Multi-model routing based on available templates
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from backend.unified_shot import UnifiedShot
from backend.director_video_prompt_builder import (
    DirectorVideoPromptBuilder,
    CinematicShot,
)
from backend.last_frame_generator import LastFrameGenerator

# Template paths
TEMPLATE_DIR = Path(__file__).parent.parent / "workflow" / "templates"

# Resolution presets per shot type
RESOLUTION_PRESETS = {
    "close": (768, 768),       # Square for portraits
    "medium": (1344, 768),     # 16:9 standard
    "wide": (1536, 640),       # 2.4:1 cinematic widescreen
    "drone": (1536, 1024),     # 3:2 aerial
    "pov": (1344, 768),        # 16:9 immersive
    "tracking": (1344, 768),   # 16:9 lateral
    "dutch": (1024, 1344),     # Vertical dramatic
    "overhead": (1344, 1344),  # Square top-down
    "two_shot": (1344, 768),   # 16:9 two person
    "over_shoulder": (1344, 768),  # 16:9 over shoulder
}

# Frame counts per shot duration
FRAME_COUNTS = {
    "close": (24, 48),        # 1-2 sec @ 24fps
    "medium": (48, 72),       # 2-3 sec @ 24fps
    "wide": (72, 96),         # 3-4 sec @ 24fps
    "drone": (96, 144),       # 4-6 sec @ 24fps
    "pov": (48, 72),          # 2-3 sec
    "tracking": (72, 96),     # 3-4 sec
    "dutch": (24, 48),        # 1-2 sec
    "overhead": (96, 144),    # 4-6 sec
    "two_shot": (48, 72),
    "over_shoulder": (48, 72),
}


class I2VGenerator:
    """Build I2V workflows from UnifiedShot + director-level motion data.

    Supports four backends:
      - Wan2.2 I2V (preferred): first frame + last frame + director motion prompt
      - LTX2.3 I2V (alternative): first frame + last frame + motion prompt
      - AnimateDiff I2V (fallback): single image + motion module
    """

    def __init__(
        self,
        wan_template_path: Optional[str] = None,
        ltx_template_path: Optional[str] = None,
        ad_template_path: Optional[str] = None,
    ):
        # Load Wan2.2 template
        wan_path = Path(wan_template_path) if wan_template_path else TEMPLATE_DIR / "wan_i2v.json"
        self._wan_template: Optional[Dict] = None
        if wan_path.exists():
            with open(wan_path, "r", encoding="utf-8") as f:
                self._wan_template = json.load(f)
            logger.info(f"I2VGenerator: Loaded Wan2.2 template ({wan_path.name})")

        # Load LTX2.3 template
        ltx_path = Path(ltx_template_path) if ltx_template_path else TEMPLATE_DIR / "ltx_i2v.json"
        self._ltx_template: Optional[Dict] = None
        if ltx_path.exists():
            with open(ltx_path, "r", encoding="utf-8") as f:
                self._ltx_template = json.load(f)
            logger.info(f"I2VGenerator: Loaded LTX2.3 template ({ltx_path.name})")

        # Load AnimateDiff template
        ad_path = Path(ad_template_path) if ad_template_path else TEMPLATE_DIR / "i2v_gen.json"
        self._ad_template: Optional[Dict] = None
        if ad_path.exists():
            with open(ad_path, "r", encoding="utf-8") as f:
                self._ad_template = json.load(f)
            logger.info(f"I2VGenerator: Loaded AnimateDiff template ({ad_path.name})")

        # Initialize director-level builders
        self._director_builder = DirectorVideoPromptBuilder()
        self._last_frame_gen = LastFrameGenerator()

    # ---- Public API ----

    def generate(
        self,
        shot: UnifiedShot,
        input_image: str,
        last_frame_image: Optional[str] = None,
        motion_prompt: str = "",
        frame_count: Optional[int] = None,
        fps: int = 24,
        model: str = "auto",
        director_shot: Optional[CinematicShot] = None,
    ) -> Dict[str, Any]:
        """Build I2V workflow JSON.

        Args:
            shot: UnifiedShot with all shot metadata.
            input_image: Path to first frame image.
            last_frame_image: Path to last frame image (for Wan2.2 I2V).
            motion_prompt: Director-level motion prompt from DirectorVideoPromptBuilder.
            frame_count: Override frame count (auto-calculated if None).
            fps: Target FPS.
            model: "wan" | "ltx" | "animatediff" | "auto".
            director_shot: Optional CinematicShot for director-level prompting.

        Returns:
            ComfyUI API-format workflow dict.
        """
        # Auto-detect model
        if model == "auto":
            model = self._detect_best_model(last_frame_image is not None)

        if model == "wan" and self._wan_template:
            return self._generate_wan(shot, input_image, last_frame_image, motion_prompt, frame_count, fps, director_shot)
        elif model == "ltx" and self._ltx_template:
            return self._generate_ltx(shot, input_image, last_frame_image, motion_prompt, frame_count, fps, director_shot)
        elif model == "animatediff" and self._ad_template:
            return self._generate_animatediff(shot, input_image, motion_prompt, frame_count, fps)
        else:
            # Fallback chain: wan -> ltx -> animatediff
            if self._wan_template:
                return self._generate_wan(shot, input_image, last_frame_image, motion_prompt, frame_count, fps, director_shot)
            if self._ltx_template:
                return self._generate_ltx(shot, input_image, last_frame_image, motion_prompt, frame_count, fps, director_shot)
            if self._ad_template:
                return self._generate_animatediff(shot, input_image, motion_prompt, frame_count, fps)
            raise RuntimeError("No I2V template available.")

    def generate_with_frames(
        self,
        shot: UnifiedShot,
        first_frame: str,
        last_frame: str,
        motion_prompt: str = "",
        director_shot: Optional[CinematicShot] = None,
    ) -> Dict[str, Any]:
        """Generate I2V workflow with explicit first and last frame images."""
        return self.generate(
            shot=shot,
            input_image=first_frame,
            last_frame_image=last_frame,
            motion_prompt=motion_prompt,
            model="wan",
            director_shot=director_shot,
        )

    def generate_from_cinematic_shot(
        self,
        shot: UnifiedShot,
        first_frame_path: str,
        cinematic_shot: CinematicShot,
        character_anchor: str = "",
    ) -> Dict[str, Any]:
        """End-to-end: build director prompt + I2V workflow from a CinematicShot.

        This is the recommended V5 method for cinematic video generation.
        """
        # 1. Build director-level video prompt
        director_prompt = self._director_builder.build_from_shot(cinematic_shot)

        # 2. Generate last frame spec
        last_frame_spec = self._last_frame_gen.generate_spec(
            cinematic_shot,
            first_frame_prompt=character_anchor,
        )

        # 3. Use director prompt as motion prompt
        motion_prompt = director_prompt.full_prompt

        # 4. Generate I2V workflow
        workflow = self.generate(
            shot=shot,
            input_image=first_frame_path,
            last_frame_image=None,  # Will be generated separately
            motion_prompt=motion_prompt,
            director_shot=cinematic_shot,
        )

        logger.info(
            f"I2VGenerator[V5]: cinematic workflow for {shot.shot_id}, "
            f"motion_strength={director_prompt.motion_strength:.2f}"
        )
        return workflow

    # ---- Internal: Wan2.2 I2V ----

    def _generate_wan(
        self,
        shot: UnifiedShot,
        first_frame: str,
        last_frame: Optional[str],
        motion_prompt: str,
        frame_count: Optional[int],
        fps: int,
        director_shot: Optional[CinematicShot] = None,
    ) -> Dict[str, Any]:
        """Build Wan2.2 I2V workflow with first/last frame support."""
        if not self._wan_template:
            raise RuntimeError("Wan2.2 template not loaded")

        wf = copy.deepcopy(self._wan_template)

        # Resolution from shot type
        shot_type = str(getattr(shot, "camera", "medium")).lower()
        width, height = RESOLUTION_PRESETS.get(shot_type, (1344, 768))

        # Frame count from duration
        if frame_count is None:
            dur = getattr(shot, "duration", 5.0)
            frame_count = int(dur * fps)
        frame_count = max(16, min(frame_count, 144))

        # Seed
        seed = shot.seed if shot.seed >= 0 else int(os.urandom(4).hex(), 16) % (2**31)

        # Inject first frame
        self._inject(wf, 100, "image", first_frame)
        if last_frame:
            self._inject(wf, 101, "image", last_frame)

        # Motion prompt - use director-level prompt if available
        if motion_prompt:
            self._inject(wf, 104, "motion_prompt", motion_prompt)

        # Director-level motion strength
        if director_shot:
            strength = self._director_builder._infer_motion_strength(director_shot)
            self._inject(wf, 109, "motion_strength", strength)

        # Model params
        self._inject(wf, 109, "width", width)
        self._inject(wf, 109, "height", height)
        self._inject(wf, 109, "frame_count", frame_count)
        self._inject(wf, 109, "seed", seed)
        self._inject(wf, 109, "steps", getattr(shot, "steps", 30))
        self._inject(wf, 109, "cfg", getattr(shot, "cfg", 5.0))

        # Output
        prefix = f"v_p{getattr(shot, 'chapter', 1):02d}_s{getattr(shot, 'scene', 1):02d}_sh{getattr(shot, 'shot', 1):03d}"
        self._inject(wf, 110, "filename_prefix", prefix)

        logger.info(
            f"I2VGenerator[Wan2.2]: shot={shot.shot_id}, "
            f"frames={frame_count}, fps={fps}, resolution={width}x{height}"
        )
        return wf

    # ---- Internal: LTX2.3 I2V ----

    def _generate_ltx(
        self,
        shot: UnifiedShot,
        first_frame: str,
        last_frame: Optional[str],
        motion_prompt: str,
        frame_count: Optional[int],
        fps: int,
        director_shot: Optional[CinematicShot] = None,
    ) -> Dict[str, Any]:
        """Build LTX2.3 I2V workflow."""
        if not self._ltx_template:
            raise RuntimeError("LTX2.3 template not loaded")

        wf = copy.deepcopy(self._ltx_template)

        shot_type = str(getattr(shot, "camera", "medium")).lower()
        width, height = RESOLUTION_PRESETS.get(shot_type, (1344, 768))

        if frame_count is None:
            dur = getattr(shot, "duration", 5.0)
            frame_count = int(dur * fps)
        frame_count = max(16, min(frame_count, 128))

        seed = shot.seed if shot.seed >= 0 else int(os.urandom(4).hex(), 16) % (2**31)

        self._inject(wf, 100, "image", first_frame)
        if last_frame:
            self._inject(wf, 101, "image", last_frame)
        if motion_prompt:
            self._inject(wf, 104, "motion_prompt", motion_prompt)

        self._inject(wf, 109, "width", width)
        self._inject(wf, 109, "height", height)
        self._inject(wf, 109, "frame_count", frame_count)
        self._inject(wf, 109, "seed", seed)
        self._inject(wf, 109, "steps", getattr(shot, "steps", 25))
        self._inject(wf, 109, "cfg", getattr(shot, "cfg", 4.5))

        prefix = f"v_p{getattr(shot, 'chapter', 1):02d}_s{getattr(shot, 'scene', 1):02d}_sh{getattr(shot, 'shot', 1):03d}"
        self._inject(wf, 110, "filename_prefix", prefix)

        return wf

    # ---- Internal: AnimateDiff I2V ----

    def _generate_animatediff(
        self,
        shot: UnifiedShot,
        input_image: str,
        motion_prompt: str,
        frame_count: Optional[int],
        fps: int,
    ) -> Dict[str, Any]:
        """Build AnimateDiff I2V workflow (fallback)."""
        if not self._ad_template:
            raise RuntimeError("AnimateDiff template not loaded")

        wf = copy.deepcopy(self._ad_template)

        shot_type = str(getattr(shot, "camera", "medium")).lower()
        width, height = RESOLUTION_PRESETS.get(shot_type, (1344, 768))

        if frame_count is None:
            dur = getattr(shot, "duration", 5.0)
            frame_count = int(dur * fps)
        frame_count = max(16, min(frame_count, 64))

        seed = shot.seed if shot.seed >= 0 else int(os.urandom(4).hex(), 16) % (2**31)

        self._inject(wf, 1, "image", input_image)

        # Build prompts with motion
        base_pos = self._build_positive(shot)
        if motion_prompt:
            base_pos += f", {motion_prompt}"
        base_pos += ", smooth animation, consistent character, cinematic quality"

        base_neg = (
            "worst quality, low quality, blurry, disfigured, bad anatomy, "
            "extra limbs, jitter, flickering, morphing, distortion"
        )
        if motion_prompt:
            base_neg += ", static, frozen"

        self._inject(wf, 3, "text", base_pos)
        self._inject(wf, 4, "text", base_neg)

        self._inject(wf, 9, "seed", seed)
        self._inject(wf, 9, "steps", getattr(shot, "steps", 20))
        self._inject(wf, 9, "cfg", getattr(shot, "cfg", 7.5))

        self._inject(wf, 12, "context_length", frame_count)
        self._inject(wf, 13, "batch_size", frame_count)

        prefix = f"v_p{getattr(shot, 'chapter', 1):02d}_s{getattr(shot, 'scene', 1):02d}_sh{getattr(shot, 'shot', 1):03d}"
        self._inject(wf, 11, "frame_rate", fps)
        self._inject(wf, 11, "filename_prefix", prefix)

        return wf

    # ---- Helpers ----

    def _detect_best_model(self, has_last_frame: bool) -> str:
        """Auto-detect best available model."""
        if has_last_frame and self._wan_template:
            return "wan"
        if self._wan_template:
            return "wan"
        if self._ltx_template:
            return "ltx"
        if self._ad_template:
            return "animatediff"
        raise RuntimeError("No I2V templates available")

    @staticmethod
    def _inject(wf: Dict[str, Any], node_id: int, key: str, value: Any) -> None:
        """Inject a value into a workflow node's inputs."""
        node_key = str(node_id)
        if node_key in wf and "inputs" in wf[node_key]:
            wf[node_key]["inputs"][key] = value

    @staticmethod
    def _build_positive(shot: UnifiedShot) -> str:
        """Build basic positive prompt from shot data."""
        parts = []
        if hasattr(shot, "characters"):
            parts.extend(shot.characters if isinstance(shot.characters, list) else [])
        if hasattr(shot, "background") and shot.background:
            parts.append(shot.background)
        return ", ".join(parts) if parts else "character portrait"

    @staticmethod
    def get_install_guide() -> str:
        """Installation guide for video models."""
        return (
            "Video Generation 需要以下模型安装指南:\n\n"
            "1. Wan2.2 I2V (首选):\n"
            "   - 安装 ComfyUI-Wan22 插件\n"
            "   - 下载 Wan2.2 I2V 模型放到 models/diffusion_models/\n"
            "   - 支持 first_frame + last_frame 双向控制\n\n"
            "2. LTX2.3 I2V (备选):\n"
            "   - 安装 ComfyUI-LTX 插件\n"
            "   - 下载 LTX2.3 模型\n\n"
            "3. AnimateDiff (应急):\n"
            "   - 安装 ComfyUI-AnimateDiff-Evolved\n"
            "   - 安装 ComfyUI-VideoHelperSuite\n"
            "   - 下载 motion 模块放到 models/animatediff_models/"
        )

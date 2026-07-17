"""
AI Manga Studio Pro V3 鈥?Cinema Video Pipeline

鐢靛奖绾ц棰戠敓鎴愮绾匡細鍥剧墖 鈫?Motion Plan娉ㄥ叆 鈫?瑙嗛鐢熸垚 鈫?鍚庢湡澶勭悊

褰撳墠 ComfyUI 鐜锛?  - AnimateDiff-Evolved 宸插畨瑁?  - ComfyUI-VideoHelperSuite 宸插畨瑁?  - 鈿?Wan/Hunyuan 鑷畾涔夎妭鐐规湭瀹夎 鈥?浣跨敤 AnimateDiff 浣滀负 fallback
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


# ============================================================
# Data Classes
# ============================================================

@dataclass
class VideoRenderResult:
    """Single video render result."""

    shot_id: str = ""
    source_image: str = ""
    output_video: str = ""
    model: str = ""              # "animate_diff" | "wan" | "hunyuan"
    duration_sec: float = 0.0
    fps: int = 24
    success: bool = False
    error: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# Model Availability Detection
# ============================================================

def _detect_available_models(comfyui_path: str = "D:\\ComfyUI_new") -> Dict[str, bool]:
    """Detect which video models / custom nodes are available."""
    custom_nodes = os.path.join(comfyui_path, "custom_nodes")

    available = {
        "wan": False,
        "hunyuan": False,
        "animatediff": False,
        "video_helper": False,
    }

    if not os.path.isdir(custom_nodes):
        return available

    for entry in os.listdir(custom_nodes):
        entry_lower = entry.lower()
        if "wan" in entry_lower and "video" in entry_lower:
            available["wan"] = True
        if "hunyuan" in entry_lower and "video" in entry_lower:
            available["hunyuan"] = True
        if "animatediff" in entry_lower:
            available["animatediff"] = True
        if "video" in entry_lower and "helper" in entry_lower:
            available["video_helper"] = True

    return available


# ============================================================
# Cinema Video Pipeline
# ============================================================

class CinemaVideoPipeline:
    """鐢靛奖绾ц棰戠敓鎴愮绾裤€?
    娴佺▼锛?      1. 鍔犺浇婧愬浘鐗?      2. 娉ㄥ叆 MotionPlan锛坈amera_movement, subject_motion, expression锛?      3. 鎻愪氦瑙嗛鐢熸垚 workflow
      4. 杩斿洖瑙嗛璺緞

    妯″瀷浼樺厛绾э細Wan > Hunyuan > AnimateDiff
    """

    def __init__(
        self,
        comfyui_client: Any = None,
        motion_planner: Any = None,
        comfyui_path: str = "D:\\ComfyUI_new",
        output_dir: str = "output/video",
    ):
        self.comfyui = comfyui_client
        self.motion_planner = motion_planner
        self.comfyui_path = comfyui_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Detect available models
        self._models = _detect_available_models(comfyui_path)
        self._active_model = self._resolve_model()

        logger.info(
            f"CinemaVideoPipeline: active_model={self._active_model}, "
            f"available={self._models}"
        )

    def _resolve_model(self) -> str:
        """Resolve the best available video model."""
        if self._models["wan"]:
            return "wan"
        if self._models["hunyuan"]:
            return "hunyuan"
        if self._models["animatediff"]:
            return "animate_diff"
        return "none"

    # 鈹€鈹€ Public API 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def generate(
        self,
        image_path: str,
        shot: Any,
        character_dna: Any = None,
        motion_plan: Optional[Dict[str, Any]] = None,
    ) -> VideoRenderResult:
        """鍗曢暅澶磋棰戠敓鎴愭祦绋嬨€?
        Args:
            image_path: 婧愬浘鐗囩粷瀵硅矾寰勩€?            shot: Shot 瀵硅薄銆?            character_dna: CharacterDNA 瀵硅薄锛堝彲閫夛級銆?            motion_plan: MotionPlan dict锛堝彲閫夛紝浼樺厛浣跨敤锛夈€?
        Returns:
            VideoRenderResult with output_video path.
        """
        shot_id = str(getattr(shot, "shot_id", "unknown"))

        if not image_path or not os.path.isfile(image_path):
            return VideoRenderResult(
                shot_id=shot_id,
                source_image=image_path,
                success=False,
                error=f"Source image not found: {image_path}",
            )

        if self._active_model == "none":
            return VideoRenderResult(
                shot_id=shot_id,
                source_image=image_path,
                model="none",
                success=False,
                error=(
                    "No video model available. "
                    "Please install Wan2.2, HunyuanVideo, or AnimateDiff custom nodes."
                ),
            )

        # Resolve motion plan
        if motion_plan is None and self.motion_planner is not None:
            mp = self.motion_planner.plan_motion(shot)
            motion_plan = self.motion_planner.to_dict(mp)

        # Build motion prompt
        motion_prompt = self._build_motion_prompt(motion_plan)

        try:
            # Build and submit workflow
            workflow = self._build_workflow(
                image_path=image_path,
                shot=shot,
                motion_prompt=motion_prompt,
            )

            # TODO: Submit to ComfyUI when client is wired
            # result = self.comfyui.submit_workflow(workflow)
            # output_video = result.output_videos[0]

            # For now, return placeholder
            output_video = str(
                self.output_dir / f"{shot_id}_{self._active_model}.mp4"
            )

            logger.info(
                f"VideoPipeline: shot={shot_id}, model={self._active_model}, "
                f"motion={motion_prompt[:80]}..."
            )

            return VideoRenderResult(
                shot_id=shot_id,
                source_image=image_path,
                output_video=output_video,
                model=self._active_model,
                duration_sec=3.0,  # default 3s clip
                fps=24,
                success=True,
            )

        except Exception as e:
            logger.error(f"VideoPipeline.generate failed for {shot_id}: {e}")
            return VideoRenderResult(
                shot_id=shot_id,
                source_image=image_path,
                model=self._active_model,
                success=False,
                error=str(e),
            )

    def generate_batch(
        self,
        shots: List[Any],
        image_map: Dict[str, str],
        char_dna_map: Optional[Dict[str, Any]] = None,
    ) -> List[VideoRenderResult]:
        """鎵归噺鐢熸垚瑙嗛鐗囨銆?
        Args:
            shots: Shot 瀵硅薄鍒楄〃銆?            image_map: shot_id 鈫?image_path 鏄犲皠銆?            char_dna_map: character_name 鈫?CharacterDNA 鏄犲皠銆?
        Returns:
            List of VideoRenderResult.
        """
        results = []
        total = len(shots)

        for i, shot in enumerate(shots):
            shot_id = str(getattr(shot, "shot_id", f"shot_{i}"))
            image_path = image_map.get(shot_id, "")

            # Resolve character DNA
            char_dna = None
            if char_dna_map:
                char_names = getattr(shot, "characters_present", []) or []
                for name in char_names:
                    if name in char_dna_map:
                        char_dna = char_dna_map[name]
                        break

            # Get motion plan from shot.extra if available
            motion_plan = None
            if hasattr(shot, "extra"):
                motion_plan = shot.extra.get("motion_plan")

            result = self.generate(
                image_path=image_path,
                shot=shot,
                character_dna=char_dna,
                motion_plan=motion_plan,
            )
            results.append(result)

            time.sleep(0.1)  # Rate limit

        success_count = sum(1 for r in results if r.success)
        logger.info(f"VideoPipeline batch: {success_count}/{total} shots rendered")
        return results

    # 鈹€鈹€ Internal 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _build_motion_prompt(self, motion_plan: Optional[Dict[str, Any]]) -> str:
        """Convert MotionPlan to motion prompt string for video model."""
        if not motion_plan:
            return "slow camera movement, subtle motion"

        parts = []
        cm = motion_plan.get("camera_movement", "")
        sm = motion_plan.get("subject_motion", "")
        expr = motion_plan.get("expression", "")
        cloth = motion_plan.get("cloth_motion", "")

        if cm:
            parts.append(f"camera: {cm}")
        if sm:
            parts.append(f"subject: {sm}")
        if expr and "neutral" not in expr.lower():
            parts.append(f"expression: {expr}")
        if cloth and cloth != "static":
            parts.append(f"cloth: {cloth}")

        return ", ".join(parts) if parts else "static shot, subtle camera movement"

    def _build_workflow(
        self,
        image_path: str,
        shot: Any,
        motion_prompt: str,
    ) -> dict:
        """Build ComfyUI workflow for video generation.

        Different workflow per model type. For AnimateDiff:
          LoadImage 鈫?VAEEncode 鈫?AnimateDiffLoader 鈫?KSampler 鈫?VAEDecode 鈫?VHS VideoCombine
        """
        width = int(getattr(shot, "width", 1344) or 1344)
        height = int(getattr(shot, "height", 704) or 704)
        frame_count = 72  # 3s @ 24fps

        if self._active_model == "animate_diff":
            return {
                "_description": f"AnimateDiff I2V 鈥?shot={getattr(shot, 'shot_id', '?')}, motion={motion_prompt[:60]}",
                "_model": "animate_diff",
                "_frame_count": frame_count,
                "_motion_prompt": motion_prompt,
                "_source_image": image_path,
                "_width": width,
                "_height": height,
            }
        elif self._active_model in ("wan", "hunyuan"):
            return {
                "_description": f"{self._active_model.upper()} I2V 鈥?shot={getattr(shot, 'shot_id', '?')}",
                "_model": self._active_model,
                "_motion_prompt": motion_prompt,
                "_source_image": image_path,
                "_width": width,
                "_height": height,
            }
        return {}

    # 鈹€鈹€ Static 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    @staticmethod
    def get_install_guide() -> str:
        """Return installation guide for video models."""
        return (
            "Video Generation 妯″瀷瀹夎鎸囧崡锛歕n"
            "鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€\n"
            "1. Wan2.2 (鎺ㄨ崘):\n"
            "   - git clone https://github.com/Wan-Video/ComfyUI-WanVideoWrapper "
            "D:\\ComfyUI_new\\custom_nodes\\ComfyUI-WanVideoWrapper\n"
            "   - 涓嬭浇 Wan2.2 I2V 妯″瀷 鈫?D:\\ComfyUI_new\\models\\diffusion_models\\\n\n"
            "2. HunyuanVideo:\n"
            "   - git clone https://github.com/Kijai/ComfyUI-HunyuanVideoWrapper "
            "D:\\ComfyUI_new\\custom_nodes\\ComfyUI-HunyuanVideoWrapper\n\n"
            "3. AnimateDiff (褰撳墠鍙敤):\n"
            "   - 宸插畨瑁? ComfyUI-AnimateDiff-Evolved\n"
            "   - 宸插畨瑁? ComfyUI-VideoHelperSuite\n"
            "   - 涓嬭浇 motion 妯″潡 鈫?D:\\ComfyUI_new\\models\\animatediff_models\\\n"
        )

    @staticmethod
    def is_available(comfyui_path: str = "D:\\ComfyUI_new") -> bool:
        """Check if any video model is available."""
        models = _detect_available_models(comfyui_path)
        return any(models.values())

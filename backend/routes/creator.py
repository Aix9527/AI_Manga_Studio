"""AI Creator Studio API routes.

Provides endpoints for:
- Listing shots with their keyframe images and AI video clips
- Regenerating specific shot keyframes
- Generating AI video clips from keyframes (immediate generation)
- Batch generating all AI videos (one-click)
- Managing generation settings
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/creator", tags=["creator"])


def _get_workspace_service(request: Request):
    svc = getattr(request.app.state, "workspace_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="服务未就绪")
    return svc


def _get_job_service(request: Request):
    svc = getattr(request.app.state, "job_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="服务未就绪")
    return svc


def _get_config(request: Request):
    return getattr(request.app.state, "config", None)


def _get_workspace_repo(request: Request):
    return getattr(request.app.state, "workspace_repo", None)


def _get_job_repo(request: Request):
    return getattr(request.app.state, "repo", None)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ShotInfo(BaseModel):
    shot_id: str
    shot_number: int
    description: str = ""
    narration: str = ""
    duration: float = 6.0
    camera: str = ""
    positive_prompt: str = ""
    negative_prompt: str = ""
    seed: int = 0
    transition: str = "fade"
    has_keyframe: bool = False
    keyframe_url: str = ""
    has_ai_video: bool = False
    ai_video_url: str = ""
    ai_video_status: str = "pending"


class CreatorProjectResponse(BaseModel):
    project_id: str
    title: str = ""
    total_shots: int = 0
    shots: list[ShotInfo] = []
    settings: dict[str, Any] = {}


class RegenerateImageRequest(BaseModel):
    prompt: str = ""
    negative_prompt: str = ""
    seed: int | None = None
    width: int | None = None
    height: int | None = None


class GenerateVideoRequest(BaseModel):
    motion_bucket_id: int = 127
    motion_level: int | None = None
    frames: int = 33
    fps: int = 24
    use_ai_video: bool = True


class UpdateSettingsRequest(BaseModel):
    motion_bucket_id: int = 127
    motion_level: int = 1
    video_frames: int = 33
    ai_video: bool = False
    character_consistency: bool = False
    provider: str = "ltx23"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_project_root(request: Request, project_id: str) -> Path:
    config = _get_config(request)
    return Path(config.project_root) / project_id if config else Path("projects") / project_id


def _find_latest_job_id(request: Request, project_id: str) -> str | None:
    """Find the latest job_id for a project from the database."""
    job_repo = _get_job_repo(request)
    if job_repo is None:
        return None
    try:
        jobs = job_repo.list_jobs(project_id=project_id, limit=1)
        if jobs:
            return str(jobs[0]["id"])
    except Exception:
        pass
    return None


def _register_video_asset(
    request: Request,
    job_id: str,
    project_id: str,
    shot_id: str,
    video_path: Path,
) -> None:
    """Register a generated video file as a workspace asset."""
    workspace_repo = _get_workspace_repo(request)
    if workspace_repo is None:
        return
    try:
        workspace_repo.add_project_asset(
            job_id=job_id,
            kind="video",
            path=str(video_path),
            stage_key="video",
            shot_id=shot_id,
            metadata={"source": "creator_studio", "shot_id": shot_id},
        )
    except Exception as exc:
        logger.warning("Failed to register video asset for %s: %s", shot_id, exc)


async def _check_comfyui_available() -> bool:
    """Check if ComfyUI is running and available."""
    try:
        import httpx
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.get("http://127.0.0.1:8188/system_stats", timeout=3.0)
            return resp.status_code == 200
    except Exception:
        return False


def _enhance_prompt_with_cinema_dna(
    prompt: str,
    shot_description: str,
    camera: str,
    narration: str,
) -> tuple[str, str]:
    """Enhance prompt using Cinema DNA (电影感) rules.

    Returns (enhanced_positive, enhanced_negative).
    Falls back to original prompt if Cinema DNA is unavailable.
    """
    try:
        from backend.integrations.cinema_dna import get_enhancer
        enhancer = get_enhancer()

        # Determine mood from narration/description
        mood = "suspenseful"
        desc_lower = (shot_description + narration).lower()
        if any(w in desc_lower for w in ["happy", "joy", "阳光", "温暖", "笑"]):
            mood = "warm"
        elif any(w in desc_lower for w in ["dark", "danger", "恐惧", "黑暗", "危险"]):
            mood = "ominous"
        elif any(w in desc_lower for w in ["sad", "loss", "悲伤", "失去"]):
            mood = "melancholic"

        # Determine shot type from camera
        shot_type = "medium"
        if "aerial" in camera or "establishing" in camera or "long shot" in camera:
            shot_type = "establishing"
        elif "close" in camera:
            shot_type = "close-up"
        elif "wide" in camera:
            shot_type = "wide"

        # Step 1: Get cinematic keyframe base with mood-based composition
        kf_result = enhancer.enhance_keyframe_prompt(
            scene_desc=shot_description,
            shot_type=shot_type,
            mood=mood,
        )
        # Step 2: Get video motion enhancement (camera movement, rhythm)
        vid_result = enhancer.enhance_video_prompt(
            scene_desc=shot_description,
            motion_desc=camera,
            shot_type=shot_type,
        )
        # Combine: keyframe cinematic base + video motion parts
        enhanced_pos = vid_result.get("positive_prompt", kf_result.get("positive_prompt", prompt))
        enhanced_neg = vid_result.get("negative_prompt", kf_result.get("negative_prompt", ""))
        # Merge original prompt with enhanced one
        if prompt and prompt not in enhanced_pos:
            enhanced_pos = f"{enhanced_pos}, {prompt}"
        return enhanced_pos, enhanced_neg
    except Exception as exc:
        logger.debug("Cinema DNA enhancement skipped: %s", exc)
        return prompt, ""


def _enhance_prompt_with_localdrama(
    prompt: str,
    shot_description: str,
    camera: str,
    shot_id: str,
) -> str:
    """Enhance prompt using LocalMiniDrama storyboard rules.

    Adds professional shot type, camera angle, and movement descriptors
    from LocalMiniDrama's 96-angle combination system.

    Returns enhanced prompt string. Falls back to original on error.
    """
    try:
        from backend.integrations.localdrama import (
            SHOT_TYPES, CAMERA_MOVEMENTS, VERTICAL_ANGLES,
        )

        camera_lower = (camera or "").lower()

        # Determine shot type from camera description
        shot_key = "medium"
        if "extreme close" in camera_lower:
            shot_key = "extreme_close"
        elif "close" in camera_lower and "up" in camera_lower:
            shot_key = "close_up"
        elif "medium close" in camera_lower:
            shot_key = "medium_close"
        elif "aerial" in camera_lower or "establishing" in camera_lower:
            shot_key = "extreme_wide"
        elif "wide" in camera_lower:
            shot_key = "wide"
        elif "full" in camera_lower:
            shot_key = "full"

        # Determine camera movement
        move_key = "static"
        if "push" in camera_lower or "dolly" in camera_lower:
            move_key = "push"
        elif "pull" in camera_lower:
            move_key = "pull"
        elif "tracking" in camera_lower or "track" in camera_lower:
            move_key = "tracking"
        elif "tilt" in camera_lower:
            move_key = "tilt"
        elif "pan" in camera_lower:
            move_key = "pan"
        elif "crane" in camera_lower:
            move_key = "crane_up" if "up" in camera_lower else "crane_down"
        elif "handheld" in camera_lower:
            move_key = "handheld"
        elif "orbit" in camera_lower:
            move_key = "orbit"

        # Determine vertical angle
        v_key = "eye_level"
        if "low-angle" in camera_lower or "low angle" in camera_lower:
            v_key = "low"
        elif "high-angle" in camera_lower or "high angle" in camera_lower or "bird" in camera_lower:
            v_key = "high"

        # Get English prompt fragments from LocalDrama data tables
        fragments: list[str] = []
        shot_data_entry = SHOT_TYPES.get(shot_key)
        if shot_data_entry:
            fragments.append(shot_data_entry[1])  # English fragment
        move_entry = CAMERA_MOVEMENTS.get(move_key)
        if move_entry:
            fragments.append(move_entry[1])
        v_entry = VERTICAL_ANGLES.get(v_key)
        if v_entry:
            fragments.append(v_entry[1])

        if fragments:
            fragment_str = ", ".join(fragments)
            if fragment_str not in prompt:
                return f"{prompt}, {fragment_str}"
        return prompt
    except Exception as exc:
        logger.debug("LocalDrama enhancement skipped: %s", exc)
        return prompt


def _select_provider_with_openmontage(
    shot_description: str,
    camera: str,
    narration: str,
) -> tuple[str, dict[str, Any]]:
    """Select best video provider using OpenMontage scoring engine.

    Returns (provider_name, score_breakdown).
    Falls back to ("wan22", {}) on error.

    Provider priority: MiniMax H3 > Seedance 2.0 > Wan2.1 > LTX.
    Ken Burns (静态缩放) 已被禁用，不再参与选择或兜底。
    API providers are only selected if their API keys are configured.
    """
    try:
        from backend.integrations.openmontage import registry, TaskParams, ProviderStatus

        # Update provider availability based on actual status
        # MiniMax H3
        minimax_ok = _check_provider_available("minimax_h3")
        registry.set_provider_status(
            "minimax_h3",
            ProviderStatus.AVAILABLE if minimax_ok else ProviderStatus.UNAVAILABLE,
        )

        # Seedance 2.0
        seedance_ok = _check_provider_available("seedance")
        registry.set_provider_status(
            "seedance",
            ProviderStatus.AVAILABLE if seedance_ok else ProviderStatus.UNAVAILABLE,
        )

        # ComfyUI providers (wan22, ltx23) - check async separately
        # For now, assume available if ComfyUI is running (checked in _do_generate_video)
        registry.set_provider_status("wan22", ProviderStatus.AVAILABLE)
        registry.set_provider_status("ltx23", ProviderStatus.AVAILABLE)
        # GPT P0: Ken Burns 只是"静态图缩放"，不是真实 AI 视频，禁止参与选择
        registry.set_provider_status("ken_burns", ProviderStatus.UNAVAILABLE)

        # Build task params from shot data
        desc_lower = (shot_description + narration).lower()
        style_keywords = []
        if any(w in desc_lower for w in ["action", "fight", "chase", "动作", "追", "战"]):
            style_keywords.extend(["action", "dynamic"])
        if any(w in desc_lower for w in ["cinematic", "film", "电影"]):
            style_keywords.append("cinematic")
        if any(w in desc_lower for w in ["dialogue", "talk", "对话"]):
            style_keywords.append("dialogue")

        task_type = "cinematic"
        if style_keywords:
            if "action" in style_keywords:
                task_type = "action"
            elif "dialogue" in style_keywords and "action" not in style_keywords:
                task_type = "dialogue"

        task = TaskParams(
            task_type=task_type,
            intent=shot_description[:200],
            style_keywords=style_keywords,
            motion_required=True,
            asset_type="video",
            shot_id="",
        )

        best = registry.select_best_provider(task_type, task)
        scores = registry.score_all(task_type, task)
        breakdown = scores[0].to_dict() if scores else {}
        logger.info("OpenMontage selected provider: %s (score: %s)",
                    best, breakdown.get("score_100", "N/A"))
        return best, breakdown
    except Exception as exc:
        logger.debug("OpenMontage provider selection skipped: %s", exc)
        return "wan22", {}


async def _generate_video_native(
    image_path: Path,
    output_path: Path,
    prompt: str,
    negative_prompt: str,
    seed: int,
    width: int,
    height: int,
    frames: int,
    fps: int,
    denoise: float = 0.55,
    steps: int = 30,
    cfg: float = 3.0,
) -> bool:
    """Generate AI video via ComfyUI using native Wan 2.1 14B I2V workflow.

    Uses standard ComfyUI nodes (CLIPLoader, UNETLoader, WanImageToVideo, KSampler)
    instead of WanVideoWrapper, which produces higher quality results.

    The input keyframe image is automatically cropped and resized to (width, height)
    to match the model's expected spatial dimensions.

    Args:
        denoise: Scene-type dependent denoise strength (character=0.45, action=0.55, etc.)
        steps: Number of sampling steps (30-35 recommended for production)
        cfg: CFG scale (2.5-3.0 recommended; higher values risk texture explosion)
    """
    import httpx
    import tempfile

    resized_path: Path | None = None
    comfy_url = "http://127.0.0.1:8188"

    try:
        workflow_path = Path("backend/production/workflows/wan22_native_i2v.json")
        if not workflow_path.exists():
            logger.warning("Native workflow file not found: %s", workflow_path)
            return False

        # Load workflow template
        with open(workflow_path, "r", encoding="utf-8") as f:
            template = json.load(f)
        workflow = dict(template["workflow"])
        bindings = template["bindings"]

        # Crop and resize keyframe image to target dimensions
        from PIL import Image as PILImage
        img = PILImage.open(image_path)
        src_w, src_h = img.size
        target_ratio = width / height
        src_ratio = src_w / src_h

        if src_ratio > target_ratio:
            new_w = int(src_h * target_ratio)
            left = (src_w - new_w) // 2
            img_cropped = img.crop((left, 0, left + new_w, src_h))
        else:
            new_h = int(src_w / target_ratio)
            top = (src_h - new_h) // 2
            img_cropped = img.crop((0, top, src_w, top + new_h))

        img_resized = img_cropped.resize((width, height), PILImage.LANCZOS)
        resized_path = image_path.parent / "frame_native_input.png"
        img_resized.save(resized_path, format="PNG")
        logger.info("Resized keyframe %s from %s to %dx%d (portrait crop)",
                    image_path.name, img.size, width, height)

        # Upload image to ComfyUI
        async with httpx.AsyncClient(trust_env=False, timeout=120) as client:
            with open(resized_path, "rb") as img_file:
                upload_resp = await client.post(
                    f"{comfy_url}/upload/image",
                    files={"image": (resized_path.name, img_file, "application/octet-stream")},
                    data={"type": "input", "subfolder": "novel_video"},
                )
                upload_data = upload_resp.json()

        uploaded_name = upload_data.get("name", "")
        uploaded_subfolder = upload_data.get("subfolder", "")
        image_ref = f"{uploaded_subfolder}/{uploaded_name}" if uploaded_subfolder else uploaded_name
        logger.info("Uploaded image to ComfyUI: %s", image_ref)

        # Fill in workflow parameters
        workflow[bindings["image"][0]]["inputs"][bindings["image"][1]] = image_ref
        workflow[bindings["prompt"][0]]["inputs"][bindings["prompt"][1]] = prompt
        workflow[bindings["negative_prompt"][0]]["inputs"][bindings["negative_prompt"][1]] = negative_prompt
        workflow[bindings["seed"][0]]["inputs"][bindings["seed"][1]] = seed
        workflow[bindings["width"][0]]["inputs"][bindings["width"][1]] = width
        workflow[bindings["height"][0]]["inputs"][bindings["height"][1]] = height
        workflow[bindings["frames"][0]]["inputs"][bindings["frames"][1]] = frames
        workflow[bindings["fps"][0]]["inputs"][bindings["fps"][1]] = fps
        # Scene-type dependent parameters (GPT optimization)
        workflow[bindings["denoise"][0]]["inputs"][bindings["denoise"][1]] = denoise
        workflow[bindings["steps"][0]]["inputs"][bindings["steps"][1]] = steps
        workflow[bindings["cfg"][0]]["inputs"][bindings["cfg"][1]] = cfg
        workflow[bindings["filename_prefix"][0]]["inputs"][bindings["filename_prefix"][1]] = f"novel_video/{output_path.stem}"

        # Submit workflow
        async with httpx.AsyncClient(trust_env=False, timeout=30) as client:
            submit_resp = await client.post(
                f"{comfy_url}/prompt",
                json={"prompt": workflow},
            )
            submit_data = submit_resp.json()

        if submit_resp.status_code >= 400:
            logger.warning("ComfyUI rejected workflow: %s", json.dumps(submit_data, indent=2)[:500])
            return False

        prompt_id = submit_data.get("prompt_id", "")
        if not prompt_id:
            logger.warning("No prompt_id from ComfyUI: %s", submit_data)
            return False
        logger.info("Submitted workflow to ComfyUI, prompt_id: %s", prompt_id)

        # Wait for completion (up to 15 minutes)
        import time
        start = time.monotonic()
        timeout = 900
        while time.monotonic() - start < timeout:
            async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                hist_resp = await client.get(f"{comfy_url}/history/{prompt_id}")

            data = hist_resp.json()
            entry = data.get(prompt_id)
            if entry is not None:
                outputs = entry.get("outputs", {})
                status = entry.get("status", {})
                if outputs:
                    # Download the first video artifact
                    for node_output in outputs.values():
                        if not isinstance(node_output, dict):
                            continue
                        for media_kind in ("videos", "images", "gifs"):
                            items = node_output.get(media_kind, [])
                            if not isinstance(items, list):
                                continue
                            for item in items:
                                if isinstance(item, dict) and item.get("filename"):
                                    filename = item["filename"]
                                    subfolder = item.get("subfolder", "")
                                    file_type = item.get("type", "output")
                                    params = {
                                        "filename": filename,
                                        "subfolder": subfolder,
                                        "type": file_type,
                                    }
                                    async with httpx.AsyncClient(trust_env=False, timeout=120) as client:
                                        dl_resp = await client.get(
                                            f"{comfy_url}/view",
                                            params=params,
                                        )
                                    if dl_resp.status_code == 200 and len(dl_resp.content) > 0:
                                        output_path.parent.mkdir(parents=True, exist_ok=True)
                                        output_path.write_bytes(dl_resp.content)
                                        logger.info("Downloaded video: %s (%d KB)",
                                                    filename, len(dl_resp.content) // 1024)
                                        return True
                    logger.warning("ComfyUI completed but no downloadable artifact")
                    return False

                if status.get("status_str") == "error":
                    messages = status.get("messages", [])
                    for msg in reversed(messages):
                        if isinstance(msg, list) and len(msg) == 2 and msg[0] == "execution_error":
                            err = msg[1]
                            logger.warning("ComfyUI execution error: %s (node: %s)",
                                          err.get("exception_message", "Unknown"),
                                          err.get("node_type", "?"))
                            return False
                    logger.warning("ComfyUI job failed: %s", json.dumps(status, indent=2)[:500])
                    return False

                if status.get("completed"):
                    logger.warning("ComfyUI completed but no outputs")
                    return False

            await asyncio.sleep(3)

        logger.warning("ComfyUI job timed out after %ds", timeout)
        return False

    except Exception as exc:
        logger.warning("Native ComfyUI video generation failed: %s", exc, exc_info=True)
        return False
    finally:
        if resized_path and resized_path.exists():
            try:
                resized_path.unlink()
            except Exception:
                pass


async def _generate_video_minimax(
    image_path: Path,
    output_path: Path,
    prompt: str,
    negative_prompt: str = "",
    end_image_path: Path | None = None,
    duration: int = 10,
    resolution: str = "768P",
) -> tuple[bool, Path | None]:
    """Generate AI video via MiniMax H3 API.

    Returns (success, last_frame_path) for tail-frame linking.
    Falls back to (False, None) on error.
    """
    try:
        from backend.integrations.minimax_h3 import MiniMaxH3Provider
        provider = MiniMaxH3Provider()
        success, last_frame = await provider.generate_video(
            image_path=image_path,
            output_path=output_path,
            prompt=prompt,
            negative_prompt=negative_prompt,
            end_image_path=end_image_path,
            duration=duration,
            resolution=resolution,
        )
        if success:
            logger.info("MiniMax H3 video generated: %s (%d KB)",
                        output_path.name,
                        output_path.stat().st_size // 1024 if output_path.exists() else 0)
        return success, last_frame
    except Exception as exc:
        logger.warning("MiniMax H3 video generation failed: %s", exc, exc_info=True)
        return False, None


async def _generate_video_seedance(
    image_path: Path,
    output_path: Path,
    prompt: str,
    negative_prompt: str = "",
    end_image_path: Path | None = None,
    duration: int = 10,
    resolution: str = "1080p",
) -> tuple[bool, Path | None]:
    """Generate AI video via Seedance 2.0 (Volcengine Ark API).

    Returns (success, last_frame_path) for tail-frame linking.
    Falls back to (False, None) on error.
    """
    try:
        from backend.integrations.seedance import SeedanceProvider
        provider = SeedanceProvider()
        success, last_frame = await provider.generate_video(
            image_path=image_path,
            output_path=output_path,
            prompt=prompt,
            negative_prompt=negative_prompt,
            end_image_path=end_image_path,
            duration=duration,
            resolution=resolution,
        )
        if success:
            logger.info("Seedance 2.0 video generated: %s (%d KB)",
                        output_path.name,
                        output_path.stat().st_size // 1024 if output_path.exists() else 0)
        return success, last_frame
    except Exception as exc:
        logger.warning("Seedance 2.0 video generation failed: %s", exc, exc_info=True)
        return False, None


def _check_provider_available(provider_name: str) -> bool:
    """Check if a specific provider is available (API key configured, etc.)."""
    if provider_name in ("wan22", "ltx23"):
        # ComfyUI providers - checked separately in _do_generate_video
        return True
    if provider_name == "minimax_h3":
        try:
            from backend.integrations.minimax_h3 import check_availability
            return check_availability()
        except Exception:
            return False
    if provider_name == "seedance":
        try:
            from backend.integrations.seedance import check_availability
            return check_availability()
        except Exception:
            return False
    return False


async def _do_generate_video(
    request: Request,
    project_id: str,
    shot_id: str,
    project_root: Path,
    plan_data: dict,
    settings: dict,
    force_comfyui: bool = False,
    tail_frame_path: Path | None = None,
) -> dict[str, Any]:
    """Core video generation logic shared by single-shot and batch endpoints.

    1. Updates settings in production_plan.json
    2. Checks keyframe exists
    3. Selects provider via OpenMontage (MiniMax H3 > Seedance > Wan2.1 > FFmpeg)
    4. Applies LocalDrama + Cinema DNA prompt enhancement
    5. Generates video with tail-frame linking for continuity
    6. Registers the video as a workspace asset

    Args:
        tail_frame_path: Previous shot's last frame for visual continuity.
                         If provided, used as the start image instead of the keyframe.
    """
    # Find shot data
    shot_data = None
    for s in plan_data.get("shots", []):
        if s.get("id") == shot_id:
            shot_data = s
            break
    if shot_data is None:
        return {"shot_id": shot_id, "status": "error", "message": f"未找到分镜 {shot_id}"}

    # Check keyframe
    output_dir = project_root / "outputs"
    img_path = output_dir / "images" / shot_id / "frame.png"
    if not img_path.exists():
        return {"shot_id": shot_id, "status": "error", "message": f"分镜 {shot_id} 尚无关键帧"}

    # Prepare video output
    vid_dir = output_dir / "videos" / shot_id
    vid_dir.mkdir(parents=True, exist_ok=True)
    output_path = vid_dir / "ai_clip.mp4"
    if output_path.exists():
        output_path.unlink()  # Remove old video file before regenerating

    # Generation parameters
    # API providers support up to 15s; ComfyUI Wan2.1 limited to ~2s (49 frames)
    video_fps = settings.get("fps", 24)
    shot_prompt = shot_data.get("positive_prompt", "cinematic animation, smooth motion, high quality")
    shot_negative = shot_data.get("negative_prompt", "low quality, blurry, distorted")
    shot_seed = shot_data.get("seed", 42)
    shot_description = shot_data.get("description", "")
    shot_camera = shot_data.get("camera", "")
    shot_narration = shot_data.get("narration", "")

    # === Shot Duration Strategy (GPT optimization) ===
    # Instead of fixed 6s, dynamically calculate duration based on scene type.
    # GPT P0: motion profile drives denoise/frames so the clip has real motion.
    # 前端全局运动档位（0-4）优先覆盖本镜档位，驱动 denoise/帧数/steps/cfg。
    motion_level_override = settings.get("motion_level")
    if isinstance(motion_level_override, int) and 0 <= motion_level_override <= 4:
        shot_data["motion_level"] = motion_level_override
    from backend.video.duration_strategy import (
        classify_scene_type, calculate_shot_duration, get_motion_profile,
    )
    scene_type = classify_scene_type(shot_data)
    motion_profile = get_motion_profile(shot_data)
    shot_idx = next((i for i, s in enumerate(plan_data.get("shots", [])) if s.get("id") == shot_id), 0)
    total_shots_count = len(plan_data.get("shots", []))
    duration_plan = calculate_shot_duration(
        shot_data=shot_data,
        scene_type=scene_type,
        shot_index=shot_idx,
        total_shots=total_shots_count,
        source_frames=motion_profile.frames,
        fps=video_fps,
    )
    shot_duration = duration_plan.final_duration
    interp_multiplier = duration_plan.interpolation_multiplier
    logger.info("Shot %s duration strategy: type=%s, duration=%.1fs, interp=%dx (%s)",
                shot_id, scene_type, shot_duration, interp_multiplier,
                ", ".join(duration_plan.adjustments) if duration_plan.adjustments else "no adjustments")

    # === Integration Pipeline: OpenMontage > LocalMiniDrama > Cinema DNA ===

    # 1. OpenMontage: Select best video provider using 7-dimensional scoring
    selected_provider, provider_score = _select_provider_with_openmontage(
        shot_description=shot_description,
        camera=shot_camera,
        narration=shot_narration,
    )
    logger.info("Shot %s provider: %s (OpenMontage)", shot_id, selected_provider)

    # 2. LocalMiniDrama: Enhance prompt with professional shot type, angle, movement
    enhanced_pos = _enhance_prompt_with_localdrama(
        prompt=shot_prompt,
        shot_description=shot_description,
        camera=shot_camera,
        shot_id=shot_id,
    )

    # 3. Cinema DNA (电影感): Add cinematic composition, lighting, color grading
    cinema_pos, cinema_neg = _enhance_prompt_with_cinema_dna(
        prompt=enhanced_pos,
        shot_description=shot_description,
        camera=shot_camera,
        narration=shot_narration,
    )
    enhanced_pos = cinema_pos
    if cinema_neg:
        shot_negative = f"{shot_negative}, {cinema_neg}" if shot_negative else cinema_neg

    # GPT P0: 注入运动语义（Action/Camera/Motion），让视频模型真正生成动作
    MOTION_PROMPT = (
        "natural body movement, subtle breathing, realistic motion, "
        "dynamic pose transition, smooth animation"
    )
    if "natural body movement" not in enhanced_pos.lower():
        enhanced_pos = f"{enhanced_pos}, {MOTION_PROMPT}"

    logger.info("Shot %s enhanced prompt: %s...", shot_id, enhanced_pos[:120])

    # Determine start image: use tail frame from previous shot if available
    start_image = tail_frame_path if tail_frame_path and tail_frame_path.exists() else img_path
    if tail_frame_path and tail_frame_path.exists():
        logger.info("Shot %s using tail frame from previous shot: %s", shot_id, tail_frame_path.name)

    # Determine target keyframe as end_image for providers that support first+last frame
    end_image = img_path  # The shot's own keyframe serves as the target end frame

    # === Provider Dispatch ===
    used_provider = None
    last_frame_path: Path | None = None
    quality_report = None  # GPT P0: 运动/质量门禁结果

    # Try MiniMax H3 first (highest quality, up to 15s, supports first+last frame)
    if selected_provider == "minimax_h3" and _check_provider_available("minimax_h3"):
        api_duration = min(int(shot_duration), 15)
        logger.info("Generating AI video for %s via MiniMax H3 (%ds, tail-frame=%s)",
                    shot_id, api_duration, tail_frame_path is not None)
        success, last_frame = await _generate_video_minimax(
            image_path=start_image,
            output_path=output_path,
            prompt=enhanced_pos,
            negative_prompt=shot_negative,
            end_image_path=end_image,
            duration=api_duration,
            resolution="768P",
        )
        if success:
            used_provider = "MiniMax H3"
            last_frame_path = last_frame
        else:
            logger.warning("MiniMax H3 failed for %s, trying fallback", shot_id)

    # Try Seedance 2.0 (Volcengine Ark, up to 15s, supports first+last frame)
    if used_provider is None and selected_provider in ("minimax_h3", "seedance") and _check_provider_available("seedance"):
        api_duration = min(int(shot_duration), 15)
        logger.info("Generating AI video for %s via Seedance 2.0 (%ds, tail-frame=%s)",
                    shot_id, api_duration, tail_frame_path is not None)
        success, last_frame = await _generate_video_seedance(
            image_path=start_image,
            output_path=output_path,
            prompt=enhanced_pos,
            negative_prompt=shot_negative,
            end_image_path=end_image,
            duration=api_duration,
            resolution="1080p",
        )
        if success:
            used_provider = "Seedance 2.0"
            last_frame_path = last_frame
        else:
            logger.warning("Seedance 2.0 failed for %s, trying fallback", shot_id)

    # Try ComfyUI Wan 2.1 (local, free)
    comfy_available = await _check_comfyui_available()
    # GPT P0: motion-aware sampling parameters (真实运动优先)
    # denoise 是图生视频的"改动强度"：之前被硬钳制在 0.20-0.32 导致输出
    # 几乎等于输入关键帧 → 定帧图。现在按镜头运动档位取 0.45-0.65。
    # 帧数也从 49 提升到 81+，让动作有足够的生成空间。
    gen_width = 480
    gen_height = 832
    video_frames = motion_profile.frames
    frontend_frames = int(settings.get("video_frames", 0) or 0)
    if frontend_frames > video_frames:
        video_frames = frontend_frames
    shot_denoise = motion_profile.denoise
    shot_steps = motion_profile.steps
    shot_cfg = motion_profile.cfg

    # Add comprehensive anti-mosaic negative prompts
    ANTI_MOSAIC_NEG = (
        "mosaic, pixelated, blocky, low quality, worst quality, blurry, distorted, "
        "deformed, bad anatomy, extra limbs, watermark, text, signature, "
        "jpeg artifacts, compressed, noise, grain, artifacts, censored, "
        "duplicate, split screen, collage, grid pattern, checkered"
    )
    shot_negative = f"{shot_negative}, {ANTI_MOSAIC_NEG}" if shot_negative else ANTI_MOSAIC_NEG

    # GPT P0: 明确禁止静态帧语义，避免模型输出"定帧图"
    STATIC_FRAME_NEG = (
        "static image, still frame, freeze, photo, no movement, "
        "slideshow, duplicate frames, frozen face, rigid body"
    )
    shot_negative = f"{shot_negative}, {STATIC_FRAME_NEG}" if shot_negative else STATIC_FRAME_NEG

    if used_provider is None and selected_provider in ("wan22", "ltx23") and (comfy_available or force_comfyui):
        logger.info("Generating AI video for %s via ComfyUI (Wan 2.1 14B, %dx%d, %d frames, denoise=%.2f, steps=%d, cfg=%.1f, motion=%d)",
                    shot_id, gen_width, gen_height, video_frames, shot_denoise, shot_steps, shot_cfg,
                    settings.get("motion_bucket_id", 127))
        success = await _generate_video_native(
            image_path=start_image,
            output_path=output_path,
            prompt=enhanced_pos,
            negative_prompt=shot_negative,
            seed=shot_seed,
            width=gen_width,
            height=gen_height,
            frames=video_frames,
            fps=video_fps,
            denoise=shot_denoise,
            steps=shot_steps,
            cfg=shot_cfg,
        )
        if success:
            used_provider = "ComfyUI (Wan 2.1 14B)"
            logger.info("ComfyUI video generation succeeded for %s (%d KB)",
                        shot_id, output_path.stat().st_size // 1024)

            # Frame interpolation: extend the raw clip to target duration.
            # GPT P0: 原始镜头帧数已提升（81+），只有当目标时长超过原始时长才插帧；
            # multiplier<=1 时直接保留原始镜头，不做"复制帧"式伪延长。
            try:
                from backend.video.frame_interp import interpolate_frames
                if interp_multiplier <= 1:
                    logger.info("Shot %s: raw clip covers target duration (%.1fs), skipping interpolation",
                                shot_id, shot_duration)
                else:
                    extended_path = vid_dir / "ai_clip_extended.mp4"
                    final_path = interpolate_frames(
                        input_path=output_path,
                        output_path=extended_path,
                        target_fps=video_fps,
                        multiplier=interp_multiplier,
                    )
                    if final_path and final_path != output_path and final_path.exists():
                        # Replace original with extended version
                        output_path.unlink()
                        final_path.rename(output_path)
                        logger.info("Video extended via frame interpolation: %s (%dx, %d KB)",
                                    shot_id, interp_multiplier, output_path.stat().st_size // 1024)
            except Exception as exc:
                logger.debug("Frame interpolation skipped: %s", exc)

            # === Video Intelligence Layer (GPT Sprint upgrade) ===
            # Agent 2: Quality Judge - evaluate video quality with multi-indicator fusion
            # Agent 4: Retry Optimization - auto-retry with parameter adjustment if quality fails
            try:
                from backend.video.intelligence_layer import (
                    QualityJudgeAgent, RetryOptimizationAgent,
                )
                from backend.video.retry_controller import get_retry_controller

                judge = QualityJudgeAgent()
                retry_agent = RetryOptimizationAgent(max_retries=2)

                quality_report, quality_issues = judge.evaluate(output_path, shot_id)
                logger.info("Shot %s quality: %s (score=%.1f, consistency=%.2f, issues=%s)",
                            shot_id, quality_report.verdict,
                            quality_report.overall_score,
                            quality_report.temporal_consistency,
                            quality_issues or "none")

                if not quality_report.passed:
                    logger.warning("Shot %s FAILED quality gate: %s",
                                   shot_id, quality_report.verdict)
                    for rec in quality_report.recommendations:
                        logger.info("  Recommendation: %s", rec)

                    # Agent 4: Check if retry is worthwhile
                    if retry_agent.should_retry(shot_id, quality_report, min_score=35):
                        logger.info("Shot %s: attempting automatic retry with adjusted parameters",
                                    shot_id)

                        # Get adjusted parameters
                        adjusted_data, adjustments = retry_agent.get_retry_params(
                            shot_data, quality_issues
                        )
                        logger.info("Shot %s retry adjustments: %s",
                                    shot_id, ", ".join(adjustments))

                        # Retry generation with adjusted parameters
                        retry_denoise = adjusted_data.get("denoise", shot_denoise)
                        retry_steps = adjusted_data.get("steps", shot_steps)
                        retry_cfg = adjusted_data.get("cfg", shot_cfg)
                        retry_prompt = adjusted_data.get("positive_prompt", enhanced_pos)
                        retry_frames = int(adjusted_data.get("frames", video_frames) or video_frames)

                        retry_success = await _generate_video_native(
                            image_path=start_image,
                            output_path=output_path,
                            prompt=retry_prompt,
                            negative_prompt=shot_negative,
                            seed=shot_seed,
                            width=gen_width,
                            height=gen_height,
                            frames=retry_frames,
                            fps=video_fps,
                            denoise=retry_denoise,
                            steps=retry_steps,
                            cfg=retry_cfg,
                        )

                        if retry_success:
                            # Re-evaluate the retried video
                            retry_report, retry_issues = judge.evaluate(
                                output_path, f"{shot_id}_retry"
                            )
                            logger.info("Shot %s retry quality: %s (score=%.1f)",
                                        shot_id, retry_report.verdict,
                                        retry_report.overall_score)

                            retry_agent.record_result(
                                shot_id=shot_id,
                                adjustments=adjustments,
                                quality_score=retry_report.overall_score,
                                passed=retry_report.passed,
                                failure_reasons=retry_issues,
                            )

                            if retry_report.passed or retry_report.overall_score > quality_report.overall_score:
                                logger.info("Shot %s: retry improved quality (%.1f -> %.1f), accepting",
                                            shot_id, quality_report.overall_score,
                                            retry_report.overall_score)
                                quality_report = retry_report
                            else:
                                logger.warning("Shot %s: retry did not improve quality, keeping original",
                                              shot_id)
                        else:
                            logger.warning("Shot %s: retry generation failed", shot_id)
                            retry_agent.record_result(
                                shot_id=shot_id,
                                adjustments=adjustments,
                                quality_score=0.0,
                                passed=False,
                                failure_reasons=["generation_failed"],
                            )
                    else:
                        logger.info("Shot %s: retry not recommended (score=%.1f or max retries reached)",
                                    shot_id, quality_report.overall_score)
            except Exception as exc:
                logger.debug("Video Intelligence Layer evaluation skipped: %s", exc)

            # GPT P0: 质量/运动门禁 —— 定帧图等未通过的视频禁止交付为"完成"
            if quality_report is not None and not quality_report.passed:
                return {
                    "shot_id": shot_id,
                    "status": "error",
                    "message": (
                        f"分镜 {shot_id} 视频未通过质量/运动门禁"
                        f"(score={quality_report.overall_score:.1f}, 问题: "
                        f"{', '.join(quality_report.issues) if quality_report.issues else '未知'})。"
                        "已停止而非交付定帧假视频，请调整参数后重试。"
                    ),
                    "issues": quality_report.issues,
                }

            # Agent 3: Continuity - extract tail frame for next shot
            try:
                from backend.video.tailframe import extract_last_frame
                lf_path = output_dir / "videos" / shot_id / "tail_frame.png"
                last_frame_path = extract_last_frame(output_path, lf_path)
            except Exception as exc:
                logger.debug("Tail frame extraction skipped: %s", exc)
        else:
            logger.warning("ComfyUI video generation failed for %s (无 Ken Burns 兜底，镜头将失败)", shot_id)

    # GPT P0: 禁止 Ken Burns 静态兜底 —— 失败即失败，不允许"假成功"。
    # 定帧图不是 AI 漫剧视频，必须让用户看到错误并重试/调整参数。
    if used_provider is None:
        return {
            "shot_id": shot_id,
            "status": "error",
            "message": (
                f"分镜 {shot_id} AI 视频生成失败：所有真实视频提供器"
                "(ComfyUI Wan/LTX、MiniMax、Seedance) 均失败或不可用。"
                "已停止而非生成 Ken Burns 定帧假视频。请检查 ComfyUI 与参数后重试。"
            ),
        }

    # Register asset
    job_id = _find_latest_job_id(request, project_id)
    if job_id:
        _register_video_asset(request, job_id, project_id, shot_id, output_path)

    method = f"{used_provider} + OpenMontage + LocalDrama + Cinema DNA"
    file_size = output_path.stat().st_size if output_path.exists() else 0

    return {
        "shot_id": shot_id,
        "status": "completed",
        "message": f"分镜 {shot_id} AI视频已生成 ({method}, {file_size // 1024}KB)",
        "method": method,
        "provider": used_provider,
        "file_size": file_size,
        "video_path": str(output_path),
        "last_frame_path": str(last_frame_path) if last_frame_path else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/{project_id}", response_model=CreatorProjectResponse)
async def get_creator_project(project_id: str, request: Request) -> CreatorProjectResponse:
    """Get all shots with their keyframe and AI video status for the Creator Studio."""
    config = _get_config(request)

    project_root = Path(config.project_root) / project_id if config else Path("projects") / project_id
    plan_path = project_root / "production_plan.json"

    if not plan_path.exists():
        raise HTTPException(status_code=404, detail="未找到生产计划")

    plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    shots_data = plan_data.get("shots", [])
    settings = plan_data.get("settings", {})

    output_dir = project_root / "outputs"
    shots: list[ShotInfo] = []

    for s in shots_data:
        sid = s["id"]
        img_path = output_dir / "images" / sid / "frame.png"
        vid_path = output_dir / "videos" / sid / "ai_clip.mp4"

        has_keyframe = img_path.exists()
        has_ai_video = vid_path.exists()

        keyframe_url = f"/api/workspace/{project_id}/assets?shot_id={sid}&kind=image&active=true" if has_keyframe else ""
        ai_video_url = f"/api/creator/{project_id}/shots/{sid}/video-file" if has_ai_video else ""

        if has_ai_video:
            ai_video_status = "completed"
        elif has_keyframe:
            ai_video_status = "ready"
        else:
            ai_video_status = "pending"

        shots.append(ShotInfo(
            shot_id=sid,
            shot_number=s.get("shot_number", 0),
            description=s.get("description", ""),
            narration=s.get("narration", ""),
            duration=s.get("duration", 6.0),
            camera=s.get("camera", ""),
            positive_prompt=s.get("positive_prompt", ""),
            negative_prompt=s.get("negative_prompt", ""),
            seed=s.get("seed", 0),
            transition=s.get("transition", "fade"),
            has_keyframe=has_keyframe,
            keyframe_url=keyframe_url,
            has_ai_video=has_ai_video,
            ai_video_url=ai_video_url,
            ai_video_status=ai_video_status,
        ))

    return CreatorProjectResponse(
        project_id=project_id,
        title=plan_data.get("input_contract", {}).get("title", ""),
        total_shots=len(shots),
        shots=shots,
        settings=settings,
    )


@router.post("/{project_id}/shots/{shot_id}/regenerate-image")
async def regenerate_shot_image(
    project_id: str,
    shot_id: str,
    body: RegenerateImageRequest,
    request: Request,
) -> dict[str, Any]:
    """Regenerate a specific shot's keyframe image."""
    config = _get_config(request)
    project_root = Path(config.project_root) / project_id if config else Path("projects") / project_id
    plan_path = project_root / "production_plan.json"

    if not plan_path.exists():
        raise HTTPException(status_code=404, detail="未找到生产计划")

    plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    shot = None
    for s in plan_data.get("shots", []):
        if s.get("id") == shot_id:
            shot = s
            break

    if shot is None:
        raise HTTPException(status_code=404, detail=f"未找到分镜 {shot_id}")

    if body.prompt:
        shot["positive_prompt"] = body.prompt
    if body.negative_prompt:
        shot["negative_prompt"] = body.negative_prompt
    if body.seed is not None:
        shot["seed"] = body.seed

    plan_path.write_text(json.dumps(plan_data, ensure_ascii=False, indent=2), encoding="utf-8")

    output_dir = project_root / "outputs"
    img_dir = output_dir / "images" / shot_id
    img_dir.mkdir(parents=True, exist_ok=True)

    return {
        "status": "accepted",
        "shot_id": shot_id,
        "message": f"分镜 {shot_id} 的关键帧参数已更新，将在下次生产时生效",
        "prompt": shot.get("positive_prompt", "")[:100],
        "seed": shot.get("seed", 0),
    }


@router.post("/{project_id}/shots/{shot_id}/generate-video")
async def generate_shot_video(
    project_id: str,
    shot_id: str,
    body: GenerateVideoRequest,
    request: Request,
) -> dict[str, Any]:
    """Generate AI video for a specific shot from its keyframe.

    Uses real AI video providers only (ComfyUI Wan/LTX, MiniMax, Seedance).
    Ken Burns 静态兜底已移除：失败返回 error，不会生成定帧假视频。
    """
    project_root = _resolve_project_root(request, project_id)
    plan_path = project_root / "production_plan.json"

    if not plan_path.exists():
        raise HTTPException(status_code=404, detail="未找到生产计划")

    plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    settings = plan_data.get("settings", {})

    # Update video generation settings
    settings["ai_video"] = body.use_ai_video
    settings["motion_bucket_id"] = body.motion_bucket_id
    if body.motion_level is not None:
        settings["motion_level"] = body.motion_level
    settings["video_frames"] = body.frames
    settings["fps"] = body.fps
    plan_data["settings"] = settings
    plan_path.write_text(json.dumps(plan_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Actually generate the video
    result = await _do_generate_video(
        request, project_id, shot_id, project_root, plan_data, settings,
    )
    return result


@router.post("/{project_id}/generate-all-videos")
async def generate_all_videos(
    project_id: str,
    request: Request,
) -> dict[str, Any]:
    """Batch generate AI videos for all shots that have keyframes but no video yet.

    One-click generation endpoint - processes all eligible shots sequentially.
    """
    project_root = _resolve_project_root(request, project_id)
    plan_path = project_root / "production_plan.json"

    if not plan_path.exists():
        raise HTTPException(status_code=404, detail="未找到生产计划")

    plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    settings = plan_data.get("settings", {})
    shots_data = plan_data.get("shots", [])
    output_dir = project_root / "outputs"

    # Find all shots with keyframes
    eligible_shots = []
    skipped = []
    for s in shots_data:
        sid = s.get("id", "")
        img_path = output_dir / "images" / sid / "frame.png"
        vid_path = output_dir / "videos" / sid / "ai_clip.mp4"

        if not img_path.exists():
            skipped.append({"shot_id": sid, "reason": "无关键帧"})
        else:
            eligible_shots.append(sid)

    if not eligible_shots:
        return {
            "status": "completed",
            "project_id": project_id,
            "total": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": skipped,
            "results": [],
            "message": "没有需要生成的分镜（所有有关键帧的分镜均已生成视频）",
        }

    # Generate videos sequentially with tail-frame linking + Character Memory Anchor
    from backend.video.character_anchor import CharacterMemoryAnchor

    anchor_dir = output_dir / "anchors"
    char_anchor = CharacterMemoryAnchor(work_dir=anchor_dir)

    # Register the primary character from the first shot's keyframe
    first_img = output_dir / "images" / eligible_shots[0] / "frame.png"
    if first_img.exists():
        first_shot_data = next((s for s in shots_data if s.get("id") == eligible_shots[0]), {})
        characters = first_shot_data.get("characters", [])
        if characters and isinstance(characters, list) and len(characters) > 0:
            char_name = characters[0] if isinstance(characters[0], str) else characters[0].get("name", "主角")
            char_id = "char_01"
        else:
            char_name = "主角"
            char_id = "char_01"
        char_anchor.register_character(
            character_id=char_id,
            character_name=char_name,
            anchor_image_path=first_img,
            first_appearance_shot=eligible_shots[0],
        )
        logger.info("Character Memory Anchor registered: %s from %s", char_name, eligible_shots[0])

    results = []
    succeeded = 0
    failed = 0
    prev_tail_frame: Path | None = None

    for i, sid in enumerate(eligible_shots):
        logger.info("=" * 60)
        logger.info("[%d/%d] Processing %s (tail-frame linking: %s, anchor: %s)",
                    i + 1, len(eligible_shots), sid,
                    prev_tail_frame is not None,
                    "refresh" if i > 0 and i % 5 == 0 else "normal")

        # Use Character Memory Anchor to determine start image
        # This periodically refreshes the character anchor to prevent visual drift
        effective_tail = prev_tail_frame
        if char_anchor._anchors:
            try:
                effective_tail = char_anchor.get_start_image(
                    shot_id=sid,
                    tail_frame=prev_tail_frame,
                    shot_index=i,
                    refresh_interval=5,  # Refresh every 5 shots
                )
                if effective_tail != prev_tail_frame:
                    logger.info("  Character anchor applied for %s (blended/refreshed)", sid)
            except Exception:
                effective_tail = prev_tail_frame  # Fallback to plain tail frame

        result = await _do_generate_video(
            request, project_id, sid, project_root, plan_data, settings,
            tail_frame_path=effective_tail,
        )
        results.append(result)

        if result.get("status") == "completed":
            succeeded += 1
            # Extract tail frame for next shot continuity
            last_frame_str = result.get("last_frame_path")
            if last_frame_str:
                prev_tail_frame = Path(last_frame_str)
                logger.info("  Tail frame captured for next shot: %s", prev_tail_frame.name)
            else:
                # Fallback: extract tail frame via quality-scored Handoff selector
                # (GPT P2: 不用机械最后一帧，而选尾部最佳交接帧)
                try:
                    from backend.video.tailframe import select_handoff_frame
                    vid_path = output_dir / "videos" / sid / "ai_clip.mp4"
                    if vid_path.exists():
                        handoff_dir = output_dir / "videos" / sid / "handoff"
                        handoff_dir.mkdir(parents=True, exist_ok=True)
                        prev_tail_frame = select_handoff_frame(vid_path, handoff_dir)
                        if prev_tail_frame:
                            logger.info("  Handoff frame selected: %s", prev_tail_frame.name)
                    else:
                        prev_tail_frame = None
                except Exception as exc:
                    logger.warning("  Failed to select handoff frame: %s", exc)
                    prev_tail_frame = None
        else:
            failed += 1
            # Tail-frame chain recovery: try to use the previous successful shot's keyframe
            # as the start image for the next shot, instead of completely resetting
            logger.warning("  Shot %s failed, attempting chain recovery for next shot", sid)
            try:
                # Use the failed shot's own keyframe as fallback start for next shot
                next_keyframe = output_dir / "images" / sid / "frame.png"
                if next_keyframe.exists():
                    # Extract a tail frame from the keyframe itself (just copy it)
                    recovery_frame = output_dir / "videos" / sid / "tail_frame_recovery.png"
                    import shutil
                    shutil.copy2(next_keyframe, recovery_frame)
                    prev_tail_frame = recovery_frame
                    logger.info("  Chain recovery: using keyframe as tail frame for next shot")
                else:
                    prev_tail_frame = None
            except Exception:
                prev_tail_frame = None

    return {
        "status": "completed",
        "project_id": project_id,
        "total": len(eligible_shots),
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "results": results,
        "tail_frame_linking": "enabled",
        "message": f"批量生成完成: {succeeded} 成功, {failed} 失败, {len(skipped)} 跳过 (尾帧链接已启用)",
    }


@router.get("/{project_id}/shots/{shot_id}/video-file")
async def serve_shot_video(
    project_id: str,
    shot_id: str,
    request: Request,
):
    """Serve the generated AI video file directly from the output directory."""
    project_root = _resolve_project_root(request, project_id)
    vid_path = project_root / "outputs" / "videos" / shot_id / "ai_clip.mp4"

    if not vid_path.exists():
        raise HTTPException(status_code=404, detail=f"分镜 {shot_id} 的视频尚未生成")

    return FileResponse(
        path=str(vid_path),
        media_type="video/mp4",
        filename=f"{shot_id}_ai_video.mp4",
    )


@router.put("/{project_id}/settings")
async def update_creator_settings(
    project_id: str,
    body: UpdateSettingsRequest,
    request: Request,
) -> dict[str, Any]:
    """Update AI generation settings for the project."""
    project_root = _resolve_project_root(request, project_id)
    plan_path = project_root / "production_plan.json"

    if not plan_path.exists():
        raise HTTPException(status_code=404, detail="未找到生产计划")

    plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    settings = plan_data.get("settings", {})

    settings["motion_bucket_id"] = body.motion_bucket_id
    settings["motion_level"] = body.motion_level
    settings["video_frames"] = body.video_frames
    settings["ai_video"] = body.ai_video
    settings["character_consistency"] = body.character_consistency
    settings["provider"] = body.provider

    plan_data["settings"] = settings
    plan_path.write_text(json.dumps(plan_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "updated",
        "project_id": project_id,
        "settings": settings,
    }


@router.get("/{project_id}/comfyui-status")
async def comfyui_status(request: Request) -> dict[str, Any]:
    """Check if ComfyUI is available for AI generation."""
    comfy_url = "http://127.0.0.1:8188"

    try:
        import httpx
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.get(f"{comfy_url}/system_stats", timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "available": True,
                    "url": comfy_url,
                    "system": data.get("data", {}),
                }
    except Exception:
        pass

    return {
        "available": False,
        "url": comfy_url,
        "message": "ComfyUI 未运行，AI 视频生成将失败（已禁用 Ken Burns 定帧兜底）",
    }


@router.get("/{project_id}/providers")
async def get_provider_status(project_id: str, request: Request) -> dict[str, Any]:
    """Get availability status of all video generation providers."""
    comfy_available = await _check_comfyui_available()
    minimax_ok = _check_provider_available("minimax_h3")
    seedance_ok = _check_provider_available("seedance")

    providers = []
    for name, available, desc in [
        ("minimax_h3", minimax_ok, "MiniMax H3 (2K/15s, 原生音频, 尾帧链接)"),
        ("seedance", seedance_ok, "Seedance 2.0 (1080p/15s, 尾帧链接)"),
        ("wan22", comfy_available, "Wan 2.1 14B via ComfyUI (480p/3-4s, 本地免费)"),
        ("ltx23", comfy_available, "LTX-Video via ComfyUI (本地免费)"),
        ("ken_burns", False, "FFmpeg Ken Burns (已禁用 — 定帧静态缩放不是 AI 视频)"),
    ]:
        providers.append({
            "name": name,
            "available": available,
            "description": desc,
            "supports_tail_frame": name in ("minimax_h3", "seedance"),
            "supports_long_duration": name in ("minimax_h3", "seedance"),
            "max_duration_s": 15 if name in ("minimax_h3", "seedance") else (4 if name in ("wan22", "ltx23") else 0),
        })

    # Determine which provider will be used
    from backend.integrations.openmontage import registry, TaskParams, ProviderStatus
    for p in providers:
        registry.set_provider_status(
            p["name"],
            ProviderStatus.AVAILABLE if p["available"] else ProviderStatus.UNAVAILABLE,
        )

    task = TaskParams(
        task_type="cinematic",
        intent="default",
        style_keywords=["cinematic"],
        motion_required=True,
        asset_type="video",
        shot_id="",
    )
    best = registry.select_best_provider("cinematic", task)

    return {
        "providers": providers,
        "selected": best,
        "tail_frame_linking": "enabled",
        "message": f"当前最佳供应商: {best}" if best else "无可用供应商",
    }


@router.get("/{project_id}/episodes")
async def list_episodes(project_id: str, request: Request) -> dict[str, Any]:
    """List episodes with their shots and video status.

    Groups shots into episodes based on the production plan's episode structure.
    If no episode structure exists, treats all shots as one episode.
    """
    project_root = _resolve_project_root(request, project_id)
    plan_path = project_root / "production_plan.json"

    if not plan_path.exists():
        raise HTTPException(status_code=404, detail="未找到生产计划")

    plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    shots_data = plan_data.get("shots", [])
    output_dir = project_root / "outputs"

    # Group shots by episode (default: all in one episode)
    episodes_map: dict[str, list[dict]] = {}
    for s in shots_data:
        sid = s.get("id", "")
        ep_id = s.get("episode", "ep_01")
        if ep_id not in episodes_map:
            episodes_map[ep_id] = []
        img_path = output_dir / "images" / sid / "frame.png"
        vid_path = output_dir / "videos" / sid / "ai_clip.mp4"
        episodes_map[ep_id].append({
            "shot_id": sid,
            "description": s.get("description", ""),
            "duration": s.get("duration", 6.0),
            "has_keyframe": img_path.exists(),
            "has_video": vid_path.exists(),
            "video_size_kb": vid_path.stat().st_size // 1024 if vid_path.exists() else 0,
        })

    episodes = []
    for ep_id, ep_shots in episodes_map.items():
        total_duration = sum(s["duration"] for s in ep_shots)
        completed = sum(1 for s in ep_shots if s["has_video"])
        episodes.append({
            "episode_id": ep_id,
            "title": f"第{ep_id.replace('ep_', '')}集",
            "total_shots": len(ep_shots),
            "completed_shots": completed,
            "total_duration_s": total_duration,
            "total_duration_str": f"{int(total_duration // 60)}分{int(total_duration % 60)}秒",
            "shots": ep_shots,
        })

    total_duration = sum(e["total_duration_s"] for e in episodes)
    return {
        "project_id": project_id,
        "episodes": episodes,
        "total_episodes": len(episodes),
        "total_shots": sum(e["total_shots"] for e in episodes),
        "total_completed": sum(e["completed_shots"] for e in episodes),
        "total_duration_s": total_duration,
        "total_duration_str": f"{int(total_duration // 3600)}小时{int((total_duration % 3600) // 60)}分",
    }


@router.post("/{project_id}/episodes/{episode_id}/compose")
async def compose_episode_video(
    project_id: str,
    episode_id: str,
    request: Request,
) -> dict[str, Any]:
    """Compose all shots in an episode into a single video with crossfade transitions.

    Uses VideoComposer.compose_episode() which normalises all clips to a
    uniform format and applies crossfade transitions at shot boundaries for
    smooth continuity — especially important for tail-frame-linked shots.
    """
    project_root = _resolve_project_root(request, project_id)
    plan_path = project_root / "production_plan.json"

    if not plan_path.exists():
        raise HTTPException(status_code=404, detail="未找到生产计划")

    plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    shots_data = plan_data.get("shots", [])
    output_dir = project_root / "outputs"

    # Filter shots by episode
    ep_shots = [s for s in shots_data if s.get("episode", "ep_01") == episode_id]
    if not ep_shots:
        return {"status": "error", "message": f"未找到剧集 {episode_id}"}

    # Collect video paths for existing clips
    video_paths: list[Path] = []
    missing: list[str] = []
    for s in ep_shots:
        sid = s.get("id", "")
        vid_path = output_dir / "videos" / sid / "ai_clip.mp4"
        if vid_path.exists():
            video_paths.append(vid_path)
        else:
            missing.append(sid)

    if missing:
        return {
            "status": "error",
            "message": f"缺少视频: {', '.join(missing)}",
            "missing_shots": missing,
        }

    # Use VideoComposer for episode-level composition with transitions
    from backend.video.composer import VideoComposer

    ep_dir = output_dir / "episodes" / episode_id
    ep_dir.mkdir(parents=True, exist_ok=True)
    output_path = ep_dir / "episode.mp4"

    composer = VideoComposer(output_dir=output_dir)

    try:
        composer.compose_episode(
            video_paths=video_paths,
            output_path=output_path,
            transition="fade",
            transition_duration=0.5,
            target_width=1080,
            target_height=1920,
            fps=24,
        )
    except FileNotFoundError as exc:
        return {"status": "error", "message": f"视频文件缺失: {exc}"}
    except Exception as exc:
        logger.error("Episode composition failed: %s", exc, exc_info=True)
        return {"status": "error", "message": f"视频合成失败: {exc}"}

    if output_path.exists():
        file_size = output_path.stat().st_size
        return {
            "status": "completed",
            "episode_id": episode_id,
            "output_path": str(output_path),
            "file_size": file_size,
            "file_size_str": f"{file_size // (1024*1024)}MB" if file_size > 1024*1024 else f"{file_size // 1024}KB",
            "shot_count": len(video_paths),
            "transition": "crossfade (0.5s)",
            "message": f"剧集 {episode_id} 合成完成 ({len(video_paths)} 个分镜, {file_size // 1024}KB, 含转场效果)",
        }
    else:
        return {"status": "error", "message": "视频合成失败"}


@router.post("/{project_id}/expand-shots")
async def expand_shots(
    project_id: str,
    body: dict[str, Any],
    request: Request,
) -> dict[str, Any]:
    """Expand the production plan with additional shots for longer episodes.

    Request body:
    {
        "target_shots": 60,       // Total desired shot count
        "episode_id": "ep_01",   // Episode to assign new shots to
        "duration_per_shot": 10   // Duration per shot in seconds
    }
    """
    project_root = _resolve_project_root(request, project_id)
    plan_path = project_root / "production_plan.json"

    if not plan_path.exists():
        raise HTTPException(status_code=404, detail="未找到生产计划")

    plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    shots = plan_data.get("shots", [])
    current_count = len(shots)
    target_count = body.get("target_shots", 60)
    episode_id = body.get("episode_id", "ep_01")
    duration = body.get("duration_per_shot", 10.0)

    if target_count <= current_count:
        return {
            "status": "no_change",
            "message": f"当前已有 {current_count} 个分镜，目标 {target_count} 无需扩展",
        }

    # Get the last shot as template
    last_shot = shots[-1] if shots else {}
    new_shots = []

    for i in range(current_count + 1, target_count + 1):
        shot_id = f"shot_{i:02d}"
        new_shot = {
            "id": shot_id,
            "shot_number": i,
            "description": f"扩展分镜 {i} - 待补充场景描述",
            "narration": "",
            "duration": duration,
            "camera": "medium shot, subtle movement",
            "characters": last_shot.get("characters", []),
            "dialogue": "",
            "sfx": "",
            "positive_prompt": last_shot.get("positive_prompt", "cinematic shot, high quality"),
            "negative_prompt": last_shot.get("negative_prompt", "low quality, blurry"),
            "transition": "crossfade",
            "seed": last_shot.get("seed", 42) + i,
            "episode": episode_id,
        }
        new_shots.append(new_shot)

    # Add episode field to existing shots if missing
    for s in shots:
        if "episode" not in s:
            s["episode"] = episode_id

    shots.extend(new_shots)
    plan_data["shots"] = shots

    # Update settings
    settings = plan_data.get("settings", {})
    settings["total_episodes"] = 1
    settings["target_duration_per_episode_s"] = target_count * duration
    plan_data["settings"] = settings

    plan_path.write_text(json.dumps(plan_data, ensure_ascii=False, indent=2), encoding="utf-8")

    total_duration = sum(s.get("duration", duration) for s in shots)
    return {
        "status": "expanded",
        "project_id": project_id,
        "previous_count": current_count,
        "new_count": target_count,
        "added": target_count - current_count,
        "total_duration_s": total_duration,
        "total_duration_str": f"{int(total_duration // 60)}分{int(total_duration % 60)}秒",
        "message": f"分镜已扩展: {current_count} → {target_count} (总时长 {int(total_duration // 60)}分{int(total_duration % 60)}秒)",
    }

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
import traceback
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.orchestration.automation import (
    EXECUTION_TO_UI_STAGE,
    QualityGateError,
    StageDecision,
    decide_after_quality_failure,
    decide_after_success,
)
from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.enums import JobStatus, StepStatus, JOB_TERMINAL
from backend.orchestration.repository import JobRepository
from backend.orchestration.template_provider_policy import (
    resolve_video_provider_plan,
    stage_provider_is_required,
)
from backend.workspace.models import StageAutomation, StageKey
from backend.workspace.repository import WorkspaceRepository

logger = logging.getLogger(__name__)


def _formal_package_hash(package) -> str:
    """Canonical scheduler/worker binding for an immutable H3 package."""
    encoded = json.dumps(
        package.model_dump(mode="json"), ensure_ascii=False,
        sort_keys=True, separators=(",", ":"),
    )
    from hashlib import sha256
    return sha256(encoded.encode("utf-8")).hexdigest()


class FormalNovelVideoWorker:
    """Run formal novel-video segments without changing legacy orchestration semantics."""

    def __init__(self, repository, router) -> None:
        self.repository = repository
        self.router = router

    async def generate_segment(
        self, run_id: str, request: Any, *, resume_prompt_id: str | None = None,
        checkpoint: dict | None = None, generation_identity: dict[str, str] | None = None,
    ):
        """Persist blocking evidence for a formal run, then let its generation failure propagate."""
        package = getattr(request, "package", None)
        try:
            if package is not None:
                self.repository.mark_generation_started(run_id, package.shot_id)
            if resume_prompt_id:
                result = await self.router.resume(request, resume_prompt_id, checkpoint)
            else:
                result = await self.router.generate(request)
            from backend.novel_video.h3_provider import H3SegmentResult
            if package is None or not isinstance(result, H3SegmentResult):
                raise TypeError("formal novel-video provider must return an H3 paired segment result")
            if not result.video_path.is_file() or not result.tail_frame_path.is_file() or not result.prompt_id:
                raise ValueError("formal paired segment result is incomplete")
            self.repository.record_generation_success(
                run_id, shot_id=package.shot_id, video_path=result.video_path, tail_path=result.tail_frame_path,
                prompt_id=result.prompt_id, metadata=result.metadata,
                generation_identity=generation_identity,
            )
        except Exception as error:
            shot_id = getattr(package, "shot_id", None)
            code = getattr(getattr(error, "code", None), "value", type(error).__name__)
            routing = dict(getattr(error, "details", {}).get("routing", {}))
            evidence = {
                "failure_key": f"{shot_id or ''}:{code}:{routing.get('original_size', '')}:{routing.get('downgraded_size', '')}",
                "shot_id": shot_id, "error_code": code, "message": str(error), "geometry": routing,
            }
            try:
                self.repository.block_generation_failure(run_id, shot_id=shot_id, evidence=evidence)
            except Exception:
                logger.exception("Could not persist formal novel-video failure for %s", run_id)
            raise
        return result


class SSEBroadcaster:
    """Simple in-process SSE broadcaster."""

    def __init__(self):
        self._queues: dict[str, list[queue.Queue]] = {}
        self._lock = threading.Lock()

    def subscribe(self, job_id: str) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._queues.setdefault(job_id, []).append(q)
        return q

    def unsubscribe(self, job_id: str, q: queue.Queue) -> None:
        with self._lock:
            if job_id in self._queues:
                self._queues[job_id] = [x for x in self._queues[job_id] if x is not q]

    def broadcast(self, job_id: str, event: str, data: dict) -> None:
        with self._lock:
            queues = self._queues.get(job_id, [])
        payload = json.dumps({"event": event, "data": data})
        for q in queues:
            try:
                q.put_nowait(payload)
            except Exception:
                pass


class StageExecutor:
    """Executes a single production stage with real ComfyUI integration."""

    def __init__(
        self,
        repo: JobRepository,
        broadcaster: SSEBroadcaster,
        config: OrchestrationConfig,
        comfy_url: str = "http://127.0.0.1:8188",
    ):
        self.repo = repo
        self.broadcaster = broadcaster
        self.config = config
        self.comfy_url = comfy_url
        self._comfy = None

    async def _get_comfy(self):
        if self._comfy is None:
            from backend.production.comfy_adapter import ComfyUIAdapter
            self._comfy = ComfyUIAdapter(base_url=self.comfy_url)
        return self._comfy

    async def execute_step(self, job_id: str, step: dict) -> None:
        step_id = step["id"]
        stage_key = step["stage_key"]
        shot_id = step.get("shot_id", "")

        if not self.repo.set_step_status(
            step_id,
            StepStatus.RUNNING,
            increment_attempt=True,
            allowed_from={StepStatus.QUEUED},
        ):
            raise RuntimeError(f"Step {step_id} must be queued before execution")

        self.broadcaster.broadcast(
            job_id, "step_started",
            {"step_id": step_id, "stage_key": stage_key, "shot_id": shot_id},
        )

        await self._run_stage(job_id, step)

    async def _run_stage(self, job_id: str, step: dict) -> None:
        job = self.repo.get_job(job_id)
        if not job:
            raise RuntimeError(f"Job {job_id} not found")

        stage_key = step["stage_key"]
        settings = json.loads(job.get("settings", "{}"))
        width = settings.get("width", 1080)
        height = settings.get("height", 1920)
        gen_width = settings.get("generation_width", 432)
        gen_height = settings.get("generation_height", 768)
        fps = settings.get("fps", 24)

        input_path = job.get("input_path", "")
        project_id = job.get("project_id", "")
        project_root = Path(self.config.project_root) / project_id
        output_dir = project_root / "outputs"

        if stage_key == "load_input":
            await self._load_input(job_id, input_path, project_id)
        elif stage_key == "planning":
            await self._run_planning(job_id, input_path, project_id, settings)
        elif stage_key == "character_design":
            await self._run_character_design(job_id, project_id, settings)
        elif stage_key.startswith("visual_"):
            await self._run_comfyui_stage(job_id, step, output_dir, gen_width, gen_height, settings, project_id)
        elif stage_key == "hd_redraw":
            await self._run_hd_redraw(job_id, step, output_dir, project_id)
        elif stage_key.startswith("video_"):
            await self._run_video_stage(job_id, step, output_dir, gen_width, gen_height, settings, project_id)
        elif stage_key.startswith("audio_"):
            await self._run_audio_stage(job_id, step, output_dir, project_id)
        elif stage_key.startswith("composition_"):
            timeline_settings = settings.get("timeline") or {}
            if timeline_settings.get("source") == "timeline_snapshot":
                await self._run_timeline_composition(job_id, step, output_dir, fps, settings, project_id)
            else:
                await self._run_composition(job_id, step, output_dir, fps, settings, project_id)
        elif stage_key == "export":
            await self._run_export(job_id, output_dir, fps, project_id)
        else:
            self.repo.set_job_progress(job_id, stage_key, step.get("shot_id", ""), 0.5, f"Running {stage_key}")

    async def _load_input(self, job_id: str, input_path: str, project_id: str) -> None:
        self.repo.set_job_progress(job_id, "load_input", "", 0.05, "Loading input file...")

        try:
            from backend.production.input_loader import load_input, detect_input_type

            input_type = detect_input_type(input_path)
            loaded = load_input(input_path)
            self.repo.set_job_progress(
                job_id, "load_input", "", 0.1,
                f"Loaded: {loaded.contract.title} ({input_type.value})",
            )
        except Exception as e:
            self.repo.set_job_progress(job_id, "load_input", "", 0.1, f"Load failed: {e}")

    async def _run_planning(self, job_id: str, input_path: str, project_id: str, settings: dict) -> None:
        self.repo.set_job_progress(job_id, "planning", "", 0.15, "Building production plan...")

        try:
            from backend.production.input_loader import load_input
            from backend.production.plan_builder import PlanSettings, build_trailer_plan, save_plan
            from backend.production.script_generator import ScriptGenerator, script_to_json

            loaded = load_input(input_path)

            # Use tutorial-recommended settings: 10 min episodes, 40+ shots
            plan_settings = PlanSettings(
                target_seconds=settings.get("target_duration", 600),
                max_shots=settings.get("max_shots", 40),
                width=settings.get("width", 1080),
                height=settings.get("height", 1920),
                fps=settings.get("fps", 24),
                provider=settings.get("provider", "ltx23"),
                episode_count=settings.get("episode_count", 1),
                shots_per_episode=settings.get("shots_per_episode", 40),
            )
            plan = build_trailer_plan(project_id, loaded, plan_settings)

            plan_path = Path(self.config.project_root) / project_id / "production_plan.json"
            save_plan(plan, plan_path)

            # Also generate structured script (tutorial Step 02) and save it
            try:
                full_text = loaded.text
                if not full_text and loaded.chapters:
                    full_text = "\n\n".join(ch.content for ch in loaded.chapters)
                if full_text:
                    generator = ScriptGenerator()
                    script = generator.generate(full_text, title=loaded.contract.title)
                    script_path = Path(self.config.project_root) / project_id / "video_script.json"
                    script_path.write_text(
                        json.dumps(script_to_json(script), ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    logger.info("Structured script saved: %d scenes, %d shots",
                                len(script.scenes), script.total_shots)
            except Exception as script_err:
                logger.warning("Script generation failed (non-fatal): %s", script_err)

            self.repo.set_job_progress(
                job_id, "planning", "", 0.2,
                f"Planned {len(plan.shots)} shots, {plan.total_duration:.1f}s total",
            )
        except Exception as e:
            self.repo.set_job_progress(job_id, "planning", "", 0.2, f"Planning failed: {e}")

    def _shot_exists_in_plan(self, shot_id: str, project_id: str) -> bool:
        """Check if a shot_id exists in the production plan."""
        plan_path = Path(self.config.project_root) / project_id / "production_plan.json"
        if not plan_path.exists():
            return True  # If no plan, don't skip
        try:
            plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
            shot_ids = {s.get("id", "") for s in plan_data.get("shots", [])}
            return shot_id in shot_ids
        except Exception:
            return True

    async def _run_character_design(self, job_id: str, project_id: str, settings: dict) -> None:
        """Generate character design reference images (tutorial Step 03)."""
        self.repo.set_job_progress(job_id, "character_design", "", 0.25,
                                   "Generating character reference images...")

        try:
            from backend.production.character_designer import CharacterDesigner

            # Load character data from production plan
            plan_path = Path(self.config.project_root) / project_id / "production_plan.json"
            characters: list[dict] = []

            if plan_path.exists():
                plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
                # Get characters from plan settings (LLM parser output)
                plan_chars = plan_data.get("settings", {}).get("characters", {})
                for name, styling in plan_chars.items():
                    characters.append({
                        "name": name,
                        "appearance": styling if isinstance(styling, str) else "",
                        "image_prompt": styling if isinstance(styling, str) else "",
                    })

            if not characters:
                self.repo.set_job_progress(
                    job_id, "character_design", "", 0.25,
                    "No characters found in plan, skipping character design",
                )
                return

            designer = CharacterDesigner(
                output_root=str(self.config.project_root),
            )
            results = await designer.design_characters(project_id, characters)

            # Save character reference map for downstream stages
            ref_map = designer.get_reference_image_map(results)
            ref_path = Path(self.config.project_root) / project_id / "character_refs.json"
            ref_path.write_text(
                json.dumps(ref_map, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            self.repo.set_job_progress(
                job_id, "character_design", "", 0.25,
                f"Designed {len(results)} characters, {sum(1 for r in results if r.get('reference_image'))} images generated",
            )
        except Exception as e:
            self.repo.set_job_progress(
                job_id, "character_design", "", 0.25,
                f"Character design failed: {e}",
            )

    async def _run_hd_redraw(
        self, job_id: str, step: dict, output_dir: Path, project_id: str
    ) -> None:
        """Upscale keyframe to HD resolution (tutorial Step 05)."""
        shot_id = step.get("shot_id", "")
        step_id = step["id"]

        # Skip if shot doesn't exist in plan
        if not self._shot_exists_in_plan(shot_id, project_id):
            self.repo.set_job_progress(
                job_id, "hd_redraw", shot_id, 0.45,
                f"Skipping {shot_id} (not in plan)",
            )
            return

        image_dir = output_dir / "images" / shot_id
        frame_path = image_dir / "frame.png"

        if not frame_path.exists():
            self.repo.set_job_progress(
                job_id, "hd_redraw", shot_id, 0.45,
                f"No keyframe found for {shot_id}, skipping HD redraw",
            )
            return

        hd_path = image_dir / "frame_hd.png"

        self.repo.set_job_progress(
            job_id, "hd_redraw", shot_id, 0.42,
            f"HD redrawing {shot_id}...",
        )

        try:
            from backend.production.hd_redraw import HDRedrawer

            redrawer = HDRedrawer(comfy_base_url=self.comfy_url)

            # Load original prompt from plan
            prompt = ""
            plan_path = Path(self.config.project_root) / project_id / "production_plan.json"
            if plan_path.exists():
                plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
                for s in plan_data.get("shots", []):
                    if s.get("id") == shot_id:
                        prompt = s.get("positive_prompt", "")
                        break

            success = await redrawer.redraw_frame(
                input_path=frame_path,
                output_path=hd_path,
                original_prompt=prompt,
                shot_id=shot_id,
            )

            if success and hd_path.exists():
                self._register_artifact(job_id, step_id, "image", str(hd_path), shot_id)
                self.repo.set_job_progress(
                    job_id, "hd_redraw", shot_id, 0.45,
                    f"HD redraw complete for {shot_id}",
                )
            else:
                # Fallback: copy original as HD
                import shutil
                shutil.copy2(frame_path, hd_path)
                self.repo.set_job_progress(
                    job_id, "hd_redraw", shot_id, 0.45,
                    f"HD redraw fallback for {shot_id}",
                )
        except Exception as e:
            self.repo.set_job_progress(
                job_id, "hd_redraw", shot_id, 0.45,
                f"HD redraw failed for {shot_id}: {e}",
            )

    async def _run_comfyui_stage(
        self, job_id: str, step: dict, output_dir: Path, gen_width: int, gen_height: int,
        settings: dict, project_id: str = "",
    ) -> None:
        shot_id = step.get("shot_id", "")
        stage_key = step["stage_key"]
        step_id = step["id"]
        strict_flux = stage_provider_is_required(settings, stage_key, "flux")

        # Skip if shot doesn't exist in plan
        if project_id and not self._shot_exists_in_plan(shot_id, project_id):
            self.repo.set_job_progress(
                job_id, stage_key, shot_id, 0.4,
                f"Skipping {shot_id} (not in plan)",
            )
            return

        image_dir = output_dir / "images" / shot_id
        image_dir.mkdir(parents=True, exist_ok=True)
        output_path = image_dir / "frame.png"

        self.repo.set_job_progress(
            job_id, stage_key, shot_id, 0.3, f"Generating image for {shot_id}...",
        )

        comfy = await self._get_comfy()
        if not await comfy.is_available():
            message = f"ComfyUI not available at {self.comfy_url} for {shot_id}"
            self.repo.set_job_progress(job_id, stage_key, shot_id, 0.35, message)
            if strict_flux:
                raise RuntimeError(message)
            _create_placeholder_image(output_path)
            self._register_artifact(job_id, step_id, "image", str(output_path), shot_id)
            return

        try:
            from backend.production.providers import ImageRequest
            from backend.production.workflow_templates import WorkflowTemplate

            # Load plan to get shot prompts
            plan_path = Path(self.config.project_root) / (project_id or "default") / "production_plan.json"
            shot_prompt = "manga style, cinematic lighting, high quality"
            shot_negative = "low quality, blurry, deformed"
            shot_seed = 42

            if plan_path.exists():
                plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
                for s in plan_data.get("shots", []):
                    if s.get("id") == shot_id:
                        shot_prompt = s.get("positive_prompt", shot_prompt)
                        shot_negative = s.get("negative_prompt", shot_negative)
                        shot_seed = s.get("seed", shot_seed)
                        try:
                            from backend.production.contracts import ShotSpec
                            from backend.prompt_compiler.compiler import PromptCompiler
                            compiled = PromptCompiler().compile_video_shot(
                                ShotSpec(
                                    id=str(s.get("id", shot_id)),
                                    shot_number=int(s.get("shot_number", 0) or 0),
                                    description=str(s.get("description", "")),
                                    duration=float(s.get("duration", 5.0) or 5.0),
                                    camera=str(s.get("camera", "")),
                                    characters=list(s.get("characters", []) or []),
                                    dialogue=list(s.get("dialogue", []) or []),
                                    sfx=list(s.get("sfx", []) or []),
                                    positive_prompt=shot_prompt,
                                    negative_prompt=shot_negative,
                                    narration=str(s.get("narration", "")),
                                    transition=str(s.get("transition", "fade")),
                                    seed=int(shot_seed),
                                )
                            )
                            shot_prompt = compiled.positive_prompt
                            shot_negative = compiled.negative_prompt
                        except Exception as prompt_err:
                            logger.warning("Video prompt compile failed for %s: %s", shot_id, prompt_err)
                        break

            # Auto-enable character consistency when character_refs.json exists
            use_consistency = settings.get("character_consistency", True)  # Default: True
            reference_image = self._get_character_reference(job_id, shot_id, project_id)

            # If no explicit reference but character_refs.json exists, use it
            if not reference_image and project_id:
                registry_path = Path(self.config.project_root) / project_id / "reference_registry.json"
                legacy_ref_path = Path(self.config.project_root) / project_id / "character_refs.json"
                ref_path = registry_path if registry_path.exists() else legacy_ref_path
                if ref_path.exists():
                    try:
                        from backend.production.reference_registry import ReferenceRegistry
                        ref_registry = ReferenceRegistry.load(ref_path)
                        # Load plan to find which characters appear in this shot
                        if plan_path.exists():
                            plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
                            for s in plan_data.get("shots", []):
                                if s.get("id") == shot_id:
                                    shot_chars = s.get("characters", [])
                                    for char_name in shot_chars:
                                        resolved = ref_registry.resolve_primary_reference(char_name)
                                        if resolved:
                                            reference_image = resolved
                                            logger.info("Using character ref for %s: %s",
                                                       char_name, reference_image)
                                            break
                                    break
                    except Exception as ref_err:
                        logger.warning("Failed to load character refs: %s", ref_err)

            if use_consistency and reference_image:
                # Use IP-Adapter FaceID workflow for character consistency
                workflow_path = Path("backend/production/workflows/flux_ipadapter_faceid.json")
                if workflow_path.exists():
                    template_data = json.loads(workflow_path.read_text(encoding="utf-8"))
                    template = WorkflowTemplate.from_dict(template_data)

                    from backend.production.comfy_image import FluxImageWithConsistencyProvider
                    provider = FluxImageWithConsistencyProvider(adapter=comfy, template=template)
                    request = ImageRequest(
                        prompt=shot_prompt,
                        negative_prompt=shot_negative,
                        seed=shot_seed,
                        width=gen_width,
                        height=gen_height,
                        output_path=output_path,
                        reference_image=reference_image,
                        ipadapter_weight=0.85,
                    )
                    result = await provider.generate(request)
                else:
                    self.repo.set_job_progress(
                        job_id, stage_key, shot_id, 0.35,
                        "IP-Adapter workflow not found, falling back to standard generation",
                    )
                    await self._run_standard_image_gen(
                        comfy, shot_prompt, shot_negative, shot_seed,
                        gen_width, gen_height, output_path, job_id, stage_key, shot_id,
                    )
            else:
                await self._run_standard_image_gen(
                    comfy, shot_prompt, shot_negative, shot_seed,
                    gen_width, gen_height, output_path, job_id, stage_key, shot_id,
                )

            self.repo.set_job_progress(
                job_id, stage_key, shot_id, 0.4,
                f"Generated {shot_id}",
            )
            self._register_artifact(job_id, step_id, "image", str(output_path), shot_id)
        except Exception as e:
            self.repo.set_job_progress(
                job_id, stage_key, shot_id, 0.35,
                f"Image generation failed for {shot_id}: {e}",
            )
            if strict_flux:
                raise
            _create_placeholder_image(output_path)
            self._register_artifact(job_id, step_id, "image", str(output_path), shot_id)

    async def _run_standard_image_gen(
        self, comfy, prompt: str, negative: str, seed: int,
        width: int, height: int, output_path: Path,
        job_id: str, stage_key: str, shot_id: str,
    ) -> None:
        """Standard FLUX image generation without IP-Adapter."""
        from backend.production.providers import ImageRequest
        from backend.production.workflow_templates import WorkflowTemplate
        from backend.production.comfy_image import FluxImageProvider

        workflow_path = Path("backend/production/workflows/flux_live_action.json")
        if workflow_path.exists():
            template_data = json.loads(workflow_path.read_text(encoding="utf-8"))
            template = WorkflowTemplate.from_dict(template_data)
        else:
            template = WorkflowTemplate(
                workflow=_default_image_template(),
                bindings={},
            )

        provider = FluxImageProvider(adapter=comfy, template=template)
        request = ImageRequest(
            prompt=prompt,
            negative_prompt=negative,
            seed=seed,
            width=width,
            height=height,
            output_path=output_path,
        )
        await provider.generate(request)

    def _get_character_reference(self, job_id: str, shot_id: str, project_id: str = "") -> str:
        """Find reference image for character consistency (IP-Adapter).

        Searches in order:
        1. Character-specific reference from plan
        2. Auto-generated character image from previous shots
        3. Manually placed reference in projects/characters/
        """
        project_root = Path(self.config.project_root) / (project_id or "default")

        # 1. Check plan for character reference
        plan_path = project_root / "production_plan.json"
        if plan_path.exists():
            plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
            for s in plan_data.get("shots", []):
                if s.get("id") == shot_id:
                    ref = s.get("character_reference", "")
                    if ref and Path(ref).exists():
                        return ref
                    break

        # 2. Check for previously generated character images
        characters_dir = project_root / "characters"
        if characters_dir.exists():
            for ref_img in sorted(characters_dir.glob("*.png"), reverse=True):
                return str(ref_img)

        # 3. Check auto-generated first frame as reference
        first_frame = project_root / "outputs" / "images" / "shot_001" / "frame.png"
        if first_frame.exists():
            return str(first_frame)

        return ""

    async def _run_video_stage(
        self, job_id: str, step: dict, output_dir: Path, gen_width: int, gen_height: int,
        settings: dict, project_id: str = "",
    ) -> None:
        """Generate AI video (Wan2.2) from a previously generated image."""
        shot_id = step.get("shot_id", "")
        stage_key = step["stage_key"]
        step_id = step["id"]
        provider_plan = resolve_video_provider_plan(settings)

        # Skip if shot doesn't exist in plan
        if project_id and not self._shot_exists_in_plan(shot_id, project_id):
            self.repo.set_job_progress(
                job_id, stage_key, shot_id, 0.8,
                f"Skipping {shot_id} (not in plan)",
            )
            return

        video_dir = output_dir / "videos" / shot_id
        video_dir.mkdir(parents=True, exist_ok=True)
        output_path = video_dir / "ai_clip.mp4"

        # Input image from the visual stage — prefer HD version if available
        hd_image_path = output_dir / "images" / shot_id / "frame_hd.png"
        image_path = output_dir / "images" / shot_id / "frame.png"
        if hd_image_path.exists():
            image_path = hd_image_path
        if not image_path.exists():
            self.repo.set_job_progress(
                job_id, stage_key, shot_id, 0.45,
                f"No source image for {shot_id}, skipping AI video",
            )
            return

        # Check for last frame (FLF2V mode — first-last frame to video)
        hd_last_path = output_dir / "images" / shot_id / "frame_last_hd.png"
        last_frame_path = output_dir / "images" / shot_id / "frame_last.png"
        end_frame_path = ""
        if hd_last_path.exists():
            end_frame_path = str(hd_last_path)
        elif last_frame_path.exists():
            end_frame_path = str(last_frame_path)

        self.repo.set_job_progress(
            job_id, stage_key, shot_id, 0.45, f"Generating AI video for {shot_id}...",
        )

        comfy = await self._get_comfy()
        if not await comfy.is_available():
            message = f"ComfyUI not available for AI video {shot_id}"
            self.repo.set_job_progress(job_id, stage_key, shot_id, 0.45, message)
            if provider_plan.enforced:
                raise RuntimeError(message)
            return

        try:
            from backend.production.providers import VideoRequest
            from backend.production.workflow_templates import WorkflowTemplate
            from backend.production.comfy_video import WanVideoProvider

            wan_template = None
            if "wan" in provider_plan.providers:
                from backend.production.workflow_registry import select_wan_video_workflow
                workflow_spec = select_wan_video_workflow(has_end_frame=bool(end_frame_path))
                workflow_name = workflow_spec.path.name
                workflow_path = workflow_spec.path
                if workflow_path.exists():
                    wan_template = WorkflowTemplate.load(workflow_path)
                elif provider_plan.providers == ("wan",):
                    message = f"Wan2.2 workflow {workflow_name} not found"
                    self.repo.set_job_progress(job_id, stage_key, shot_id, 0.45, message)
                    if provider_plan.enforced:
                        raise RuntimeError(message)
                    return

            # Load plan to get shot prompt
            plan_path = Path(self.config.project_root) / (project_id or "default") / "production_plan.json"
            shot_prompt = "cinematic animation, smooth motion, high quality"
            shot_negative = "low quality, blurry, distorted, jittery"
            shot_seed = 42

            shot_data: dict = {}
            if plan_path.exists():
                plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
                for s in plan_data.get("shots", []):
                    if s.get("id") == shot_id:
                        shot_data = s
                        shot_prompt = s.get("positive_prompt", shot_prompt)
                        shot_negative = s.get("negative_prompt", shot_negative)
                        shot_seed = s.get("seed", shot_seed)
                        break

            # GPT Round-1: Action Prompt v2 —— image_prompt + motion_prompt 拆分
            try:
                from backend.video.action_prompts import split_shot_prompt
                prompts = split_shot_prompt(shot_data)
                if shot_data.get("positive_prompt"):
                    shot_prompt = prompts["image_prompt"]
                    if prompts["motion_prompt"]:
                        shot_prompt = f"{shot_prompt}. {prompts['motion_prompt']}"
                shot_negative = prompts["negative_prompt"]
            except Exception:
                pass

            # GPT P0: 镜头运动档位驱动 denoise/帧数（真实运动优先，不再 0.20-0.30 硬钳制）
            try:
                from backend.video.duration_strategy import get_motion_profile
                profile = get_motion_profile(shot_data)
            except Exception:
                profile = None

            # Motion bucket: 0=static, 127=balanced, 255=maximum
            # GPT Round-1: 由镜头运动档位解析，不再固定 127 或全片 255
            try:
                from backend.video.duration_strategy import resolve_motion_bucket
                motion_bucket_id = resolve_motion_bucket(shot_data or {"motion_level": settings.get("motion_level", "medium")})
            except Exception:
                motion_bucket_id = settings.get("motion_bucket_id", 127)
            video_frames = profile.frames if profile else int(settings.get("video_frames", 81) or 81)
            video_fps = settings.get("fps", 24)
            denoise_strength = profile.denoise if profile else 0.55

            last_provider_error = None
            for provider_name in provider_plan.providers:
                try:
                    if provider_name == "minimax_h3":
                        from backend.production.minimax_h3_adapter import MiniMaxH3VideoProvider
                        provider = MiniMaxH3VideoProvider(adapter=comfy)
                    elif provider_name == "wan":
                        if wan_template is None:
                            raise RuntimeError("Wan2.2 workflow is unavailable")
                        provider = WanVideoProvider(adapter=comfy, template=wan_template)
                    else:
                        raise RuntimeError(f"Unsupported video provider: {provider_name}")

                    request = VideoRequest(
                        image_path=image_path,
                        prompt=shot_prompt,
                        negative_prompt=shot_negative,
                        seed=shot_seed,
                        width=gen_width,
                        height=gen_height,
                        frames=video_frames,
                        fps=video_fps,
                        output_path=output_path,
                        motion_bucket_id=motion_bucket_id,
                        denoise_strength=denoise_strength,
                        ai_video=True,
                        end_frame_path=end_frame_path,
                        engine=provider_name,
                    )
                    await provider.generate(request)
                    last_provider_error = None
                    break
                except Exception as provider_error:
                    last_provider_error = provider_error
                    if provider_plan.required:
                        raise
                    logger.warning(
                        "Video provider %s failed for %s; trying explicit fallback if configured: %s",
                        provider_name, shot_id, provider_error,
                    )
            if last_provider_error is not None:
                raise last_provider_error

            # GPT P0: Video Contract 硬门禁 —— 不合格视频禁止进入下游
            try:
                from backend.production.video_contract import enforce_video_contract
                enforce_video_contract(output_path)
            except Exception as gate_exc:
                self.repo.set_job_progress(
                    job_id, stage_key, shot_id, 0.45,
                    f"AI video REJECTED by contract for {shot_id}: {gate_exc}",
                )
                raise

            self.repo.set_job_progress(
                job_id, stage_key, shot_id, 0.5,
                f"AI video generated for {shot_id}",
            )
            if output_path.exists():
                self._register_artifact(job_id, step_id, "video", str(output_path), shot_id)
        except Exception as e:
            self.repo.set_job_progress(
                job_id, stage_key, shot_id, 0.45,
                f"AI video generation failed for {shot_id}: {e}",
            )
            if provider_plan.enforced:
                raise

    async def _run_audio_stage(self, job_id: str, step: dict, output_dir: Path, project_id: str = "") -> None:
        stage_key = step["stage_key"]
        shot_id = step.get("shot_id", "")
        step_id = step["id"]

        audio_dir = output_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        self.repo.set_job_progress(
            job_id, stage_key, shot_id, 0.5, f"Generating audio for {shot_id or 'all shots'}...",
        )

        try:
            from backend.audio.tts_engine import TTSEngine

            tts = TTSEngine(output_dir=str(audio_dir))

            # Load plan to get narration/dialogue for all shots
            plan_path = Path(self.config.project_root) / (project_id or "default") / "production_plan.json"
            plan_shots: list[dict] = []
            if plan_path.exists():
                plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
                plan_shots = plan_data.get("shots", [])

            # If shot_id is set, only process that shot; otherwise process all shots
            if shot_id:
                target_shots = [s for s in plan_shots if s.get("id") == shot_id]
            else:
                target_shots = plan_shots

            if stage_key == "audio_tts":
                # Generate narration for each shot
                if not target_shots:
                    target_shots = [{"id": "", "narration": " ", "dialogue": []}]

                for s in target_shots:
                    sid = s.get("id", shot_id)
                    narration = s.get("narration", "")
                    dialogue = s.get("dialogue", [])
                    text = narration or (dialogue[0] if dialogue else "")

                    if text.strip():
                        output_path = audio_dir / f"{sid}_narration.wav"
                        await tts.generate(text, output_path)
                        if output_path.exists():
                            self._register_artifact(job_id, step_id, "audio", str(output_path), sid)

            elif stage_key == "audio_dialogue":
                for s in target_shots:
                    sid = s.get("id", shot_id)
                    dialogue = s.get("dialogue", [])
                    text = dialogue[0] if dialogue else ""

                    if text.strip():
                        output_path = audio_dir / f"{sid}_dialogue.wav"
                        character_id = step.get("character_id", "")
                        archetype = step.get("character_archetype", "supporting")
                        character_index = step.get("character_index", 0)

                        if character_id:
                            await tts.generate_character_dialogue(
                                text=text,
                                shot_id=sid,
                                character_id=character_id,
                                archetype=archetype,
                                character_index=character_index,
                            )
                        else:
                            await tts.generate_dialogue(text, sid)
                        if output_path.exists():
                            self._register_artifact(job_id, step_id, "audio", str(output_path), sid)

            elif stage_key == "audio_sfx":
                output_path = audio_dir / f"{shot_id or 'ambient'}_sfx.wav"
                from backend.audio.tts_engine import SFXEngine
                sfx = SFXEngine(output_dir=str(audio_dir))
                await sfx.generate("ambient", output_path)
                if output_path.exists():
                    self._register_artifact(job_id, step_id, "audio", str(output_path), shot_id)

            self.repo.set_job_progress(
                job_id, stage_key, shot_id, 0.6,
                f"Audio generated for {shot_id or 'all shots'}",
            )
        except Exception as e:
            self.repo.set_job_progress(
                job_id, stage_key, shot_id, 0.55,
                f"Audio generation failed for {shot_id or 'all shots'}: {e}",
            )

    async def _run_timeline_composition(self, job_id: str, step: dict, output_dir: Path, fps: int, settings: dict, project_id: str = "") -> None:
        step_id = step["id"]
        self.repo.set_job_progress(job_id, "composition_compose", "", 0.7, "Compositing Timeline snapshot...")
        from backend.timeline.runtime import load_verified_composition_spec
        from backend.video.composer import VideoComposer, check_ffmpeg
        spec = load_verified_composition_spec(self.repo, settings)
        if spec is None:
            raise RuntimeError("Timeline composition provenance is missing")
        if not check_ffmpeg():
            raise RuntimeError("FFmpeg is required for Timeline composition")
        composer = VideoComposer(output_dir=str(output_dir))
        final_path = output_dir / "composition" / "composite.mp4"
        composer.compose_timeline(spec, final_path)
        if not final_path.exists() or final_path.stat().st_size <= 0:
            raise RuntimeError("Timeline composition produced empty output")
        self.repo.set_job_progress(job_id, "composition_compose", "", 0.85, f"Timeline composition complete: {final_path}")
        self._register_artifact(job_id, step_id, "composition", str(final_path), "")

    async def _run_composition(self, job_id: str, step: dict, output_dir: Path, fps: int, settings: dict, project_id: str = "") -> None:
        step_id = step["id"]
        self.repo.set_job_progress(
            job_id, "composition_compose", "", 0.7, "Compositing video...",
        )

        try:
            from backend.video.composer import VideoComposer, check_ffmpeg

            composer = VideoComposer(output_dir=str(output_dir))

            if not check_ffmpeg():
                self.repo.set_job_progress(
                    job_id, "composition_compose", "", 0.8,
                    "FFmpeg not available, skipping composition",
                )
                return

            # Gather all shots
            plan_path = Path(self.config.project_root) / (project_id or "default") / "production_plan.json"
            if not plan_path.exists():
                self.repo.set_job_progress(
                    job_id, "composition_compose", "", 0.8,
                    "No production plan found, skipping composition",
                )
                return

            plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
            shots = plan_data.get("shots", [])

            # GPT P0: 合成只接受真实 AI 视频。缺 ai_clip.mp4 的分镜不再退回
            # Ken Burns 定帧图，直接报错并列出缺失镜头（失败即失败）。
            shot_data = []
            missing_clips = []
            for s in shots:
                sid = s["id"]
                img_path = output_dir / "images" / sid / "frame.png"
                aud_path = output_dir / "audio" / f"{sid}_narration.wav"
                ai_vid_path = output_dir / "videos" / sid / "ai_clip.mp4"

                # Skip shots with no image at all
                if not img_path.exists():
                    continue

                shot_entry = {
                    "image": str(img_path),
                    "audio": str(aud_path) if aud_path.exists() else "",
                    "duration": s.get("duration", 5.0),
                    "subtitle": s.get("narration", "")[:50] if s.get("narration") else "",
                }

                if ai_vid_path.exists():
                    shot_entry["ai_video"] = str(ai_vid_path)
                else:
                    missing_clips.append(sid)

                shot_data.append(shot_entry)

            if missing_clips:
                error_message = (
                    "缺少 AI 视频分镜，合成失败（已禁用 Ken Burns 定帧兜底）: "
                    + ", ".join(missing_clips)
                )
                self.repo.set_job_progress(
                    job_id, "composition_compose", "", 0.8, error_message,
                )
                raise RuntimeError(error_message)

            if not shot_data:
                self.repo.set_job_progress(
                    job_id, "composition_compose", "", 0.8,
                    "No valid shots with images found, skipping composition",
                )
                return

            final_path = output_dir / "composition" / "composite.mp4"
            composer.compose_sequence(shot_data, final_path, fps=fps, use_ai_video=True)

            if final_path.exists() and final_path.stat().st_size > 0:
                self.repo.set_job_progress(
                    job_id, "composition_compose", "", 0.85,
                    f"Composition complete: {final_path}",
                )
                self._register_artifact(job_id, step_id, "composition", str(final_path), "")
            else:
                self.repo.set_job_progress(
                    job_id, "composition_compose", "", 0.8,
                    "Composition produced empty output",
                )
        except Exception as e:
            self.repo.set_job_progress(
                job_id, "composition_compose", "", 0.8,
                f"Composition failed: {e}",
            )
            raise

    async def _run_export(self, job_id: str, output_dir: Path, fps: int, project_id: str = "") -> None:
        self.repo.set_job_progress(
            job_id, "export", "", 0.9, "Exporting final video...",
        )

        try:
            from backend.video.composer import VideoComposer

            composer = VideoComposer(output_dir=str(output_dir))
            composite_path = output_dir / "composition" / "composite.mp4"

            if composite_path.exists() and composite_path.stat().st_size > 0:
                final_path = output_dir / "export" / "final.mp4"
                composer.export_final(composite_path, final_path, format="mp4")

                if final_path.exists() and final_path.stat().st_size > 0:
                    self.repo.set_job_status(
                        job_id, JobStatus.RUNNING,
                        final_video=str(final_path),
                    )
                    self.repo.set_job_progress(
                        job_id, "export", "", 1.0,
                        f"Export complete: {final_path}",
                    )
                    self._register_artifact_simple(job_id, "video", str(final_path))
                    from backend.timeline.export_binding import bind_latest_export_artifact
                    bind_latest_export_artifact(self.repo, job_id)
                else:
                    self.repo.set_job_progress(
                        job_id, "export", "", 1.0,
                        "Export produced empty file",
                    )
            else:
                self.repo.set_job_progress(
                    job_id, "export", "", 1.0,
                    "No composite video to export",
                )
        except Exception as e:
            self.repo.set_job_progress(
                job_id, "export", "", 0.95,
                f"Export failed: {e}",
            )

    def _register_artifact(
        self, job_id: str, step_id: str, kind: str, path: str, shot_id: str = "",
    ) -> None:
        """Register an artifact produced by a step, computing sha256 and metadata."""
        import hashlib

        try:
            file_path = Path(path)
            if not file_path.exists():
                return
            sha256 = hashlib.sha256(file_path.read_bytes()).hexdigest()
            metadata: dict[str, Any] = {"shot_id": shot_id} if shot_id else {}
            self.repo.add_artifact(job_id, step_id, kind, path, sha256, metadata)
        except Exception:
            pass

    def _register_artifact_simple(
        self, job_id: str, kind: str, path: str,
    ) -> None:
        """Register an artifact when only the job_id is known (e.g. export stage).

        Finds the relevant step by looking up the job's steps.
        """
        try:
            steps = self.repo.get_job_steps(job_id)
            for step in reversed(steps):
                if step["stage_key"] == "export":
                    self._register_artifact(job_id, step["id"], kind, path, "")
                    return
            # Fallback: use the last step
            if steps:
                self._register_artifact(job_id, steps[-1]["id"], kind, path, "")
        except Exception:
            pass


from backend.orchestration.adaptive_dispatcher import DispatchRequest


class TaskRunner:
    """Phase 10.7-A: executes production tasks from the :class:`TaskQueue`.

    ``video_chain`` tasks are routed through ``ChainRuntime`` (lease lock +
    cost meter + identity gate) and every shot writes back
    ``{task_id, shot_id, stage, progress, gpu_time, checkpoint}`` so the
    StudioDashboard can render live progress.  ``video_generation`` runs a
    single-shot chain, ``image_generation`` a single FLUX image.
    """

    def __init__(
        self,
        task_queue,
        broadcaster: SSEBroadcaster,
        config: OrchestrationConfig,
        workdir: str | Path = "storage/chains",
        video_provider_factory=None,
        image_provider_factory=None,
        identity_verifier=None,
        frame_extractor=None,
        novel_video_repository=None,
        formal_router_factory=None,
    ):
        from backend.orchestration.task_queue import TaskQueue

        self.task_queue = task_queue
        self.broadcaster = broadcaster
        self.config = config
        self.workdir = Path(workdir)
        self.identity_verifier = identity_verifier
        self.video_provider_factory = video_provider_factory or self._default_video_provider
        self.image_provider_factory = image_provider_factory or self._default_image_provider
        self.frame_extractor = frame_extractor
        self.novel_video_repository = novel_video_repository
        self.formal_router_factory = formal_router_factory
        self.lease_lock = None
        self.cost_meter = None

    def adaptive_dispatcher(self):
        """Lazy AdaptiveDispatcher (Phase 12.7-A)."""
        if getattr(self, "_adaptive_dispatcher", None) is None:
            from backend.orchestration.adaptive_dispatcher import AdaptiveDispatcher
            self._adaptive_dispatcher = AdaptiveDispatcher()
        return self._adaptive_dispatcher

    # ------------------------------------------------------------ providers
    @staticmethod
    def _default_video_provider(comfy_url: str = "http://127.0.0.1:8188"):
        """Production video provider (GPT Round-4: 双引擎调度).

        普通镜 -> Wan2.2 native（高吞吐）；重点镜 -> MiniMax H3（Premium Path）。
        引擎切换由 DualEngineVideoProvider + ModelLifecycleManager 管理显存。
        """
        from backend.production.dual_engine_provider import DualEngineVideoProvider

        return DualEngineVideoProvider(comfy_url=comfy_url)

    @staticmethod
    def _default_image_provider(comfy_url: str = "http://127.0.0.1:8188"):
        from backend.production.comfy_adapter import ComfyUIAdapter
        from backend.production.comfy_image import FluxImageProvider
        from backend.production.workflow_templates import WorkflowTemplate

        workflow_path = Path("backend/production/workflows/flux_live_action.json")
        template = (
            WorkflowTemplate.load(workflow_path)
            if workflow_path.exists()
            else WorkflowTemplate(workflow=_default_image_template(), bindings={})
        )
        return FluxImageProvider(adapter=ComfyUIAdapter(base_url=comfy_url), template=template)

    # ------------------------------------------------------------- dispatch
    async def execute_task(self, task) -> None:
        from backend.orchestration.task_queue import WorkerTask

        if task.task_type == "video_chain":
            await self._run_chain(task)
        elif task.task_type == "video_generation":
            if (task.payload or {}).get("formal_novel_video"):
                await self._run_formal_novel_video(task)
            else:
                await self._run_chain(task, single=True)
        elif task.task_type == "image_generation":
            await self._run_image(task)
        else:
            raise ValueError(f"unknown task_type: {task.task_type!r}")

    async def _run_formal_novel_video(self, task) -> None:
        """Route an explicit formal payload through H3 and the project's opt-in fallback policy."""
        if self.novel_video_repository is None or self.formal_router_factory is None:
            raise RuntimeError("formal novel-video routing requires an injected repository and router factory")
        # Preserve the state gate ahead of all payload parsing so stale queued
        # work cannot acquire a lock/provider or leak validation ordering.
        early_run = self.novel_video_repository.get_run(str((task.payload or {}).get("run_id", "")))
        if early_run is None:
            raise KeyError("formal task run does not exist")
        from backend.novel_video.models import RunStatus
        if early_run.status is not RunStatus.RENDERING:
            raise ValueError(f"formal generation requires a rendering run, got: {early_run.status.value}")
        context = self._formal_replay_context(task)
        if self._complete_committed_formal_success(task, context):
            return
        payload, run, project, package, request, generation_identity, task = context
        if run.status is not RunStatus.RENDERING:
            raise ValueError(f"formal generation requires a rendering run, got: {run.status.value}")
        queue_checkpoint = dict(getattr(task, "checkpoint", {}) or {})
        if queue_checkpoint.get("formal_generation_attempt_id") != generation_identity["attempt_id"]:
            queue_checkpoint["formal_generation_attempt_id"] = generation_identity["attempt_id"]
            updated_task = self.task_queue.update(task.task_id, checkpoint=queue_checkpoint)
            if updated_task is not None:
                task = updated_task
        router = self.formal_router_factory(
            allow_wan_fallback=project.allow_wan_fallback, project=project, payload=payload,
        )
        # Formal Wan currently cannot publish the required immutable video/tail
        # pair and lineage.  Fail closed rather than report a false completion.
        router.allow_wan_fallback = False
        checkpoint = self.novel_video_repository.get_generation_checkpoint(run.id, package.shot_id)
        h3 = getattr(router, "h3", None)
        if h3 is not None and hasattr(h3, "on_prompt_submitted"):
            canonical_binding = {key: generation_identity[key] for key in ("task_id", "run_id", "shot_id", "attempt_id")}
            if checkpoint:
                persisted_identity = {key: checkpoint.get(key) for key in ("task_id", "run_id", "shot_id", "attempt_id")}
                current_identity = {key: canonical_binding[key] for key in ("task_id", "run_id", "shot_id")}
                if any(persisted_identity[key] != value for key, value in current_identity.items()):
                    raise ValueError("formal prompt checkpoint task/run/shot identity mismatch")
                h3.task_binding = persisted_identity
            else:
                # H3's durable prompt schema has exactly these canonical
                # keys. Package hashing is a separate scheduler/asset fact.
                h3.task_binding = canonical_binding
            h3.on_prompt_submitted = lambda prompt_id, checkpoint=None: self.novel_video_repository.record_generation_prompt(
                run.id, shot_id=package.shot_id, prompt_id=prompt_id, checkpoint=checkpoint or {},
            )
        if self.lease_lock is None:
            from backend.video.worker_lock import WorkerLeaseLock
            self.lease_lock = WorkerLeaseLock(root=self.workdir)
        # Per-shot lock protects idempotency; the separate runtime-wide key
        # serializes heavy local GPU execution across different shots.
        self.lease_lock.acquire("formal-gpu")
        try:
            self.lease_lock.acquire(package.shot_id)
        except Exception:
            self.lease_lock.release("formal-gpu")
            raise
        try:
            active_prompt = checkpoint.get("prompt_id") if checkpoint else None
            result = await FormalNovelVideoWorker(self.novel_video_repository, router).generate_segment(
                run.id, request, resume_prompt_id=active_prompt, checkpoint=checkpoint,
                generation_identity=generation_identity,
            )
        finally:
            self.lease_lock.release(package.shot_id)
            self.lease_lock.release("formal-gpu")
        completion = {"path": str(result.video_path if hasattr(result, "video_path") else result.path), "kind": "video"}
        if "package_sha256" in payload:
            committed = self.novel_video_repository.find_generation_success(
                run.id, shot_id=package.shot_id, generation_identity=generation_identity,
                video_path=request.output_video, tail_path=request.output_tail,
            )
            if committed is None:
                raise RuntimeError("formal task completed without an authenticated candidate pair")
            video_asset, tail_asset = committed
            completion.update({"video_asset_id": video_asset.id, "tail_asset_id": tail_asset.id,
                               "prompt_id": result.prompt_id if hasattr(result, "prompt_id") else None,
                               "generation_identity": generation_identity})
        self.task_queue.complete(task.task_id, completion)

    def _formal_replay_context(self, task):
        """Resolve exact formal identity and confined outputs without constructing a provider."""
        from backend.novel_video.h3_provider import H3SegmentRequest
        from backend.novel_video.models import GenerationIdentity, H3ReferencePackage

        payload = task.payload or {}
        run_id = str(payload["run_id"])
        run = self.novel_video_repository.get_run(run_id)
        if run is None:
            raise KeyError(f"Novel-video run {run_id} does not exist")
        project = self.novel_video_repository.get_project(run.project_id)
        if project is None:
            raise KeyError(f"Novel-video project {run.project_id} does not exist")
        if task.project_id != run.project_id:
            raise ValueError("formal task project_id does not own its run")
        package = H3ReferencePackage.model_validate(payload["package"])
        if not package.shot_id:
            raise ValueError("formal package needs a shot id")
        shot = self.novel_video_repository.get_shot(package.shot_id)
        if shot is None or shot.run_id != run_id:
            raise ValueError("formal package shot does not belong to its run")
        expected_hash = _formal_package_hash(package)
        strict_scheduler = "package_sha256" in payload
        if strict_scheduler:
            if payload.get("package_sha256") != expected_hash:
                raise ValueError("formal task package hash does not verify")
            if shot.reference_package is None or _formal_package_hash(shot.reference_package) != expected_hash:
                raise ValueError("formal task package is stale against the persisted shot")
            if package.video_reference_asset_version_ids or package.audio_reference_asset_version_ids:
                raise ValueError("formal H3 API workflow does not support video/audio references")
            expected_paths = []
            previous = next((item for item in self.novel_video_repository.list_shots(run_id) if item.sequence == shot.sequence - 1), None)
            for asset_id in package.picture_asset_version_ids:
                asset = self.novel_video_repository.get_asset(asset_id)
                if asset is None or asset.project_id != project.id or asset.state != "approved" or not asset.path.is_file():
                    raise ValueError("formal picture reference is not an approved project asset")
                if asset.kind == "tail":
                    if previous is None or previous.status.value != "approved" or previous.approved_tail_asset_id != asset.id or asset.run_id != run_id:
                        raise ValueError("formal inherited tail is not the preceding approved run tail")
                expected_paths.append(str(asset.path))
            supplied_paths = [str(Path(path)) for path in payload.get("picture_paths", [])]
            if supplied_paths != expected_paths:
                raise ValueError("formal task picture paths do not match approved references")
        output_root = (Path(project.root) / "outputs" / "formal").resolve()
        request = H3SegmentRequest(
            package=package,
            picture_paths=tuple(Path(path) for path in payload.get("picture_paths", [])),
            output_video=self._formal_output_path(output_root, str(payload["output_video"])),
            output_tail=self._formal_output_path(output_root, str(payload["output_tail"])),
        )
        queue_checkpoint = dict(getattr(task, "checkpoint", {}) or {})
        attempt_id = str(
            queue_checkpoint.get("formal_generation_attempt_id")
            or f"{task.task_id}:{max(int(getattr(task, 'attempts', 0)), 1)}"
        )
        queue_checkpoint["formal_generation_attempt_id"] = attempt_id
        package_sha256 = payload.get("package_sha256")
        if not isinstance(package_sha256, str) or not package_sha256:
            # Legacy, non-scheduler formal payloads retain their historical
            # lightweight identity. Scheduler work is always exact below.
            generation_identity = {
                "task_id": task.task_id, "run_id": run_id,
                "shot_id": package.shot_id, "attempt_id": attempt_id,
            }
        else:
            generation_identity = GenerationIdentity(
                task_id=task.task_id, run_id=run_id, shot_id=package.shot_id,
                attempt_id=attempt_id, package_sha256=package_sha256,
            ).canonical()
        # Scheduler-generated package binding is stable across task claims and
        # makes an approved asset reusable only by the exact compiled shot.
        return payload, run, project, package, request, generation_identity, task

    def _complete_committed_formal_success(self, task, context) -> bool:
        """Complete only a cryptographically authenticated DB success replay."""
        _, run, _, package, request, generation_identity, _ = context
        committed = self.novel_video_repository.find_generation_success(
            run.id, shot_id=package.shot_id, generation_identity=generation_identity,
            video_path=request.output_video, tail_path=request.output_tail,
        )
        if committed is not None:
            video_asset, tail_asset = committed
            self.task_queue.complete(task.task_id, {
                "path": str(video_asset.path), "kind": "video",
                "video_asset_id": video_asset.id, "tail_asset_id": tail_asset.id,
                "prompt_id": video_asset.metadata.get("prompt_id"),
                "generation_identity": generation_identity,
                "recovered_committed_success": True,
            })
            return True
        return False

    def recover_committed_formal_success(self, task) -> str | None:
        """Startup hook: adopt exact durable success before stale-run reconciliation."""
        if self.novel_video_repository is None:
            return None
        context = self._formal_replay_context(task)
        return context[1].id if self._complete_committed_formal_success(task, context) else None
    # ------------------------------------------------------------- writeback
    @staticmethod
    def _formal_output_path(root: Path, supplied: str) -> Path:
        """Accept only a relative formal output name and confine it to project-owned storage."""
        candidate = Path(supplied)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("formal output path must be a relative project-storage path")
        resolved = (root / candidate).resolve()
        if root != resolved and root not in resolved.parents:
            raise ValueError("formal output path escapes project storage")
        return resolved

    def _writeback(
        self,
        task_id: str,
        *,
        shot_id: str = "",
        stage: str = "",
        progress: float = 0.0,
        gpu_time: float = 0.0,
        checkpoint: dict | None = None,
    ) -> None:
        task = self.task_queue.update(
            task_id,
            shot_id=shot_id,
            stage=stage,
            progress=progress,
            gpu_time_s=gpu_time,
            checkpoint=checkpoint or {},
        )
        if task is not None:
            self.broadcaster.broadcast(task_id, "task_progress", {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "shot_id": task.shot_id,
                "stage": task.stage,
                "progress": task.progress,
                "gpu_time": task.gpu_time_s,
                "checkpoint": task.checkpoint,
                "status": task.status,
            })

    # ------------------------------------------------------------- chain
    async def _run_chain(self, task, *, single: bool = False) -> None:
        from backend.video.runtime import ChainRuntime

        payload = task.payload or {}
        shots = payload.get("shots") or []
        if single:
            one = payload.get("shot")
            shots = [one] if one else (shots[:1] if shots else [])
        comfy_url = payload.get("comfy_url") or "http://127.0.0.1:8188"
        resume = bool(payload.get("resume", True))

        if self.lease_lock is None:
            from backend.video.worker_lock import WorkerLeaseLock
            self.lease_lock = WorkerLeaseLock(root=self.workdir)
        if self.cost_meter is None:
            from backend.video.cost_meter import CostMeter
            self.cost_meter = CostMeter()

        provider = self.video_provider_factory(comfy_url=comfy_url)
        runtime = ChainRuntime(
            project_id=task.project_id or payload.get("project_id", "default"),
            workdir=self.workdir,
            frame_extractor=self.frame_extractor,
            identity_verifier=self.identity_verifier,
            lease_lock=self.lease_lock,
            cost_meter=self.cost_meter,
            video_engine_policy=payload.get("video_engine_policy"),
        )

        # Phase 12.7-A: resolve the adaptive director route for every shot so
        # production actually follows the arena-backed recommendation with a
        # failure chain (primary -> fallback -> rule-v2).
        dispatcher = self.adaptive_dispatcher()
        for shot in shots:
            decision = dispatcher.dispatch(DispatchRequest(
                project=task.project_id or payload.get("project_id", ""),
                genre=str(shot.get("genre") or payload.get("genre") or "科幻"),
                scene_type=str(shot.get("scene_type") or shot.get("shot_type") or "action"),
                shot_type=str(shot.get("shot_type") or "medium"),
                style=str(shot.get("style") or payload.get("style") or ""),
                shot_id=str(shot.get("id") or shot.get("shot_id") or ""),
            ))
            shot["director_route"] = decision.to_dict()
            shot["primary_director"] = decision.primary_director
            shot["provider_chain"] = decision.provider_chain

        total = max(len(shots), 1)

        class _TrackingProvider:
            """Wraps the real provider and writes per-shot progress back."""

            def __init__(self, inner, runner, task_ref, total_shots):
                self.inner = inner
                self.runner = runner
                self.task_ref = task_ref
                self.total_shots = total_shots
                self.done = 0

            async def generate(self, request):
                shot_id = Path(request.output_path).stem
                self.done += 1
                self.runner._writeback(
                    self.task_ref.task_id,
                    shot_id=shot_id,
                    stage="chain_generate",
                    progress=round(self.done / self.total_shots, 3),
                )
                return await self.inner.generate(request)

        result = await runtime.run(
            shots,
            _TrackingProvider(provider, self, task, total),
            resume=resume,
        )
        summary = result.get("summary", {})
        gpu_time = self.cost_meter.summary().get("total_gpu_time_s", 0.0)
        for shot_result in result.get("results", []):
            self._writeback(
                task.task_id,
                shot_id=shot_result.get("shot_id", ""),
                stage=shot_result.get("status", ""),
                progress=1.0,
                gpu_time=gpu_time,
                checkpoint=summary,
            )
        # Any non-completed/skipped shot fails the task so retry_policy applies
        # (ChainRuntime already persisted the checkpoint, so retry resumes).
        bad = [
            r.get("shot_id", "")
            for r in result.get("results", [])
            if r.get("status") not in ("completed", "skipped")
        ]
        if bad:
            detail = next(
                (r.get("error", "") for r in result.get("results", [])
                 if r.get("shot_id") == bad[0] and r.get("error")),
                "",
            )
            message = f"chain stopped at {bad[0]}"
            if detail:
                message += f": {detail}"
            self.task_queue.fail(task.task_id, message)
            return
        self.task_queue.complete(task.task_id, result)

    # ------------------------------------------------------------- image
    async def _run_image(self, task) -> None:
        from backend.production.providers import ImageRequest

        payload = task.payload or {}
        provider = self.image_provider_factory(comfy_url=payload.get("comfy_url") or "http://127.0.0.1:8188")
        output = Path(payload.get("output_path") or self.workdir / task.project_id / "images" / f"{task.task_id}.png")
        output.parent.mkdir(parents=True, exist_ok=True)
        request = ImageRequest(
            prompt=payload.get("prompt", ""),
            negative_prompt=payload.get("negative_prompt", ""),
            seed=int(payload.get("seed", 0) or 0),
            width=int(payload.get("width", 432)),
            height=int(payload.get("height", 768)),
            output_path=output,
            reference_image=payload.get("reference_image", ""),
        )
        self._writeback(task.task_id, shot_id=payload.get("shot_id", ""), stage="image_generate", progress=0.5)
        artifact = await provider.generate(request)
        self.task_queue.complete(
            task.task_id,
            {"path": str(artifact.path), "kind": artifact.kind},
        )


class OrchestratorWorker:
    def __init__(
        self,
        db: OrchestrationDatabase,
        repo: JobRepository,
        executor: StageExecutor,
        broadcaster: SSEBroadcaster,
        config: OrchestrationConfig,
        workspace_repo: WorkspaceRepository | None = None,
        task_queue=None,
        task_runner=None,
    ):
        self.db = db
        self.repo = repo
        self.executor = executor
        self.broadcaster = broadcaster
        self.config = config
        self.workspace_repo = workspace_repo or WorkspaceRepository(db)
        self.task_queue = task_queue
        self.task_runner = task_runner
        self._lease_id = str(uuid.uuid4())
        self._running = False
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ tasks
    def enqueue_task(self, task_type: str, payload: dict, **kwargs):
        """Phase 10.7-A: enqueue a production task (no-op if no task queue)."""
        if self.task_queue is None:
            raise RuntimeError("task queue not configured on this worker")
        return self.task_queue.enqueue(task_type, payload, **kwargs)

    def _poll_tasks(self) -> None:
        """Claim queued tasks and run them through the TaskRunner."""
        if self.task_queue is None or self.task_runner is None:
            return
        claimed = self.task_queue.claim_next(self._lease_id, limit=2)
        for task in claimed:
            try:
                asyncio.run(self.task_runner.execute_task(task))
            except Exception as exc:
                from backend.video.worker_lock import LeaseError
                if isinstance(exc, LeaseError) and (task.payload or {}).get("formal_novel_video"):
                    # Global GPU contention is not a failed generation and
                    # must not consume the durable semantic attempt identity.
                    self.task_queue.update(
                        task.task_id, status="queued", worker_id="", error="",
                        attempts=max(0, task.attempts - 1),
                    )
                    continue
                traceback.print_exc()
                if (task.payload or {}).get("formal_novel_video"):
                    self.task_queue.fail_terminal(task.task_id, str(exc)[:500])
                else:
                    self.task_queue.fail(task.task_id, str(exc)[:500])
                self.broadcaster.broadcast(
                    task.task_id, "task_failed",
                    {"task_id": task.task_id, "error": str(exc)[:500]},
                )

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        # A formal H3 task can write a durable accepted-prompt checkpoint.
        # It must quiesce before the application closes its shared repository.
        self._thread = threading.Thread(target=self._loop, daemon=False)
        self._thread.start()

    def stop(self, timeout_seconds: float = 10.0) -> bool:
        self._running = False
        if self._thread:
            self._thread.join(timeout=timeout_seconds)
            return not self._thread.is_alive()
        return True

    def _loop(self) -> None:
        while self._running:
            try:
                self._recover_expired_leases()
                self._poll_and_execute()
                self._poll_tasks()
            except Exception:
                traceback.print_exc()
            time.sleep(self.config.poll_interval_seconds)

    def _recover_expired_leases(self) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        expired = self.repo.list_expired_leases(now)
        for job in expired:
            job_id = job["id"]
            self.repo.release_lease(job_id)
            transitioned = self.repo.set_job_status(
                job_id, JobStatus.QUEUED,
                message="Previous lease expired; re-queued.",
                allowed_from={JobStatus.RUNNING},
            )
            if not transitioned:
                raise RuntimeError(f"Could not re-queue expired job {job_id}")
            self.broadcaster.broadcast(job_id, "lease_recovered", {"job_id": job_id})

    def _poll_and_execute(self) -> None:
        jobs = self.repo.list_queued_jobs(limit=2)
        for job in jobs:
            job_id = job["id"]
            if not self.repo.acquire_lease(job_id, self._lease_id, self.config.lease_seconds):
                continue
            self.broadcaster.broadcast(job_id, "job_started", {"job_id": job_id})
            try:
                asyncio.run(self._execute_job(job_id))
            except Exception as e:
                traceback.print_exc()
                transitioned = self.repo.set_job_status(
                    job_id, JobStatus.FAILED,
                    message=str(e)[:500],
                    allowed_from={JobStatus.RUNNING},
                )
                if transitioned:
                    self.broadcaster.broadcast(job_id, "job_failed", {"job_id": job_id, "error": str(e)[:500]})
                self.repo.release_lease(job_id)

    async def _execute_job(self, job_id: str) -> None:
        steps = self.repo.get_job_steps(job_id)
        for initial_step in steps:
            step = initial_step
            job = self.repo.get_job(job_id)
            if not job or job["status"] in (JobStatus.PAUSED, JobStatus.CANCELLED):
                self.repo.release_lease(job_id)
                return

            step_status = step["status"]
            if step_status in (StepStatus.COMPLETED, StepStatus.CANCELLED, StepStatus.INVALIDATED):
                continue
            if step_status == StepStatus.WAITING_REVIEW:
                self._wait_for_review(
                    job_id, step,
                    reason="quality_gate" if step.get("quality_report") else "manual_gate",
                )
                return

            if step_status in (StepStatus.PENDING, StepStatus.RETRY_WAIT, StepStatus.RUNNING):
                self._set_step_status(
                    step["id"], StepStatus.QUEUED,
                    allowed_from={StepStatus(step_status)},
                )

            while True:
                step = self.repo.get_step(step["id"])
                if not step:
                    raise RuntimeError(f"Step {initial_step['id']} not found")
                policy, ui_stage_key = self._automation_policy(job, step)
                try:
                    await self.executor.execute_step(job_id, step)
                except QualityGateError as error:
                    if self._finish_interrupted_step(job_id, step["id"]):
                        return
                    self.repo.save_quality_report(step["id"], error.report)
                    step = self.repo.get_step(step["id"])
                    quality_attempt = step["quality_attempt"]
                    decision = (
                        decide_after_quality_failure(policy, quality_attempt)
                        if policy else StageDecision.WAIT_FOR_REVIEW
                    )
                    if decision == StageDecision.RETRY:
                        quality_attempt = self.repo.increment_quality_attempt(step["id"])
                        self._set_step_status(
                            step["id"], StepStatus.QUEUED,
                            allowed_from={StepStatus.RUNNING},
                        )
                        self.broadcaster.broadcast(
                            job_id, "quality_retry",
                            {
                                "job_id": job_id, "step_id": step["id"],
                                "stage_key": step["stage_key"],
                                "ui_stage_key": ui_stage_key,
                                "quality_attempt": quality_attempt,
                                "max_quality_retries": policy.max_quality_retries,
                                "quality_report": error.report,
                            },
                        )
                        continue
                    self._wait_for_review(
                        job_id, self.repo.get_step(step["id"]),
                        reason="quality_gate", ui_stage_key=ui_stage_key,
                    )
                    return
                except Exception as error:
                    if self._finish_interrupted_step(job_id, step["id"]):
                        return
                    error_message = str(error)[:500]
                    self._set_step_status(
                        step["id"], StepStatus.FAILED,
                        error_code="SYSTEM_ERROR", error_message=error_message,
                        allowed_from={StepStatus.RUNNING},
                    )
                    self.broadcaster.broadcast(
                        job_id, "step_failed",
                        {
                            "job_id": job_id, "step_id": step["id"],
                            "stage_key": step["stage_key"],
                            "ui_stage_key": ui_stage_key,
                            "error": error_message,
                        },
                    )
                    raise

                if self._finish_interrupted_step(job_id, step["id"]):
                    return

                decision = decide_after_success(policy) if policy else StageDecision.ADVANCE
                if decision == StageDecision.ADVANCE:
                    self._set_step_status(
                        step["id"], StepStatus.COMPLETED,
                        allowed_from={StepStatus.RUNNING},
                    )
                    self.broadcaster.broadcast(
                        job_id, "step_completed",
                        {
                            "job_id": job_id, "step_id": step["id"],
                            "stage_key": step["stage_key"],
                            "ui_stage_key": ui_stage_key,
                        },
                    )
                    break
                self._wait_for_review(
                    job_id, self.repo.get_step(step["id"]),
                    reason="manual_gate", ui_stage_key=ui_stage_key,
                )
                return

        completed = self.repo.set_job_status(
            job_id, JobStatus.COMPLETED,
            message="All stages completed.",
            allowed_from={JobStatus.RUNNING},
        )
        if completed:
            self.broadcaster.broadcast(job_id, "job_completed", {"job_id": job_id})
        self.repo.release_lease(job_id)

    def _automation_policy(self, job: dict, step: dict) -> tuple[StageAutomation | None, str]:
        ui_stage_key = step.get("ui_stage_key", "")
        if not ui_stage_key:
            mapped = EXECUTION_TO_UI_STAGE.get(step["stage_key"])
            ui_stage_key = mapped.value if mapped else ""
        if not ui_stage_key:
            return None, ""
        stage_key = StageKey(ui_stage_key)
        return self.workspace_repo.get_stage_automation(job["project_id"], stage_key), ui_stage_key

    def _wait_for_review(
        self, job_id: str, step: dict, *, reason: str, ui_stage_key: str | None = None,
    ) -> None:
        ui_stage_key = ui_stage_key or step.get("ui_stage_key", "")
        if not ui_stage_key:
            mapped = EXECUTION_TO_UI_STAGE.get(step["stage_key"])
            ui_stage_key = mapped.value if mapped else ""
        if step["status"] != StepStatus.WAITING_REVIEW:
            self._set_step_status(
                step["id"], StepStatus.WAITING_REVIEW,
                allowed_from={StepStatus.RUNNING},
            )
        transitioned = self.repo.set_job_status(
            job_id, JobStatus.WAITING_REVIEW,
            message=f"Waiting for review at step {step['stage_key']}",
            allowed_from={JobStatus.RUNNING},
        )
        if not transitioned:
            raise RuntimeError(f"Could not move job {job_id} to review")
        self.repo.release_lease(job_id)
        data = {
            "job_id": job_id, "step_id": step["id"],
            "stage_key": step["stage_key"], "ui_stage_key": ui_stage_key,
            "reason": reason,
        }
        if reason == "quality_gate":
            current = self.repo.get_step(step["id"])
            data.update(
                quality_attempt=current["quality_attempt"],
                quality_report=current["quality_report"],
            )
        self.broadcaster.broadcast(job_id, "review_needed", data)

    def _set_step_status(
        self, step_id: str, status: StepStatus, *, allowed_from: set[StepStatus], **kwargs: Any,
    ) -> None:
        if not self.repo.set_step_status(step_id, status, allowed_from=allowed_from, **kwargs):
            expected = ", ".join(sorted(value.value for value in allowed_from))
            raise RuntimeError(
                f"Could not move step {step_id} to {status.value} from expected state: {expected}"
            )

    def _finish_interrupted_step(self, job_id: str, step_id: str) -> bool:
        job = self.repo.get_job(job_id)
        if not job:
            raise RuntimeError(f"Job {job_id} not found")
        status = JobStatus(job["status"])
        if status == JobStatus.PAUSED:
            self._set_step_status(step_id, StepStatus.QUEUED, allowed_from={StepStatus.RUNNING})
        elif status == JobStatus.CANCELLED:
            self._set_step_status(step_id, StepStatus.CANCELLED, allowed_from={StepStatus.RUNNING})
        else:
            return False
        self.repo.release_lease(job_id)
        return True


def _create_placeholder_image(output_path: Path) -> None:
    """Create a minimal placeholder image when generation fails."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image
        img = Image.new("RGB", (432, 768), color=(30, 30, 40))
        img.save(str(output_path))
    except Exception:
        output_path.write_bytes(b"")


def _default_image_template() -> dict:
    """Minimal Flux image generation workflow."""
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-dev.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "{prompt}", "clip": ["1", 1]}},
        "3": {"class_type": "EmptyLatentImage", "inputs": {"width": "{width}", "height": "{height}", "batch_size": 1}},
        "4": {"class_type": "KSampler", "inputs": {"seed": "{seed}", "steps": 20, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0], "negative": ["2", 0], "latent_image": ["3", 0]}},
        "5": {"class_type": "VAEDecode", "inputs": {"samples": ["4", 0], "vae": ["1", 2]}},
        "6": {"class_type": "SaveImage", "inputs": {"filename_prefix": "{filename_prefix}", "images": ["5", 0]}},
    }

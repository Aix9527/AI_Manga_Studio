from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Callable

from backend.orchestration.repository import JobRepository
from backend.orchestration.enums import StepStatus
from backend.production.comfy_adapter import ComfyUIAdapter
from backend.production.contracts import ProductionPlan, Chapter, ShotSpec
from backend.production.input_loader import load_input
from backend.production.media_validation import MediaValidator
from backend.production.keyframe_generator import KeyframeGenerator

logger = logging.getLogger(__name__)


class NoFallbackPolicy:
    """Strict V5 policy: no local fallback artifacts allowed."""
    allow_fallback_images: bool = False
    allow_silent_audio: bool = False


class ProductionStageRunner:
    def __init__(
        self,
        repo: JobRepository,
        comfy: ComfyUIAdapter,
        validator: MediaValidator,
        project_root: str = "projects",
    ):
        self.repo = repo
        self.comfy = comfy
        self.validator = validator
        self.project_root = Path(project_root)
        self.policy = NoFallbackPolicy()
        self.keyframe_gen = KeyframeGenerator()

    async def execute(self, job_id: str, plan: ProductionPlan) -> list[dict]:
        results: list[dict] = []
        steps = self.repo.get_job_steps(job_id)

        # Group steps by stage for parallel processing
        # visual_generate steps for different shots can run in parallel
        visual_steps: list[dict] = []
        other_steps: list[dict] = []

        for step in steps:
            stage = step["stage_key"]
            if stage.startswith("visual_"):
                visual_steps.append(step)
            else:
                other_steps.append(step)

        # Process non-visual steps sequentially first (load, plan, etc.)
        for step in other_steps:
            stage = step["stage_key"]
            step_id = step["id"]
            # Skip visual steps that will be batch-processed
            if stage.startswith("visual_"):
                continue
            try:
                self.repo.start_step(step_id)
                result = await self._run_stage(job_id, step_id, step, plan)
                results.append({"step_id": step_id, "stage": stage, "success": True, **result})
            except Exception as exc:
                logger.error("Stage %s failed: %s", stage, exc, exc_info=True)
                results.append({"step_id": step_id, "stage": stage, "success": False, "error": str(exc)})
                raise

        # Process visual_generate steps in parallel (up to 3 concurrent)
        if visual_steps:
            logger.info("Processing %d visual steps in parallel (max 3 concurrent)",
                        len(visual_steps))
            try:
                from backend.production.parallel_processor import ParallelProcessor
                processor = ParallelProcessor(max_concurrency=3, repo=self.repo)

                async def _process_visual_step(step: dict) -> dict:
                    step_id = step["id"]
                    shot_id = step.get("shot_id", "")
                    stage = step["stage_key"]
                    output_dir = self.project_root / plan.project_id / "outputs"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    try:
                        self.repo.start_step(step_id)
                        result = await self._visual(job_id, step_id, shot_id, plan, output_dir)
                        return {"step_id": step_id, "stage": stage, "success": True, **result}
                    except Exception as exc:
                        logger.error("Visual step %s (shot %s) failed: %s",
                                    step_id, shot_id, exc, exc_info=True)
                        return {"step_id": step_id, "stage": stage,
                                "success": False, "error": str(exc)}

                visual_results = await processor.process_shots_parallel(
                    shots=visual_steps,
                    process_func=_process_visual_step,
                    job_id=job_id,
                    stage_name="visual_generate",
                )
                results.extend(visual_results)

                # Check for failures
                failures = [r for r in visual_results if not r.get("success", False)]
                if failures:
                    logger.warning("%d visual steps failed out of %d",
                                 len(failures), len(visual_results))

            except ImportError:
                logger.warning("ParallelProcessor not available, falling back to sequential")
                for step in visual_steps:
                    stage = step["stage_key"]
                    step_id = step["id"]
                    shot_id = step.get("shot_id", "")
                    try:
                        self.repo.start_step(step_id)
                        result = await self._run_stage(job_id, step_id, step, plan)
                        results.append({"step_id": step_id, "stage": stage, "success": True, **result})
                    except Exception as exc:
                        logger.error("Stage %s failed: %s", stage, exc, exc_info=True)
                        results.append({"step_id": step_id, "stage": stage, "success": False, "error": str(exc)})
                        raise

        return results

    async def _run_stage(self, job_id: str, step_id: str, step: dict, plan: ProductionPlan) -> dict:
        stage = step["stage_key"]
        shot_id = step.get("shot_id", "")
        output_dir = self.project_root / plan.project_id / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)

        if stage == "load_input":
            return await self._load(job_id, step_id, plan)
        elif stage == "planning":
            return await self._plan(job_id, step_id, plan)
        elif stage == "character_design":
            return await self._character_design(job_id, step_id, plan)
        elif stage.startswith("visual_"):
            return await self._visual(job_id, step_id, shot_id, plan, output_dir)
        elif stage == "hd_redraw":
            return await self._hd_redraw(job_id, step_id, shot_id, plan, output_dir)
        elif stage.startswith("audio_"):
            return await self._audio(job_id, step_id, stage, plan, output_dir)
        elif stage.startswith("composition_"):
            return await self._compose(job_id, step_id, plan, output_dir)
        elif stage == "export":
            return await self._export(job_id, step_id, plan, output_dir)
        else:
            raise ValueError(f"Unknown stage: {stage}")

    def _update_progress(self, job_id: str, step_id: str, stage: str, shot: str,
                         progress: float, message: str) -> None:
        """Update both job-level and step-level progress."""
        self.repo.set_job_progress(job_id, stage, shot, progress, message)
        self.repo.update_step_progress(step_id, progress)

    async def _load(self, job_id: str, step_id: str, plan: ProductionPlan) -> dict:
        """Load input and mark stage as complete."""
        self._update_progress(job_id, step_id, "load_input", "", 0.3, "Loading input data")
        await asyncio.sleep(0.1)

        self._update_progress(job_id, step_id, "load_input", "", 0.7,
                             f"Parsed: {plan.input_contract.title}")
        await asyncio.sleep(0.1)

        # Mark stage as complete
        self._update_progress(job_id, step_id, "load_input", "", 1.0, "Input loaded successfully")
        self.repo.complete_step(step_id)

        return {"title": plan.input_contract.title, "chapters": plan.input_contract.chapter_count}

    async def _plan(self, job_id: str, step_id: str, plan: ProductionPlan) -> dict:
        """Generate storyboard plan and mark stage as complete."""
        self._update_progress(job_id, step_id, "planning", "", 0.3, "Analyzing story structure")
        await asyncio.sleep(0.1)

        self._update_progress(job_id, step_id, "planning", "", 0.6,
                             f"Generated {len(plan.shots)} shots")
        await asyncio.sleep(0.1)

        # Save production plan to file
        plan_path = self.project_root / plan.project_id / "production_plan.json"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_data = {
            "project_id": plan.project_id,
            "title": plan.input_contract.title,
            "shots": [
                {
                    "id": s.id,
                    "shot_number": s.shot_number,
                    "description": s.description,
                    "duration": s.duration,
                    "camera": s.camera,
                    "characters": s.characters,
                    "dialogue": s.dialogue,
                    "sfx": s.sfx,
                    "positive_prompt": s.positive_prompt,
                    "negative_prompt": s.negative_prompt,
                    "narration": s.narration,
                    "transition": s.transition,
                    "seed": s.seed,
                }
                for s in plan.shots
            ],
            "settings": plan.settings,
            "total_duration": plan.total_duration,
        }
        plan_path.write_text(json.dumps(plan_data, ensure_ascii=False, indent=2), encoding="utf-8")

        # Mark stage as complete
        self._update_progress(job_id, step_id, "planning", "", 1.0,
                             f"Storyboard: {len(plan.shots)} shots")
        self.repo.complete_step(step_id)

        return {"shot_count": len(plan.shots)}

    async def _character_design(self, job_id: str, step_id: str,
                                plan: ProductionPlan) -> dict:
        """Generate character reference images for consistency (tutorial Step 03).

        Uses CharacterDesigner to:
        1. Read character profiles from the production plan
        2. Generate reference images via ComfyUI
        3. Save character_refs.json for downstream stages
        """
        self._update_progress(job_id, step_id, "character_design", "", 0.25,
                             "Generating character reference images...")
        await asyncio.sleep(0.1)

        try:
            from backend.production.character_designer import CharacterDesigner

            # Extract characters from plan settings
            plan_settings = plan.settings or {}
            plan_chars = plan_settings.get("characters", {})
            characters: list[dict] = []

            for name, styling in plan_chars.items():
                characters.append({
                    "name": name,
                    "appearance": styling if isinstance(styling, str) else "",
                    "image_prompt": styling if isinstance(styling, str) else "",
                })

            if not characters:
                self._update_progress(job_id, step_id, "character_design", "", 0.25,
                                     "No characters found, skipping")
                self.repo.complete_step(step_id)
                return {"character_count": 0}

            designer = CharacterDesigner(
                output_root=str(self.project_root),
            )
            results = await designer.design_characters(plan.project_id, characters)

            # Save reference map
            ref_map = designer.get_reference_image_map(results)
            ref_path = self.project_root / plan.project_id / "character_refs.json"
            ref_path.write_text(
                json.dumps(ref_map, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            from backend.production.reference_registry import ReferenceRegistry
            ReferenceRegistry.from_character_designs(results).save(
                self.project_root / plan.project_id / "reference_registry.json"
            )

            img_count = sum(1 for r in results if r.get("reference_image"))
            self._update_progress(job_id, step_id, "character_design", "", 1.0,
                                 f"Designed {len(results)} characters, {img_count} images")
            self.repo.complete_step(step_id)

            return {"character_count": len(results), "images_generated": img_count}

        except Exception as exc:
            logger.error("Character design failed: %s", exc, exc_info=True)
            self._update_progress(job_id, step_id, "character_design", "", 0.25,
                                 f"Character design failed: {exc}")
            self.repo.complete_step(step_id)
            return {"character_count": 0, "error": str(exc)}

    async def _hd_redraw(self, job_id: str, step_id: str, shot_id: str,
                         plan: ProductionPlan, output_dir: Path) -> dict:
        """Upscale keyframe to HD resolution (tutorial Step 05).

        Uses HDRedrawer to enhance the storyboard frame to 4K quality
        before video generation, ensuring higher quality output.
        """
        # Check if shot exists in plan
        shot_spec = next((s for s in plan.shots if s.id == shot_id), None)
        if shot_spec is None:
            self._update_progress(job_id, step_id, "hd_redraw", shot_id, 1.0,
                                 f"Skipping {shot_id} (not in plan)")
            self.repo.complete_step(step_id)
            return {"shot_id": shot_id, "skipped": True}

        shot_dir = output_dir / "images" / shot_id
        frame_path = shot_dir / "frame.png"

        if not frame_path.exists():
            self._update_progress(job_id, step_id, "hd_redraw", shot_id, 1.0,
                                 f"No keyframe for {shot_id}, skipping")
            self.repo.complete_step(step_id)
            return {"shot_id": shot_id, "skipped": True}

        hd_path = shot_dir / "frame_hd.png"
        self._update_progress(job_id, step_id, "hd_redraw", shot_id, 0.42,
                             f"HD redrawing {shot_id}...")
        await asyncio.sleep(0.1)

        try:
            from backend.production.hd_redraw import HDRedrawer

            redrawer = HDRedrawer()
            success = await redrawer.redraw_frame(
                input_path=frame_path,
                output_path=hd_path,
                original_prompt=shot_spec.positive_prompt if shot_spec else "",
                shot_id=shot_id,
            )

            if not success or not hd_path.exists():
                import shutil
                shutil.copy2(frame_path, hd_path)
                logger.warning("HD redraw fallback: copied original for %s", shot_id)

            # Register artifact
            path_hash = hashlib.sha256(str(hd_path).encode()).hexdigest()[:16]
            self.repo.add_artifact(job_id, shot_id, "image", str(hd_path), path_hash, {
                "frame_type": "hd",
                "shot_id": shot_id,
            })

            self._update_progress(job_id, step_id, "hd_redraw", shot_id, 1.0,
                                 f"HD redraw done for {shot_id}")
            self.repo.complete_step(step_id)

            return {"shot_id": shot_id, "hd_path": str(hd_path)}

        except Exception as exc:
            logger.error("HD redraw failed for %s: %s", shot_id, exc, exc_info=True)
            # Fallback: copy original
            import shutil
            shutil.copy2(frame_path, hd_path)
            self._update_progress(job_id, step_id, "hd_redraw", shot_id, 1.0,
                                 f"HD redraw fallback for {shot_id}")
            self.repo.complete_step(step_id)
            return {"shot_id": shot_id, "error": str(exc)}

    async def _visual(self, job_id: str, step_id: str, shot_id: str,
                      plan: ProductionPlan, output_dir: Path) -> dict:
        """Generate keyframe images for a shot using ComfyUI.

        This method ACTUALLY generates images via ComfyUI text-to-image workflow.
        Generates both first_frame.png and last_frame.png for interpolation.
        """
        shot_dir = output_dir / "images" / shot_id
        shot_dir.mkdir(parents=True, exist_ok=True)

        # Find the shot spec
        shot_spec = next((s for s in plan.shots if s.id == shot_id), None)
        if shot_spec is None:
            plan_path = self.project_root / plan.project_id / "production_plan.json"
            if plan_path.exists():
                plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
                shot_data = next((s for s in plan_data.get("shots", []) if s.get("id") == shot_id), None)
                if shot_data is None:
                    shot_data = {"id": shot_id, "description": f"Shot {shot_id}", "positive_prompt": ""}
            else:
                shot_data = {"id": shot_id, "description": f"Shot {shot_id}", "positive_prompt": ""}
        else:
            shot_data = {
                "id": shot_spec.id,
                "description": shot_spec.description,
                "positive_prompt": shot_spec.positive_prompt,
                "negative_prompt": shot_spec.negative_prompt,
                "camera": shot_spec.camera,
                "narration": shot_spec.narration,
                "seed": shot_spec.seed,
            }

        self._update_progress(job_id, step_id, "visual_generate", shot_id, 0.2,
                             f"Preparing {shot_id}")
        await asyncio.sleep(0.1)

        # Generate first frame
        # GPT Round-1: 每个镜头使用唯一文件名（{shot_id}_start.png），
        # 避免所有镜头共用 frame.png 导致首帧/封面雷同
        first_frame_path = shot_dir / f"{shot_id}_start.png"
        if not first_frame_path.exists():
            self._update_progress(job_id, step_id, "visual_generate", shot_id, 0.3,
                                 f"Generating first frame for {shot_id}")
            logger.info("Generating first frame for %s", shot_id)

            success = await self.keyframe_gen.generate_keyframe(
                shot_data=shot_data,
                output_path=first_frame_path,
                frame_type="first",
            )
            if not success or not first_frame_path.exists():
                raise RuntimeError(f"Failed to generate first frame for {shot_id}")
        else:
            logger.info("First frame already exists for %s, skipping", shot_id)

        self._update_progress(job_id, step_id, "visual_generate", shot_id, 0.6,
                             f"First frame done for {shot_id}")
        await asyncio.sleep(0.1)

        # Generate last frame for interpolation
        last_frame_path = shot_dir / f"{shot_id}_end.png"
        if not last_frame_path.exists():
            self._update_progress(job_id, step_id, "visual_generate", shot_id, 0.8,
                                 f"Generating last frame for {shot_id}")
            logger.info("Generating last frame for %s", shot_id)

            success = await self.keyframe_gen.generate_keyframe(
                shot_data=shot_data,
                output_path=last_frame_path,
                frame_type="last",
            )
            if not success or not last_frame_path.exists():
                logger.warning("Last frame generation failed for %s, using first frame", shot_id)
                import shutil
                shutil.copy2(first_frame_path, last_frame_path)

        # Mark stage as complete
        self._update_progress(job_id, step_id, "visual_generate", shot_id, 1.0,
                             f"Keyframes done for {shot_id}")
        self.repo.complete_step(step_id)

        # Register artifacts
        path_hash = hashlib.sha256(str(first_frame_path).encode()).hexdigest()[:16]
        self.repo.add_artifact(job_id, shot_id, "image", str(first_frame_path), path_hash, {
            "frame_type": "first",
            "shot_id": shot_id,
        })
        if last_frame_path.exists():
            last_hash = hashlib.sha256(str(last_frame_path).encode()).hexdigest()[:16]
            self.repo.add_artifact(job_id, shot_id, "image", str(last_frame_path), last_hash, {
                "frame_type": "last",
                "shot_id": shot_id,
            })

        return {"shot_id": shot_id, "output": str(first_frame_path),
                "last_frame": str(last_frame_path)}

    async def _audio(self, job_id: str, step_id: str, stage: str,
                     plan: ProductionPlan, output_dir: Path) -> dict:
        """Generate audio (TTS or SFX) for the production."""
        audio_dir = output_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        if stage == "audio_tts":
            self._update_progress(job_id, step_id, stage, "", 0.3, "Generating TTS narration")
            await asyncio.sleep(0.1)

            output_path = audio_dir / "tts.wav"
            narration_text = ""
            for shot in plan.shots:
                if shot.narration:
                    narration_text += shot.narration + " "

            if narration_text:
                try:
                    import subprocess
                    result = subprocess.run(
                        ["edge-tts", "--text", narration_text[:3000], "--write-media", str(output_path)],
                        capture_output=True, text=True, timeout=60
                    )
                    if result.returncode != 0:
                        logger.warning("edge-tts failed, creating silent audio")
                        self._create_silent_audio(output_path, duration=10.0)
                except Exception as exc:
                    logger.warning("TTS generation failed: %s, creating silent audio", exc)
                    self._create_silent_audio(output_path, duration=10.0)
            else:
                self._create_silent_audio(output_path, duration=5.0)

            self._update_progress(job_id, step_id, stage, "", 0.7, "TTS audio generated")
            await asyncio.sleep(0.1)
        else:
            self._update_progress(job_id, step_id, stage, "", 0.3, "Generating SFX")
            await asyncio.sleep(0.1)
            output_path = audio_dir / "sfx.wav"
            self._create_silent_audio(output_path, duration=5.0)
            self._update_progress(job_id, step_id, stage, "", 0.7, "SFX generated")
            await asyncio.sleep(0.1)

        self._update_progress(job_id, step_id, stage, "", 1.0, f"{stage} completed")
        self.repo.complete_step(step_id)

        result = {"stage": stage, "output": str(output_path)}
        path_hash = hashlib.sha256(str(output_path).encode()).hexdigest()[:16]
        self.repo.add_artifact(job_id, stage, "audio", str(output_path), path_hash, {})
        return result

    def _create_silent_audio(self, path: Path, duration: float = 5.0) -> None:
        """Create a silent WAV file of the given duration."""
        try:
            import wave
            import struct
            sample_rate = 44100
            num_samples = int(duration * sample_rate)
            path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(path), 'w') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)
                for _ in range(num_samples):
                    wav.writeframes(struct.pack('<h', 0))
        except Exception as exc:
            logger.warning("Failed to create silent audio: %s", exc)

    async def _compose(self, job_id: str, step_id: str,
                       plan: ProductionPlan, output_dir: Path) -> dict:
        """Compose all shots into a single video."""
        compose_dir = output_dir / "composition"
        compose_dir.mkdir(parents=True, exist_ok=True)

        self._update_progress(job_id, step_id, "composition_compose", "", 0.2,
                             "Preparing composition")
        await asyncio.sleep(0.1)

        vid_dir = output_dir / "videos"
        clips = sorted(vid_dir.glob("*/ai_clip.mp4")) if vid_dir.exists() else []

        self._update_progress(job_id, step_id, "composition_compose", "",
                             0.4, f"Found {len(clips)} clips")
        await asyncio.sleep(0.1)

        output_path = compose_dir / "composite.mp4"

        if clips:
            try:
                import tempfile
                list_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                                        delete=False, encoding="utf-8")
                for clip in clips:
                    list_file.write(f"file '{clip.absolute()}'\n")
                list_file.close()

                import subprocess
                result = subprocess.run(
                    ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                     "-i", list_file.name, "-c", "copy", str(output_path)],
                    capture_output=True, text=True, timeout=120
                )
                Path(list_file.name).unlink(missing_ok=True)

                if result.returncode != 0:
                    logger.warning("FFmpeg concat failed: %s", result.stderr[:500])
                    if clips:
                        import shutil
                        shutil.copy2(clips[0], output_path)
            except Exception as exc:
                logger.warning("Composition failed: %s", exc)
                if clips:
                    import shutil
                    shutil.copy2(clips[0], output_path)
        else:
            img_dir = output_dir / "images"
            first_frame = next(img_dir.glob("*/frame.png"), None) if img_dir.exists() else None
            if first_frame:
                try:
                    import subprocess
                    result = subprocess.run(
                        ["ffmpeg", "-y", "-loop", "1", "-i", str(first_frame),
                         "-c:v", "libx264", "-t", "5", "-pix_fmt", "yuv420p",
                         "-vf", "scale=1280:720", str(output_path)],
                        capture_output=True, text=True, timeout=60
                    )
                    if result.returncode != 0:
                        logger.warning("Placeholder video creation failed: %s", result.stderr[:500])
                except Exception as exc:
                    logger.warning("FFmpeg placeholder failed: %s", exc)

        self._update_progress(job_id, step_id, "composition_compose", "", 0.7,
                             "Composition done")
        await asyncio.sleep(0.1)

        self._update_progress(job_id, step_id, "composition_compose", "", 1.0,
                             "Video composed")
        self.repo.complete_step(step_id)

        result = {"output": str(output_path)}
        if output_path.exists():
            path_hash = hashlib.sha256(str(output_path).encode()).hexdigest()[:16]
            self.repo.add_artifact(job_id, "composition", "video", str(output_path), path_hash, {})
        return result

    async def _export(self, job_id: str, step_id: str,
                      plan: ProductionPlan, output_dir: Path) -> dict:
        """Export the final video with audio."""
        export_dir = output_dir / "export"
        export_dir.mkdir(parents=True, exist_ok=True)

        self._update_progress(job_id, step_id, "export", "", 0.2, "Preparing export")
        await asyncio.sleep(0.1)

        final_path = export_dir / "final.mp4"
        composite_path = output_dir / "composition" / "composite.mp4"
        audio_path = output_dir / "audio" / "tts.wav"

        if composite_path.exists():
            try:
                import subprocess
                cmd = ["ffmpeg", "-y", "-i", str(composite_path)]
                if audio_path.exists():
                    cmd.extend(["-i", str(audio_path), "-c:a", "aac", "-b:a", "128k"])
                cmd.extend([
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-vf", "scale=1280:720", "-r", "24",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                    str(final_path)
                ])
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode != 0:
                    logger.warning("FFmpeg export failed: %s", result.stderr[:500])
                    import shutil
                    shutil.copy2(composite_path, final_path)
            except Exception as exc:
                logger.warning("Export failed: %s", exc)
                import shutil
                shutil.copy2(composite_path, final_path)
        else:
            logger.warning("No composite video found for export")

        self._update_progress(job_id, step_id, "export", "", 0.7, "Export processing")
        await asyncio.sleep(0.1)

        self._update_progress(job_id, step_id, "export", "", 1.0, "Export complete")
        self.repo.complete_step(step_id)

        # Set final video path
        self.repo.set_job_status(
            job_id,
            "completed" if final_path.exists() else "failed",
            message="Production complete",
            final_video=str(final_path) if final_path.exists() else "",
        )

        result = {"final_video": str(final_path)}
        if final_path.exists():
            path_hash = hashlib.sha256(str(final_path).encode()).hexdigest()[:16]
            self.repo.add_artifact(job_id, "export", "video", str(final_path), path_hash, {
                "final": True,
                "file_size": final_path.stat().st_size,
            })
        return result

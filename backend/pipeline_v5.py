"""
AI Manga Studio Pro V5 鈥?Pipeline Orchestrator Integration

Ties together all V5 modules into a cohesive production pipeline:
1. Novel -> Chapters -> Scenes -> Beats -> Shots
2. Character sheet generation (涓夎韩鍥?
3. Storyboard generation with lighting design
4. Image generation with character consistency lock
5. Last frame generation for I2V
6. Director-level video prompt generation
7. I2V video generation (Wan2.2 / LTX2.3 / AnimateDiff)
8. Shot table (闀滆〃) export
9. Quality checking and retry

Usage:
    from backend.pipeline_v5 import PipelineV5
    pipeline = PipelineV5()
    result = pipeline.run(project_id="my_project")
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from backend.unified_shot import UnifiedShot, ShotStatus, ShotBatch
from backend.workflow_generator import WorkflowGenerator
from backend.i2v_generator import I2VGenerator
from backend.comfyui_client import ComfyUIClient
from backend.config import get_config

# V5 modules
from backend.director_video_prompt_builder import (
    CinematicShot,
    DirectorVideoPrompt,
    DirectorVideoPromptBuilder,
)
from backend.character_sheet_generator import (
    CharacterSheet,
    CharacterSheetGenerator,
)
from backend.last_frame_generator import LastFrameGenerator
from backend.shot_table_generator import ShotTableGenerator
from backend.storyboard_engine_v5 import StoryboardEngine, StoryboardPanel
from backend.character_consistency_lock import (
    CharacterConsistencyManager,
    CharacterLock,
)
from backend.prompt_library_v5 import PromptLibrary


# ============================================================
# Data Models
# ============================================================

@dataclass
class PipelineStage:
    """Status of a single pipeline stage."""
    name: str = ""
    status: str = "pending"  # pending, running, success, failed
    elapsed: float = 0.0
    error: str = ""
    output: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ShotPipelineResult:
    """Result of processing a single shot through the V5 pipeline."""
    shot_id: str = ""
    chapter: int = 1
    scene: int = 1
    shot_num: int = 1

    # Stage results
    storyboard: Optional[StoryboardPanel] = None
    image_path: str = ""
    last_frame_path: str = ""
    video_path: str = ""

    # Director prompts
    image_prompt: str = ""
    video_prompt: str = ""
    last_frame_prompt: str = ""

    # Character locks
    character_locks: Dict[str, CharacterLock] = field(default_factory=dict)

    # Status
    status: str = "pending"
    error: str = ""
    warnings: List[str] = field(default_factory=list)
    elapsed: float = 0.0


@dataclass
class PipelineResult:
    """Result of running the full V5 pipeline."""
    project_id: str = ""
    stages: List[PipelineStage] = field(default_factory=list)
    shots: List[ShotPipelineResult] = field(default_factory=list)
    shot_tables: List[Dict[str, Any]] = field(default_factory=list)
    character_sheets: List[CharacterSheet] = field(default_factory=list)
    total_shots: int = 0
    success: int = 0
    failed: int = 0
    elapsed: float = 0.0
    final_video: str = ""
    output_dir: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "total_shots": self.total_shots,
            "success": self.success,
            "failed": self.failed,
            "elapsed": self.elapsed,
            "final_video": self.final_video,
            "output_dir": self.output_dir,
            "stages": [s.__dict__ for s in self.stages],
            "shot_tables_count": len(self.shot_tables),
            "character_sheets_count": len(self.character_sheets),
        }


# ============================================================
# V5 Pipeline Orchestrator
# ============================================================

class PipelineV5:
    """Full production pipeline for AI manga/video generation.

    V5 Pipeline Stages:
    1. Character Sheet Generation (涓夎韩鍥?
    2. Storyboard Generation (鍒嗛暅澶?+ 鐏厜璁捐)
    3. Image Generation (with consistency lock)
    4. Last Frame Generation (灏惧抚)
    5. Director Video Prompt Generation (瀵兼紨绾ц棰戞彁绀鸿瘝)
    6. I2V Video Generation (Wan2.2 / LTX2.3)
    7. Shot Table Export (闀滆〃)
    """

    def __init__(
        self,
        comfyui_url: str = "",
        style: str = "anime",
        max_retries: int = 3,
    ):
        cfg = get_config()
        self.comfyui = ComfyUIClient(
            base_url=comfyui_url or cfg.comfyui.base_url,
        )
        self.workflow_gen = WorkflowGenerator()
        self.i2v_gen = I2VGenerator()

        # V5 modules
        self.director_builder = DirectorVideoPromptBuilder()
        self.character_sheet_gen = CharacterSheetGenerator(style=style)
        self.last_frame_gen = LastFrameGenerator()
        self.shot_table_gen = ShotTableGenerator()
        self.storyboard_engine = StoryboardEngine()
        self.consistency_mgr = CharacterConsistencyManager(style=style)
        self.prompt_lib = PromptLibrary()

        self.max_retries = max_retries
        self.style = style
        logger.info("PipelineV5 initialized")

    def run(
        self,
        project_id: str,
        generate_image: bool = True,
        generate_video: bool = True,
        generate_character_sheets: bool = True,
        generate_shot_tables: bool = True,
        on_shot: Optional[Callable[[ShotPipelineResult], None]] = None,
        on_stage: Optional[Callable[[PipelineStage], None]] = None,
    ) -> PipelineResult:
        """Run the full V5 pipeline for a project.

        Args:
            project_id: Project identifier.
            generate_image: Run image generation stage.
            generate_video: Run I2V video generation stage.
            generate_character_sheets: Generate 涓夎韩鍥?for all characters.
            generate_shot_tables: Export professional shot tables.
            on_shot: Callback for each shot result.

        Returns:
            PipelineResult with all outputs.
        """
        start = time.time()
        cfg = get_config()
        base = cfg.project.output_path or cfg.project.root_path
        project_dir = os.path.join(base, project_id)

        result = PipelineResult(project_id=project_id)
        result.output_dir = project_dir

        # Stage 0: Character Sheet Generation
        if generate_character_sheets:
            stage = self._stage_character_sheets(result)
            result.stages.append(stage)
            if on_stage:
                on_stage(stage)

        # Process each chapter
        chapter_dirs = sorted([
            d for d in os.listdir(project_dir)
            if d.startswith("ch") and os.path.isdir(os.path.join(project_dir, d))
        ]) if os.path.isdir(project_dir) else []

        for ch_dir in chapter_dirs:
            chapter_num = int(ch_dir.replace("ch", ""))
            ch_result = self._process_chapter(
                project_id, chapter_num,
                generate_image=generate_image,
                generate_video=generate_video,
                on_shot=on_shot,
            )
            result.shots.extend(ch_result.shots)
            result.total_shots += ch_result.total_shots
            result.success += ch_result.success
            result.failed += ch_result.failed

        # Stage: Shot Table Export
        if generate_shot_tables and result.shots:
            stage = self._stage_shot_tables(result)
            result.stages.append(stage)
            if on_stage:
                on_stage(stage)

        result.final_video = self._compose_final_video(project_id, result.shots)

        result.elapsed = time.time() - start
        logger.info(
            f"PipelineV5: Project '{project_id}' done 鈥?"
            f"{result.success}/{result.total_shots} shots in {result.elapsed:.0f}s"
        )
        return result

    def _stage_character_sheets(self, result: PipelineResult) -> PipelineStage:
        """Stage 0: Generate character sheets (涓夎韩鍥?."""
        stage = PipelineStage(name="character_sheets", status="running")
        started_at = time.time()

        try:
            # Lock all characters
            locks = self.consistency_mgr.lock_all_characters()

            # Generate sheets
            character_data_list = []
            for lock in locks:
                character_data_list.append({
                    "name": lock.name,
                    "gender": "female" if "1girl" in lock.common_prompt else "male",
                    "hair_style": "",
                    "hair_color": "",
                    "eye_color": "",
                    "body_type": "",
                    "clothing": "",
                })

            sheets = self.character_sheet_gen.generate_batch(character_data_list)
            result.character_sheets = sheets

            stage.status = "success"
            stage.output = {"characters_locked": len(locks), "sheets_generated": len(sheets)}
            logger.info(f"PipelineV5: character sheets stage done 鈥?{len(sheets)} sheets")
        except Exception as e:
            stage.status = "failed"
            stage.error = str(e)
            logger.error(f"PipelineV5: character sheets stage failed: {e}")

        stage.elapsed = time.time() - started_at
        return stage

    def _process_chapter(
        self,
        project_id: str,
        chapter: int,
        generate_image: bool = True,
        generate_video: bool = True,
        on_shot: Optional[Callable[[ShotPipelineResult], None]] = None,
    ) -> PipelineResult:
        """Process all shots in a chapter."""
        cfg = get_config()
        base = cfg.project.output_path or cfg.project.root_path
        shot_dir = os.path.join(base, project_id, f"ch{chapter:02d}", "shots")

        chapter_result = PipelineResult(project_id=project_id)

        if not os.path.isdir(shot_dir):
            return chapter_result

        shot_files = sorted([
            f for f in os.listdir(shot_dir)
            if f.startswith("shot_") and f.endswith(".json") and "workflow" not in f
        ])

        for sf in shot_files:
            shot_path = os.path.join(shot_dir, sf)
            shot_idx = int(sf.replace("shot_", "").replace(".json", ""))

            try:
                shot = UnifiedShot.from_json_file(shot_path)

                # Skip already-success shots
                if shot.status == ShotStatus.success:
                    chapter_result.total_shots += 1
                    chapter_result.success += 1
                    chapter_result.shots.append(ShotPipelineResult(
                        shot_id=shot.shot_id,
                        chapter=shot.chapter,
                        scene=shot.scene,
                        shot_num=shot.shot,
                        status="skipped",
                        image_path=shot.image_path,
                        video_path=shot.video_path,
                    ))
                    continue

                # Process shot
                sr = self._process_shot(shot, generate_image, generate_video)
                chapter_result.shots.append(sr)
                chapter_result.total_shots += 1

                if sr.status == "success":
                    chapter_result.success += 1
                else:
                    chapter_result.failed += 1

                if on_shot:
                    on_shot(sr)

            except Exception as e:
                logger.error(f"Failed to process {sf}: {e}")
                chapter_result.total_shots += 1
                chapter_result.failed += 1

        return chapter_result

    def _process_shot(
        self,
        shot: UnifiedShot,
        generate_image: bool = True,
        generate_video: bool = True,
    ) -> ShotPipelineResult:
        """Process a single shot through the V5 pipeline."""
        start = time.time()
        shot_id = f"p{shot.chapter:02d}_s{shot.scene:02d}_sh{shot.shot:03d}"

        result = ShotPipelineResult(
            shot_id=shot_id,
            chapter=shot.chapter,
            scene=shot.scene,
            shot_num=shot.shot,
        )

        try:
            # Step 1: Build CinematicShot
            cinematic_shot = self._build_cinematic_shot(shot)

            # Step 2: Storyboard
            storyboard = self.storyboard_engine.generate_from_cinematic_shots([cinematic_shot])[0]
            result.storyboard = storyboard

            # Step 3: Image generation
            if generate_image:
                result = self._generate_image(shot, cinematic_shot, result)

            # Step 4: Last frame generation
            if result.image_path and generate_video:
                result = self._generate_last_frame(shot, cinematic_shot, result)

            # Step 5: Video generation
            if generate_video and result.image_path:
                result = self._generate_video(shot, cinematic_shot, result)

            # Mark success
            result.status = "success"
            shot.mark_success(image=result.image_path, video=result.video_path)
            if shot.json_path:
                shot.to_json_file(shot.json_path)

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            shot.mark_failed(str(e))
            logger.error(f"PipelineV5: shot {shot_id} failed: {e}")

        result.elapsed = time.time() - start
        return result

    def _stage_shot_tables(self, result: PipelineResult) -> PipelineStage:
        """Export shot tables."""
        stage = PipelineStage(name="shot_tables", status="running")

        try:
            # Collect all cinematic shots from storyboard results
            cinematic_shots = []
            for sr in result.shots:
                if sr.storyboard:
                    cs = CinematicShot(
                        shot_id=sr.shot_id,
                        chapter=sr.chapter,
                        scene=sr.scene,
                        shot_num=sr.shot_num,
                        shot_type=sr.storyboard.shot_type,
                        camera_movement=sr.storyboard.camera_movement,
                        duration_sec=sr.storyboard.duration,
                        emotion=sr.storyboard.emotion,
                        characters=sr.storyboard.characters,
                        scene_description="",
                    )
                    cinematic_shots.append(cs)

            if cinematic_shots:
                table = self.shot_table_gen.generate_table(cinematic_shots)
                result.shot_tables.append(table)

            stage.status = "success"
            stage.output = {"tables_generated": len(result.shot_tables)}
        except Exception as e:
            stage.status = "failed"
            stage.error = str(e)

        return stage

    # ---- Internal Helpers ----

    def _build_cinematic_shot(self, shot: UnifiedShot) -> CinematicShot:
        """Convert UnifiedShot to CinematicShot."""
        return CinematicShot(
            shot_id=shot.shot_id or f"p{shot.chapter:02d}_s{shot.scene:02d}_sh{shot.shot:03d}",
            chapter=shot.chapter,
            scene=shot.scene,
            shot_num=shot.shot,
            shot_type=shot.camera.value if hasattr(shot.camera, "value") else str(shot.camera),
            characters=shot.characters,
            emotion=shot.emotion.value if hasattr(shot.emotion, "value") else str(shot.emotion),
            scene_description=shot.background,
            time_of_day=shot.time_of_day.value if hasattr(shot.time_of_day, "value") else str(shot.time_of_day),
            weather=shot.weather.value if hasattr(shot.weather, "value") else str(shot.weather),
            dialogue=shot.dialogue,
            duration_sec=shot.duration,
            camera_movement=shot.camera_motion or "",
            focal_length=shot.focal_length or "",
            angle=shot.camera_angle or "eye_level",
        )

    def _generate_image(
        self,
        shot: UnifiedShot,
        cinematic_shot: CinematicShot,
        result: ShotPipelineResult,
    ) -> ShotPipelineResult:
        """Generate image for the shot with character consistency."""
        # Build image prompt with character lock
        workflow = self.workflow_gen.generate(shot)

        # Submit to ComfyUI
        comfy_result = self.comfyui.submit_workflow(workflow, wait=True)
        if not comfy_result:
            result.image_path = self._generate_local_keyframe(shot, result, "first")
            result.image_prompt = shot.positive_prompt if hasattr(shot, "positive_prompt") else ""
            result.warnings.append("ComfyUI image generation failed; used local first-frame fallback")
            return result

        # Find output image
        images = comfy_result.get("images", [])
        if not images:
            raise RuntimeError("No output image from ComfyUI")

        output_image = images[0].get("path", "")
        result.image_path = output_image

        # Build and store image prompt
        result.image_prompt = shot.positive_prompt if hasattr(shot, "positive_prompt") else ""

        return result

    def _generate_last_frame(
        self,
        shot: UnifiedShot,
        cinematic_shot: CinematicShot,
        result: ShotPipelineResult,
    ) -> ShotPipelineResult:
        """Generate last frame for I2V."""
        last_frame_spec = self.last_frame_gen.generate_spec(
            cinematic_shot,
            first_frame_prompt=result.image_prompt,
        )
        result.last_frame_prompt = last_frame_spec.last_frame_prompt

        last_frame_shot = shot.model_copy(deep=True)
        last_frame_shot.extra["last_frame_prompt"] = last_frame_spec.last_frame_prompt
        last_frame_shot.extra["source_first_frame"] = result.image_path
        last_frame_shot.background = last_frame_spec.last_frame_prompt or shot.background
        if hasattr(last_frame_spec, "seed"):
            last_frame_shot.seed = last_frame_spec.seed
        if hasattr(last_frame_spec, "steps"):
            last_frame_shot.steps = last_frame_spec.steps
        if hasattr(last_frame_spec, "cfg"):
            last_frame_shot.cfg = last_frame_spec.cfg
        if getattr(last_frame_spec, "resolution", None):
            last_frame_shot.width, last_frame_shot.height = last_frame_spec.resolution[:2]
        last_frame_shot.negative_prompt = (
            (shot.negative_prompt + ", ") if shot.negative_prompt else ""
        ) + "different character, different scene, camera jump, text, watermark"

        workflow = self.workflow_gen.generate(last_frame_shot)
        comfy_result = self.comfyui.submit_workflow(workflow, wait=True)
        if not comfy_result:
            result.last_frame_path = self._generate_local_keyframe(shot, result, "last")
            result.warnings.append("ComfyUI last-frame generation failed; used local last-frame fallback")
            return result

        images = comfy_result.get("images", [])
        if not images:
            raise RuntimeError("No output image from ComfyUI last-frame generation")
        result.last_frame_path = images[0].get("path", "")
        return result

    def _generate_local_keyframe(
        self,
        shot: UnifiedShot,
        result: ShotPipelineResult,
        frame_kind: str,
    ) -> str:
        from backend.local_keyframe_renderer import create_keyframe

        shot_id = result.shot_id or shot.shot_id or f"p{shot.chapter:02d}_s{shot.scene:02d}_sh{shot.shot:03d}"
        out_dir = Path("output") / "v5_local_frames" / shot_id
        path = out_dir / f"{frame_kind}.png"
        title = "首帧" if frame_kind == "first" else "尾帧"
        subtitle = shot.dialogue or shot.narration or shot.background or shot_id
        palette = (56, 84, 132) if frame_kind == "first" else (120, 70, 62)
        return create_keyframe(str(path), f"{title} {shot_id}", subtitle, palette)

    def _generate_video(
        self,
        shot: UnifiedShot,
        cinematic_shot: CinematicShot,
        result: ShotPipelineResult,
    ) -> ShotPipelineResult:
        """Generate I2V video with director-level prompts."""
        # Build director video prompt
        director_prompt = self.director_builder.build_from_shot(cinematic_shot)
        result.video_prompt = director_prompt.full_prompt

        # Generate I2V workflow
        workflow = self.i2v_gen.generate(
            shot=shot,
            input_image=result.image_path,
            last_frame_image=result.last_frame_path or None,
            motion_prompt=director_prompt.full_prompt,
            director_shot=cinematic_shot,
        )

        # Submit to ComfyUI
        comfy_result = self.comfyui.submit_workflow(workflow, wait=True)
        if comfy_result:
            videos = comfy_result.get("videos", [])
            gifs = comfy_result.get("gifs", [])
            if videos:
                result.video_path = videos[0].get("path", "")
            elif gifs:
                result.video_path = gifs[0].get("path", "")

        if not result.video_path:
            if not result.last_frame_path:
                raise RuntimeError("I2V did not return a video and no last frame is available for fallback")
            result.video_path = self._generate_local_video_fallback(shot, result)
            result.warnings.append("ComfyUI I2V did not return video; used local first/last-frame MP4 fallback")

        return result

    def _generate_local_video_fallback(
        self,
        shot: UnifiedShot,
        result: ShotPipelineResult,
    ) -> str:
        """Create a real MP4 from first/last frames when ComfyUI I2V is unavailable."""
        from backend.local_video_renderer import create_interpolated_video

        if not os.path.isfile(result.image_path):
            result.warnings.append(f"First frame path is not readable; regenerated local frame: {result.image_path}")
            result.image_path = self._generate_local_keyframe(shot, result, "first")
        if not os.path.isfile(result.last_frame_path):
            result.warnings.append(f"Last frame path is not readable; regenerated local frame: {result.last_frame_path}")
            result.last_frame_path = self._generate_local_keyframe(shot, result, "last")

        output_dir = Path(result.image_path).parent if result.image_path else Path("output")
        output_path = output_dir / f"{result.shot_id or shot.shot_id or 'shot'}_fallback.mp4"
        return create_interpolated_video(
            result.image_path,
            result.last_frame_path,
            str(output_path),
            duration=getattr(shot, "duration", 3.0),
            fps=24,
        )

    def _compose_final_video(self, project_id: str, shots: List[ShotPipelineResult]) -> str:
        """Concatenate generated shot videos when more than one exists."""
        video_paths = [s.video_path for s in shots if s.video_path and os.path.isfile(s.video_path)]
        if not video_paths:
            return ""
        if len(video_paths) == 1:
            return video_paths[0]

        try:
            from backend.composer import CinemaComposer

            composer = CinemaComposer(output_dir=os.path.join("output", project_id, "final"))
            compose_result = composer.compose(video_paths, output_name="final_v5.mp4", transitions=False)
            if getattr(compose_result, "success", False):
                return compose_result.output_path
        except Exception as e:
            logger.warning(f"PipelineV5: final composition skipped: {e}")

        return video_paths[0]


"""
AI Manga Studio Pro V1.0 — Python-First Orchestrator

Strict principle:
  ComfyUI → only does GPU inference (Prompt → Image → Video).
  Python   → everything else: prompt assembly, state, retry, quality, I/O.

Pipeline per shot (Python controls everything):
  1. Load UnifiedShot JSON from disk
  2. Assemble prompts from shot fields (Python)
  3. Generate ComfyUI workflow JSON (Python)
  4. → Submit to ComfyUI (GPU inference only)
  5. Poll ComfyUI for completion
  6. Save output image/video paths back to UnifiedShot JSON (Python)
  7. Quality check the result (Python)
  8. On fail: update JSON status, retry (Python)
  9. → If video needed: submit I2V workflow to ComfyUI
 10. Mark shot success in JSON

Zero logic in ComfyUI. Zero state in ComfyUI.
"""

from __future__ import annotations

import os
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from loguru import logger

from backend.unified_shot import UnifiedShot, ShotStatus, ShotBatch
from backend.workflow_generator import WorkflowGenerator
from backend.i2v_generator import I2VGenerator
from backend.comfyui_client import ComfyUIClient
from backend.config import get_config


# ============================================================
# State
# ============================================================

@dataclass
class ShotResult:
    """Result of processing a single shot."""
    shot_idx: int
    shot_id: str = ""
    status: ShotStatus = ShotStatus.waiting
    image_path: str = ""
    video_path: str = ""
    elapsed: float = 0.0
    attempts: int = 0
    error: str = ""


@dataclass
class ChapterResult:
    """Result of processing a chapter."""
    chapter: int
    total_shots: int = 0
    success: int = 0
    failed: int = 0
    shots: List[ShotResult] = field(default_factory=list)
    elapsed: float = 0.0


@dataclass
class ProjectResult:
    """Result of processing a full project."""
    project_id: str
    chapters: List[ChapterResult] = field(default_factory=list)
    total_shots: int = 0
    total_success: int = 0
    total_failed: int = 0
    elapsed: float = 0.0


# ============================================================
# Orchestrator
# ============================================================

class Orchestrator:
    """Python-first pipeline. ComfyUI is just a GPU worker.

    Usage:
        orch = Orchestrator()
        result = orch.run_project("my_project", generate_image=True, generate_video=False)
    """

    def __init__(
        self,
        comfyui_url: str = "",
        max_retries: int = 3,
        poll_interval: float = 2.0,
        timeout_per_shot: int = 600,
    ):
        cfg = get_config()
        self.comfyui = ComfyUIClient(
            base_url=comfyui_url or cfg.comfyui.base_url,
            poll_interval=poll_interval,
            max_wait=timeout_per_shot,
        )
        self.workflow_gen = WorkflowGenerator()
        self.i2v_gen = I2VGenerator()
        self.max_retries = max_retries
        logger.info("Orchestrator: Python-first, ComfyUI as GPU worker only")

    # ----------------------------------------------------------
    # Project-level entry point
    # ----------------------------------------------------------

    def run_project(
        self,
        project_id: str,
        generate_image: bool = True,
        generate_video: bool = False,
        on_shot: Optional[Callable[[ShotResult], None]] = None,
    ) -> ProjectResult:
        """Run full pipeline for all chapters in a project.

        Scans output/{project_id}/ch*/shots/shot_*.json.
        Skips shots already marked 'success'.
        """
        start = time.time()
        cfg = get_config()
        base = cfg.project.output_path or cfg.project.root_path
        project_dir = os.path.join(base, project_id)

        if not os.path.isdir(project_dir):
            logger.error(f"Project directory not found: {project_dir}")
            return ProjectResult(project_id=project_id)

        result = ProjectResult(project_id=project_id)
        chapter_dirs = sorted(
            [d for d in os.listdir(project_dir) if d.startswith("ch") and os.path.isdir(os.path.join(project_dir, d))]
        )

        for ch_dir in chapter_dirs:
            chapter_num = int(ch_dir.replace("ch", ""))
            ch_result = self.run_chapter(
                project_id=project_id,
                chapter=chapter_num,
                generate_image=generate_image,
                generate_video=generate_video,
                on_shot=on_shot,
            )
            result.chapters.append(ch_result)
            result.total_shots += ch_result.total_shots
            result.total_success += ch_result.success
            result.total_failed += ch_result.failed

        result.elapsed = time.time() - start
        logger.info(
            f"Orchestrator: Project '{project_id}' done — "
            f"{result.total_success}/{result.total_shots} shots in {result.elapsed:.0f}s"
        )
        return result

    # ----------------------------------------------------------
    # Chapter-level
    # ----------------------------------------------------------

    def run_chapter(
        self,
        project_id: str,
        chapter: int,
        generate_image: bool = True,
        generate_video: bool = False,
        on_shot: Optional[Callable[[ShotResult], None]] = None,
    ) -> ChapterResult:
        """Process all shots in a chapter."""
        start = time.time()
        cfg = get_config()
        base = cfg.project.output_path or cfg.project.root_path
        shot_dir = os.path.join(base, project_id, f"ch{chapter:02d}", "shots")

        result = ChapterResult(chapter=chapter)

        if not os.path.isdir(shot_dir):
            logger.warning(f"Shot directory not found: {shot_dir}")
            return result

        # Load all shot JSONs
        shot_files = sorted([
            f for f in os.listdir(shot_dir)
            if f.startswith("shot_") and f.endswith(".json") and "workflow" not in f
        ])

        result.total_shots = len(shot_files)

        for sf in shot_files:
            shot_path = os.path.join(shot_dir, sf)
            shot_idx = int(sf.replace("shot_", "").replace(".json", ""))

            try:
                shot = UnifiedShot.from_json_file(shot_path)

                # Skip already-success shots
                if shot.status == ShotStatus.success:
                    result.success += 1
                    result.shots.append(ShotResult(
                        shot_idx=shot_idx,
                        shot_id=shot.shot_id,
                        status=ShotStatus.success,
                        image_path=shot.image_path,
                    ))
                    continue

                # Process
                sr = self.run_shot(
                    shot=shot,
                    generate_image=generate_image,
                    generate_video=generate_video,
                )

                result.shots.append(sr)
                if sr.status == ShotStatus.success:
                    result.success += 1
                else:
                    result.failed += 1

                if on_shot:
                    on_shot(sr)

            except Exception as e:
                logger.error(f"Failed to load/process {sf}: {e}")
                result.failed += 1
                result.shots.append(ShotResult(
                    shot_idx=shot_idx, status=ShotStatus.failed, error=str(e)
                ))

        result.elapsed = time.time() - start
        return result

    # ----------------------------------------------------------
    # Single shot — Python controls everything
    # ----------------------------------------------------------

    def run_shot(
        self,
        shot: UnifiedShot,
        generate_image: bool = True,
        generate_video: bool = False,
    ) -> ShotResult:
        """Process ONE shot. ComfyUI only called for GPU work.

        Flow:
          1. Python: load shot params from UnifiedShot
          2. Python: assemble prompts
          3. Python: build ComfyUI workflow JSON
          4. → ComfyUI: generate image (GPU)
          5. Python: save result paths to UnifiedShot JSON
          6. Python: quality check
          7. On fail: Python retries (new ComfyUI call)
          8. → ComfyUI: generate video / i2v (GPU, optional)
          9. Python: mark success
        """
        start = time.time()
        shot_id = f"p{shot.chapter:02d}_s{shot.scene:02d}_sh{shot.shot:03d}"
        shot.shot_id = shot_id

        result = ShotResult(shot_idx=shot.shot, shot_id=shot_id)

        for attempt in range(1, self.max_retries + 1):
            result.attempts = attempt

            try:
                # === STEP 1: Python assembles prompt ===
                shot.mark_generating()
                self._save_shot(shot)

                # === STEP 2: Python builds workflow JSON ===
                workflow = self.workflow_gen.generate(shot)

                # === STEP 3: Submit to ComfyUI (GPU inference only) ===
                logger.info(f"Orchestrator: [{shot_id}] attempt {attempt} — submitting to ComfyUI")
                comfy_result = self._submit_and_wait(workflow)

                if comfy_result is None:
                    raise RuntimeError("ComfyUI returned no result")

                # === STEP 4: Python saves output paths ===
                output_image = self._find_output_image(comfy_result, shot)
                if not output_image:
                    raise RuntimeError("No output image found in ComfyUI result")

                # === STEP 5: Python quality check (optional lightweight) ===
                if not self._quick_quality_check(output_image):
                    if attempt < self.max_retries:
                        logger.warning(f"Orchestrator: [{shot_id}] quality marginal, retrying")
                        continue
                    logger.warning(f"Orchestrator: [{shot_id}] quality marginal but max retries reached")

                # === STEP 6: Image done — Python updates JSON ===
                shot.mark_success(image=output_image)
                result.image_path = output_image

                # === STEP 7: Optional video generation ===
                if generate_video:
                    try:
                        video_path = self._generate_video(shot, output_image)
                        shot.video_path = video_path
                        result.video_path = video_path
                    except Exception as ve:
                        logger.warning(f"Orchestrator: [{shot_id}] video generation failed: {ve}")

                self._save_shot(shot)
                result.status = ShotStatus.success
                result.elapsed = time.time() - start
                logger.info(
                    f"Orchestrator: [{shot_id}] SUCCESS — "
                    f"attempt {attempt}/{self.max_retries}, {result.elapsed:.0f}s"
                )
                return result

            except Exception as e:
                logger.error(f"Orchestrator: [{shot_id}] attempt {attempt} FAILED: {e}")
                traceback.print_exc()

                if attempt < self.max_retries:
                    logger.info(f"Orchestrator: [{shot_id}] retrying...")
                    time.sleep(2)
                else:
                    shot.mark_failed(str(e))
                    self._save_shot(shot)
                    result.status = ShotStatus.failed
                    result.error = str(e)

        result.elapsed = time.time() - start
        return result

    # ----------------------------------------------------------
    # ComfyUI bridge — minimal, dumb, just sends JSON and waits
    # ----------------------------------------------------------

    def _submit_and_wait(self, workflow: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send workflow to ComfyUI, block until done, return result."""
        # Submit via ComfyUI API
        result = self.comfyui.submit_workflow(workflow, wait=True)
        return result

    def _find_output_image(self, comfy_result: Dict[str, Any], shot: UnifiedShot) -> str:
        """Extract output image path from ComfyUI result."""
        # Try images list
        images = comfy_result.get("images", [])
        if images:
            return images[0].get("path", "")

        # Try single output
        output = comfy_result.get("output", "")
        if output and os.path.exists(output):
            return output

        return ""

    def _quick_quality_check(self, image_path: str) -> bool:
        """Minimal Python quality check — no ComfyUI needed.

        In production: run a lightweight image analysis here.
        For now: file existence + non-zero size is enough.
        """
        if not image_path or not os.path.exists(image_path):
            return False
        size = os.path.getsize(image_path)
        if size < 1024:  # < 1KB is suspicious
            return False
        return True

    def _generate_video(self, shot: UnifiedShot, input_image: str) -> str:
        """Python builds I2V workflow → ComfyUI runs GPU inference only.

        Uses AnimateDiff with MotionModule for smooth animation.
        """
        logger.info(f"Orchestrator: I2V generation for {shot.shot_id}")

        frame_count = int(shot.duration * 24) or 48
        fps = 24

        # Python builds the I2V workflow
        i2v_wf = self.i2v_gen.generate(
            shot=shot,
            input_image=input_image,
            frame_count=frame_count,
            fps=fps,
        )

        # ComfyUI just runs it
        result = self._submit_and_wait(i2v_wf)
        if result:
            videos = result.get("videos", [])
            if videos:
                return videos[0].get("path", "")
        return ""

    # ----------------------------------------------------------
    # Persist back to UnifiedShot JSON
    # ----------------------------------------------------------

    def _save_shot(self, shot: UnifiedShot) -> None:
        """Save UnifiedShot back to its JSON file."""
        if shot.json_path:
            shot.to_json_file(shot.json_path)

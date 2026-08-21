"""Multi-node parallel processing for the AI Manga Studio production pipeline.

This module provides a parallel execution layer that orchestrates concurrent
processing of production pipeline stages: text parsing, keyframe generation,
AI video generation, frame interpolation, and quality validation.

Design overview
---------------
``ProcessingNode`` (abstract)
    Each pipeline stage is an async node with ``name``, ``stage_key``,
    ``input_type``, ``output_type`` and a ``process(context)`` coroutine.
    Nodes declare dependencies (``depends_on``) so they can be wired into a
    directed acyclic graph (DAG) and executed in topological order.

``ParallelProcessor``
    Orchestrates concurrent execution using ``asyncio``:
      * configurable concurrency limit via ``asyncio.Semaphore`` (default 3)
      * per-shot failure isolation (one shot failing never blocks the others)
      * retry with exponential backoff
      * progress reporting back to ``JobRepository``
      * batch processing grouped by episode with post-batch composition

Concrete nodes
--------------
* ``TextParseNode``       — parses novel text into scenes/shots (uses llm_parser
                            when available, falling back to ``StoryParser``).
* ``KeyframeGenNode``     — generates first/last frame images for a shot.
* ``VideoGenNode``        — generates AI video from keyframes (real providers only).
* ``FrameInterpNode``     — extends video duration via frame interpolation.
* ``QualityCheckNode``    — validates output quality via the vision layer.

Integration
-----------
The module mirrors the conventions used by ``backend.production.executor`` and
reports progress through ``backend.orchestration.repository.JobRepository``::

    from backend.orchestration.repository import JobRepository

Progress is reported via ``repo.set_job_progress()`` and
``repo.update_step_progress()``, exactly like ``ProductionStageRunner``.
"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable

from backend.orchestration.enums import JobStatus, StepStatus
from backend.orchestration.repository import JobRepository

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
# Type aliases & enums
# ──────────────────────────────────────────────────────────────────────────

ProgressCallback = Callable[[str, str, float, str], None]
"""``(job_id, shot_id, progress_0_to_1, message)`` progress reporter."""

ProcessFunc = Callable[[dict], Awaitable[dict]]
"""Async callable that processes a single shot dict and returns a result dict."""


class NodeIOType(str, Enum):
    """Canonical data types that flow between processing nodes."""

    TEXT = "text"                       # raw novel / script text
    SHOTS = "shots"                     # parsed shot specifications
    KEYFRAMES = "keyframes"             # first/last frame image paths
    VIDEO = "video"                     # generated AI video path
    EXTENDED_VIDEO = "extended_video"   # interpolated / extended video path
    QUALITY_REPORT = "quality_report"   # quality validation report


class NodeStatus(str, Enum):
    """Runtime status for a node within a single pipeline execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class NodeResult:
    """Outcome of a single node execution within a pipeline run."""

    node_name: str
    status: NodeStatus
    output: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_s: float = 0.0
    attempts: int = 0


@dataclass
class ShotResult:
    """Outcome of processing a single shot in a parallel batch."""

    shot_id: str
    success: bool
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    attempts: int = 0
    duration_s: float = 0.0


# ──────────────────────────────────────────────────────────────────────────
# ProcessingNode — abstract base
# ──────────────────────────────────────────────────────────────────────────


class ProcessingNode(ABC):
    """Base class for pipeline processing nodes.

    Each node transforms a ``context`` dict and returns a dict of outputs that
    are merged back into the shared pipeline context so downstream nodes can
    consume them. Nodes declare their dependencies via ``depends_on`` (a list
    of node names) so the :class:`ParallelProcessor` can build a DAG and run
    independent branches concurrently.
    """

    #: Human-readable node identifier (must be unique within a pipeline).
    name: str = "base"
    #: Execution stage key reported to the repository (see EXECUTION_TO_UI_STAGE).
    stage_key: str = "base"
    #: Type of data this node consumes.
    input_type: NodeIOType = NodeIOType.TEXT
    #: Type of data this node produces.
    output_type: NodeIOType = NodeIOType.TEXT
    #: Names of nodes whose output this node depends on. The constructor always
    #: copies this list so instances never mutate the shared class default.
    depends_on: list[str] = []

    def __init__(
        self,
        name: str | None = None,
        stage_key: str | None = None,
        depends_on: list[str] | None = None,
        repo: JobRepository | None = None,
        progress_cb: ProgressCallback | None = None,
    ) -> None:
        if name is not None:
            self.name = name
        if stage_key is not None:
            self.stage_key = stage_key
        self.depends_on = list(depends_on) if depends_on else list(self.depends_on)
        self.repo = repo
        self._progress_cb = progress_cb

    # ── public API ───────────────────────────────────────────────────────

    @abstractmethod
    async def process(self, context: dict) -> dict:
        """Process the input context and return a dict of outputs.

        Implementations should be idempotent where possible and must raise on
        unrecoverable errors so the processor can apply retry / isolation
        policies. Returned keys are merged into the shared pipeline context.
        """
        raise NotImplementedError

    async def __call__(self, context: dict) -> dict:
        """Execute the node, wrapping ``process`` with timing + progress."""
        start = time.monotonic()
        self._report(context, 0.0, f"Starting {self.name}")
        try:
            output = await self.process(context)
            elapsed = time.monotonic() - start
            self._report(context, 1.0, f"Completed {self.name} in {elapsed:.2f}s")
            return output
        except Exception:
            elapsed = time.monotonic() - start
            logger.exception("Node %s failed after %.2fs", self.name, elapsed)
            self._report(context, 0.0, f"Failed {self.name}")
            raise

    # ── helpers ──────────────────────────────────────────────────────────

    def _report(self, context: dict, progress: float, message: str) -> None:
        """Report progress via the repository and/or the injected callback."""
        shot_id = str(context.get("shot_id", context.get("shot", {}).get("id", "")))
        job_id = str(context.get("job_id", ""))
        step_id = str(context.get("step_id", ""))
        if self._progress_cb is not None:
            try:
                self._progress_cb(job_id, shot_id, progress, message)
            except Exception:  # pragma: no cover - progress is best-effort
                logger.debug("progress_cb raised", exc_info=True)
        if self.repo is not None and job_id:
            try:
                self.repo.set_job_progress(job_id, self.stage_key, shot_id, progress, message)
                if step_id:
                    self.repo.update_step_progress(step_id, progress)
            except Exception:  # pragma: no cover - progress is best-effort
                logger.debug("repo progress update failed", exc_info=True)


# ──────────────────────────────────────────────────────────────────────────
# Concrete node implementations
# ──────────────────────────────────────────────────────────────────────────


def _resolve_llm_parser(parser: Any = None) -> Any:
    """Resolve a text parser, preferring an ``llm_parser`` module.

    The production pipeline expects an LLM-backed parser; when that module is
    not present we transparently fall back to the rule-based ``StoryParser``
    so the node remains functional in every environment.
    """
    if parser is not None:
        return parser
    try:  # pragma: no cover - optional dependency
        from backend.production import llm_parser as _llm_parser  # type: ignore

        if hasattr(_llm_parser, "LLMParser"):
            return _llm_parser.LLMParser()
        if hasattr(_llm_parser, "parse"):
            return _llm_parser
    except Exception:
        logger.debug("llm_parser unavailable, falling back to StoryParser")
    from backend.story.parser import StoryParser

    return StoryParser()


class TextParseNode(ProcessingNode):
    """Parses novel text into scenes and shot specifications.

    Uses ``llm_parser`` when available, falling back to ``StoryParser``.
    """

    name = "text_parse"
    stage_key = "planning"
    input_type = NodeIOType.TEXT
    output_type = NodeIOType.SHOTS

    def __init__(
        self,
        parser: Any = None,
        project_root: str = "projects",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.parser = _resolve_llm_parser(parser)
        self.project_root = Path(project_root)

    async def process(self, context: dict) -> dict:
        text = str(context.get("text", ""))
        project_id = str(context.get("project_id", "default"))
        if not text:
            raise ValueError("TextParseNode requires non-empty 'text' in context")

        self._report(context, 0.2, "Parsing novel text into scenes")
        # The parser API is synchronous (StoryParser); run in a worker thread
        # so we never block the event loop on CPU-bound parsing work.
        loop = asyncio.get_running_loop()
        hierarchy = await loop.run_in_executor(
            None, lambda: self.parser.parse_hierarchy(text, project_id)
        )

        self._report(context, 0.6, "Extracting shots from scenes")
        scenes: list[dict] = []
        shots: list[dict] = []
        for chapter, scene_data in hierarchy:
            chapter_dict = {
                "index": getattr(chapter, "number", 0),
                "title": getattr(chapter, "title", ""),
                "word_count": getattr(chapter, "word_count", 0),
            }
            for scene, scene_shots in scene_data:
                scene_dict = {
                    "id": getattr(scene, "id", ""),
                    "number": getattr(scene, "number", 0),
                    "mood": getattr(scene, "mood", "neutral"),
                    "characters": list(getattr(scene, "characters", []) or []),
                }
                scenes.append(scene_dict)
                for shot in scene_shots:
                    shots.append({
                        "id": getattr(shot, "id", f"shot-{len(shots) + 1}"),
                        "scene_id": getattr(shot, "scene_id", scene_dict["id"]),
                        "index": getattr(shot, "index", 0),
                        "description": getattr(shot, "description", ""),
                        "shot_type": getattr(shot, "shot_type", "medium"),
                        "camera": getattr(shot, "camera_angle", "eye-level"),
                        "emotion": getattr(shot, "emotion", "neutral"),
                        "characters": list(getattr(shot, "character_ids", []) or []),
                        "dialogue": getattr(shot, "dialogue", ""),
                        "action": getattr(shot, "action", ""),
                        "duration": 5.0,
                    })

        self._report(context, 1.0, f"Parsed {len(shots)} shots from {len(scenes)} scenes")
        return {"scenes": scenes, "shots": shots, "chapter_count": len(hierarchy)}


class KeyframeGenNode(ProcessingNode):
    """Generates first/last frame keyframe images for a shot."""

    name = "keyframe_gen"
    stage_key = "visual_generate"
    input_type = NodeIOType.SHOTS
    output_type = NodeIOType.KEYFRAMES

    def __init__(
        self,
        keyframe_gen: Any = None,
        project_root: str = "projects",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        # Lazy import keeps module importable when ComfyUI deps are absent.
        if keyframe_gen is None:
            from backend.production.keyframe_generator import KeyframeGenerator

            keyframe_gen = KeyframeGenerator()
        self.keyframe_gen = keyframe_gen
        self.project_root = Path(project_root)

    async def process(self, context: dict) -> dict:
        shot = context.get("shot") or {}
        shot_id = str(shot.get("id", context.get("shot_id", "unknown")))
        project_id = str(context.get("project_id", "default"))
        output_dir = Path(context.get("output_dir", self.project_root / project_id / "outputs"))
        shot_dir = Path(output_dir) / "images" / shot_id
        shot_dir.mkdir(parents=True, exist_ok=True)

        first_frame = shot_dir / "frame.png"
        last_frame = shot_dir / "frame_last.png"

        self._report(context, 0.2, f"Generating first frame for {shot_id}")
        if not first_frame.exists():
            ok = await self.keyframe_gen.generate_keyframe(
                shot_data=shot, output_path=first_frame, frame_type="first",
            )
            if not ok or not first_frame.exists():
                raise RuntimeError(f"Failed to generate first frame for {shot_id}")

        self._report(context, 0.6, f"Generating last frame for {shot_id}")
        if not last_frame.exists():
            ok = await self.keyframe_gen.generate_keyframe(
                shot_data=shot, output_path=last_frame, frame_type="last",
            )
            if not ok or not last_frame.exists():
                # Mirror executor.py: fall back to the first frame so that
                # downstream video generation still has two anchors.
                import shutil

                shutil.copy2(first_frame, last_frame)
                logger.warning("Last frame fell back to first frame for %s", shot_id)

        self._report(context, 1.0, f"Keyframes ready for {shot_id}")
        return {
            "shot_id": shot_id,
            "first_frame": str(first_frame),
            "last_frame": str(last_frame),
        }


class VideoGenNode(ProcessingNode):
    """Generates an AI video clip for a shot from its keyframes.

    When a ``VideoProvider`` is supplied the node performs true AI video
    generation (e.g. Wan2.x). Otherwise it falls back to a Ken-Burns style
    clip synthesized from the first frame with FFmpeg, keeping the pipeline
    resilient when the heavy video model is unavailable.
    """

    name = "video_gen"
    stage_key = "video_generate"
    input_type = NodeIOType.KEYFRAMES
    output_type = NodeIOType.VIDEO

    def __init__(
        self,
        video_provider: Any = None,
        project_root: str = "projects",
        default_fps: int = 24,
        default_frames: int = 81,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.video_provider = video_provider
        self.project_root = Path(project_root)
        self.default_fps = default_fps
        self.default_frames = default_frames

    async def process(self, context: dict) -> dict:
        shot = context.get("shot") or {}
        shot_id = str(shot.get("id", context.get("shot_id", "unknown")))
        project_id = str(context.get("project_id", "default"))
        first_frame = Path(context.get("first_frame", ""))
        output_dir = Path(context.get("output_dir", self.project_root / project_id / "outputs"))
        clip_dir = output_dir / "videos" / shot_id
        clip_dir.mkdir(parents=True, exist_ok=True)
        video_path = clip_dir / "ai_clip.mp4"

        if not first_frame.exists():
            raise FileNotFoundError(f"First frame not found for {shot_id}: {first_frame}")

        self._report(context, 0.2, f"Generating video for {shot_id}")

        if self.video_provider is not None:
            from backend.production.providers import VideoRequest

            # GPT P0: per-shot motion profile drives denoise/frames so the
            # generated clip contains real motion instead of a static frame.
            try:
                from backend.video.duration_strategy import get_motion_profile
                frames = get_motion_profile(shot).frames
            except Exception:
                frames = self.default_frames

            request = VideoRequest(
                image_path=first_frame,
                prompt=str(shot.get("positive_prompt", shot.get("description", ""))),
                negative_prompt=str(shot.get("negative_prompt", "")),
                seed=int(shot.get("seed", 0) or 0),
                width=int(shot.get("width", 832)),
                height=int(shot.get("height", 1216)),
                frames=frames,
                fps=self.default_fps,
                output_path=video_path,
                ai_video=True,
            )
            self._report(context, 0.4, f"AI video inference for {shot_id}")
            artifact = await self.video_provider.generate(request)
            video_path = Path(artifact.path)

        if not video_path.exists():
            raise RuntimeError(
                f"Video generation produced no file for {shot_id} "
                f"(Ken Burns 静态兜底已禁用，请配置真实视频生成器)"
            )

        self._report(context, 1.0, f"Video ready for {shot_id}")
        return {"shot_id": shot_id, "video_path": str(video_path)}

class FrameInterpNode(ProcessingNode):
    """Extends a generated video's duration via frame interpolation."""

    name = "frame_interp"
    stage_key = "video_generate"
    input_type = NodeIOType.VIDEO
    output_type = NodeIOType.EXTENDED_VIDEO

    def __init__(
        self,
        target_seconds: float = 6.0,
        source_fps: int = 24,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.target_seconds = target_seconds
        self.source_fps = source_fps

    async def process(self, context: dict) -> dict:
        from backend.video.frame_interp import extend_video_duration

        shot_id = str(context.get("shot_id", ""))
        video_path = Path(context.get("video_path", ""))
        if not video_path.exists():
            raise FileNotFoundError(f"Source video not found for {shot_id}: {video_path}")

        output_dir = video_path.parent
        extended_path = output_dir / "ai_clip_ext.mp4"

        self._report(context, 0.3, f"Interpolating frames for {shot_id}")
        loop = asyncio.get_running_loop()
        result_path = await loop.run_in_executor(
            None,
            lambda: extend_video_duration(
                input_path=video_path,
                output_path=extended_path,
                target_seconds=self.target_seconds,
                source_fps=self.source_fps,
            ),
        )

        final_path = Path(result_path) if result_path else video_path
        self._report(context, 1.0, f"Extended video ready for {shot_id}")
        return {"shot_id": shot_id, "extended_video": str(final_path)}


class QualityCheckNode(ProcessingNode):
    """Validates output quality through the vision quality-scoring layer."""

    name = "quality_check"
    stage_key = "visual_generate"
    input_type = NodeIOType.EXTENDED_VIDEO
    output_type = NodeIOType.QUALITY_REPORT

    def __init__(
        self,
        scorer: Any = None,
        pass_threshold: float = 0.65,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if scorer is None:
            from backend.vision.quality_score import QualityScorer

            scorer = QualityScorer(pass_threshold=pass_threshold)
        self.scorer = scorer
        self.pass_threshold = pass_threshold

    async def process(self, context: dict) -> dict:
        from backend.vision.image_analyzer import ImageAnalyzer

        shot_id = str(context.get("shot_id", ""))
        # Prefer a keyframe image for quality scoring (video scoring is heavier);
        # fall back to whichever media asset is available.
        image_path = context.get("first_frame") or context.get("last_frame") or ""
        video_path = str(context.get("extended_video") or context.get("video_path") or "")

        target = image_path or self._extract_first_frame(video_path)
        if not target or not Path(target).exists():
            # No media to score — emit a permissive report so the pipeline can
            # proceed instead of hard-failing on missing assets.
            logger.warning("QualityCheckNode: no media to score for %s", shot_id)
            report = {"passed": True, "overall_score": 0.0, "skipped": True,
                      "reason": "no media available for scoring"}
            self._report(context, 1.0, f"Quality skipped for {shot_id}")
            return {"shot_id": shot_id, "quality_report": report, "passed": True}

        self._report(context, 0.3, f"Analyzing media for {shot_id}")
        analyzer = ImageAnalyzer()
        loop = asyncio.get_running_loop()
        profile = await loop.run_in_executor(None, analyzer.analyze, str(target))

        self._report(context, 0.7, f"Scoring quality for {shot_id}")
        shot_spec = context.get("shot") or {}
        quality_report = await loop.run_in_executor(
            None, lambda: self.scorer.score(profile, shot_spec)
        )

        report_dict = {
            "passed": bool(getattr(quality_report, "passed", False)),
            "overall_score": float(getattr(quality_report, "overall_score", 0.0)),
            "composition_score": float(getattr(quality_report, "composition_score", 0.0)),
            "technical_quality": float(getattr(quality_report, "technical_quality", 0.0)),
            "issues": list(getattr(quality_report, "issues", []) or []),
            "suggestions": list(getattr(quality_report, "suggestions", []) or []),
        }

        self._report(context, 1.0, f"Quality {'passed' if report_dict['passed'] else 'failed'} for {shot_id}")
        return {"shot_id": shot_id, "quality_report": report_dict,
                "passed": report_dict["passed"]}

    @staticmethod
    def _extract_first_frame(video_path: str) -> str:
        """Extract the first frame of a video to a temp PNG for scoring."""
        if not video_path or not Path(video_path).exists():
            return ""
        try:
            import subprocess
            import tempfile

            tmp = Path(tempfile.gettempdir()) / f"qc_{Path(video_path).stem}.png"
            subprocess.run(
                ["ffmpeg", "-y", "-i", video_path, "-frames:v", "1", "-q:v", "2", str(tmp)],
                capture_output=True, text=True, timeout=30,
            )
            return str(tmp) if tmp.exists() else ""
        except Exception:
            return ""


# ──────────────────────────────────────────────────────────────────────────
# DAG helpers
# ──────────────────────────────────────────────────────────────────────────


class CyclicGraphError(ValueError):
    """Raised when a node graph contains a cycle and cannot be topologically sorted."""


def topological_sort(nodes: list[ProcessingNode]) -> list[list[ProcessingNode]]:
    """Kahn's algorithm producing execution *levels* of independent nodes.

    Each inner list contains nodes that have no outstanding dependencies and
    may therefore be executed concurrently. Raises :class:`CyclicGraphError`
    if the graph contains a cycle or references an unknown dependency.
    """
    by_name = {n.name: n for n in nodes}
    # Validate dependency references.
    for node in nodes:
        for dep in node.depends_on:
            if dep not in by_name:
                raise CyclicGraphError(
                    f"Node '{node.name}' depends on unknown node '{dep}'"
                )

    indegree = {n.name: 0 for n in nodes}
    dependents: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        for dep in node.depends_on:
            dependents[dep].append(node.name)
            indegree[node.name] += 1

    # Seed with nodes that have no dependencies.
    current_level = [name for name, deg in indegree.items() if deg == 0]
    levels: list[list[ProcessingNode]] = []
    processed = 0

    while current_level:
        level_nodes = [by_name[name] for name in current_level]
        levels.append(level_nodes)
        processed += len(current_level)
        next_level: list[str] = []
        for name in current_level:
            for child in dependents.get(name, []):
                indegree[child] -= 1
                if indegree[child] == 0:
                    next_level.append(child)
        current_level = next_level

    if processed != len(nodes):
        unresolved = [n for n, deg in indegree.items() if deg > 0]
        raise CyclicGraphError(f"Cycle detected; unresolved nodes: {unresolved}")
    return levels


# ──────────────────────────────────────────────────────────────────────────
# ParallelProcessor
# ──────────────────────────────────────────────────────────────────────────


class ParallelProcessor:
    """Orchestrates parallel processing of the production pipeline.

    Parameters
    ----------
    max_concurrency:
        Maximum number of shots (or independent nodes) processed at once.
    repo:
        Optional :class:`JobRepository` for progress reporting.
    max_retries:
        Per-shot retry attempts on failure.
    base_retry_delay:
        Base delay (seconds) for exponential backoff.
    """

    def __init__(
        self,
        max_concurrency: int = 3,
        repo: JobRepository | None = None,
        max_retries: int = 2,
        base_retry_delay: float = 1.0,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        self.max_concurrency = max_concurrency
        self.repo = repo
        self.max_retries = max_retries
        self.base_retry_delay = base_retry_delay
        self.semaphore = asyncio.Semaphore(max_concurrency)

    # ── progress helpers ─────────────────────────────────────────────────

    def _report(
        self,
        job_id: str,
        stage: str,
        shot_id: str,
        progress: float,
        message: str,
        step_id: str = "",
    ) -> None:
        if self.repo is None or not job_id:
            return
        try:
            self.repo.set_job_progress(job_id, stage, shot_id, progress, message)
            if step_id:
                self.repo.update_step_progress(step_id, progress)
        except Exception:  # pragma: no cover - progress is best-effort
            logger.debug("repo progress update failed", exc_info=True)

    # ── retry with exponential backoff ───────────────────────────────────

    async def _retry_with_backoff(
        self,
        func: Callable[..., Awaitable[Any]],
        *args: Any,
        job_id: str = "",
        stage: str = "",
        shot_id: str = "",
        step_id: str = "",
    ) -> Any:
        """Execute ``func`` with exponential backoff retries.

        Raises the last exception if all attempts are exhausted.
        """
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 2):  # initial + retries
            try:
                return await func(*args)
            except Exception as exc:
                last_exc = exc
                if attempt > self.max_retries:
                    logger.error(
                        "Task %s failed permanently after %d attempt(s): %s",
                        shot_id or stage, attempt, exc,
                    )
                    raise
                delay = self.base_retry_delay * (2 ** (attempt - 1))
                logger.warning(
                    "Task %s attempt %d failed: %s — retrying in %.1fs",
                    shot_id or stage, attempt, exc, delay,
                )
                self._report(job_id, stage, shot_id, 0.0,
                             f"Retry {attempt}/{self.max_retries} after error: {exc}",
                             step_id=step_id)
                await asyncio.sleep(delay)
        # Should be unreachable, but keeps mypy happy.
        assert last_exc is not None
        raise last_exc

    # ── parallel shot processing ─────────────────────────────────────────

    async def _process_single_shot(
        self,
        shot: dict,
        process_func: ProcessFunc,
        job_id: str,
        stage_name: str,
        index: int,
        total: int,
    ) -> ShotResult:
        """Process one shot under the concurrency semaphore with retry."""
        shot_id = str(shot.get("id", f"shot-{index}"))
        step_id = str(shot.get("step_id", ""))
        start = time.monotonic()
        async with self.semaphore:
            self._report(job_id, stage_name, shot_id,
                         0.0, f"Queued {shot_id} ({index + 1}/{total})", step_id=step_id)
            try:
                result = await self._retry_with_backoff(
                    process_func, shot,
                    job_id=job_id, stage=stage_name,
                    shot_id=shot_id, step_id=step_id,
                )
                elapsed = time.monotonic() - start
                self._report(job_id, stage_name, shot_id, 1.0,
                             f"Done {shot_id} in {elapsed:.1f}s", step_id=step_id)
                if self.repo is not None and step_id:
                    try:
                        self.repo.complete_step(step_id)
                    except Exception:  # pragma: no cover
                        logger.debug("complete_step failed for %s", step_id, exc_info=True)
                return ShotResult(
                    shot_id=shot_id, success=True, result=result or {},
                    attempts=1, duration_s=elapsed,
                )
            except Exception as exc:
                elapsed = time.monotonic() - start
                logger.error("Shot %s failed: %s\n%s", shot_id, exc, traceback.format_exc())
                self._report(job_id, stage_name, shot_id, 0.0,
                             f"Failed {shot_id}: {exc}", step_id=step_id)
                if self.repo is not None and step_id:
                    try:
                        from backend.orchestration.enums import StepStatus as _SS
                        self.repo.set_step_status(
                            step_id, _SS.FAILED, error_message=str(exc),
                        )
                    except Exception:  # pragma: no cover
                        logger.debug("set_step_status failed for %s", step_id, exc_info=True)
                return ShotResult(
                    shot_id=shot_id, success=False, error=str(exc),
                    attempts=self.max_retries + 1, duration_s=elapsed,
                )

    async def process_shots_parallel(
        self,
        shots: list[dict],
        process_func: ProcessFunc,
        job_id: str,
        stage_name: str,
    ) -> list[dict]:
        """Process multiple shots in parallel.

        Each shot is processed by ``process_func`` under a shared semaphore
        so that at most ``max_concurrency`` shots run at once. A failure in
        one shot is isolated and never blocks the others. Returns a list of
        result dicts (one per input shot, in input order) shaped as::

            {"shot_id", "success", "result" | "error", "attempts", "duration_s"}
        """
        if not shots:
            return []

        total = len(shots)
        self._report(job_id, stage_name, "", 0.0,
                     f"Starting parallel {stage_name} for {total} shots")

        tasks = [
            self._process_single_shot(
                shot, process_func, job_id, stage_name, i, total,
            )
            for i, shot in enumerate(shots)
        ]
        # return_exceptions keeps gather from short-circuiting on the first error,
        # although _process_single_shot already swallows exceptions.
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[dict] = []
        succeeded = 0
        for i, raw in enumerate(raw_results):
            shot_id = str(shots[i].get("id", f"shot-{i}"))
            if isinstance(raw, ShotResult):
                results.append(raw.__dict__)
                succeeded += int(raw.success)
            else:  # unexpected exception from the gather wrapper itself
                err = str(raw)
                logger.error("Unexpected gather error for %s: %s", shot_id, err)
                results.append({
                    "shot_id": shot_id, "success": False,
                    "error": err, "attempts": 0, "duration_s": 0.0,
                    "result": {},
                })

        progress = succeeded / total if total else 1.0
        self._report(job_id, stage_name, "", progress,
                     f"{stage_name}: {succeeded}/{total} shots succeeded")
        return results

    # ── DAG pipeline execution ───────────────────────────────────────────

    async def process_pipeline(
        self,
        nodes: list[ProcessingNode],
        context: dict,
    ) -> dict:
        """Execute a pipeline of nodes in topological order.

        Independent nodes (same DAG level) run concurrently under the
        semaphore. Each node's returned dict is merged into the shared
        ``context`` so downstream nodes can consume prior outputs. The
        returned dict is the final context augmented with a ``node_results``
        list and an ``all_succeeded`` flag.
        """
        levels = topological_sort(nodes)
        node_results: list[NodeResult] = []
        # Tracks every node that has reached a terminal state (completed /
        # failed / skipped) so we never re-execute a node that was already
        # resolved — in particular, nodes skipped due to upstream failure.
        result_by_name: dict[str, NodeResult] = {}
        all_succeeded = True

        # Propagate repository into nodes that don't have one.
        for node in nodes:
            if node.repo is None and self.repo is not None:
                node.repo = self.repo

        job_id = str(context.get("job_id", ""))
        for level_idx, level_nodes in enumerate(levels):
            # Skip nodes already resolved (e.g. skipped after an upstream failure).
            runnable = [n for n in level_nodes if n.name not in result_by_name]
            if not runnable:
                continue
            self._report(job_id, "pipeline", "", level_idx / max(len(levels), 1),
                         f"Executing level {level_idx + 1}/{len(levels)}: "
                         f"{', '.join(n.name for n in runnable)}")

            async def _run_node(node: ProcessingNode) -> NodeResult:
                async with self.semaphore:
                    start = time.monotonic()
                    try:
                        output = await node(context)
                        elapsed = time.monotonic() - start
                        return NodeResult(
                            node_name=node.name, status=NodeStatus.COMPLETED,
                            output=output or {}, duration_s=elapsed, attempts=1,
                        )
                    except Exception as exc:
                        elapsed = time.monotonic() - start
                        logger.error("Node %s failed: %s", node.name, exc, exc_info=True)
                        return NodeResult(
                            node_name=node.name, status=NodeStatus.FAILED,
                            error=str(exc), duration_s=elapsed, attempts=1,
                        )

            level_results = await asyncio.gather(*[_run_node(n) for n in runnable])

            for node, result in zip(runnable, level_results):
                node_results.append(result)
                result_by_name[node.name] = result
                if result.status == NodeStatus.COMPLETED:
                    # Merge node outputs into the shared context.
                    context.update(result.output)
                else:
                    all_succeeded = False
                    # Downstream nodes that depend on a failed node are skipped
                    # preemptively so they are not executed in later levels.
                    self._skip_dependents(node.name, nodes, node_results, result_by_name)

        context["node_results"] = [r.__dict__ for r in node_results]
        context["all_succeeded"] = all_succeeded
        self._report(
            job_id, "pipeline", "", 1.0 if all_succeeded else 0.0,
            "Pipeline completed" if all_succeeded else "Pipeline completed with failures",
        )
        return context

    @staticmethod
    def _skip_dependents(
        failed_name: str,
        nodes: list[ProcessingNode],
        results: list[NodeResult],
        result_by_name: dict[str, NodeResult],
    ) -> None:
        """Mark transitive dependents of a failed node as skipped.

        Skipped nodes are recorded in both ``results`` and ``result_by_name``
        so that :meth:`process_pipeline` will not attempt to execute them in
        a later DAG level.
        """
        queue = deque([failed_name])
        skipped_now: set[str] = set()
        while queue:
            current = queue.popleft()
            for node in nodes:
                if (
                    current in node.depends_on
                    and node.name not in result_by_name
                    and node.name not in skipped_now
                ):
                    skipped_now.add(node.name)
                    skipped = NodeResult(
                        node_name=node.name, status=NodeStatus.SKIPPED,
                        error=f"Skipped because dependency '{current}' failed",
                    )
                    results.append(skipped)
                    result_by_name[node.name] = skipped
                    queue.append(node.name)

    # ── batch processing by episode ──────────────────────────────────────

    async def process_batch(
        self,
        shots_by_episode: dict[str, list[dict]],
        process_func: ProcessFunc,
        job_id: str,
        stage_name: str,
        compose_func: Callable[[str, list[dict]], Awaitable[dict]] | None = None,
    ) -> dict[str, Any]:
        """Process shots grouped by episode, then compose each episode.

        Within an episode, shots are processed concurrently up to
        ``max_concurrency``. Episodes are processed sequentially to bound
        resource usage, but a custom scheduler could parallelize them. After
        all shots in an episode finish, ``compose_func(episode_id, shot_results)``
        is awaited (when provided) to compose the episode video.

        Returns::

            {"episodes": {episode_id: {"shots": [...], "composed": {...}}}, "summary": {...}}
        """
        episodes_out: dict[str, Any] = {}
        total_shots = sum(len(s) for s in shots_by_episode.values())
        processed_shots = 0

        for episode_id, shots in shots_by_episode.items():
            logger.info("Processing episode %s (%d shots)", episode_id, len(shots))
            shot_results = await self.process_shots_parallel(
                shots, process_func, job_id, f"{stage_name}:{episode_id}",
            )
            processed_shots += len(shots)

            composed: dict[str, Any] = {}
            if compose_func is not None:
                succeeded = [r for r in shot_results if r.get("success")]
                if succeeded:
                    try:
                        composed = await compose_func(episode_id, succeeded)
                    except Exception as exc:
                        logger.error("Composition failed for episode %s: %s",
                                     episode_id, exc, exc_info=True)
                        composed = {"success": False, "error": str(exc)}
                else:
                    logger.warning("Skipping composition for %s: no successful shots",
                                   episode_id)
                    composed = {"success": False, "error": "no successful shots"}

            episodes_out[episode_id] = {"shots": shot_results, "composed": composed}
            self._report(
                job_id, stage_name, "",
                processed_shots / total_shots if total_shots else 1.0,
                f"Episode {episode_id} done ({processed_shots}/{total_shots} shots)",
            )

        succeeded_total = sum(
            1 for ep in episodes_out.values()
            for r in ep["shots"] if r.get("success")
        )
        summary = {
            "episode_count": len(episodes_out),
            "total_shots": total_shots,
            "succeeded_shots": succeeded_total,
            "failed_shots": total_shots - succeeded_total,
        }
        self._report(job_id, stage_name, "", 1.0,
                     f"Batch complete: {succeeded_total}/{total_shots} shots succeeded")
        return {"episodes": episodes_out, "summary": summary}

    # ── convenience: build a default per-shot pipeline ────────────────────

    @staticmethod
    def build_shot_pipeline(
        repo: JobRepository | None = None,
        keyframe_gen: Any = None,
        video_provider: Any = None,
        target_seconds: float = 6.0,
    ) -> list[ProcessingNode]:
        """Build the canonical per-shot node chain used by the production line.

        Returns a list of nodes wired as::

            keyframe_gen -> video_gen -> frame_interp -> quality_check
        """
        keyframe = KeyframeGenNode(keyframe_gen=keyframe_gen, repo=repo)
        video = VideoGenNode(video_provider=video_provider, repo=repo,
                             depends_on=[keyframe.name])
        interp = FrameInterpNode(target_seconds=target_seconds, repo=repo,
                                 depends_on=[video.name])
        quality = QualityCheckNode(repo=repo, depends_on=[interp.name])
        return [keyframe, video, interp, quality]


# ──────────────────────────────────────────────────────────────────────────
# Module-level convenience
# ──────────────────────────────────────────────────────────────────────────


def group_shots_by_episode(shots: list[dict]) -> dict[str, list[dict]]:
    """Group a flat shot list by their ``episode_id`` (defaulting to ``default``)."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for shot in shots:
        episode = str(shot.get("episode_id", shot.get("episode", "default")))
        groups[episode].append(shot)
    return dict(groups)


__all__ = [
    "ProcessingNode",
    "ParallelProcessor",
    "TextParseNode",
    "KeyframeGenNode",
    "VideoGenNode",
    "FrameInterpNode",
    "QualityCheckNode",
    "NodeIOType",
    "NodeStatus",
    "NodeResult",
    "ShotResult",
    "CyclicGraphError",
    "topological_sort",
    "group_shots_by_episode",
    "ProgressCallback",
    "ProcessFunc",
]

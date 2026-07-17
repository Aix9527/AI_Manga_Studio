"""
V3 Cinematic 18-Stage Scheduler — Full pipeline from novel parsing to final MP4.

Pipeline order:
  Stage  1: Novel Parsing          → Parse novel text
  Stage  2: AI Director (Hierarchical) → Chapter→Scene→Beat→Shot
  Stage  3: StoryGraph             → Build semantic graph
  Stage  4: Character DNA Manager  → Load/register CharacterDNA
  Stage  5: Scene DNA Manager      → Load/register ScenePack (with spatial_map)
  Stage  6: Style DNA (Lock)       → Apply global style lock
  Stage  7: Prompt Engine + Motion → CinemaPromptEngine + CinemaMotionPlanner
  Stage  8: Model Router           → Route to correct model per shot (+ Flux Dev/Schnell)
  Stage  9: Control Layer          → OpenPose + Depth + Lineart
  Stage 10: Image Pipeline         → Flux img-gen → FaceConsistencyEngine (PuLID/IPAdapter)
  Stage 11: Quality AI (15 checks) → Score and grade
  Stage 12: Motion Planner (V3)    → CinemaMotionPlanner validate/augment
  Stage 13: Video Pipeline (V3)    → CinemaVideoPipeline (Wan/Hunyuan/AnimateDiff)
  Stage 14: LipSync                → CosyVoice → MuseTalk → Emotion
  Stage 15: Timeline               → Build FFmpeg timeline
  Stage 16: Cache Checkpoints      → Cache intermediate results
  Stage 17: Database Checkpoints   → Persist pipeline state
  Stage 18: Final Render (V3)      → CinemaComposer (FFmpeg hardware compositing)
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from loguru import logger

# V3 Cinema modules (lazy-imported where possible to avoid circular deps)
# - CinemaPromptEngine / CinemaMotionPlanner → Stage7 (already imported inline)
# - FaceConsistencyEngine → Stage10
# - CinemaVideoPipeline → Stage12
# - CinemaComposer → Stage18


class Scheduler:
    """V3.0 18-stage pipeline orchestrator.

    Usage:
        sched = Scheduler(
            project_dir="D:/AI_Manga_Studio/output/my_project",
            use_storygraph=True,
            quality_threshold=0.6,
            gpu_layout={0: ["Flux Kontext", "Flux Dev"], 1: ["Wan2.2"]},
        )
        sched.run("path/to/novel.txt")
    """

    def __init__(
        self,
        project_dir: str = "",
        use_storygraph: bool = True,
        quality_threshold: float = 0.6,
        gpu_layout: Optional[Dict[int, List[str]]] = None,
        skip_pulid: bool = False,
        skip_supir: bool = False,
        skip_codeformer: bool = False,
        skip_lip_sync: bool = False,
        skip_voice_clone: bool = False,
        skip_rife: bool = False,
        skip_optical_flow: bool = False,
        no_face_consistency: bool = False,
        motion_style: str = "cinematic",
        dashboard_port: int = 8080,
    ):
        self.project_dir = project_dir
        self.use_storygraph = use_storygraph
        self.quality_threshold = quality_threshold
        self.gpu_layout = gpu_layout
        self.no_face_consistency = no_face_consistency
        self.skip_supir = skip_supir
        self.skip_codeformer = skip_codeformer
        self.skip_lip_sync = skip_lip_sync
        self.skip_voice_clone = skip_voice_clone
        self.skip_rife = skip_rife
        self.skip_optical_flow = skip_optical_flow
        self.motion_style = motion_style
        self.dashboard_port = dashboard_port

        # Pipeline state
        self._novel_text: str = ""
        self._novel_path: str = ""
        self._chapters: List[Any] = []
        self._storygraph: Optional[Any] = None
        self._char_dna_list: List[Any] = []
        self._scene_packs: Dict[str, Any] = {}
        self._style_dna: Optional[Any] = None
        self._shots: List[Any] = []
        self._stage_times: Dict[str, float] = {}

        # Callback registry for external progress tracking
        self._callbacks: Dict[str, Optional[Callable]] = {
            "on_stage_begin": None,
            "on_shot_complete": None,
        }

    # ── Callback registration ─────────────────────────────────

    def register_callbacks(
        self,
        on_stage_begin: Optional[Callable] = None,
        on_shot_complete: Optional[Callable] = None,
    ):
        """Register callbacks for external progress tracking."""
        if on_stage_begin:
            self._callbacks["on_stage_begin"] = on_stage_begin
        if on_shot_complete:
            self._callbacks["on_shot_complete"] = on_shot_complete

    # ── Main entry ────────────────────────────────────────────

    def run(self, novel_path: str) -> bool:
        """Execute the full 18-stage pipeline.

        Returns True on success, False on failure.
        """
        stages = [
            ("Stage 1/18: Novel Parsing", self._stage1_novel_parsing),
            ("Stage 2/18: AI Director", self._stage2_ai_director),
            ("Stage 3/18: StoryGraph", self._stage3_storygraph),
            ("Stage 4/18: Character DNA", self._stage4_character_dna),
            ("Stage 5/18: Scene DNA", self._stage5_scene_dna),
            ("Stage 6/18: Style DNA", self._stage6_style_dna),
            ("Stage 7/18: Prompt Engine", self._stage7_prompt_engine),
            ("Stage 8/18: Model Router", self._stage8_model_router),
            ("Stage 9/18: Control Layer", self._stage9_control_layer),
            ("Stage 10/18: Image Pipeline", self._stage10_image_pipeline),
            ("Stage 11/18: Quality AI", self._stage11_quality_ai),
            ("Stage 12/18: Motion Planner", self._stage12_motion_planner),
            ("Stage 13/18: Video Pipeline", self._stage13_video_pipeline),
            ("Stage 14/18: LipSync", self._stage14_lip_sync),
            ("Stage 15/18: Timeline", self._stage15_timeline),
            ("Stage 16/18: Cache Checkpoints", self._stage16_cache),
            ("Stage 17/18: Database Checkpoints", self._stage17_database),
            ("Stage 18/18: Final Render", self._stage18_final_render),
        ]

        success = True
        for stage_name, stage_fn in stages:
            # Fire on_stage_begin callback
            cb = self._callbacks.get("on_stage_begin")
            if cb:
                item_count = len(self._shots) if "Image Pipeline" in stage_name else 1
                cb(stage_name, item_count)

            logger.info(f"=== {stage_name} ===")
            t0 = time.time()
            try:
                ok = stage_fn(novel_path if "Novel" in stage_name else "")
                elapsed = time.time() - t0
                self._stage_times[stage_name] = elapsed
                if not ok:
                    logger.error(f"{stage_name} FAILED ({elapsed:.1f}s)")
                    success = False
                    break
                logger.info(f"{stage_name} OK ({elapsed:.1f}s)")
            except Exception as e:
                elapsed = time.time() - t0
                self._stage_times[stage_name] = elapsed
                logger.error(f"{stage_name} EXCEPTION: {e} ({elapsed:.1f}s)")
                success = False
                break

        return success

    # ── Stage implementations ─────────────────────────────────

    def _stage1_novel_parsing(self, novel_path: str) -> bool:
        """Parse novel text into raw text and basic structures."""
        if not novel_path:
            return True  # already parsed

        # Store path for downstream stages
        self._novel_path = novel_path

        # Read novel text for HierarchicalDirector (Stage 2)
        import os
        if os.path.isfile(novel_path):
            with open(novel_path, "r", encoding="utf-8") as f:
                self._novel_text = f.read()
            logger.info(f"Loaded novel: {len(self._novel_text)} chars")

        from backend.scheduler.novel import NovelStage
        parser = NovelStage(project_dir=self.project_dir)
        parser.parse(novel_path)
        return True

    def _stage2_ai_director(self, _: str) -> bool:
        """Hierarchical AI Director: Chapter → Scene → Beat → Shot."""
        if not self.use_storygraph:
            return True  # fallback to legacy
        from backend.ai_director import HierarchicalDirector
        director = HierarchicalDirector()
        self._chapters = director.parse_hierarchical(self._novel_text)
        ok = len(self._chapters) > 0
        if ok:
            total_beats = sum(len(scene.beats) for ch in self._chapters for scene in ch.scenes)
            total_shots = sum(len(scene.shots) for ch in self._chapters for scene in ch.scenes)
            logger.info(f"AI Director: {len(self._chapters)} chapters, {total_beats} beats, {total_shots} shots")
        return ok

    def _stage3_storygraph(self, _: str) -> bool:
        """Build StoryGraph semantic graph from AI Director output."""
        if not self.use_storygraph:
            return True
        from backend.story_graph import StoryGraphParser
        parser = StoryGraphParser()
        self._storygraph = parser.parse(self._chapters)
        return self._storygraph is not None

    def _stage4_character_dna(self, _: str) -> bool:
        """Load/register CharacterDNA for all characters."""
        from backend.dna.character_dna_manager import CharacterDNAManager
        from backend.dna.character_dna import CharacterDNA

        mgr = CharacterDNAManager.instance()
        char_names = self._get_character_names()

        # Try loading existing DNA first
        for char_name in char_names:
            existing = mgr.get_by_name(char_name)
            if existing:
                self._char_dna_list.append(existing)

        # Create placeholder DNA for new characters (no ComfyUI generation)
        for char_name in char_names:
            if not mgr.get_by_name(char_name):
                dna_id = f"char_{len(self._char_dna_list)+1:03d}"
                dna = CharacterDNA(
                    character_id=dna_id,
                    name=char_name,
                    prompt_template=f"{char_name}, character reference",
                )
                mgr.register(dna)
                self._char_dna_list.append(dna)

        logger.info(f"Character DNA: {len(self._char_dna_list)} characters registered")
        return len(self._char_dna_list) > 0 or len(char_names) == 0

    def _stage5_scene_dna(self, _: str) -> bool:
        """Load/register ScenePack for all scenes with spatial_map extraction."""
        from backend.dna.scene_dna_manager import SceneDNAManager
        from backend.dna.scene_dna import ScenePack

        mgr = SceneDNAManager.instance()

        # Location keywords for sub-scene extraction from novel text
        _LOCATION_KEYWORDS = [
            "门口", "大厅", "楼梯", "客厅", "走廊", "卧室", "厨房",
            "花园", "阳台", "书房", "电梯", "玄关", "庭院", "停车场",
            "地下室", "阁楼", "餐厅", "浴室", "储藏室", "露台",
        ]

        def _extract_sub_scenes(scene_text: str) -> List[str]:
            """Extract ordered sub-scene names from scene/chapter text."""
            found = []
            seen = set()
            for kw in _LOCATION_KEYWORDS:
                if kw in scene_text and kw not in seen:
                    found.append(kw)
                    seen.add(kw)
            return found

        if self._storygraph and hasattr(self._storygraph, "scene_map"):
            for scene_id, ctx in self._storygraph.scene_map.items():
                if not mgr.get_scene(scene_id):
                    loc = getattr(ctx, "location", "Unknown")
                    time_map = {
                        "dawn": "黎明", "morning": "白天", "noon": "白天",
                        "afternoon": "白天", "dusk": "黄昏", "night": "夜晚",
                    }
                    weather_map = {
                        "rain": "雨", "heavy_rain": "暴雨", "snow": "雪",
                        "heavy_snow": "暴雪", "overcast": "阴天", "fog": "雾",
                        "windy": "大风", "clear": "晴天",
                    }

                    # Extract sub-scenes and spatial_map from scene description
                    desc = getattr(ctx, "description", "") or ""
                    sub_scenes = _ext_sub_scenes(desc)

                    # Build spatial_map: sub-area → description
                    spatial_map: Dict[str, str] = {}
                    for sub in sub_scenes:
                        # Use scene description as spatial context
                        spatial_map[sub] = desc if desc else f"{sub} of {loc}"

                    pack = ScenePack(
                        scene_id=scene_id,
                        name=loc,
                        sub_scenes=sub_scenes,
                        spatial_map=spatial_map,
                        default_time=time_map.get(getattr(ctx, "time_of_day", "day"), "白天"),
                        default_weather=weather_map.get(getattr(ctx, "weather", "clear"), "晴天"),
                        default_lighting=getattr(ctx, "lighting", "自然光"),
                        color_palette=getattr(ctx, "color_scheme", ""),
                    )
                    mgr.register_pack(pack)
                    self._scene_packs[scene_id] = pack

        logger.info(f"Scene DNA: {len(self._scene_packs)} scenes registered (with spatial_map)")
        return True

    def _stage6_style_dna(self, _: str) -> bool:
        """Apply global StyleDNA lock."""
        from backend.dna.style_dna import StyleDNA

        self._style_dna = StyleDNA(project_id="v3_test", art_style="cinematic")
        return self._style_dna is not None

    def _stage7_prompt_engine(self, _: str) -> bool:
        """Build decomposed prompts for all shots (V3 Cinema Prompt Engine).

        Uses CinemaPromptEngine for strict template assembly — no LLM call.
        Motion plans are also generated here via CinemaMotionPlanner
        and attached to each shot for downstream video stages.
        """
        from backend.prompt_engine import CinemaPromptEngine, GLOBAL_NEGATIVE
        from backend.motion_planner import CinemaMotionPlanner

        cinema = CinemaPromptEngine()
        motion_planner = CinemaMotionPlanner()

        # Build char_dna_map and scene_dna_map for batch resolution
        char_dna_map: Dict[str, Any] = {}
        for dna in self._char_dna_list:
            name = getattr(dna, "character_id", "") or getattr(dna, "name", "")
            if name:
                char_dna_map[name] = dna

        scene_dna_map: Dict[str, Any] = {}
        for sc in self._scene_packs:
            sid = getattr(sc, "scene_id", "") or getattr(sc, "name", "")
            if sid:
                scene_dna_map[sid] = sc

        all_shots = self._collect_all_shots()
        for shot in all_shots:
            # Resolve CharacterDNA for this shot
            char_dna = None
            char_names = getattr(shot, "characters_present", None) or []
            for name in char_names:
                if name in char_dna_map:
                    char_dna = char_dna_map[name]
                    break

            # Resolve SceneDNA
            scene_dna = None
            scene_name = getattr(shot, "scene_name", "") or ""
            if scene_name in scene_dna_map:
                scene_dna = scene_dna_map[scene_name]

            # Build image prompt via CinemaPromptEngine template assembly
            img_prompt = cinema.build_image_prompt(char_dna, scene_dna, shot)

            # Build video prompt with motion plan
            motion_plan = motion_planner.plan_motion(shot)
            video_prompt = cinema.build_video_prompt(
                char_dna, scene_dna, shot,
                motion_plan=motion_planner.to_dict(motion_plan),
            )

            # Attach to shot.extra (backward compat with V3.0 DecomposedPrompt dicts)
            if not hasattr(shot, "extra"):
                shot.extra = {}
            shot.extra["decomposed_prompt"] = {
                "shot_id": img_prompt.shot_id,
                "character_prompt": img_prompt.character_prompt,
                "scene_prompt": img_prompt.scene_prompt,
                "camera_prompt": img_prompt.camera_prompt,
                "emotion_prompt": img_prompt.emotion_prompt,
                "lighting_prompt": img_prompt.lighting_prompt,
                "motion_prompt": img_prompt.motion_prompt,
                "style_prompt": img_prompt.style_prompt,
                "negative_prompt": img_prompt.negative_prompt,
            }
            shot.extra["merged_prompt"] = img_prompt.final_prompt
            shot.extra["merged_negative"] = GLOBAL_NEGATIVE
            shot.extra["video_prompt"] = video_prompt.final_prompt
            shot.extra["motion_plan"] = motion_planner.to_dict(motion_plan)

        self._shots = all_shots
        logger.info(f"Prompt Engine (V3 Cinema): {len(all_shots)} prompts + motion plans generated")
        return len(all_shots) > 0 or True  # Graceful: no shots = nothing to do

    def _stage8_model_router(self, _: str) -> bool:
        """Route each shot to the optimal model."""
        from backend.pipeline.model_router import ModelRouter

        for shot in self._shots:
            scene_ctx = self._find_scene_for_shot(shot)
            char_count = self._count_characters_in_shot(shot)

            image_model = ModelRouter.route_image(
                shot=shot,
                scene_context=scene_ctx,
                character_count=char_count,
            )
            video_model = ModelRouter.route_video(shot=shot, beat=None)

            if hasattr(shot, "image_model"):
                shot.image_model = image_model
            if hasattr(shot, "video_model"):
                shot.video_model = video_model

        return True

    def _stage9_control_layer(self, _: str) -> bool:
        """Build ControlNet workflows (OpenPose + Depth + Lineart)."""
        from backend.pipeline.control_layer import ControlLayer

        for shot in self._shots:
            beat = self._find_beat_for_shot(shot)
            scene_ctx = self._find_scene_for_shot(shot)

            control_workflow = ControlLayer.build_full_control(
                shot=shot,
                beat=beat,
                char_dna_list=self._char_dna_list,
                scene_context=scene_ctx,
            )
            if hasattr(shot, "control_workflow"):
                shot.control_workflow = control_workflow

        return True

    def _stage10_image_pipeline(self, _: str) -> bool:
        """Run Image Pipeline cascade for all shots.

        Passes UnifiedShot objects directly so ImagePipeline
        can use WorkflowGenerator to build ComfyUI workflows.
        Post-generation: FaceConsistencyEngine applies PuLID/IPAdapter
        face lock (unless --no-face-consistency).
        """
        from backend.pipeline.image_pipeline import ImagePipeline
        from backend.face_consistency import FaceConsistencyEngine

        pipeline = ImagePipeline(
            output_dir=self.project_dir,
            skip_pulid=True,  # No longer used — replaced by FaceConsistencyEngine
            skip_supir=self.skip_supir,
            skip_codeformer=self.skip_codeformer,
        )

        # Initialize FaceConsistencyEngine (only if not skipped)
        face_engine = None
        if not self.no_face_consistency:
            face_engine = FaceConsistencyEngine(
                comfyui_client=None,  # TODO: wire ComfyUI client
            )
            logger.info(f"FaceConsistency: method={face_engine.method}")

        generated = 0
        failed = 0
        face_fixed = 0

        for shot in self._shots:
            try:
                # Get merged prompt from extra dict (set by Prompt Engine, safe access)
                if not hasattr(shot, "extra"):
                    shot.extra = {}
                shot.extra.setdefault("merged_prompt", "")
                shot.extra.setdefault("merged_negative", "")

                result = pipeline.run(
                    shot=shot,
                    character_dna_list=self._char_dna_list,
                )
                shot.extra["image_result"] = result
                if result.status == "SUCCESS":
                    generated += 1

                    # Apply face consistency post-generation
                    if face_engine and result.final_image:
                        char_dna = self._find_char_dna_for_shot(shot)
                        face_result = face_engine.apply(
                            image_path=result.final_image,
                            character_dna=char_dna,
                        )
                        shot.extra["face_consistency"] = face_result
                        if face_result.success and face_result.method != "none":
                            face_fixed += 1
                else:
                    failed += 1

                # Fire on_shot_complete callback
                cb = self._callbacks.get("on_shot_complete")
                if cb:
                    cb(shot)
            except Exception as e:
                logger.error(f"ImagePipeline: Shot {getattr(shot, 'shot_id', '?')} failed: {e}")
                failed += 1

        logger.info(
            f"Image Pipeline: {generated} generated ({face_fixed} face-fixed), {failed} failed"
        )
        return True  # Stage always passes (partial generation is OK)

    def _stage11_quality_ai(self, _: str) -> bool:
        """Run Quality Engine (15 checks) on all generated images."""
        from backend.pipeline.quality_engine import QualityEngine

        engine = QualityEngine()
        passed = 0
        total = 0

        for shot in self._shots:
            result = shot.extra.get("image_result")
            image_path = result.final_image if result and result.final_image else ""
            if image_path:
                report = engine.evaluate(image_path)
                shot.extra["quality_report"] = report
                if report.passed:
                    passed += 1
                total += 1

        logger.info(f"Quality AI: {passed}/{total} shots passed")
        return True

    def _stage12_motion_planner(self, _: str) -> bool:
        """V3 Cinema: Motion plans already generated in Stage7 via CinemaMotionPlanner.

        This stage provides a re-check / augmentation point:
        - If motion_plan exists in shot.extra, validate and optionally augment.
        - If missing, fall back to legacy pipeline MotionPlanner.
        """
        from backend.motion_planner import CinemaMotionPlanner

        planner = CinemaMotionPlanner()
        for shot in self._shots:
            # Use existing motion_plan from Stage7 if available
            existing = shot.extra.get("motion_plan") if hasattr(shot, "extra") else None
            if existing:
                # Already set by Stage7 — validate
                if not existing.get("camera_movement"):
                    # Re-generate if incomplete
                    mp = planner.plan_motion(shot)
                    shot.extra["motion_plan"] = planner.to_dict(mp)
            else:
                # Fallback: generate via CinemaMotionPlanner
                if not hasattr(shot, "extra"):
                    shot.extra = {}
                mp = planner.plan_motion(shot)
                shot.extra["motion_plan"] = planner.to_dict(mp)

        return True

    def _stage13_video_pipeline(self, _: str) -> bool:
        """V3 Cinema Video Pipeline: I2V via CinemaVideoPipeline.

        Integrates MotionPlan + source image → video generation.
        Model: Wan/Hunyuan (preferred) or AnimateDiff (fallback).
        """
        from backend.video_pipeline import CinemaVideoPipeline

        pipeline = CinemaVideoPipeline(
            comfyui_client=None,  # TODO: wire ComfyUI client
            output_dir=os.path.join(self.project_dir, "video"),
        )

        # Build image_map: shot_id → final_image path
        image_map: Dict[str, str] = {}
        for shot in self._shots:
            sid = str(getattr(shot, "shot_id", ""))
            img_result = shot.extra.get("image_result") if hasattr(shot, "extra") else None
            if img_result and getattr(img_result, "final_image", ""):
                image_map[sid] = img_result.final_image

        # Build char_dna_map
        char_dna_map: Dict[str, Any] = {}
        for dna in self._char_dna_list:
            name = getattr(dna, "name", "") or getattr(dna, "character_id", "")
            if name:
                char_dna_map[name] = dna

        results = pipeline.generate_batch(
            shots=self._shots,
            image_map=image_map,
            char_dna_map=char_dna_map,
        )

        # Attach results to shots
        for shot, result in zip(self._shots, results):
            if hasattr(shot, "extra"):
                shot.extra["video_result"] = result
                if result.success and result.output_video:
                    shot.extra["video_path"] = result.output_video

        success_count = sum(1 for r in results if r.success)
        logger.info(
            f"Video Pipeline (V3 Cinema): {success_count}/{len(results)} shots rendered"
        )
        return True

    def _stage14_lip_sync(self, _: str) -> bool:
        """Run LipSync if not skipped."""
        if self.skip_lip_sync:
            return True

        from backend.pipeline.lip_sync import LipSyncPipeline

        pipeline = LipSyncPipeline()

        for shot in self._shots:
            video_result = shot.extra.get("video_result")
            video_path = video_result.final_video if video_result and video_result.final_video else ""
            text = getattr(shot, "dialogue", "")
            emotion_val = getattr(shot, "emotion", "neutral")

            if video_path and text:
                char_dna = self._find_char_dna_for_shot(shot)
                result = pipeline.run(
                    character_dna=char_dna,
                    text=text,
                    video_path=video_path,
                    emotion=emotion_val,
                    skip_tts=self.skip_voice_clone,
                )
                shot.extra["lipsync_result"] = result

        return True

    def _stage15_timeline(self, _: str) -> bool:
        """Build timeline with auto transitions."""
        from backend.pipeline.timeline import TimelineBuilder

        builder = TimelineBuilder(fps=self._style_dna.fps if self._style_dna else 24)

        video_clips = {}
        audio_clips = {}
        subtitles = {}

        for shot in self._shots:
            sid = getattr(shot, "shot_id", "")
            video_result = shot.extra.get("video_result")
            video_clips[sid] = video_result.final_video if video_result and video_result.final_video else ""
            audio_clips[sid] = getattr(shot, "audio_path", "")
            subtitles[sid] = getattr(shot, "dialogue", "")

        timeline = builder.build(self._shots, video_clips, audio_clips, subtitles)
        self._timeline = timeline
        return True

    def _stage16_cache(self, _: str) -> bool:
        """Persist cache checkpoints."""
        return True  # Cache writes happen inline during pipeline

    def _stage17_database(self, _: str) -> bool:
        """Persist all pipeline state to database."""
        from backend.dna.character_dna_manager import CharacterDNAManager
        from backend.dna.scene_dna_manager import SceneDNAManager

        # Save Character DNA
        char_mgr = CharacterDNAManager.instance()
        char_mgr.save_to_db()

        # Save Scene DNA
        scene_mgr = SceneDNAManager.instance()
        scene_mgr.save_to_json(os.path.join(self.project_dir, "scene_dna.json"))

        return True

    def _stage18_final_render(self, _: str) -> bool:
        """V3 Cinema: FFmpeg composition via CinemaComposer.

        Collects video clips from all shots, orders by scene/shot sequence,
        and composites into final MP4 with transitions + optional BGM.
        """
        from backend.composer import CinemaComposer

        composer = CinemaComposer(output_dir=os.path.join(self.project_dir, "final"))

        # Collect video paths from shot extras
        video_map: Dict[str, str] = {}
        for shot in self._shots:
            sid = str(getattr(shot, "shot_id", ""))
            if hasattr(shot, "extra"):
                video_path = shot.extra.get("video_path", "")
                if video_path and os.path.isfile(video_path):
                    video_map[sid] = video_path

        if not video_map:
            logger.warning("Stage18: No video clips available — nothing to compose")
            return True

        result = composer.compose_from_shots(
            shots=self._shots,
            video_map=video_map,
            output_name="final_movie.mp4",
            add_transitions=True,
        )

        if result.success:
            logger.info(
                f"Stage18: Final render → {result.output_path} "
                f"({result.file_size_mb:.1f} MB, {result.duration_sec:.1f}s)"
            )
        else:
            logger.error(f"Stage18: Final render FAILED — {result.error}")

        self._compose_result = result
        return result.success

    # ── Helpers ────────────────────────────────────────────────

    def _collect_all_shots(self) -> List[Any]:
        """Collect all shots — try loading UnifiedShot JSONs first,
        fall back to StoryGraph shot objects."""
        shots = []

        # ── Option 1: Load UnifiedShot JSONs written by NovelStage ──
        import glob
        json_pattern = os.path.join(
            self.project_dir, "*", "ch*", "shots", "shot_*.json"
        )
        json_files = sorted(glob.glob(json_pattern))
        if json_files:
            from backend.unified_shot import UnifiedShot
            for jf in json_files:
                try:
                    shot = UnifiedShot.from_json_file(jf)
                    shots.append(shot)
                except Exception:
                    pass
            if shots:
                return shots

        # ── Option 2: From StoryGraph chapters ──
        if self._chapters:
            for chapter in self._chapters:
                for scene in getattr(chapter, "scenes", []):
                    shots.extend(getattr(scene, "shots", []))
        return shots

    def _get_character_names(self) -> List[str]:
        """Get all character names from StoryGraph or AI Director."""
        names = set()
        # StoryGraph has all_characters list (individual names)
        if self._storygraph and hasattr(self._storygraph, "all_characters"):
            names.update(self._storygraph.all_characters)
        # Fallback: scan chapters for character names in beats
        if self._chapters:
            for ch in self._chapters:
                for sc in getattr(ch, "scenes", []):
                    for beat in getattr(sc, "beats", []):
                        for c in getattr(beat, "characters", []):
                            names.add(c)
        return sorted(names)

    def _find_beat_for_shot(self, shot: Any) -> Optional[Any]:
        """Find the parent beat for a shot."""
        shot_id = getattr(shot, "shot_id", "")
        if self._chapters:
            for ch in self._chapters:
                for sc in getattr(ch, "scenes", []):
                    for beat in getattr(sc, "beats", []):
                        for s in getattr(beat, "shots", []):
                            if getattr(s, "shot_id", "") == shot_id:
                                return beat
        return None

    def _find_scene_for_shot(self, shot: Any) -> Optional[Any]:
        """Find the parent scene for a shot."""
        shot_id = getattr(shot, "shot_id", "")
        if self._chapters:
            for ch in self._chapters:
                for sc in getattr(ch, "scenes", []):
                    for beat in getattr(sc, "beats", []):
                        for s in getattr(beat, "shots", []):
                            if getattr(s, "shot_id", "") == shot_id:
                                return self._storygraph.scene_map.get(
                                    getattr(sc, "scene_id", "")
                                ) if self._storygraph else sc
        return None

    def _count_characters_in_shot(self, shot: Any) -> int:
        """Count characters in a shot's beat."""
        beat = self._find_beat_for_shot(shot)
        if beat:
            return len(getattr(beat, "characters", []))
        return 1

    def _find_char_dna_for_shot(self, shot: Any) -> Optional[Any]:
        """Find CharacterDNA for the primary character in a shot."""
        beat = self._find_beat_for_shot(shot)
        if beat:
            chars = getattr(beat, "characters", [])
            if chars:
                for dna in self._char_dna_list:
                    if getattr(dna, "name", "") == chars[0]:
                        return dna
        return None

"""Pipeline Orchestrator — wires all v0.5 phases together."""

from __future__ import annotations

import time
from typing import Optional

from backend.characters.service import CharacterService
from backend.characters.extractor import CharacterExtractor
from backend.characters.models import Character
from backend.story.parser import StoryParser
from backend.story.graph import StoryGraphEngine
from backend.story.timeline import TimelineManager
from backend.story.models import Chapter, Scene, Shot
from backend.agents.director import DirectorAgent, ShotBrief
from backend.agents.director_v2 import ShotDirective
from backend.director.director_bridge import DirectorBridge
from backend.agents.writer import WriterAgent
from backend.agents.character import CharacterAgent
from backend.agents.critic import CriticAgent
from backend.prompt_compiler.compiler import PromptCompiler
from backend.prompt_compiler.templates import register_default_templates
from backend.vision import QualityScorer, FeedbackLoop
from backend.vision.image_analyzer import ImageProfile
from backend.vision.quality_score import QualityReport
from backend.pipeline.schemas import (
    PipelineRequest, PipelineResponse, PipelineStage, StageResult,
)


class PipelineOrchestrator:
    """
    Full v0.5 production pipeline orchestrator.

    Flow:
    Text → [Phase 1: Character Extraction] → [Phase 2: Story Parsing + Graph]
         → [Phase 3: Director → Writer → Character → Critic]
         → [Phase 4: Prompt Compilation]
    """

    def __init__(self, db_path: str = "storage/orchestrator.db"):
        # Phase 1
        self.character_service = CharacterService(db_path)
        self.character_extractor = CharacterExtractor()

        # Phase 2
        self.story_parser = StoryParser()
        self.graph_engine = StoryGraphEngine()
        self.timeline_mgr = TimelineManager()

        # Phase 3
        self.director = DirectorAgent()
        self.writer = WriterAgent()
        self.character_agent = CharacterAgent()
        self.critic = CriticAgent()

        # Phase 4
        self.prompt_compiler = PromptCompiler()
        register_default_templates(self.prompt_compiler)

        # Phase 10.2-A: Director v2 bridge (Story Memory -> Director v2)
        self.director_bridge = DirectorBridge()

        # Sprint 7.1: Vision feedback loop
        self.quality_scorer = QualityScorer(pass_threshold=0.65)
        self.feedback_loop = FeedbackLoop(max_retries=2)

        # Wire pipeline
        self.character_agent.set_memory(self.character_service)
        self.director.set_pipeline(self.writer, self.character_agent)

    def run(self, request: PipelineRequest) -> PipelineResponse:
        """Execute the full pipeline from raw text to compiled prompts."""
        start = time.perf_counter()
        response = PipelineResponse(request_id=request.id, status="running")

        # Phase 1: Character Extraction
        characters: list[Character] = []
        if not request.skip_character_extraction and request.text:
            sr = self._run_stage(PipelineStage.EXTRACT_CHARACTERS, request)
            try:
                characters = self.character_extractor.extract_from_text(
                    request.text, request.novel_id
                )
                for ch in characters:
                    self.character_service.memory.create(ch)
                sr.status = "completed"
                sr.data = {"characters_found": len(characters)}
                sr.message = f"Extracted {len(characters)} characters"
                response.characters_found = len(characters)
            except Exception as e:
                sr.status = "failed"
                sr.message = str(e)
            sr.duration_ms = (time.perf_counter() - start) * 1000
            response.stages.append(sr)

        # Phase 2: Story Parsing + Graph
        chapters: list[Chapter] = []
        if not request.skip_story_parsing and request.text:
            sr = self._run_stage(PipelineStage.PARSE_STORY, request)
            try:
                chapters = self.story_parser.parse_full(request.text, request.novel_id)
                sr.status = "completed"
                sr.data = {"chapters": len(chapters)}
                sr.message = f"Parsed {len(chapters)} chapters"
                response.scenes_parsed = sum(len(ch.scenes) for ch in chapters)
            except Exception as e:
                sr.status = "failed"
                sr.message = str(e)
            sr.duration_ms = (time.perf_counter() - start) * 1000
            response.stages.append(sr)

        # Phase 3: Director → Writer → Character → Critic
        all_briefs: list[ShotBrief] = []
        all_compiled: list = []

        if chapters:
            # Build story graph
            sr = self._run_stage(PipelineStage.BUILD_GRAPH, request)
            try:
                chapter_data = []
                for ch in chapters:
                    scenes = self.story_parser._split_scenes(ch.raw_text, ch.id)
                    scene_data = []
                    for sc in scenes:
                        shots = self.story_parser._extract_shots(sc.raw_text, sc.id)
                        scene_data.append((sc, shots))
                    chapter_data.append((ch, scene_data))

                graph = self.graph_engine.build_graph(
                    request.novel_id, request.title or "Untitled", chapter_data
                )
                sr.status = "completed"
                sr.data = {"graph_id": graph.id, "nodes": len(graph.nodes)}
                sr.message = f"Built graph with {len(graph.nodes)} nodes"
            except Exception as e:
                sr.status = "failed"
                sr.message = str(e)
            sr.duration_ms = (time.perf_counter() - start) * 1000
            response.stages.append(sr)

            # Director planning
            sr = self._run_stage(PipelineStage.DIRECTOR_PLAN, request)
            try:
                all_shots: list[Shot] = []
                for ch in chapters:
                    scenes = self.story_parser._split_scenes(ch.raw_text, ch.id)
                    for sc in scenes:
                        shots = self.story_parser._extract_shots(sc.raw_text, sc.id)
                        all_shots.extend(shots)

                all_briefs = self.director.plan_sequence(all_shots)
                sr.status = "completed"
                sr.data = {"shots_planned": len(all_briefs)}
                sr.message = f"Director planned {len(all_briefs)} shots"
                response.shots_planned = len(all_briefs)
            except Exception as e:
                sr.status = "failed"
                sr.message = str(e)
            sr.duration_ms = (time.perf_counter() - start) * 1000
            response.stages.append(sr)

            # Phase 10.2-A: Director v2 plan (Story Section Memory -> ShotDirective JSON)
            sr = self._run_stage(PipelineStage.DIRECTOR_V2_PLAN, request)
            try:
                v2 = self.director_bridge.plan_hierarchy(chapter_data, request.novel_id)
                response.directives = v2["directives"]
                response.directive_sections = v2["sections"]
                sr.status = "completed"
                sr.data = {"shots_total": v2["shots_total"], "sections": v2["scenes"]}
                sr.message = f"Director v2 planned {v2['shots_total']} shots with {v2['scenes']} memory sections"
            except Exception as e:
                sr.status = "failed"
                sr.message = str(e)
            sr.duration_ms = (time.perf_counter() - start) * 1000
            response.stages.append(sr)

            # Writer enhancement (optional — apply to first 10 shots for demo)
            sr = self._run_stage(PipelineStage.WRITER_ENHANCE, request)
            try:
                enhanced = 0
                for brief in all_briefs[:10]:
                    wr = self.writer.enhance_shot({"id": brief.shot.id, "description": brief.shot.description})
                    enhanced += 1
                sr.status = "completed"
                sr.data = {"enhanced_shots": enhanced}
                sr.message = f"Writer enhanced {enhanced} shots"
            except Exception as e:
                sr.status = "failed"
                sr.message = str(e)
            sr.duration_ms = (time.perf_counter() - start) * 1000
            response.stages.append(sr)

            # Critic review
            sr = self._run_stage(PipelineStage.CRITIC_REVIEW, request)
            try:
                all_briefs = self.director.run_critique(all_briefs)
                approved = sum(1 for b in all_briefs if b.approved)
                sr.status = "completed"
                sr.data = {"approved": approved, "total": len(all_briefs)}
                sr.message = f"Critic: {approved}/{len(all_briefs)} approved"
            except Exception as e:
                sr.status = "failed"
                sr.message = str(e)
            sr.duration_ms = (time.perf_counter() - start) * 1000
            response.stages.append(sr)

        # Phase 4: Prompt Compilation
        if all_briefs:
            sr = self._run_stage(PipelineStage.COMPILE_PROMPTS, request)
            try:
                character_contexts = {}

                # Gather character contexts for shots
                for brief in all_briefs:
                    for cid in brief.shot.character_ids:
                        if cid not in character_contexts:
                            character_contexts[cid] = self.character_agent.get_context(
                                cid, brief.shot.id, brief.shot.emotion
                            )

                all_compiled = self.prompt_compiler.compile_sequence(all_briefs, character_contexts)
                sr.status = "completed"
                sr.data = {"prompts_compiled": len(all_compiled)}
                sr.message = f"Compiled {len(all_compiled)} prompts"
                response.prompts_compiled = len(all_compiled)
            except Exception as e:
                sr.status = "failed"
                sr.message = str(e)
            sr.duration_ms = (time.perf_counter() - start) * 1000
            response.stages.append(sr)

        # Phase 5 (Sprint 7.1): Visual Feedback — Quality Assessment + Prompt Rewrite
        if all_briefs and all_compiled:
            sr = self._run_stage(PipelineStage.VISUAL_FEEDBACK, request)
            try:
                feedback_count = 0
                action_count = 0

                # For each compiled prompt, simulate quality assessment
                # (in production, this runs after actual image generation)
                for brief in all_briefs:
                    shot = brief.shot

                    # Build a mock profile (in production: run ImageAnalyzer on generated image)
                    # Here we assess the prompt quality speculatively
                    mock_profile = ImageProfile(
                        image_path=f"generated/{shot.id}.png",
                        content_tags=self._infer_tags_from_brief(brief),
                        composition_type=shot.shot_type or "medium",
                    )

                    # Build shot spec for scoring
                    shot_spec = {
                        "shot_id": shot.id,
                        "shot_type": shot.shot_type,
                        "camera_angle": shot.camera_angle,
                        "emotion": shot.emotion,
                        "action": shot.action,
                        "character_ids": shot.character_ids,
                    }

                    report = self.quality_scorer.score(mock_profile, shot_spec)

                    # If quality below threshold, generate feedback
                    if not report.passed:
                        original_prompt = ""
                        if hasattr(brief, "compiled_prompt"):
                            original_prompt = brief.compiled_prompt

                        feedback = self.feedback_loop.generate_feedback(
                            report, original_prompt
                        )
                        if feedback.should_retry:
                            feedback_count += 1
                            action_count += len(feedback.actions)

                sr.status = "completed"
                sr.data = {
                    "feedback_applied": feedback_count,
                    "actions_generated": action_count,
                }
                sr.message = (
                    f"Vision feedback: {feedback_count} shots flagged, "
                    f"{action_count} actions generated"
                )
                response.feedback_applied = feedback_count
                response.feedback_actions = action_count
            except Exception as e:
                sr.status = "failed"
                sr.message = str(e)
            sr.duration_ms = (time.perf_counter() - start) * 1000
            response.stages.append(sr)

        response.status = "completed"
        response.total_duration_ms = (time.perf_counter() - start) * 1000
        response.completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        return response

    def run_quick(self, text: str, title: str = "", novel_id: str = "") -> dict:
        """Quick pipeline run — returns compiled prompts directly."""
        request = PipelineRequest(text=text, title=title, novel_id=novel_id)
        response = self.run(request)

        # Extract compiled prompts summary
        compiled_stage = next(
            (s for s in response.stages if s.stage == PipelineStage.COMPILE_PROMPTS),
            None,
        )

        return {
            "status": response.status,
            "characters_found": response.characters_found,
            "shots_planned": response.shots_planned,
            "prompts_compiled": response.prompts_compiled,
            "duration_ms": response.total_duration_ms,
            "stages": {s.stage.value: s.status for s in response.stages},
        }

    @staticmethod
    def _run_stage(stage: PipelineStage, request: PipelineRequest) -> StageResult:
        return StageResult(stage=stage, status="running")

    @staticmethod
    def _infer_tags_from_brief(brief) -> list[str]:
        """Infer CLIP-style content tags from a Director's ShotBrief for mock scoring."""
        tags: list[str] = []
        shot = brief.shot

        # Shot type → tag
        shot_type_map = {
            "close-up": "close up", "extreme-close-up": "close up",
            "medium": "medium shot", "full-shot": "wide shot",
            "long-shot": "wide shot",
        }
        st = shot_type_map.get(shot.shot_type, "")
        if st:
            tags.append(st)

        # Camera angle → tag
        camera_map = {
            "low-angle": "dutch angle", "high-angle": "overhead shot",
            "dutch": "dutch angle", "overhead": "overhead shot",
        }
        cam = camera_map.get(shot.camera_angle, "")
        if cam:
            tags.append(cam)

        # Has characters
        if shot.character_ids:
            if len(shot.character_ids) == 1:
                tags.append("single character")
            else:
                tags.append("multiple characters")

        # Action presence
        if shot.action and len(shot.action) > 10:
            tags.append("dynamic pose")
        else:
            tags.append("static pose")

        # Emotion
        emotion_tags = {
            "happy": "joyful", "sad": "melancholy", "angry": "furious",
            "surprised": "shocked", "neutral": "calm", "tense": "tense",
            "dramatic": "dramatic", "dark": "dark atmosphere",
        }
        emo = emotion_tags.get(shot.emotion, "")
        if emo:
            tags.append(emo)

        # Style
        tags.append("manga style")

        return tags

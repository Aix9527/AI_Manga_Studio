"""
AI Manga Studio Pro V1.0 — LLM Service

The LLM Service is the narrative understanding engine that transforms
raw novel text into structured Story JSON consumed by the entire pipeline.

Architecture:

    Novel Text → LLM Service → Story JSON → AIDirector → Shots → ComfyUI

Supports:
- OpenAI-compatible API (local LLM / remote API)
- Rule-based fallback via AIDirector heuristics
- Chapter segmentation, character profiling, scene identification
- Shot-by-shot storyboard generation with camera/emotion/motion hints
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from loguru import logger
from pydantic import BaseModel, Field

from backend.ai_director import AIDirector
from backend.config import AppConfig, get_config


# ============================================================
# Models
# ============================================================

class LLMProvider(str, Enum):
    """Supported LLM provider backends."""
    openai = "openai"            # OpenAI / compatible API
    local = "local"              # Local LLM (LM Studio / Ollama)
    rule_based = "rule_based"    # Pure heuristic fallback
    disabled = "disabled"


class LLMServiceStatus(str, Enum):
    online = "online"
    offline = "offline"
    fallback = "fallback"
    error = "error"


class StoryParseRequest(BaseModel):
    """Request model for story parsing."""
    text: str = Field(..., description="Full novel/story text to parse")
    title: str = Field(default="Untitled", description="Story title")
    language: str = Field(default="zh", description="Language code")
    max_shots_per_chapter: int = Field(default=50, description="Max shots per chapter")
    use_llm: bool = Field(default=True, description="Use LLM or rule-based")


class StoryParseResponse(BaseModel):
    """Response containing the parsed Story JSON."""
    title: str
    language: str
    total_chapters: int
    total_characters: int
    total_scenes: int
    total_shots: int
    chapters: List[Dict[str, Any]] = Field(default_factory=list)
    characters: List[Dict[str, Any]] = Field(default_factory=list)
    scenes: List[Dict[str, Any]] = Field(default_factory=list)
    shots: List[Dict[str, Any]] = Field(default_factory=list)
    story_json: Dict[str, Any] = Field(default_factory=dict)
    provider_used: str = "rule_based"
    parse_time_ms: float = 0.0


class LLMStatusResponse(BaseModel):
    status: LLMServiceStatus
    provider: LLMProvider
    model: str = ""
    endpoint: str = ""
    available: bool = False
    latency_ms: float = 0.0


# ============================================================
# Prompt Templates
# ============================================================

SYSTEM_PROMPT = """You are an AI Manga Director. Your task is to analyze a novel and produce a precise, structured JSON storyboard.

Analyze the novel and output JSON with this exact structure:
{
  "title": "故事标题",
  "chapters": [
    {
      "index": 1,
      "title": "章节标题",
      "summary": "章节概要",
      "scenes": [
        {
          "index": 1,
          "name": "场景名",
          "location": "地点",
          "time_of_day": "day/night/dawn/dusk",
          "weather": "clear/rain/snow/overcast",
          "mood": "tense/peaceful/mysterious/joyful/sad",
          "shots": [
            {
              "index": 1,
              "camera": "CloseUp/Medium/Wide/Drone/POV/Tracking",
              "duration_seconds": 4,
              "characters": ["角色名"],
              "dialogue": "台词内容",
              "narration": "旁白",
              "action": "动作描述",
              "emotion": "情感标签",
              "prompt_hint": "SD prompt关键词"
            }
          ]
        }
      ]
    }
  ],
  "characters": [
    {
      "name": "角色名",
      "gender": "male/female",
      "estimated_age": 25,
      "role": "protagonist/antagonist/supporting",
      "traits": ["标签"],
      "appearance": "外貌描述",
      "voice_profile": "声音特征"
    }
  ]
}

Rules:
1. Split the novel into chapters based on chapter markers (第X章, Chapter X, etc.)
2. Extract ALL named characters with their traits and appearances
3. Identify distinct scene locations
4. Each paragraph/section = approximately 1 shot
5. Infer camera type from action context:
   - Dialogue / emotional moment → CloseUp
   - Character interaction → Medium
   - Location reveal / crowd → Wide
   - Aerial view → Drone
   - Subjective view → POV
   - Action / chase → Tracking
6. Estimate shot duration: dialogue ~3-5s, action ~2-3s, establishing ~4-6s
7. Generate English prompt_hint keywords for Stable Diffusion (masterpiece, cinematic, etc.)
8. Output ONLY valid JSON, no markdown, no explanation."""


# ============================================================
# LLM Service Engine
# ============================================================

@dataclass
class LLMServiceConfig:
    """Runtime configuration for LLM Service."""
    provider: LLMProvider = LLMProvider.rule_based
    api_base: str = "http://127.0.0.1:1234/v1"
    api_key: str = "not-needed"
    model: str = "local-model"
    max_tokens: int = 16384
    temperature: float = 0.3
    timeout: float = 120.0
    fallback_to_rule: bool = True


class LLMService:
    """Core LLM Service engine.

    Provides narrative understanding as a standalone service.
    Falls back to rule-based AIDirector when LLM is unavailable.

    Attributes:
        config: LLM service configuration.
        director: AIDirector instance for rule-based fallback.
        client: HTTPX async client for API calls.
    """

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self.app_config = config or get_config()
        self.director = AIDirector()
        self.client: Optional[httpx.AsyncClient] = None

        # Build LLM config from app config
        self.llm_config = LLMServiceConfig()

        # Try to read from settings
        try:
            gen_cfg = self.app_config.generation
            if hasattr(gen_cfg, 'llm_provider'):
                self.llm_config.provider = LLMProvider(gen_cfg.llm_provider)
            if hasattr(gen_cfg, 'llm_api_base'):
                self.llm_config.api_base = gen_cfg.llm_api_base
            if hasattr(gen_cfg, 'llm_api_key'):
                self.llm_config.api_key = gen_cfg.llm_api_key
            if hasattr(gen_cfg, 'llm_model'):
                self.llm_config.model = gen_cfg.llm_model
        except Exception:
            pass

        logger.info(
            f"LLM Service initialized: provider={self.llm_config.provider.value}"
        )

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTPX async client."""
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.llm_config.timeout),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.llm_config.api_key}",
                },
            )
        return self.client

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    async def check_status(self) -> LLMStatusResponse:
        """Check LLM service availability and latency.

        Returns:
            LLMStatusResponse with current status.
        """
        if self.llm_config.provider == LLMProvider.rule_based:
            return LLMStatusResponse(
                status=LLMServiceStatus.fallback,
                provider=LLMProvider.rule_based,
                available=True,
                model="rule-based (AIDirector)",
            )

        if self.llm_config.provider == LLMProvider.disabled:
            return LLMStatusResponse(
                status=LLMServiceStatus.offline,
                provider=LLMProvider.disabled,
                available=False,
            )

        try:
            client = await self._get_client()
            start = asyncio.get_event_loop().time()
            resp = await client.get(
                f"{self.llm_config.api_base}/models",
            )
            elapsed = (asyncio.get_event_loop().time() - start) * 1000

            if resp.status_code == 200:
                return LLMStatusResponse(
                    status=LLMServiceStatus.online,
                    provider=self.llm_config.provider,
                    model=self.llm_config.model,
                    endpoint=self.llm_config.api_base,
                    available=True,
                    latency_ms=round(elapsed, 1),
                )
        except Exception as e:
            logger.warning(f"LLM health check failed: {e}")

        return LLMStatusResponse(
            status=LLMServiceStatus.offline,
            provider=self.llm_config.provider,
            model=self.llm_config.model,
            endpoint=self.llm_config.api_base,
            available=False,
        )

    async def parse_story(self, request: StoryParseRequest) -> StoryParseResponse:
        """Parse a novel into structured Story JSON.

        Attempts LLM-based parsing first, falls back to rule-based
        AIDirector if LLM is unavailable or request.use_llm is False.

        Args:
            request: StoryParseRequest with novel text and options.

        Returns:
            StoryParseResponse with full storyboard JSON.
        """
        t0 = asyncio.get_event_loop().time()

        if request.use_llm and self.llm_config.provider not in (
            LLMProvider.rule_based, LLMProvider.disabled
        ):
            try:
                result = await self._parse_with_llm(request)
                if result:
                    elapsed = (asyncio.get_event_loop().time() - t0) * 1000
                    result.parse_time_ms = round(elapsed, 1)
                    return result
            except Exception as e:
                logger.warning(f"LLM parsing failed, falling back to rule-based: {e}")

        # Fallback to rule-based
        if self.llm_config.fallback_to_rule:
            result = self._parse_with_rules(request)
            elapsed = (asyncio.get_event_loop().time() - t0) * 1000
            result.parse_time_ms = round(elapsed, 1)
            return result

        # No fallback enabled — return empty
        elapsed = (asyncio.get_event_loop().time() - t0) * 1000
        return StoryParseResponse(
            title=request.title,
            language=request.language,
            total_chapters=0,
            total_characters=0,
            total_scenes=0,
            total_shots=0,
            provider_used="none",
            parse_time_ms=round(elapsed, 1),
        )

    # ----------------------------------------------------------
    # LLM-based Parsing
    # ----------------------------------------------------------

    async def _parse_with_llm(self, request: StoryParseRequest) -> Optional[StoryParseResponse]:
        """Send novel to LLM API for structured parsing.

        Args:
            request: Story parse request.

        Returns:
            StoryParseResponse or None on failure.
        """
        client = await self._get_client()

        # Truncate text if too long
        max_chars = 30000
        text = request.text[:max_chars]
        if len(request.text) > max_chars:
            logger.warning(f"Text truncated from {len(request.text)} to {max_chars} chars")

        payload = {
            "model": self.llm_config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"请分析以下小说并输出结构化JSON:\n\n{text}",
                },
            ],
            "temperature": self.llm_config.temperature,
            "max_tokens": self.llm_config.max_tokens,
            "response_format": {"type": "json_object"},
        }

        logger.info(f"LLM Service: Sending parse request to {self.llm_config.api_base}")
        resp = await client.post(
            f"{self.llm_config.api_base}/chat/completions",
            json=payload,
        )

        if resp.status_code != 200:
            logger.error(f"LLM API error: {resp.status_code} {resp.text[:200]}")
            return None

        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Parse the JSON from LLM response
        try:
            story_json = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code block
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
            if match:
                story_json = json.loads(match.group(1))
            else:
                logger.error("LLM returned invalid JSON")
                return None

        return self._build_response(request, story_json, "llm")

    # ----------------------------------------------------------
    # Rule-based Parsing (AIDirector Fallback)
    # ----------------------------------------------------------

    def _parse_with_rules(self, request: StoryParseRequest) -> StoryParseResponse:
        """Use AIDirector heuristics for story parsing.

        Args:
            request: Story parse request.

        Returns:
            StoryParseResponse from rule-based analysis.
        """
        logger.info("LLM Service: Using rule-based AIDirector fallback")

        self.director.novel_text = request.text
        self.director.segment_chapters()
        self.director.extract_characters()
        self.director.identify_scenes()
        self.director.plan_shots()

        # Build Story JSON from AIDirector output
        story_json: Dict[str, Any] = {
            "title": request.title,
            "language": request.language,
            "chapters": [],
            "characters": [],
            "scenes": [],
        }

        # Characters
        for char in self.director.characters:
            story_json["characters"].append({
                "name": char.name,
                "aliases": char.aliases,
                "gender": char.gender,
                "estimated_age": char.estimated_age,
                "role": char.role,
                "traits": char.traits,
                "appearance": ", ".join(char.appearance_hints) if char.appearance_hints else "",
                "first_appearance_chapter": char.first_appearance_chapter,
            })

        # Scenes
        for scene in self.director.scenes:
            story_json["scenes"].append({
                "name": scene.name,
                "location": scene.location,
                "time_of_day": scene.time_of_day,
                "weather": scene.weather,
                "mood": scene.mood,
                "description": scene.description,
            })

        # Chapters & Shots
        for chapter_idx, chapter_text in enumerate(self.director.chapters):
            chapter_shots = [
                s for s in self.director.shots
                if s.chapter_index == chapter_idx
            ]

            if not chapter_shots:
                # Fallback: create basic shot from chapter text
                chapter_shots = [self._make_basic_shot(0, chapter_idx, chapter_text)]

            if len(chapter_shots) > request.max_shots_per_chapter:
                chapter_shots = chapter_shots[:request.max_shots_per_chapter]

            chapter_scenes: List[Dict[str, Any]] = []
            current_scene_shots: List[Dict[str, Any]] = []
            current_scene_name = chapter_shots[0].scene_name if chapter_shots else ""

            for shot in chapter_shots:
                if shot.scene_name and shot.scene_name != current_scene_name:
                    if current_scene_shots:
                        chapter_scenes.append({
                            "index": len(chapter_scenes) + 1,
                            "name": current_scene_name,
                            "location": current_scene_name,
                            "time_of_day": "day",
                            "weather": "clear",
                            "mood": "neutral",
                            "shots": current_scene_shots,
                        })
                    current_scene_shots = []
                    current_scene_name = shot.scene_name

                current_scene_shots.append({
                    "index": shot.index,
                    "camera": shot.camera or shot.shot_type.value,
                    "duration_seconds": 4,
                    "characters": shot.characters_present,
                    "dialogue": shot.dialogue,
                    "narration": shot.narration,
                    "action": shot.action,
                    "emotion": shot.emotion,
                    "prompt_hint": shot.raw_prompt_hint,
                })

            if current_scene_shots:
                chapter_scenes.append({
                    "index": len(chapter_scenes) + 1,
                    "name": current_scene_name or f"Scene {len(chapter_scenes) + 1}",
                    "location": current_scene_name or "",
                    "time_of_day": "day",
                    "weather": "clear",
                    "mood": "neutral",
                    "shots": current_scene_shots,
                })

            story_json["chapters"].append({
                "index": chapter_idx + 1,
                "title": f"Chapter {chapter_idx + 1}",
                "summary": chapter_text[:200] + "..." if len(chapter_text) > 200 else chapter_text,
                "scenes": chapter_scenes,
            })

        return self._build_response(request, story_json, "rule_based")

    def _make_basic_shot(self, index: int, chapter_idx: int, text: str) -> Any:
        """Create a basic shot from raw text when no shots are generated."""
        from backend.ai_director import ShotDirective
        from backend.models import ShotType
        return ShotDirective(
            index=index,
            chapter_index=chapter_idx,
            shot_type=ShotType.medium,
            camera="Medium",
            action=text[:100],
            raw_prompt_hint="cinematic shot",
        )

    def _build_response(
        self,
        request: StoryParseRequest,
        story_json: Dict[str, Any],
        provider: str,
    ) -> StoryParseResponse:
        """Build StoryParseResponse from parsed JSON.

        Args:
            request: Original parse request.
            story_json: Parsed story JSON dict.
            provider: Which provider generated the result.

        Returns:
            Populated StoryParseResponse.
        """
        chapters = story_json.get("chapters", [])
        characters = story_json.get("characters", [])
        scenes = story_json.get("scenes", [])

        # Flatten all shots
        all_shots: List[Dict[str, Any]] = []
        for ch in chapters:
            for sc in ch.get("scenes", []):
                for shot in sc.get("shots", []):
                    shot["chapter_index"] = ch.get("index", 0)
                    shot["scene_name"] = sc.get("name", "")
                    all_shots.append(shot)

        return StoryParseResponse(
            title=story_json.get("title", request.title),
            language=story_json.get("language", request.language),
            total_chapters=len(chapters),
            total_characters=len(characters),
            total_scenes=len(scenes),
            total_shots=len(all_shots),
            chapters=chapters,
            characters=characters,
            scenes=scenes,
            shots=all_shots,
            story_json=story_json,
            provider_used=provider,
        )


# ============================================================
# Singleton
# ============================================================

_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get or create the singleton LLMService instance."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


async def shutdown_llm_service() -> None:
    """Clean up LLM service resources."""
    global _llm_service
    if _llm_service and _llm_service.client:
        await _llm_service.client.aclose()
        _llm_service.client = None
    _llm_service = None
    logger.info("LLM Service shut down")

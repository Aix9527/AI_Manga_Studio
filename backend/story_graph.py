"""
AI Manga Studio Pro V2.0 — StoryGraph Semantic Graph

The StoryGraph is the central semantic data hub for the V2.0 pipeline.
All downstream modules (Character Manager, Scene Manager, Style Manager,
Timeline Manager, Storyboard Engine, Prompt Engine) read exclusively from
StoryGraph — never from raw chapter data directly.

Architecture:
  AI Director (hierarchical) → StoryGraphParser → StoryGraph
      ↑                                                    ↓
  Raw novel text                              All downstream modules

Generated from the AI Director's hierarchical Chapter→Scene→Beat→Shot
output, the StoryGraph enriches the data with:
  - Character relationship edges (who appears with whom, relationship type)
  - Timeline axis (beat-level timestamps)
  - Emotion curve (chapter-level and beat-level arcs)
  - Scene context map (location/time/weather/characters/mood/tone)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


# ============================================================
# Data Classes
# ============================================================

@dataclass
class RelationEdge:
    """Directed relationship between two characters."""
    char_a: str
    char_b: str
    relation: str = ""          # 父女/恋人/仇敌/师徒/朋友/同事/陌路
    intensity: float = 0.5      # 0~1, how strong the relationship is
    status: str = "neutral"     # 和谐/冲突/微妙/亲密/疏远/敌对
    first_appears_beat: str = ""
    notes: str = ""


@dataclass
class SceneContext:
    """Full environmental context for a scene."""
    location: str = ""
    time_of_day: str = "day"
    weather: str = "clear"
    characters_present: List[str] = field(default_factory=list)
    relationships: List[RelationEdge] = field(default_factory=list)
    emotion: str = "neutral"
    mood: str = "neutral"       # majestic/mysterious/tense/peaceful/melancholic/surreal/oppressive
    lighting: str = "natural"   # natural/warm/cold/dim/harsh/dramatic/soft
    tone: str = "neutral"       # bright/dark/serene/hectic/intimate/epic
    color_scheme: str = ""      # warm/cool/monochrome/pastel/vivid/dark-palette
    interior_exterior: str = "interior"


@dataclass
class BeatNode:
    """A beat in the timeline."""
    beat_id: str = ""
    beat_type: str = ""         # dialogue/action/monologue/transition/narration
    scene_id: str = ""
    chapter_idx: int = 0
    start_sec: float = 0.0
    duration_sec: float = 3.0
    characters: List[str] = field(default_factory=list)
    emotion: str = "neutral"
    intensity: float = 0.5      # emotional intensity 0~1


@dataclass
class ChapterGraph:
    """Per-chapter graph node."""
    chapter_idx: int = 0
    title: str = ""
    scene_ids: List[str] = field(default_factory=list)
    beat_ids: List[str] = field(default_factory=list)
    shot_count: int = 0
    total_duration: float = 0.0
    summary: str = ""


@dataclass
class EmotionCurve:
    """Emotion curve over the timeline."""
    points: List[Tuple[float, str, float]] = field(default_factory=list)
    # Each point: (time_sec, emotion_label, intensity_0_to_1)
    dominant_emotions: List[str] = field(default_factory=list)


@dataclass
class TimelineAxis:
    """Timeline with beat-level precision."""
    beats: List[BeatNode] = field(default_factory=list)
    total_duration: float = 0.0
    chapter_boundaries: List[float] = field(default_factory=list)  # start_sec per chapter


@dataclass
class StoryGraph:
    """The master StoryGraph — all downstream modules read from this.

    This is the single source of truth for the V2.0 pipeline.
    After construction, it is read-only for all consumers.
    """
    project_id: str = ""
    chapters: List[ChapterGraph] = field(default_factory=list)
    character_relations: Dict[str, List[RelationEdge]] = field(default_factory=dict)
    timeline: TimelineAxis = field(default_factory=TimelineAxis)
    emotion_curve: EmotionCurve = field(default_factory=EmotionCurve)
    scene_map: Dict[str, SceneContext] = field(default_factory=dict)

    # All characters discovered
    all_characters: List[str] = field(default_factory=list)
    # All scene IDs
    all_scene_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "project_id": self.project_id,
            "chapters": [
                {
                    "chapter_idx": ch.chapter_idx,
                    "title": ch.title,
                    "scene_ids": ch.scene_ids,
                    "beat_ids": ch.beat_ids,
                    "shot_count": ch.shot_count,
                    "total_duration": ch.total_duration,
                    "summary": ch.summary,
                }
                for ch in self.chapters
            ],
            "character_relations": {
                key: [
                    {
                        "char_a": r.char_a,
                        "char_b": r.char_b,
                        "relation": r.relation,
                        "intensity": r.intensity,
                        "status": r.status,
                    }
                    for r in rels
                ]
                for key, rels in self.character_relations.items()
            },
            "timeline": {
                "total_duration": self.timeline.total_duration,
                "chapter_boundaries": self.timeline.chapter_boundaries,
                "beats": [
                    {
                        "beat_id": b.beat_id,
                        "beat_type": b.beat_type,
                        "scene_id": b.scene_id,
                        "chapter_idx": b.chapter_idx,
                        "start_sec": b.start_sec,
                        "duration_sec": b.duration_sec,
                        "characters": b.characters,
                        "emotion": b.emotion,
                        "intensity": b.intensity,
                    }
                    for b in self.timeline.beats
                ],
            },
            "emotion_curve": {
                "points": [
                    {"time_sec": t, "emotion": e, "intensity": i}
                    for t, e, i in self.emotion_curve.points
                ],
                "dominant_emotions": self.emotion_curve.dominant_emotions,
            },
            "scene_map": {
                key: {
                    "location": sc.location,
                    "time_of_day": sc.time_of_day,
                    "weather": sc.weather,
                    "characters_present": sc.characters_present,
                    "emotion": sc.emotion,
                    "mood": sc.mood,
                    "lighting": sc.lighting,
                    "tone": sc.tone,
                    "color_scheme": sc.color_scheme,
                    "interior_exterior": sc.interior_exterior,
                    "relationships": [
                        {
                            "char_a": r.char_a,
                            "char_b": r.char_b,
                            "relation": r.relation,
                            "intensity": r.intensity,
                            "status": r.status,
                        }
                        for r in sc.relationships
                    ],
                }
                for key, sc in self.scene_map.items()
            },
            "all_characters": self.all_characters,
            "all_scene_ids": self.all_scene_ids,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def save(self, path: str) -> str:
        """Save StoryGraph to JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())
        logger.info(f"StoryGraph saved → {path}")
        return path

    @classmethod
    def load(cls, path: str) -> "StoryGraph":
        """Load StoryGraph from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryGraph":
        """Deserialize from JSON-compatible dict."""
        sg = cls(project_id=data.get("project_id", ""))

        # Chapters
        for ch_data in data.get("chapters", []):
            sg.chapters.append(ChapterGraph(
                chapter_idx=ch_data.get("chapter_idx", 0),
                title=ch_data.get("title", ""),
                scene_ids=ch_data.get("scene_ids", []),
                beat_ids=ch_data.get("beat_ids", []),
                shot_count=ch_data.get("shot_count", 0),
                total_duration=ch_data.get("total_duration", 0.0),
                summary=ch_data.get("summary", ""),
            ))

        # Character relations
        for key, rels in data.get("character_relations", {}).items():
            sg.character_relations[key] = [
                RelationEdge(
                    char_a=r.get("char_a", ""),
                    char_b=r.get("char_b", ""),
                    relation=r.get("relation", ""),
                    intensity=r.get("intensity", 0.5),
                    status=r.get("status", "neutral"),
                )
                for r in rels
            ]

        # Timeline
        tl = data.get("timeline", {})
        sg.timeline = TimelineAxis(
            total_duration=tl.get("total_duration", 0.0),
            chapter_boundaries=tl.get("chapter_boundaries", []),
            beats=[
                BeatNode(
                    beat_id=b.get("beat_id", ""),
                    beat_type=b.get("beat_type", ""),
                    scene_id=b.get("scene_id", ""),
                    chapter_idx=b.get("chapter_idx", 0),
                    start_sec=b.get("start_sec", 0.0),
                    duration_sec=b.get("duration_sec", 3.0),
                    characters=b.get("characters", []),
                    emotion=b.get("emotion", "neutral"),
                    intensity=b.get("intensity", 0.5),
                )
                for b in tl.get("beats", [])
            ],
        )

        # Emotion curve
        ec = data.get("emotion_curve", {})
        sg.emotion_curve = EmotionCurve(
            points=[(p["time_sec"], p["emotion"], p["intensity"])
                     for p in ec.get("points", [])],
            dominant_emotions=ec.get("dominant_emotions", []),
        )

        # Scene map
        for key, sc in data.get("scene_map", {}).items():
            sg.scene_map[key] = SceneContext(
                location=sc.get("location", ""),
                time_of_day=sc.get("time_of_day", "day"),
                weather=sc.get("weather", "clear"),
                characters_present=sc.get("characters_present", []),
                emotion=sc.get("emotion", "neutral"),
                mood=sc.get("mood", "neutral"),
                lighting=sc.get("lighting", "natural"),
                tone=sc.get("tone", "neutral"),
                color_scheme=sc.get("color_scheme", ""),
                interior_exterior=sc.get("interior_exterior", "interior"),
                relationships=[
                    RelationEdge(
                        char_a=r.get("char_a", ""),
                        char_b=r.get("char_b", ""),
                        relation=r.get("relation", ""),
                        intensity=r.get("intensity", 0.5),
                        status=r.get("status", "neutral"),
                    )
                    for r in sc.get("relationships", [])
                ],
            )

        sg.all_characters = data.get("all_characters", [])
        sg.all_scene_ids = data.get("all_scene_ids", [])
        return sg


# ============================================================
# StoryGraph Parser
# ============================================================

class StoryGraphParser:
    """Build a StoryGraph from the AI Director's hierarchical output.

    Input: List of Chapter (with Scenes → Beats → Shots) from AI Director.
    Output: Fully populated StoryGraph semantic graph.

    Responsibilities:
      - Infer character relationships from co-appearance patterns
      - Build beat-level timeline with timestamps
      - Compute emotion curve across all beats
      - Build scene context map with environment details
    """

    # Relationship inference: emotion-keyword-based pairing
    EMOTION_TO_RELATION = {
        "angry": "冲突",
        "sad": "疏远",
        "happy": "亲密",
        "fearful": "紧张",
        "surprised": "微妙",
        "loving": "亲密",
        "hateful": "敌对",
        "worried": "关心",
        "neutral": "中性",
    }

    # Emotion → color scheme mapping
    EMOTION_TO_COLOR = {
        "angry": "warm",
        "sad": "cool",
        "happy": "vivid",
        "fearful": "dark-palette",
        "surprised": "vivid",
        "loving": "pastel",
        "hateful": "dark-palette",
        "worried": "cool",
        "neutral": "natural",
    }

    # Mood → lighting mapping
    MOOD_TO_LIGHTING = {
        "majestic": "dramatic",
        "mysterious": "dim",
        "tense": "harsh",
        "peaceful": "soft",
        "melancholic": "cold",
        "surreal": "dramatic",
        "oppressive": "dim",
        "neutral": "natural",
    }

    def parse(self, chapters: List[Any], project_id: str = "") -> StoryGraph:
        """Parse hierarchical chapters into a StoryGraph.

        Args:
            chapters: List of Chapter objects from AI Director.
                Each Chapter has .scenes (List[Scene]), each Scene has
                .beats (List[Beat]) and .shots (List[Shot]).
            project_id: Project identifier.

        Returns:
            Fully populated StoryGraph.
        """
        sg = StoryGraph(project_id=project_id)

        all_characters: set = set()
        all_scenes: Dict[str, SceneContext] = {}
        co_appearance: Dict[Tuple[str, str], int] = {}  # (a,b) → count
        beat_nodes: List[BeatNode] = []
        emotion_points: List[Tuple[float, str, float]] = []
        chapter_graphs: List[ChapterGraph] = []
        chapter_boundaries: List[float] = []
        running_time: float = 0.0

        for ch_idx, chapter in enumerate(chapters):
            ch_boundary = running_time
            chapter_boundaries.append(ch_boundary)
            ch_scene_ids: List[str] = []
            ch_beat_ids: List[str] = []
            ch_shot_count: int = 0
            ch_duration: float = 0.0

            scenes = getattr(chapter, "scenes", [])
            if not scenes:
                continue

            for scene in scenes:
                scene_id = getattr(scene, "scene_id", f"sc_{ch_idx+1:02d}_01")
                location = getattr(scene, "location", "")
                time_of_day = getattr(scene, "time", "day")
                weather = getattr(scene, "weather", "clear")
                emotion = getattr(scene, "emotion", "neutral")
                mood = getattr(scene, "mood", "neutral")

                ch_scene_ids.append(scene_id)

                # Collect characters present in this scene
                scene_characters: set = set()

                beats = getattr(scene, "beats", [])
                for beat_idx, beat in enumerate(beats):
                    beat_id = getattr(beat, "beat_id",
                                      f"bt_{ch_idx+1:02d}_{len(beat_nodes)+1:03d}")
                    beat_type = getattr(beat, "beat_type", "action")
                    beat_desc = getattr(beat, "description", "")
                    beat_chars = list(getattr(beat, "characters", []))
                    beat_emotion = getattr(beat, "emotion", emotion)
                    beat_duration = float(getattr(beat, "duration", 3.0))

                    # Track characters
                    for c in beat_chars:
                        scene_characters.add(c)
                        all_characters.add(c)

                    # Track co-appearance pairs
                    sorted_chars = sorted(beat_chars)
                    for i in range(len(sorted_chars)):
                        for j in range(i + 1, len(sorted_chars)):
                            pair = (sorted_chars[i], sorted_chars[j])
                            co_appearance[pair] = co_appearance.get(pair, 0) + 1

                    # Beat node
                    bn = BeatNode(
                        beat_id=beat_id,
                        beat_type=beat_type,
                        scene_id=scene_id,
                        chapter_idx=ch_idx + 1,
                        start_sec=running_time,
                        duration_sec=beat_duration,
                        characters=beat_chars,
                        emotion=beat_emotion,
                        intensity=0.5,
                    )
                    beat_nodes.append(bn)
                    ch_beat_ids.append(beat_id)

                    # Emotion curve point
                    intensity = float(getattr(beat, "emotion_intensity", 0.5))
                    emotion_points.append((running_time, beat_emotion, intensity))

                    running_time += beat_duration
                    ch_duration += beat_duration

                # Shots in this scene
                shots = getattr(scene, "shots", [])
                ch_shot_count += len(shots)

                # Build SceneContext
                scene_chars_list = sorted(scene_characters)
                scene_relationships = self._infer_relationships(
                    scene_chars_list, co_appearance
                )

                scene_context = SceneContext(
                    location=location,
                    time_of_day=time_of_day,
                    weather=weather,
                    characters_present=scene_chars_list,
                    relationships=scene_relationships,
                    emotion=emotion,
                    mood=mood,
                    lighting=self.MOOD_TO_LIGHTING.get(mood, "natural"),
                    tone=self._infer_tone(mood, emotion),
                    color_scheme=self.EMOTION_TO_COLOR.get(emotion, "natural"),
                    interior_exterior=self._infer_interior_exterior(location),
                )
                all_scenes[scene_id] = scene_context

            ch_graph = ChapterGraph(
                chapter_idx=ch_idx + 1,
                title=getattr(chapter, "title", f"Chapter {ch_idx+1}"),
                scene_ids=ch_scene_ids,
                beat_ids=ch_beat_ids,
                shot_count=ch_shot_count,
                total_duration=ch_duration,
                summary=getattr(chapter, "summary", ""),
            )
            chapter_graphs.append(ch_graph)

        # Build character relations
        character_relations: Dict[str, List[RelationEdge]] = {}
        for (a, b), count in co_appearance.items():
            pair_key = f"{a}|{b}"
            edge = RelationEdge(
                char_a=a,
                char_b=b,
                relation=self._infer_relation_type(a, b, co_appearance),
                intensity=min(1.0, count / max(1, max(co_appearance.values()))),
                status="中性",
            )
            character_relations.setdefault(a, []).append(edge)
            character_relations.setdefault(b, []).append(RelationEdge(
                char_a=b, char_b=a,
                relation=edge.relation,
                intensity=edge.intensity,
                status=edge.status,
            ))

        # Build emotion curve
        dominant_emotions = self._compute_dominant_emotions(emotion_points)

        sg.chapters = chapter_graphs
        sg.character_relations = character_relations
        sg.timeline = TimelineAxis(
            beats=beat_nodes,
            total_duration=running_time,
            chapter_boundaries=chapter_boundaries,
        )
        sg.emotion_curve = EmotionCurve(
            points=emotion_points,
            dominant_emotions=dominant_emotions,
        )
        sg.scene_map = all_scenes
        sg.all_characters = sorted(all_characters)
        sg.all_scene_ids = sorted(all_scenes.keys())

        logger.info(
            f"StoryGraph: Built — {len(chapter_graphs)} chapters, "
            f"{len(beat_nodes)} beats, {len(all_characters)} characters, "
            f"{len(all_scenes)} scenes, {running_time:.1f}s total"
        )
        return sg

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    def _infer_relationships(
        self,
        chars: List[str],
        co_appearance: Dict[Tuple[str, str], int],
    ) -> List[RelationEdge]:
        """Infer relationships among characters in a scene."""
        edges: List[RelationEdge] = []
        for i in range(len(chars)):
            for j in range(i + 1, len(chars)):
                pair = (chars[i], chars[j])
                rev_pair = (chars[j], chars[i])
                count = co_appearance.get(pair, co_appearance.get(rev_pair, 0))
                if count > 0:
                    edges.append(RelationEdge(
                        char_a=chars[i],
                        char_b=chars[j],
                        relation="对手戏" if count > 1 else "相遇",
                        intensity=min(1.0, count / 10.0),
                        status="互动",
                    ))
        return edges

    def _infer_relation_type(
        self,
        a: str,
        b: str,
        co_appearance: Dict[Tuple[str, str], int],
    ) -> str:
        """Infer the type of relationship from co-appearance strength."""
        pair = (a, b)
        rev = (b, a)
        count = co_appearance.get(pair, co_appearance.get(rev, 0))
        if count >= 10:
            return "密切"
        elif count >= 5:
            return "重要"
        elif count >= 2:
            return "一般"
        return "偶遇"

    def _infer_tone(self, mood: str, emotion: str) -> str:
        """Infer tone from mood and emotion."""
        tone_map = {
            "majestic": "epic",
            "mysterious": "dark",
            "tense": "hectic",
            "peaceful": "serene",
            "melancholic": "dark",
            "surreal": "hectic",
            "oppressive": "dark",
            "neutral": "bright",
        }
        return tone_map.get(mood, "bright")

    def _infer_interior_exterior(self, location: str) -> str:
        """Infer whether a scene is interior or exterior."""
        outdoor_keywords = [
            "森林", "山顶", "海边", "街道", "广场", "花园", "沙漠",
            "战场", "废墟", "天空", "洞穴", "河流", "公路", "公园",
            "校园", "机场", "车站", "码头", "田野", "山间", "海滩",
        ]
        for kw in outdoor_keywords:
            if kw in location:
                return "exterior"
        return "interior"

    def _compute_dominant_emotions(
        self,
        points: List[Tuple[float, str, float]],
    ) -> List[str]:
        """Compute the top 3 dominant emotions by cumulative intensity×duration."""
        if not points:
            return ["neutral"]

        emotion_weight: Dict[str, float] = {}
        for i, (time_sec, emotion, intensity) in enumerate(points):
            weight = intensity
            emotion_weight[emotion] = emotion_weight.get(emotion, 0.0) + weight

        sorted_emotions = sorted(emotion_weight.items(), key=lambda x: -x[1])
        return [e for e, _ in sorted_emotions[:3]]


# ============================================================
# Utility: Load from AI Director hierarchical output
# ============================================================

def build_story_graph(chapters: List[Any], project_id: str = "") -> StoryGraph:
    """Convenience function to build StoryGraph from AI Director output.

    Args:
        chapters: List of Chapter objects (from AIDirector.parse_hierarchical()).
        project_id: Project identifier.

    Returns:
        Fully populated StoryGraph.
    """
    parser = StoryGraphParser()
    return parser.parse(chapters, project_id)

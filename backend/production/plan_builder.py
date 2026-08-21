from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from backend.production.contracts import (
    InputType,
    LoadedInput,
    ProductionPlan,
    ShotSpec,
)

logger = logging.getLogger(__name__)


LIVE_ACTION_ANCHOR = (
    "photorealistic live-action Chinese cinema, realistic Chinese cast, "
    "natural skin texture, physically accurate fabric, cinematic lighting, "
    "volumetric atmosphere, 35mm film still, controlled depth of field, "
    "high dynamic range, subtle film grain"
)
NEGATIVE_PROMPT = (
    "anime, manga, illustration, cartoon, 3d render, plastic skin, doll face, "
    "extra fingers, malformed hands, duplicate person, low resolution, blur, "
    "text, logo, subtitle, watermark, mosaic, pixelated, blocky"
)
CAMERAS = (
    "aerial establishing shot, slow push-in",
    "wide shot, measured dolly movement",
    "medium tracking shot, handheld restraint",
    "close-up, shallow depth of field",
    "low-angle wide shot, slow tilt",
    "over-the-shoulder shot, subtle parallax",
    "extreme close-up, rack focus",
    "epic long shot, crane movement",
    "profile close-up, slow orbit",
    "final wide shot, pull back into darkness",
)
TRANSITIONS = ("fade", "dip_to_black", "crossfade", "light_flash")


@dataclass(frozen=True)
class PlanSettings:
    target_seconds: int = 600  # 10 minutes per episode (was 60)
    max_shots: int = 50  # 50 shots per episode (was 10)
    width: int = 1080
    height: int = 1920
    generation_width: int = 480
    generation_height: int = 832
    fps: int = 24
    provider: str = "ltx23"
    style: str = "live_action_cinematic"
    episode_count: int = 1  # Number of episodes to generate
    shots_per_episode: int = 40  # Target shots per episode

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)


def build_trailer_plan(
    project_id: str,
    loaded: LoadedInput,
    settings: PlanSettings,
) -> ProductionPlan:
    """Build a production plan from the loaded input.

    - STORYBOARD 输入（分镜 HTML/XML）-> storyboard_loader 直接转 ShotSpec，
      分镜数据（镜号/景别/运镜/画面/台词/时长）成为唯一生成依据。
    - 其他文本输入 -> LLM parser（text-driven），失败回退 beat-selection。
    """
    # 分镜驱动：分镜数据优先级最高（用户指令：使用该分镜进行生成）
    if loaded.contract.type == InputType.STORYBOARD:
        try:
            from backend.production.storyboard_loader import (
                load_storyboard,
                storyboard_to_plan,
            )

            path = loaded.contract.path
            sb = load_storyboard(path)
            plan = storyboard_to_plan(
                project_id, sb, settings=settings.to_dict()
            )
            logger.info("Storyboard plan: %d shots, %.1fs total",
                        len(plan.shots), plan.total_duration)
            return plan
        except Exception as exc:
            logger.warning("Storyboard plan failed (%s); falling back", exc)

    # Try LLM parser first for text-driven generation
    try:
        plan = _build_plan_with_llm_parser(project_id, loaded, settings)
        if plan is not None:
            logger.info("Built plan with LLM parser: %d shots, %.1fs total",
                        len(plan.shots), plan.total_duration)
            return plan
    except Exception as exc:
        logger.warning("LLM parser plan generation failed, falling back: %s", exc)

    # Fallback: original beat-selection algorithm
    return _build_plan_fallback(project_id, loaded, settings)


def _build_plan_with_llm_parser(
    project_id: str,
    loaded: LoadedInput,
    settings: PlanSettings,
) -> ProductionPlan | None:
    """Build production plan using LLM-based text parser."""
    from backend.production.llm_parser import parse_novel

    # Get full novel text
    full_text = loaded.text
    if not full_text and loaded.chapters:
        full_text = "\n\n".join(ch.content for ch in loaded.chapters)
    if not full_text:
        return None

    title = loaded.contract.title or "未命名小说"

    # Parse novel into episodes and scenes
    parsed = parse_novel(full_text, title=title)

    if not parsed.episodes or not parsed.episodes[0].scenes:
        logger.warning("LLM parser produced no episodes/scenes")
        return None

    # Convert parsed scenes to ShotSpec objects
    shots: list[ShotSpec] = []
    shot_number = 0

    max_shots = min(
        value for value in (settings.max_shots, settings.shots_per_episode) if value
    )
    for episode in parsed.episodes[:settings.episode_count]:
        for scene in episode.scenes:
            if shot_number >= max_shots:
                break
            shot_number += 1
            shot_id = f"shot_{shot_number:02d}"

            # Build positive prompt with cinematic anchor
            positive = scene.positive_prompt
            if LIVE_ACTION_ANCHOR not in positive:
                positive = f"{LIVE_ACTION_ANCHOR}, {positive}"

            # Build negative prompt with anti-mosaic
            negative = scene.negative_prompt or NEGATIVE_PROMPT
            if "mosaic" not in negative:
                negative = f"{negative}, mosaic, pixelated, blocky"

            shots.append(ShotSpec(
                id=shot_id,
                shot_number=shot_number,
                description=scene.description,
                duration=scene.duration_hint if scene.duration_hint > 0 else 12.0,
                camera=scene.camera or CAMERAS[(shot_number - 1) % len(CAMERAS)],
                characters=scene.characters,
                dialogue=[],
                sfx=_infer_sfx(scene.description),
                positive_prompt=positive,
                negative_prompt=negative,
                narration=scene.narration,
                transition=TRANSITIONS[(shot_number - 1) % len(TRANSITIONS)],
                seed=scene.seed if scene.seed > 0 else 20260727 + shot_number * 7919,
                motion_level=_shot_motion_level(
                    description=scene.description,
                    camera=scene.camera or "",
                    dialogue=getattr(scene, "dialogue", ""),
                    narration=scene.narration,
                ),
            ))
        if shot_number >= max_shots:
            break

    if not shots:
        return None

    # Select source chapter
    source_chapter = _select_story_chapter(loaded)

    total_duration = sum(s.duration for s in shots)

    logger.info("LLM plan: %d shots across %d episodes, %.1f minutes total",
                len(shots), min(len(parsed.episodes), settings.episode_count),
                total_duration / 60)

    return ProductionPlan(
        project_id=project_id,
        input_contract=loaded.contract,
        chapters=[source_chapter],
        shots=shots,
        total_duration=total_duration,
        settings={
            **settings.to_dict(),
            "episodes": [
                {"id": ep.episode_id, "title": ep.title, "scene_count": len(ep.scenes)}
                for ep in parsed.episodes[:settings.episode_count]
            ],
            "characters": parsed.characters,
            "llm_parsed": True,
        },
    )


def _build_plan_fallback(
    project_id: str,
    loaded: LoadedInput,
    settings: PlanSettings,
) -> ProductionPlan:
    """Original beat-selection algorithm as fallback."""
    source_chapter = _select_story_chapter(loaded)
    # Use more shots for longer episodes
    max_shots = settings.shots_per_episode or settings.max_shots
    beats = _select_beats(source_chapter.content, max_shots)
    shot_count = min(max_shots, max(20, len(beats)))
    beats = _fit_beats(beats, shot_count)
    shot_duration = max(8.0, settings.target_seconds / shot_count)

    shots: list[ShotSpec] = []
    for index, beat in enumerate(beats, start=1):
        camera = CAMERAS[(index - 1) % len(CAMERAS)]
        shots.append(
            ShotSpec(
                id=f"shot_{index:03d}",
                shot_number=index,
                description=beat,
                duration=shot_duration,
                camera=camera,
                sfx=_infer_sfx(beat),
                positive_prompt=f"{LIVE_ACTION_ANCHOR}, {camera}, {beat}",
                negative_prompt=f"{NEGATIVE_PROMPT}, mosaic, pixelated, blocky",
                narration=_narration_line(beat),
                transition=TRANSITIONS[(index - 1) % len(TRANSITIONS)],
                seed=20260727 + index * 7919,
                motion_level=_shot_motion_level(
                    description=beat,
                    camera=camera,
                    narration=_narration_line(beat),
                ),
            )
        )

    return ProductionPlan(
        project_id=project_id,
        input_contract=loaded.contract,
        chapters=[source_chapter],
        shots=shots,
        total_duration=sum(shot.duration for shot in shots),
        settings=settings.to_dict(),
    )



def _shot_motion_level(
    description: str,
    camera: str,
    dialogue: list[str] | str = "",
    narration: str = "",
) -> int:
    """Derive the 0-4 motion level for a shot via scene/camera classification."""
    try:
        from backend.video.duration_strategy import get_shot_motion_level
        return get_shot_motion_level({
            "description": description,
            "camera": camera,
            "dialogue": dialogue if isinstance(dialogue, list) else ([dialogue] if dialogue else []),
            "narration": narration,
        })
    except Exception:
        return 2


def save_plan(plan: ProductionPlan, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(plan), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _select_story_chapter(loaded: LoadedInput):
    if not loaded.chapters:
        raise ValueError("Novel has no chapters")
    substantive = [chapter for chapter in loaded.chapters if chapter.word_count >= 200]
    return substantive[0] if substantive else max(loaded.chapters, key=lambda chapter: chapter.word_count)


def _select_beats(text: str, max_shots: int) -> list[str]:
    sentences = [
        re.sub(r"\s+", " ", sentence).strip(" \r\n")
        for sentence in re.split(r"(?<=[。！？!?])", text)
    ]
    sentences = [sentence for sentence in sentences if len(sentence) >= 8]
    if not sentences:
        compact = re.sub(r"\s+", " ", text).strip()
        if not compact:
            raise ValueError("Selected chapter has no usable story text")
        sentences = [compact]

    desired = min(max_shots, max(8, len(sentences)))
    if len(sentences) <= desired:
        return sentences
    indexes = [
        round(index * (len(sentences) - 1) / (desired - 1))
        for index in range(desired)
    ]
    return [sentences[index][:120] for index in indexes]


def _fit_beats(beats: list[str], shot_count: int) -> list[str]:
    if len(beats) >= shot_count:
        indexes = [
            round(index * (len(beats) - 1) / (shot_count - 1))
            for index in range(shot_count)
        ]
        return [beats[index] for index in indexes]

    fitted = list(beats)
    while len(fitted) < shot_count:
        source = beats[len(fitted) % len(beats)]
        fitted.append(f"{source} 镜头转向环境中正在扩大的异常现象。")
    return fitted


def _narration_line(beat: str) -> str:
    line = re.sub(r"[“”\"']", "", beat)
    return line[:42].rstrip("，、；：")


def _infer_sfx(beat: str) -> list[str]:
    mapping = (
        (("海", "潮", "水", "雨"), "water"),
        (("警报", "爆炸", "震动"), "impact"),
        (("风", "门", "黑暗"), "wind"),
        (("脚步", "奔跑"), "footsteps"),
    )
    return [sound for keywords, sound in mapping if any(keyword in beat for keyword in keywords)]

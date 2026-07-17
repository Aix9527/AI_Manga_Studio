"""
AI Manga Studio Pro V5 — Shot Table Generator (镜表生成器)

Generates professional shot tables (镜表) for manga/video production.
A shot table is the blueprint of every shot in a scene, containing:
- Shot number, type, angle, movement
- Subject action, dialogue, lighting, VFX
- Duration, transition, emotional notes, director notes

This module integrates with:
- DirectorVideoPromptBuilder (for cinematic descriptions)
- CinematicShot (for structured shot data)
- StoryboardEngine (for visual planning)
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.director_video_prompt_builder import (
    CinematicShot,
    DirectorVideoPrompt,
    DirectorVideoPromptBuilder,
    ShotTableEntry,
)


# ============================================================
# Shot Table Generator
# ============================================================

class ShotTableGenerator:
    """Generates professional shot tables (镜表) for manga/video production.

    Outputs:
    1. JSON shot table (machine-readable)
    2. CSV shot table (spreadsheet-compatible)
    3. Markdown shot table (human-readable)
    4. Director's shot table notes (PDF-ready)
    """

    def __init__(self):
        self.builder = DirectorVideoPromptBuilder()
        logger.info("ShotTableGenerator initialized (V5)")

    def generate_table(
        self,
        shots: List[CinematicShot],
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a complete shot table from a list of CinematicShots.

        Args:
            shots: List of CinematicShot objects.
            output_dir: Optional directory to save output files.

        Returns:
            Dict with keys: shots (list), summary, metadata.
        """
        # Build director prompts for all shots
        prompts = self.builder.build_batch(shots)

        # Build shot table entries
        table_entries = self.builder.build_shot_table(prompts, shots)

        # Compile results
        result = {
            "shots": [entry.to_dict() for entry in table_entries],
            "prompts": [p.to_dict() for p in prompts],
            "summary": self._compile_summary(table_entries, prompts, shots),
            "metadata": {
                "total_shots": len(shots),
                "total_duration": sum(s.duration_sec for s in shots),
                "shot_types": self._count_shot_types(shots),
                "emotions": self._count_emotions(shots),
                "generated_at": self._timestamp(),
            },
        }

        # Save to files if output_dir provided
        if output_dir:
            self._save_tables(result, output_dir)

        logger.info(
            f"ShotTableGenerator: built table with {len(table_entries)} shots, "
            f"total duration {result['metadata']['total_duration']:.1f}s"
        )
        return result

    def generate_from_dict_list(
        self,
        shot_dicts: List[Dict[str, Any]],
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate shot table from a list of shot dictionaries.

        Converts dicts to CinematicShot objects internally.
        """
        shots = []
        for sd in shot_dicts:
            shot = CinematicShot(
                shot_id=sd.get("shot_id", ""),
                chapter=sd.get("chapter", 1),
                scene=sd.get("scene", 1),
                shot_num=sd.get("shot", 1),
                shot_type=sd.get("shot_type", "medium"),
                camera_movement=sd.get("camera_movement", ""),
                focal_length=sd.get("focal_length", ""),
                angle=sd.get("angle", "eye_level"),
                characters=sd.get("characters", []),
                character_actions=sd.get("character_actions", []),
                expressions=sd.get("expressions", []),
                emotion=sd.get("emotion", "neutral"),
                scene_description=sd.get("scene_description", ""),
                time_of_day=sd.get("time_of_day", "day"),
                weather=sd.get("weather", "clear"),
                custom_lighting=sd.get("lighting", ""),
                subject_motion=sd.get("subject_motion", ""),
                cloth_motion=sd.get("cloth_motion", ""),
                dialogue=sd.get("dialogue", ""),
                sfx=sd.get("sfx", ""),
                bgm_mood=sd.get("bgm_mood", ""),
                visual_effects=sd.get("visual_effects", []),
                transition_in=sd.get("transition_in", "cut"),
                transition_out=sd.get("transition_out", "cut"),
                duration_sec=sd.get("duration_sec", 5.0),
            )
            shots.append(shot)

        return self.generate_table(shots, output_dir)

    # ---- Internal Methods ----

    def _compile_summary(
        self,
        entries: List[ShotTableEntry],
        prompts: List[DirectorVideoPrompt],
        shots: List[CinematicShot],
    ) -> Dict[str, Any]:
        """Compile a summary of the shot table."""
        durations = [s.duration_sec for s in shots]
        return {
            "total_duration": sum(durations),
            "average_shot_duration": sum(durations) / len(durations) if durations else 0,
            "min_duration": min(durations) if durations else 0,
            "max_duration": max(durations) if durations else 0,
            "total_transitions": len([e for e in entries if e.transition != "cut"]),
            "action_shots": len([s for s in shots if s.character_actions]),
            "dialogue_shots": len([s for s in shots if s.dialogue]),
        }

    def _count_shot_types(self, shots: List[CinematicShot]) -> Dict[str, int]:
        """Count distribution of shot types."""
        counts: Dict[str, int] = {}
        for s in shots:
            t = s.shot_type
            counts[t] = counts.get(t, 0) + 1
        return counts

    def _count_emotions(self, shots: List[CinematicShot]) -> Dict[str, int]:
        """Count distribution of emotions."""
        counts: Dict[str, int] = {}
        for s in shots:
            e = s.emotion
            counts[e] = counts.get(e, 0) + 1
        return counts

    def _timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _save_tables(self, result: Dict[str, Any], output_dir: str) -> None:
        """Save shot table to various formats."""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # 1. JSON (machine-readable)
        json_path = out_path / "shot_table.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"ShotTableGenerator: saved JSON to {json_path}")

        # 2. CSV (spreadsheet-compatible)
        csv_path = out_path / "shot_table.csv"
        self._save_csv(result, csv_path)

        # 3. Markdown (human-readable)
        md_path = out_path / "shot_table.md"
        self._save_markdown(result, md_path)

    def _save_csv(self, result: Dict[str, Any], path: Path) -> None:
        """Save shot table as CSV."""
        if not result.get("shots"):
            return

        fieldnames = [
            "镜号", "景别", "角度", "运镜", "画面内容",
            "台词", "灯光", "特效", "时长", "转场",
            "情绪备注", "导演备注"
        ]

        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for shot in result["shots"]:
                writer.writerow({
                    "镜号": shot.get("镜号", ""),
                    "景别": shot.get("景别", ""),
                    "角度": shot.get("角度", ""),
                    "运镜": shot.get("运镜", ""),
                    "画面内容": shot.get("画面内容", ""),
                    "台词": shot.get("台词", ""),
                    "灯光": shot.get("灯光", ""),
                    "特效": shot.get("特效", ""),
                    "时长": shot.get("时长", ""),
                    "转场": shot.get("转场", ""),
                    "情绪备注": shot.get("情绪备注", ""),
                    "导演备注": shot.get("导演备注", ""),
                })

    def _save_markdown(self, result: Dict[str, Any], path: Path) -> None:
        """Save shot table as Markdown table."""
        if not result.get("shots"):
            return

        lines = [
            "# 镜表 (Shot Table)",
            "",
            "## 概览",
            f"- 总镜头数: {result['metadata']['total_shots']}",
            f"- 总时长: {result['metadata']['total_duration']:.1f}秒",
            f"- 平均镜头时长: {result['summary']['average_shot_duration']:.1f}秒",
            "",
            "## 镜头明细",
            "",
            "| 镜号 | 景别 | 运镜 | 画面内容 | 台词 | 时长 | 转场 |",
            "|------|------|------|----------|------|------|------|",
        ]

        for shot in result["shots"]:
            lines.append(
                f"| {shot.get('镜号', '')} "
                f"| {shot.get('景别', '')} "
                f"| {shot.get('运镜', '')[:30]} "
                f"| {shot.get('画面内容', '')[:40]} "
                f"| {shot.get('台词', '')[:20]} "
                f"| {shot.get('时长', '')}s "
                f"| {shot.get('转场', '')} |"
            )

        lines.append("")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

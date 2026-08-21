"""Phase 15.1：归墟第二部剧本解析 → 100 集 Pilot 规划。"""

from __future__ import annotations

import re
from pathlib import Path

DEFAULT_SCRIPT = r"C:\Users\X\Desktop\归墟第二部.txt"

# 6 章 → 100 集分配（序章/第一章…/尾声）
CHAPTER_EPISODE_PLAN = [
    ("序章 广播之后", 6),
    ("第一章 地下城第四层", 24),
    ("第二章 渗透者", 20),
    ("第三章 觉醒者", 30),
    ("第四章 地维绝", 15),
    ("尾声 来自太阳系边缘的回信", 5),
]


def parse_script(path: str | Path | None = DEFAULT_SCRIPT) -> dict:
    """解析剧本：返回章节标题与正文行数（用于集标题生成）。"""
    path = Path(path or DEFAULT_SCRIPT)
    if not path.exists():
        raise FileNotFoundError(f"script not found: {path}")
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    chapters: list[dict] = []
    current: dict | None = None
    for line in lines:
        s = line.strip()
        if re.match(r"^(序章|第.+章|尾声|终章)", s) and len(s) < 30:
            if current:
                chapters.append(current)
            current = {"title": s, "lines": 0}
        elif current:
            if s:
                current["lines"] += 1
    if current:
        chapters.append(current)
    return {"title": "归墟第二部·地维绝", "chapters": chapters}


def build_episode_plan(script_path: str | Path | None = DEFAULT_SCRIPT) -> dict:
    """按 6 章配额生成 100 集规划（EP001–EP100）。"""
    parsed = parse_script(script_path)
    chapters = parsed["chapters"]
    episodes: list[dict] = []
    ep_no = 0
    chapter_plan: list[dict] = []
    for idx, (title, count) in enumerate(CHAPTER_EPISODE_PLAN):
        chapter_meta = next((c for c in chapters if c["title"] == title), {"title": title, "lines": 0})
        chapter_plan.append({"title": title, "episodes": count, "lines": chapter_meta["lines"]})
        for i in range(1, count + 1):
            ep_no += 1
            episodes.append({
                "id": f"EP{ep_no:03d}",
                "title": f"{title} · 第{i}节",
                "chapter": title,
            })
    return {
        "project_id": "guixu2",
        "title": parsed["title"],
        "total_episodes": len(episodes),
        "chapters": chapter_plan,
        "episodes": episodes,
    }

"""SQLite persistence for canonical story hierarchies and graphs."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional

from backend.story.models import Chapter, Scene, Shot, StoryGraph, StoryNode


StoryHierarchy = list[tuple[Chapter, list[tuple[Scene, list[Shot]]]]]


@dataclass
class StoryRecord:
    graph: StoryGraph
    hierarchy: StoryHierarchy


class StoryRepository:
    """Stores one authoritative story record per novel ID."""

    def __init__(self, db_path: str = "storage/orchestrator.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize_schema()

    def _conn(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize_schema(self) -> None:
        with self._conn() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS story_records (
                    novel_id TEXT PRIMARY KEY,
                    graph_json TEXT NOT NULL,
                    hierarchy_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    @staticmethod
    def _known_fields(model, value: dict) -> dict:
        """Load older or newer JSON records without coupling to every schema version."""
        names = {item.name for item in fields(model)}
        return {key: item for key, item in value.items() if key in names}

    @staticmethod
    def _graph_to_dict(graph: StoryGraph) -> dict:
        return {
            "id": graph.id,
            "novel_id": graph.novel_id,
            "title": graph.title,
            "nodes": {node_id: asdict(node) for node_id, node in graph.nodes.items()},
            "edges": graph.edges,
            "created_at": graph.created_at,
        }

    @staticmethod
    def _hierarchy_to_list(hierarchy: StoryHierarchy) -> list[dict]:
        return [
            {
                "chapter": asdict(chapter),
                "scenes": [
                    {"scene": asdict(scene), "shots": [asdict(shot) for shot in shots]}
                    for scene, shots in scene_data
                ],
            }
            for chapter, scene_data in hierarchy
        ]

    def save_story(self, graph: StoryGraph, hierarchy: StoryHierarchy) -> StoryRecord:
        graph_json = json.dumps(self._graph_to_dict(graph), ensure_ascii=False)
        hierarchy_json = json.dumps(self._hierarchy_to_list(hierarchy), ensure_ascii=False)
        with self._conn() as connection:
            connection.execute(
                """
                INSERT INTO story_records (novel_id, graph_json, hierarchy_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(novel_id) DO UPDATE SET
                    graph_json = excluded.graph_json,
                    hierarchy_json = excluded.hierarchy_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (graph.novel_id, graph_json, hierarchy_json),
            )
        return StoryRecord(graph=graph, hierarchy=hierarchy)

    def load_story(self, novel_id: str) -> Optional[StoryRecord]:
        with self._conn() as connection:
            row = connection.execute(
                "SELECT graph_json, hierarchy_json FROM story_records WHERE novel_id = ?",
                (novel_id,),
            ).fetchone()
        if not row:
            return None

        graph_data = json.loads(row["graph_json"])
        graph = StoryGraph(
            id=graph_data["id"],
            novel_id=graph_data["novel_id"],
            title=graph_data["title"],
            nodes={
                node_id: StoryNode(**self._known_fields(StoryNode, node_data))
                for node_id, node_data in graph_data["nodes"].items()
            },
            edges=[tuple(edge) for edge in graph_data["edges"]],
            created_at=graph_data["created_at"],
        )
        hierarchy: StoryHierarchy = []
        for chapter_entry in json.loads(row["hierarchy_json"]):
            chapter = Chapter(**self._known_fields(Chapter, chapter_entry["chapter"]))
            scene_data = []
            for scene_entry in chapter_entry["scenes"]:
                scene_data.append(
                    (
                        Scene(**self._known_fields(Scene, scene_entry["scene"])),
                        [
                            Shot(**self._known_fields(Shot, shot))
                            for shot in scene_entry["shots"]
                        ],
                    )
                )
            hierarchy.append((chapter, scene_data))
        return StoryRecord(graph=graph, hierarchy=hierarchy)

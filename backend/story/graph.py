"""Story graph builder backed by the canonical story repository."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Optional

from backend.story.models import Chapter, Scene, Shot, StoryGraph, StoryNode
from backend.story.repository import StoryHierarchy, StoryRepository


class StoryGraphEngine:
    """Builds story graphs while treating SQLite as the authority."""

    def __init__(self, repository: StoryRepository | None = None):
        self.repository = repository or StoryRepository()
        self.graphs: dict[str, StoryGraph] = {}
        self.graph_ids_by_novel: dict[str, str] = {}
        self.hierarchies_by_novel: dict[str, StoryHierarchy] = {}

    def _cache(self, graph: StoryGraph, hierarchy: StoryHierarchy) -> None:
        previous_id = self.graph_ids_by_novel.get(graph.novel_id)
        if previous_id and previous_id != graph.id:
            self.graphs.pop(previous_id, None)
        self.graphs[graph.id] = graph
        self.graph_ids_by_novel[graph.novel_id] = graph.id
        self.hierarchies_by_novel[graph.novel_id] = hierarchy

    def _load(self, novel_id: str) -> bool:
        record = self.repository.load_story(novel_id)
        if not record:
            return False
        self._cache(record.graph, record.hierarchy)
        return True

    def build_graph(
        self,
        novel_id: str,
        title: str,
        chapters: StoryHierarchy,
        *,
        persist: bool = True,
    ) -> StoryGraph:
        """Build a graph whose node IDs are the canonical domain IDs."""
        graph = StoryGraph(novel_id=novel_id, title=title)
        previous_chapter: Optional[str] = None
        previous_scene: Optional[str] = None

        for chapter, scene_data in chapters:
            chapter_node = StoryNode(
                id=chapter.id,
                novel_id=novel_id,
                node_type="chapter",
                data_id=chapter.id,
                title=f"第{chapter.number}章",
                summary=chapter.summary,
            )
            graph.nodes[chapter.id] = chapter_node
            if previous_chapter:
                graph.edges.append((previous_chapter, chapter.id))
            previous_chapter = chapter.id

            for scene, shots in scene_data:
                scene_node = StoryNode(
                    id=scene.id,
                    novel_id=novel_id,
                    node_type="scene",
                    data_id=scene.id,
                    parent_id=chapter.id,
                    title=f"场景{scene.number}",
                    summary=scene.summary,
                )
                graph.nodes[scene.id] = scene_node
                chapter_node.children.append(scene.id)
                if previous_scene:
                    graph.edges.append((previous_scene, scene.id))
                previous_scene = scene.id

                for shot in shots:
                    shot_node = StoryNode(
                        id=shot.id,
                        novel_id=novel_id,
                        node_type="shot",
                        data_id=shot.id,
                        parent_id=scene.id,
                        title=f"镜头{shot.index + 1}",
                        summary=shot.description[:100],
                    )
                    graph.nodes[shot.id] = shot_node
                    scene_node.children.append(shot.id)

        if persist and novel_id:
            self.repository.save_story(graph, chapters)
        self._cache(graph, chapters)
        return graph

    def get_graph_for_novel(self, novel_id: str) -> Optional[StoryGraph]:
        graph_id = self.graph_ids_by_novel.get(novel_id)
        graph = self.graphs.get(graph_id) if graph_id else None
        if graph:
            return graph
        if self._load(novel_id):
            return self.graphs.get(self.graph_ids_by_novel[novel_id])
        return None

    def get_hierarchy_for_novel(self, novel_id: str) -> Optional[StoryHierarchy]:
        hierarchy = self.hierarchies_by_novel.get(novel_id)
        if hierarchy is not None:
            return hierarchy
        if self._load(novel_id):
            return self.hierarchies_by_novel.get(novel_id)
        return None

    def update_shot(self, novel_id: str, shot_id: str, patch: dict) -> Optional[Shot]:
        """Persist one shot before publishing the replacement to the in-memory cache."""
        graph = self.get_graph_for_novel(novel_id)
        hierarchy = self.get_hierarchy_for_novel(novel_id)
        if not graph or hierarchy is None:
            return None

        updated: Shot | None = None
        next_hierarchy: StoryHierarchy = []
        for chapter, scene_data in hierarchy:
            next_scenes: list[tuple[Scene, list[Shot]]] = []
            for scene, shots in scene_data:
                next_shots: list[Shot] = []
                for shot in shots:
                    if shot.id == shot_id:
                        updated = replace(shot, **patch)
                        next_shots.append(updated)
                    else:
                        next_shots.append(shot)
                next_scenes.append((scene, next_shots))
            next_hierarchy.append((chapter, next_scenes))

        if updated is None:
            return None

        self.repository.save_story(graph, next_hierarchy)
        self._cache(graph, next_hierarchy)
        return updated

    def export_frontend_graph(self, novel_id: str) -> dict:
        graph = self.get_graph_for_novel(novel_id)
        hierarchy = self.get_hierarchy_for_novel(novel_id)
        if not graph or hierarchy is None:
            return {}

        indexes: dict[str, int] = {}
        data: dict[str, dict] = {}
        for chapter, scene_data in hierarchy:
            indexes[chapter.id] = max(chapter.number - 1, 0)
            data[chapter.id] = asdict(chapter)
            for scene, shots in scene_data:
                indexes[scene.id] = max(scene.number - 1, 0)
                data[scene.id] = asdict(scene)
                for shot in shots:
                    indexes[shot.id] = shot.index
                    data[shot.id] = asdict(shot)

        return {
            "id": graph.id,
            "novel_id": graph.novel_id,
            "title": graph.title,
            "nodes": [
                {
                    "id": node.id,
                    "type": node.node_type,
                    "label": node.title,
                    "index": indexes.get(node.data_id, 0),
                    "parent_id": node.parent_id or None,
                    "data": data.get(node.data_id, {}),
                }
                for node in graph.nodes.values()
            ],
            "edges": [
                {"source": source, "target": target, "edge_type": "sequence"}
                for source, target in graph.edges
            ],
        }

    def get_shots_for_novel(
        self, novel_id: str, chapter_index: Optional[int] = None
    ) -> list[dict]:
        hierarchy = self.get_hierarchy_for_novel(novel_id)
        if hierarchy is None:
            return []
        shots: list[dict] = []
        for index, (_chapter, scene_data) in enumerate(hierarchy):
            if chapter_index is not None and index != chapter_index:
                continue
            for _scene, scene_shots in scene_data:
                shots.extend(asdict(shot) for shot in scene_shots)
        return shots

    def get_sequential_shots(self, graph_id: str) -> list[str]:
        graph = self.graphs.get(graph_id)
        if not graph:
            return []
        shots_order: list[str] = []
        chapters = [node for node in graph.nodes.values() if node.node_type == "chapter"]
        for chapter in chapters:
            for scene_id in chapter.children:
                scene = graph.nodes.get(scene_id)
                if scene:
                    shots_order.extend(scene.children)
        return shots_order

    def get_shot_context(self, graph_id: str, shot_id: str) -> dict:
        graph = self.graphs.get(graph_id)
        if not graph:
            return {}
        shot = graph.nodes.get(shot_id)
        if not shot:
            return {}
        scene = graph.nodes.get(shot.parent_id) if shot.parent_id else None
        chapter = graph.nodes.get(scene.parent_id) if scene and scene.parent_id else None
        sibling_ids = scene.children if scene else []
        shot_position = sibling_ids.index(shot_id) if shot_id in sibling_ids else 0
        return {
            "shot": shot,
            "scene": scene,
            "chapter": chapter,
            "sibling_shots": sibling_ids,
            "preceding_shots": [graph.nodes[item] for item in sibling_ids[:shot_position]],
        }

    def export_graph(self, graph_id: str) -> dict:
        graph = self.graphs.get(graph_id)
        if not graph:
            return {}
        return {
            "id": graph.id,
            "novel_id": graph.novel_id,
            "title": graph.title,
            "nodes": {key: value.__dict__ for key, value in graph.nodes.items()},
            "edges": graph.edges,
        }

"""World service (Phase 13.1) — World Bible + Scene Bible + Locations + Environment Memory."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from backend.world.environment_memory import EnvironmentMemory
from backend.world.location import Location, LocationStore
from backend.world.scene_bible import SceneBible, SceneBibleStore
from backend.world.world_bible import WorldBible, WorldBibleStore


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class WorldService:
    def __init__(self, root: str | Path = "storage/world"):
        self.worlds = WorldBibleStore(root)
        self.scenes = SceneBibleStore(root)
        self.locations = LocationStore(root)
        self.environment = EnvironmentMemory(root)

    # ------------------------------------------------------------- worlds
    def create_world(self, project_id: str, name: str = "", **fields) -> WorldBible:
        world = WorldBible(id=_new_id("WLD"), project_id=project_id, name=name)
        for key, value in fields.items():
            if hasattr(world, key) and value is not None:
                setattr(world, key, value)
        return self.worlds.put(world)

    def get_world(self, world_id: str) -> Optional[WorldBible]:
        return self.worlds.get(world_id)

    def list_worlds(self, project_id: str | None = None) -> list[WorldBible]:
        if project_id:
            return self.worlds.by_project(project_id)
        return self.worlds.all()

    def update_world(self, world_id: str, **fields) -> WorldBible:
        world = self.worlds.get(world_id)
        if not world:
            raise KeyError(f"world not found: {world_id}")
        for key, value in fields.items():
            if hasattr(world, key) and value is not None:
                setattr(world, key, value)
        world.updated_at = __import__("datetime").datetime.now().isoformat(timespec="seconds")
        return self.worlds.put(world)

    # ------------------------------------------------------------- scenes
    def create_scene(self, project_id: str, world_id: str = "", name: str = "", **fields) -> SceneBible:
        scene = SceneBible(id=_new_id("SCN"), project_id=project_id, world_id=world_id, name=name)
        for key, value in fields.items():
            if hasattr(scene, key) and value is not None:
                setattr(scene, key, value)
        return self.scenes.put(scene)

    def get_scene(self, scene_id: str) -> Optional[SceneBible]:
        return self.scenes.get(scene_id)

    def list_scenes(self, project_id: str | None = None) -> list[SceneBible]:
        if project_id:
            return self.scenes.by_project(project_id)
        return self.scenes.all()

    def update_scene(self, scene_id: str, **fields) -> SceneBible:
        scene = self.scenes.get(scene_id)
        if not scene:
            raise KeyError(f"scene not found: {scene_id}")
        for key, value in fields.items():
            if hasattr(scene, key) and value is not None:
                setattr(scene, key, value)
        scene.updated_at = __import__("datetime").datetime.now().isoformat(timespec="seconds")
        return self.scenes.put(scene)

    # ------------------------------------------------------------- locations
    def create_location(self, project_id: str, world_id: str = "", name: str = "", **fields) -> Location:
        location = Location(id=_new_id("LOC"), project_id=project_id, world_id=world_id, name=name)
        for key, value in fields.items():
            if hasattr(location, key) and value is not None:
                setattr(location, key, value)
        return self.locations.put(location)

    def get_location(self, location_id: str) -> Optional[Location]:
        return self.locations.get(location_id)

    def list_locations(self, project_id: str | None = None) -> list[Location]:
        if project_id:
            return self.locations.by_project(project_id)
        return self.locations.all()

    # ------------------------------------------------------------- environment
    def note_environment(self, project_id: str, kind: str, content: str, source: str = "world_agent") -> dict:
        entry = {"kind": kind, "content": content, "source": source}
        self.environment.note(project_id, entry)
        return entry

    def environment_summary(self, project_id: str) -> dict:
        return self.environment.summary(project_id)

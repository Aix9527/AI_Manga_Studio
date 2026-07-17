"""Multi-database engine management for AI Manga Studio Pro."""

from backend.db.characters import init_characters_db, get_characters_session, Character
from backend.db.scenes import init_scenes_db, get_scenes_session, Scene
from backend.db.projects import init_projects_db, get_projects_session, Project, Chapter, Shot
from backend.db.tasks import init_tasks_db, get_tasks_session, Task
from backend.db.cache import init_cache_db, get_cache_session, Cache

__all__ = [
    "init_characters_db", "get_characters_session", "Character",
    "init_scenes_db", "get_scenes_session", "Scene",
    "init_projects_db", "get_projects_session", "Project", "Chapter", "Shot",
    "init_tasks_db", "get_tasks_session", "Task",
    "init_cache_db", "get_cache_session", "Cache",
]


def init_all_databases():
    """Initialize all five databases at once."""
    init_characters_db()
    init_scenes_db()
    init_projects_db()
    init_tasks_db()
    init_cache_db()

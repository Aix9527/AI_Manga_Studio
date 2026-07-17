"""Compatibility shim — re-exports from the new multi-database backend.db package.

Use ``from backend.database import get_session, Project, ...`` as before.
New code should prefer ``from backend.db import ...`` directly.
"""

from backend.db import (
    init_all_databases,
    get_characters_session,
    get_scenes_session,
    get_projects_session,
    get_tasks_session,
    get_cache_session,
    Character,
    Scene,
    Project,
    Chapter,
    Shot,
    Task,
    Cache,
)

# Backward-compatible aliases
init_database = init_all_databases


def get_session():
    """Return a projects session (most common use-case from old API)."""
    return get_projects_session()

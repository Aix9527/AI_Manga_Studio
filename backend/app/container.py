"""Application dependency injection container."""

from __future__ import annotations

from dataclasses import dataclass

from backend.modules.characters.public import CharactersModuleApi
from backend.modules.generation.public import GenerationModuleApi
from backend.modules.media.public import MediaModuleApi
from backend.modules.narrative.public import NarrativeModuleApi
from backend.modules.platform.public import PlatformModuleApi
from backend.modules.projects.public import ProjectsModuleApi
from backend.modules.storyboard.public import StoryboardModuleApi
from backend.modules.workflows.public import WorkflowsModuleApi


@dataclass(slots=True)
class ApplicationContainer:
    """Holds module-level public APIs, not individual repositories/handlers."""

    projects: ProjectsModuleApi
    narrative: NarrativeModuleApi
    characters: CharactersModuleApi
    storyboard: StoryboardModuleApi
    generation: GenerationModuleApi
    media: MediaModuleApi
    workflows: WorkflowsModuleApi
    platform: PlatformModuleApi

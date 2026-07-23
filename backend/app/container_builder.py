
"""Application container builder with full module wiring."""

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from backend.app.container import ApplicationContainer
from backend.modules.platform.public import PlatformModuleApi
from backend.modules.platform.infrastructure.settings import AppSettings
from backend.modules.platform.infrastructure.database import DatabaseManager
from backend.modules.projects.public import ProjectsModuleApi
from backend.modules.projects.infrastructure.repository import SqlAlchemyProjectRepository
from backend.modules.narrative.public import NarrativeModuleApi
from backend.modules.narrative.infrastructure.repository import SqlAlchemyNarrativeRepository
from backend.modules.characters.public import CharactersModuleApi
from backend.modules.characters.infrastructure.repository import SqlAlchemyCharacterRepository
from backend.modules.storyboard.public import StoryboardModuleApi
from backend.modules.storyboard.infrastructure.repository import SqlAlchemyStoryboardRepository
from backend.modules.media.public import MediaModuleApi
from backend.modules.media.infrastructure.repository import SqlAlchemyAssetRepository
from backend.modules.generation.public import GenerationModuleApi
from backend.modules.generation.infrastructure.repository import SqlAlchemyGenerationRepository
from backend.modules.generation.infrastructure.provider_registry import InMemoryProviderRegistry
from backend.modules.generation.infrastructure.adapters.fake.adapter import FakeImageProvider
from backend.modules.workflows.public import WorkflowsModuleApi
from backend.modules.workflows.infrastructure.repository import SqlAlchemyJobRepository
from backend.shared.ids import IdGenerator, Uuid7Generator
from backend.shared.time import Clock, SystemClock


async def build_container(
    settings: AppSettings,
    database_manager: DatabaseManager,
) -> ApplicationContainer:
    """Build the application container with all module dependencies wired."""

    session_factory: async_sessionmaker[AsyncSession] = database_manager.session_factory

    # Shared services
    id_generator: IdGenerator = Uuid7Generator()
    clock: Clock = SystemClock()

    # Repositories
    project_repo = SqlAlchemyProjectRepository(session_factory)
    narrative_repo = SqlAlchemyNarrativeRepository(session_factory)
    character_repo = SqlAlchemyCharacterRepository(session_factory)
    storyboard_repo = SqlAlchemyStoryboardRepository(session_factory)
    asset_repo = SqlAlchemyAssetRepository(session_factory)
    generation_repo = SqlAlchemyGenerationRepository(session_factory)
    job_repo = SqlAlchemyJobRepository(session_factory)

    # Provider Registry
    provider_registry = InMemoryProviderRegistry()
    fake_provider = FakeImageProvider()
    provider_registry.register("fake-image", fake_provider)

    # Module APIs
    platform = PlatformModuleApi(
        _database=database_manager,
        _settings=settings,
        _session_factory=session_factory,
    )
    projects = ProjectsModuleApi(
        project_repo=project_repo,
        id_generator=id_generator,
        clock=clock,
    )
    narrative = NarrativeModuleApi(
        narrative_repo=narrative_repo,
        id_generator=id_generator,
        clock=clock,
    )
    characters = CharactersModuleApi(
        character_repo=character_repo,
        id_generator=id_generator,
        clock=clock,
    )
    storyboard = StoryboardModuleApi(
        storyboard_repo=storyboard_repo,
        character_repo=character_repo,
        id_generator=id_generator,
        clock=clock,
    )
    media = MediaModuleApi(
        asset_repo=asset_repo,
        id_generator=id_generator,
        clock=clock,
    )
    generation = GenerationModuleApi(
        generation_repo=generation_repo,
        job_repo=job_repo,
        provider_registry=provider_registry,
        id_generator=id_generator,
        clock=clock,
    )
    workflows = WorkflowsModuleApi(
        job_repo=job_repo,
        id_generator=id_generator,
        clock=clock,
    )

    return ApplicationContainer(
        platform=platform,
        projects=projects,
        narrative=narrative,
        characters=characters,
        storyboard=storyboard,
        media=media,
        generation=generation,
        workflows=workflows,
        settings=settings,
    )

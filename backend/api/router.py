from fastapi import APIRouter

from .project_api import router as project_router
from .shot_api import router as shot_router
from .asset_api import router as asset_router
from .production_api import router as production_router
from .event_api import router as event_router
from .workspace_api import router as workspace_router
from .task_api import router as task_router
from .production_plan_api import router as plan_router
from .review_api import router as review_router
from .creative_api import router as creative_router
from .narrative_api import router as narrative_router
from .change_api import router as change_router
from .canvas_api import router as canvas_router
from .storyboard_api import router as storyboard_router
from .runtime_api import router as runtime_router
from .agent_api import router as agent_router
from .orchestration_api import router as orchestration_router
from .quality_api import router as quality_router
from .media_api import router as media_router
from .export_api import router as export_router
from .longform_api import router as longform_router
from .longform_scheduler_api import router as longform_scheduler_router
from .longform_graph_api import router as longform_graph_router
from .validation_api import router as validation_router
from .release_api import router as release_router
from .voice_api import router as voice_router
from .release_voice_api import router as release_voice_router
from .h3_prompt_api import router as h3_prompt_router
from .h3_prompt_v2_api import router as h3_prompt_v2_router
from .h3_director_api import router as h3_director_router
from backend.novel_video.routes import router as novel_video_router


api_router = APIRouter()

api_router.include_router(
    novel_video_router,
    prefix="/novel-video",
    tags=["novel-video"],
)


api_router.include_router(
    project_router,
    prefix="/projects",
    tags=["projects"]
)


api_router.include_router(
    shot_router,
    prefix="/shots",
    tags=["shots"]
)


api_router.include_router(
    asset_router,
    prefix="/assets",
    tags=["assets"]
)


api_router.include_router(
    production_router,
    prefix="/production",
    tags=["production"]
)


api_router.include_router(
    event_router,
    prefix="/events",
    tags=["events"]
)


api_router.include_router(
    workspace_router,
    prefix="/workspace",
    tags=["workspace"]
)


api_router.include_router(
    task_router,
    prefix="/tasks",
    tags=["tasks"]
)


api_router.include_router(
    plan_router,
    prefix="/production",
    tags=["production-plan"]
)


api_router.include_router(
    review_router,
    prefix="/review",
    tags=["review"]
)


api_router.include_router(
    creative_router,
    prefix="/creative",
    tags=["creative"]
)


api_router.include_router(
    narrative_router,
    prefix="/narrative",
    tags=["narrative"]
)


api_router.include_router(
    change_router,
    prefix="/changes",
    tags=["changes"]
)


api_router.include_router(
    canvas_router,
    prefix="/canvas",
    tags=["canvas"]
)


api_router.include_router(
    storyboard_router,
    prefix="/storyboard",
    tags=["storyboard"]
)


api_router.include_router(
    runtime_router,
    prefix="/runtime",
    tags=["runtime"]
)


api_router.include_router(
    agent_router,
    prefix="/agent",
    tags=["agent"]
)


api_router.include_router(
    orchestration_router,
    prefix="/orchestration",
    tags=["orchestration"]
)


api_router.include_router(
    quality_router,
    prefix="/quality",
    tags=["quality"]
)


api_router.include_router(
    media_router,
    prefix="/media",
    tags=["media"]
)


api_router.include_router(
    export_router,
    prefix="/export",
    tags=["export"]
)


api_router.include_router(
    longform_router,
    prefix="/longform",
    tags=["longform"]
)


api_router.include_router(
    longform_scheduler_router,
    prefix="/longform",
    tags=["longform"]
)


api_router.include_router(
    longform_graph_router,
    prefix="/longform",
    tags=["longform"]
)


api_router.include_router(
    validation_router,
    prefix="/validation",
    tags=["validation"]
)


api_router.include_router(
    release_router,
    prefix="/release",
    tags=["release"]
)


api_router.include_router(
    release_voice_router,
    prefix="/release",
    tags=["release-voice"]
)


api_router.include_router(
    h3_prompt_router,
    prefix="/h3",
    tags=["h3-prompts"]
)


api_router.include_router(
    h3_prompt_v2_router,
    prefix="/h3/prompts",
    tags=["h3-prompt-intelligence"]
)


api_router.include_router(
    h3_director_router,
    prefix="/h3/director",
    tags=["h3-director"]
)


api_router.include_router(
    voice_router,
    prefix="/voice",
    tags=["voice"]
)

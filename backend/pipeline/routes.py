"""Pipeline API routes for FastAPI."""

from fastapi import APIRouter, Query, Request, HTTPException
from pydantic import BaseModel

from backend.orchestration.schemas import TaskCreate, TaskInfo
from backend.pipeline.orchestrator import PipelineOrchestrator
from backend.pipeline.schemas import PipelineRequest

router = APIRouter(prefix="/api/pipeline", tags=["Pipeline"])
orchestrator = PipelineOrchestrator()


class PipelineRunRequest(BaseModel):
    text: str
    title: str = ""
    novel_id: str = ""


class PipelineRunResponse(BaseModel):
    status: str
    characters_found: int
    shots_planned: int
    prompts_compiled: int
    duration_ms: float
    stages: dict


@router.post("/run", response_model=PipelineRunResponse)
def run_pipeline(req: PipelineRunRequest):
    """Run the full v0.5 pipeline: Text → Characters → Story → Prompts."""
    pipeline_req = PipelineRequest(
        text=req.text,
        title=req.title,
        novel_id=req.novel_id,
    )
    response = orchestrator.run(pipeline_req)

    stages = {s.stage.value: s.status for s in response.stages}
    return PipelineRunResponse(
        status=response.status,
        characters_found=response.characters_found,
        shots_planned=response.shots_planned,
        prompts_compiled=response.prompts_compiled,
        duration_ms=response.total_duration_ms,
        stages=stages,
    )


@router.post("/compile/shot")
def compile_single_shot(shot_data: dict, character_ids: list[str] = Query(default=[])):
    """Compile a prompt for a single shot."""
    from backend.story.models import Shot
    from backend.agents.director import DirectorAgent

    shot = Shot(
        id=shot_data.get("id", ""),
        scene_id=shot_data.get("scene_id", ""),
        index=shot_data.get("index", 0),
        shot_type=shot_data.get("shot_type", "medium"),
        camera_angle=shot_data.get("camera_angle", "eye-level"),
        description=shot_data.get("description", ""),
        action=shot_data.get("action", ""),
        dialogue=shot_data.get("dialogue", ""),
        emotion=shot_data.get("emotion", "neutral"),
        character_ids=character_ids or [],
    )

    director = DirectorAgent()
    brief = director.plan_shot(shot)

    contexts = {}
    for cid in (character_ids or []):
        ctx = orchestrator.character_agent.get_context(cid, shot.id, shot.emotion)
        contexts[cid] = ctx

    compiled = orchestrator.prompt_compiler.compile_shot(brief, contexts)
    return {
        "positive_prompt": compiled.positive_prompt,
        "negative_prompt": compiled.negative_prompt,
        "parameters": compiled.parameters,
    }


@router.post("/director/plan")
def director_plan(req: PipelineRunRequest):
    """Phase 10.2-A: novel snippet -> Director v2 directives JSON (shot_id/camera/lighting/emotion/continuity)."""
    from backend.director.director_bridge import DirectorBridge
    bridge = DirectorBridge()
    result = bridge.plan_text(req.text, req.novel_id)
    return {
        "novel_id": result["novel_id"],
        "chapters": result["chapters"],
        "scenes": result["scenes"],
        "shots_total": result["shots_total"],
        "directives": result["directives"],
        "sections": result["sections"],
    }


@router.get("/stats")
def pipeline_stats():
    """Get pipeline statistics."""
    return {
        "version": "0.5.0",
        "phases": {
            "phase_1_character_memory": True,
            "phase_2_story_graph": True,
            "phase_3_director_agent": True,
            "phase_3b_director_v2": True,   # Phase 10.2-A
            "phase_4_prompt_compiler": True,
        },
        "modules": {
            "characters": ["models", "repository", "extractor", "embedding", "memory", "service", "routes", "identity"],
            "story": ["models", "parser", "graph", "timeline", "routes"],
            "agents": ["director", "director_v2", "writer", "character", "critic"],
            "director": ["director_bridge"],
            "story": ["models", "parser", "graph", "timeline", "section_memory", "routes"],
            "video": ["chain_manager", "runtime", "identity_gate", "quality_gate", "composer"],
            "prompt_compiler": ["compiler", "templates"],
        },
    }


# ---------------------------------------------------------------------------
# Phase 10.3-B: Long Video Chain Runtime
# ---------------------------------------------------------------------------


class ChainPlanRequest(BaseModel):
    project_id: str = "default"
    shots: list[dict] = []


class ChainRunRequest(ChainPlanRequest):
    resume: bool = True
    comfy_url: str = ""


@router.post("/chain/plan")
def chain_plan(req: ChainPlanRequest):
    """Phase 10.3-B: plan chain modes (keyframe/last_frame/reset) without running."""
    from backend.video.runtime import ChainRuntime

    return ChainRuntime(project_id=req.project_id).plan(req.shots)


@router.get("/chain/status")
def chain_status(project_id: str = "default"):
    """Phase 10.3-B: checkpoint manifest status (completed/current/resume_from)."""
    from backend.video.runtime import ChainRuntime

    return ChainRuntime(project_id=project_id).status()


@router.post("/chain/run")
async def chain_run(req: ChainRunRequest):
    """Phase 10.3-B: run the chain through the Wan2.2 ComfyUI provider.

    Generates videos in order, inherits last frames across same-space shots,
    persists a checkpoint manifest per shot, and resumes from the manifest
    when ``resume=true`` (skips completed shots).
    """
    from backend.production.comfy_adapter import ComfyUIAdapter
    from backend.production.comfy_video import WanVideoProvider
    from backend.production.workflow_registry import select_wan_video_workflow
    from backend.production.workflow_templates import WorkflowTemplate
    from backend.video.runtime import ChainRuntime

    runtime = ChainRuntime(project_id=req.project_id)
    comfy = ComfyUIAdapter(base_url=req.comfy_url or "http://127.0.0.1:8188")
    spec = select_wan_video_workflow(
        has_end_frame=any(s.get("end_frame_path") for s in req.shots)
    )
    provider = WanVideoProvider(
        adapter=comfy,
        template=WorkflowTemplate.load(spec.path),
    )
    return await runtime.run(req.shots, provider, resume=req.resume)


# ---------------------------------------------------------------------------
# Phase 10.5-C: Identity Verification Gate
# ---------------------------------------------------------------------------


class IdentityVerifyRequest(BaseModel):
    video_path: str
    character_references: dict = {}   # {character_id: [embedding]}
    presence_threshold: float = 0.6
    sample_frames: int = 5


@router.post("/identity/verify")
def identity_verify(req: IdentityVerifyRequest):
    """Phase 10.5-C: post-generation identity gate over a generated video.

    Samples frames from the video and runs the multi-character identity lock.
    Returns per-character presence ratios + overall verdict.
    """
    from backend.characters.identity import IdentityEngine
    from backend.video.identity_gate import IdentityVerifier

    verifier = IdentityVerifier(
        engine=IdentityEngine(),
        presence_threshold=req.presence_threshold,
        sample_frames=req.sample_frames,
    )
    report = verifier.verify_video(req.video_path, req.character_references)
    return report.__dict__


# ---------------------------------------------------------------------------
# Phase 10.7-A: Production task queue (Queue -> Worker -> ChainRuntime)
# ---------------------------------------------------------------------------


@router.post("/tasks")
def enqueue_task(req: TaskCreate, request: Request):
    """Phase 10.7-A: enqueue a production task for the OrchestratorWorker.

    ``video_chain`` tasks carry ``payload.shots`` and are routed through
    ``ChainRuntime`` by the worker; status is written back as
    ``{task_id, shot_id, stage, progress, gpu_time, checkpoint}``.
    """
    queue = getattr(request.app.state, "task_queue", None)
    if queue is None:
        raise HTTPException(status_code=503, detail="task queue not configured")
    task = queue.enqueue(
        req.task_type.value,
        req.payload,
        project_id=req.project_id,
        priority=req.priority,
        retry_policy=req.retry_policy.model_dump(),
        checkpoint_id=req.checkpoint_id,
    )
    return TaskInfo(**task.to_dict())


@router.get("/tasks/{task_id}")
def get_task(task_id: str, request: Request):
    """Phase 10.7-A: task status (StudioDashboard writeback view)."""
    queue = getattr(request.app.state, "task_queue", None)
    if queue is None:
        raise HTTPException(status_code=503, detail="task queue not configured")
    task = queue.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task {task_id} not found")
    return TaskInfo(**task.to_dict())


@router.get("/tasks")
def list_tasks(request: Request, status: str | None = None):
    """Phase 10.7-A: list tasks, optionally filtered by status."""
    queue = getattr(request.app.state, "task_queue", None)
    if queue is None:
        raise HTTPException(status_code=503, detail="task queue not configured")
    items = [TaskInfo(**t.to_dict()) for t in queue.list(status=status)]
    return {"items": items, "total": len(items)}

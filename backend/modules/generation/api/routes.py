
"""Generation API routes."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.app.container import ApplicationContainer

router = APIRouter()


class SubmitGenerationRequest(BaseModel):
    project_id: str
    shot_id: str
    purpose: str = "image_generation"
    prompt: str = ""
    parameters: dict = {}


@router.post("/generation/submit")
async def submit_generation(request: Request, body: SubmitGenerationRequest):
    container: ApplicationContainer = request.app.state.container
    gen_request = await container.generation.submit(body.project_id, body.shot_id, body.purpose, body.prompt, body.parameters)
    return {
        "requestId": gen_request.request_id,
        "status": str(gen_request.status),
        "purpose": gen_request.purpose,
    }


@router.get("/generation/projects/{project_id}/requests")
async def list_requests(project_id: str, request: Request):
    container: ApplicationContainer = request.app.state.container
    reqs = await container.generation._generation_repo.list_requests_by_project(project_id)
    return [{"requestId": r.request_id, "purpose": r.purpose, "status": str(r.status)} for r in reqs]


@router.get("/generation/requests/{request_id}")
async def get_request(request_id: str, request_obj: Request):
    container: ApplicationContainer = request_obj.app.state.container
    req = await container.generation._generation_repo.get_request(request_id)
    return {"requestId": req.request_id, "purpose": req.purpose, "status": str(req.status),
            "compiledPrompt": req.compiled_prompt, "snapshotHash": req.snapshot_hash}

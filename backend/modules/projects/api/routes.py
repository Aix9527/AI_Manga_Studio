
"""Project REST API routes."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.app.container import ApplicationContainer
from backend.modules.projects.application.commands import CreateProjectCommand
from backend.shared.infrastructure.database.pagination import PageRequest

router = APIRouter()


class CreateProjectRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""


class ProjectResponse(BaseModel):
    projectId: str
    title: str
    description: str
    status: str
    createdAt: str
    updatedAt: str
    revision: int


@router.post("/projects", response_model=ProjectResponse)
async def create_project(request: Request, body: CreateProjectRequest) -> ProjectResponse:
    container: ApplicationContainer = request.app.state.container
    handler = container.projects._create_project_handler
    project = await handler.handle(CreateProjectCommand(title=body.title, description=body.description))
    return ProjectResponse(
        projectId=project.project_id,
        title=project.title,
        description=project.description,
        status=project.status,
        createdAt=project.created_at.isoformat(),
        updatedAt=project.updated_at.isoformat(),
        revision=project.revision,
    )


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(request: Request, limit: int = 50) -> list[ProjectResponse]:
    container: ApplicationContainer = request.app.state.container
    result = await container.projects._project_repo.list_recent(PageRequest(limit=limit))
    return [
        ProjectResponse(
            projectId=p.project_id,
            title=p.title,
            description=p.description,
            status=p.status,
            createdAt=p.created_at.isoformat(),
            updatedAt=p.updated_at.isoformat(),
            revision=p.revision,
        )
        for p in result.items
    ]


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, request: Request) -> ProjectResponse:
    container: ApplicationContainer = request.app.state.container
    project = await container.projects._project_repo.get(project_id)
    return ProjectResponse(
        projectId=project.project_id,
        title=project.title,
        description=project.description,
        status=project.status,
        createdAt=project.created_at.isoformat(),
        updatedAt=project.updated_at.isoformat(),
        revision=project.revision,
    )

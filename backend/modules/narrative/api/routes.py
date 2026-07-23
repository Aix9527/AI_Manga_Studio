
"""Narrative API routes."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.app.container import ApplicationContainer

router = APIRouter()


class ImportStoryRequest(BaseModel):
    project_id: str
    title: str = Field(min_length=1, max_length=300)
    content: str


class StoryResponse(BaseModel):
    storyId: str
    projectId: str
    title: str
    content: str
    createdAt: str


@router.post("/narrative/stories", response_model=StoryResponse)
async def import_story(request: Request, body: ImportStoryRequest) -> StoryResponse:
    container: ApplicationContainer = request.app.state.container
    story = await container.narrative.import_story(body.project_id, body.title, body.content)
    return StoryResponse(storyId=story.story_id, projectId=story.project_id, title=story.title,
                         content=story.content, createdAt=story.created_at.isoformat())


@router.get("/narrative/projects/{project_id}/stories")
async def list_stories(project_id: str, request: Request):
    container: ApplicationContainer = request.app.state.container
    stories = await container.narrative._narrative_repo.list_stories_by_project(project_id)
    return [{"storyId": s.story_id, "projectId": s.project_id, "title": s.title, "contentPreview": s.content[:200], "createdAt": s.created_at.isoformat()} for s in stories]

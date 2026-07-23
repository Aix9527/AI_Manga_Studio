
"""Characters API routes."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.app.container import ApplicationContainer

router = APIRouter()


class CreateCharacterRequest(BaseModel):
    project_id: str
    name: str = Field(min_length=1, max_length=200)
    role: str = ""
    personality: str = ""


class CharacterResponse(BaseModel):
    characterId: str
    projectId: str
    name: str
    role: str
    personality: str
    isActive: bool
    createdAt: str


@router.post("/characters", response_model=CharacterResponse)
async def create_character(request: Request, body: CreateCharacterRequest) -> CharacterResponse:
    container: ApplicationContainer = request.app.state.container
    char = await container.characters.create(body.project_id, body.name, body.role, body.personality)
    return CharacterResponse(characterId=char.character_id, projectId=char.project_id,
                             name=char.name, role=char.role, personality=char.personality,
                             isActive=char.is_active, createdAt=char.created_at.isoformat())


@router.get("/characters/{project_id}", response_model=list[CharacterResponse])
async def list_characters(project_id: str, request: Request) -> list[CharacterResponse]:
    container: ApplicationContainer = request.app.state.container
    chars = await container.characters._character_repo.list_by_project(project_id)
    return [CharacterResponse(characterId=c.character_id, projectId=c.project_id,
                               name=c.name, role=c.role, personality=c.personality,
                               isActive=c.is_active, createdAt=c.created_at.isoformat()) for c in chars]

from fastapi import APIRouter, HTTPException, Query, Request, status

from backend.projects.schemas import ProjectCreate, SourceCreate


router = APIRouter(prefix='/api/projects', tags=['Projects'])


def _service(request: Request):
    return request.app.state.project_service


@router.get('')
def list_projects(
    request: Request,
    include_archived: bool = Query(default=False),
):
    items = _service(request).list(include_archived)
    return {'total': len(items), 'projects': items}


@router.post('', status_code=status.HTTP_201_CREATED)
def create_project(command: ProjectCreate, request: Request):
    return _service(request).create(command)


@router.get('/{project_id}')
def get_project(project_id: str, request: Request):
    project = _service(request).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail='Project not found')
    return project


@router.post(
    '/{project_id}/sources',
    status_code=status.HTTP_201_CREATED,
)
def add_source(project_id: str, command: SourceCreate, request: Request):
    try:
        return _service(request).add_source(project_id, command)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete('/{project_id}')
def archive_project(project_id: str, request: Request):
    try:
        return _service(request).archive(project_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

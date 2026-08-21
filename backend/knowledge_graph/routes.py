"""Knowledge Graph API（GPT Priority 2，跨项目分析 / 检索 / 智能推荐）。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.knowledge_graph.service import KnowledgeGraphService

router = APIRouter(prefix="/api/knowledge-graph", tags=["knowledge-graph"])

_service = KnowledgeGraphService()


def _http(exception: Exception) -> HTTPException:
    if isinstance(exception, KeyError):
        return HTTPException(status_code=404, detail=str(exception))
    if isinstance(exception, ValueError):
        return HTTPException(status_code=422, detail=str(exception))
    return HTTPException(status_code=500, detail=str(exception))


class IngestBody(BaseModel):
    actor: str = ""
    reason: str = ""
    clear: bool = True


@router.get("/stats")
def stats():
    return _service.stats()


@router.post("/ingest")
def ingest(body: IngestBody):
    try:
        return _service.ingest(clear=body.clear)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/nodes")
def nodes(node_type: str | None = None, project_id: str | None = None,
          q: str | None = None, limit: int = 50):
    try:
        return {"nodes": _service.nodes(node_type=node_type, project_id=project_id,
                                        q=q, limit=limit)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/nodes/{node_id}")
def get_node(node_id: str):
    try:
        return _service.get_node(node_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/neighbors/{node_id}")
def neighbors(node_id: str, edge_type: str | None = None, depth: int = 1, limit: int = 50):
    try:
        return _service.neighbors(node_id, edge_type=edge_type, depth=depth, limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/paths")
def paths(from_id: str, to_id: str, limit: int = 3):
    try:
        return _service.paths(from_id, to_id, limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/search")
def search(q: str, limit: int = 20):
    try:
        return _service.search(q, limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/recommend/{node_id}")
def recommend(node_id: str, limit: int = 5):
    try:
        return _service.recommend(node_id, limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)

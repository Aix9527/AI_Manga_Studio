"""Director Council API (Phase 12.8, GPT approved).

Endpoints:
- GET /api/director/council/run          council over arena report
- GET /api/director/council/candidates   council -> policy candidates
- GET /api/director/council/agents       five council agents + weights
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from backend.director.arena_runner import RealArenaRunner
from backend.director.council import DirectorCouncil

router = APIRouter(prefix="/api/director/council", tags=["director-council"])

_council: DirectorCouncil | None = None


def get_council() -> DirectorCouncil:
    global _council
    if _council is None:
        _council = DirectorCouncil()
    return _council


@router.get("/agents")
def agents():
    council = get_council()
    return {
        "agents": [
            {"name": a.name, "weight": a.weight} for a in council.agents
        ],
        "total_weight": round(sum(a.weight for a in council.agents), 2),
    }


@router.get("/run")
def run(limit: int = 100):
    report = RealArenaRunner(limit=limit).run()
    summary = get_council().run(report)
    return summary.to_dict()


@router.get("/candidates")
def candidates(limit: int = 200):
    report = RealArenaRunner(limit=limit).run()
    council = get_council()
    summary = council.run(report)
    return {
        "count": len(council.to_candidates(summary, report)),
        "candidates": [c.to_dict() for c in council.to_candidates(summary, report)],
        "agents": council.agent_names(),
    }

"""Real Director Arena Runner API (Phase 12.7-B, GPT spec).

Endpoints:
- GET  /api/director/arena-runner/run        run the arena (hermetic default)
- GET  /api/director/arena-runner/proposal   arena scores -> router candidates
- GET  /api/director/arena-runner/registry   provider registry summary

``real=true`` enables live LLM calls when API keys are present; the default
stays deterministic (simulated stand-ins) for dry-runs and tests.
"""

from __future__ import annotations

from typing import Optional

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.director.arena_runner import RealArenaRunner
from backend.director.evolution import ControlledEvolution
from backend.director.evolution.rollback import PolicyVersionStore
from backend.director.memory import PolicyMemory
from backend.director.policy_router import DEFAULT_POLICY_PATH
from backend.director.providers.registry import DirectorProviderRegistry

router = APIRouter(prefix="/api/director/arena-runner", tags=["arena-runner"])

_runners: dict[bool, RealArenaRunner] = {}


def _runner(real: bool, limit: int | None = None) -> RealArenaRunner:
    key = bool(real)
    if key not in _runners:
        _runners[key] = RealArenaRunner(real=real)
    return _runners[key]


@router.get("/run")
def run(real: bool = False, limit: Optional[int] = None):
    runner = _runner(real, limit)
    return runner.run()


@router.get("/proposal")
def proposal(real: bool = False, limit: int = 40, source: str = "mock"):
    runner = _runner(real, limit)
    policy_path = Path("storage/director_evolution_mock/policy.yaml")
    memory = PolicyMemory(Path("storage/director_evolution_mock/memory"))
    evolution = ControlledEvolution(
        memory, policy_path=policy_path,
        versions_dir=Path("storage/director_evolution_mock/versions"),
    )
    return runner.propose(evolution)


@router.get("/registry")
def registry():
    reg = DirectorProviderRegistry()
    return reg.summary()

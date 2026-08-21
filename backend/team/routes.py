"""Team Collaboration API (Phase 13.5-C, GPT 批准 API 清单).

所有写操作要求 actor + reason；关键操作（升级处理 / 最终成片锁定）要求
approval_id（人工审批门）。复用 TaskQueue（task_id 外键），新建队列 0。

路由顺序：静态路径（/stats、/assignments…）必须先于 /{project_id} 声明，
避免路径参数捕获。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.team.service import TeamService

router = APIRouter(prefix="/api/team", tags=["team-collaboration"])

_service = TeamService()


def _http(exception: Exception) -> HTTPException:
    if isinstance(exception, KeyError):
        return HTTPException(status_code=404, detail=str(exception))
    if isinstance(exception, ValueError):
        return HTTPException(status_code=422, detail=str(exception))
    return HTTPException(status_code=500, detail=str(exception))


# ------------------------------------------------------------- write bodies
class WriteBody(BaseModel):
    actor: str = ""
    reason: str = ""


class CreateTeamBody(WriteBody):
    project_id: str = ""
    name: str = ""
    season_id: str = ""
    members: list = []
    role_bindings: dict = {}


class AssignBody(WriteBody):
    stage: str = "planning"
    role: str = "Producer"
    assignee_type: str = "agent"
    assignee_id: str = ""
    input_artifacts: list = []
    dependencies: list = []
    task_id: str = ""
    checkpoint_id: str = ""
    max_attempts: int | None = None
    deadline: str = ""


class ReviewBody(WriteBody):
    reviewer_role: str = "Reviewer"
    reviewer_id: str = ""
    verdict: str = "approve"
    rule_results: dict = {}
    evidence: dict = {}
    comments: str = ""
    next_stage: str = ""
    approval_id: str = ""


class ReworkBody(WriteBody):
    issue_category: str = ""
    evidence: dict = {}


class EscalateBody(WriteBody):
    decision: str = "escalate"
    approval_id: str = ""


class ApprovalWriteBody(WriteBody):
    approval_id: str = ""


# ------------------------------------------------------------- team
@router.get("/stats")
def stats():
    return _service.stats()


@router.post("")
def create_team(body: CreateTeamBody):
    try:
        if not body.project_id:
            raise HTTPException(status_code=422, detail="project_id required")
        return _service.create_team(
            project_id=body.project_id,
            name=body.name,
            season_id=body.season_id,
            members=body.members,
            role_bindings=body.role_bindings,
            actor=body.actor,
            reason=body.reason,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


# ------------------------------------------------------------- assignments
@router.get("/assignments")
def list_assignments(project_id: str | None = None, status: str | None = None,
                     role: str | None = None, episode_id: str | None = None):
    try:
        return {"assignments": _service.assignments(
            project_id=project_id, status=status, role=role, episode_id=episode_id,
        )}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/assignments/{assignment_id}")
def get_assignment(assignment_id: str):
    try:
        return _service.get_assignment(assignment_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/assignments/{assignment_id}/start")
def start(assignment_id: str, body: WriteBody):
    try:
        return _service.start(assignment_id, actor=body.actor, reason=body.reason)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/assignments/{assignment_id}/review")
def review(assignment_id: str, body: ReviewBody):
    try:
        return _service.review(
            assignment_id=assignment_id,
            reviewer_role=body.reviewer_role,
            reviewer_id=body.reviewer_id,
            verdict=body.verdict,
            rule_results=body.rule_results,
            evidence=body.evidence,
            comments=body.comments,
            next_stage=body.next_stage,
            actor=body.actor,
            reason=body.reason,
            approval_id=body.approval_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/assignments/{assignment_id}/rework")
def rework(assignment_id: str, body: ReworkBody):
    try:
        return _service.rework(
            assignment_id=assignment_id,
            issue_category=body.issue_category,
            evidence=body.evidence,
            actor=body.actor,
            reason=body.reason,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/assignments/{assignment_id}/escalate")
def escalate(assignment_id: str, body: EscalateBody):
    try:
        return _service.escalate(
            assignment_id=assignment_id,
            decision=body.decision,
            approval_id=body.approval_id,
            actor=body.actor,
            reason=body.reason,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


# 状态机补充端点（blocked / failed / done 完整可达）
@router.post("/assignments/{assignment_id}/block")
def block(assignment_id: str, body: WriteBody):
    try:
        return _service.block(assignment_id, actor=body.actor, reason=body.reason)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/assignments/{assignment_id}/unblock")
def unblock(assignment_id: str, body: WriteBody):
    try:
        return _service.unblock(assignment_id, actor=body.actor, reason=body.reason)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/assignments/{assignment_id}/fail")
def fail(assignment_id: str, body: WriteBody):
    try:
        return _service.fail(assignment_id, actor=body.actor, reason=body.reason)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/assignments/{assignment_id}/complete")
def complete(assignment_id: str, body: ApprovalWriteBody):
    try:
        return _service.complete(
            assignment_id, actor=body.actor, reason=body.reason,
            approval_id=body.approval_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


# ------------------------------------------------------------- project views
@router.get("/{project_id}")
def get_team(project_id: str):
    try:
        return _service.get_team(project_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/{project_id}/episodes/{episode_id}/assign")
def assign(project_id: str, episode_id: str, body: AssignBody):
    try:
        return _service.assign(
            project_id=project_id,
            episode_id=episode_id,
            stage=body.stage,
            role=body.role,
            assignee_type=body.assignee_type,
            assignee_id=body.assignee_id,
            input_artifacts=body.input_artifacts,
            dependencies=body.dependencies,
            task_id=body.task_id,
            checkpoint_id=body.checkpoint_id,
            max_attempts=body.max_attempts,
            deadline=body.deadline,
            actor=body.actor,
            reason=body.reason,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/{project_id}/flow")
def flow(project_id: str):
    try:
        return _service.flow(project_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/{project_id}/episodes/{episode_id}/artifacts")
def artifacts(project_id: str, episode_id: str):
    try:
        return _service.artifacts(project_id=project_id, episode_id=episode_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/{project_id}/audit")
def audit(project_id: str):
    try:
        return _service.audit(project_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)

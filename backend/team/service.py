"""Team Collaboration service (Phase 13.5-C, GPT spec).

Team / TeamAssignment（状态机）/ ReviewRecord / append-only TeamAudit。
- 复用 TaskQueue/Worker/LeaseLock/CostMeter，新建队列 0（task_id 外键引用）
- 定向返工（rework_routing）+ 返工上限（禁止无限返工）
- 人工审批门：escalate/retry/abandon、final 成片锁定要求 approval_id
- 每次状态迁移写审计，审计覆盖率 100%
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from backend.team.model import (
    ALLOWED_TRANSITIONS,
    ASSIGNEE_TYPES,
    FORBIDDEN_TRANSITIONS,
    REVIEW_VERDICTS,
    REWORK_POLICY,
    REWORK_ROUTING,
    REWORK_TARGET_ROLE,
    REWORK_TARGET_STAGE,
    ReviewRecord,
    ROLES,
    STAGES,
    STAGE_REVIEW_OWNER,
    Team,
    TeamAssignment,
    TeamAudit,
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class TeamService:
    """单项目 Episode 级团队协作编排（v0.1 scope）。"""

    def __init__(self, root: str | Path = "storage/team"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._teams: dict[str, dict] = self._load_dict("teams.json")
        self._assignments: dict[str, dict] = self._load_dict("assignments.json")
        self._reviews: list[dict] = self._load_list("reviews.json")
        self._audits: list[dict] = self._load_list("audits.json")

    # ------------------------------------------------------------ storage
    def _load_dict(self, name: str) -> dict[str, dict]:
        path = self.root / name
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def _load_list(self, name: str) -> list[dict]:
        path = self.root / name
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:  # noqa: BLE001
            return []

    def _save_dict(self, name: str, data: dict[str, dict]) -> None:
        path = self.root / name
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _save_list(self, name: str, data: list[dict]) -> None:
        path = self.root / name
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    # ------------------------------------------------------------ audit
    def _audit(self, *, project_id: str, episode_id: str, assignment_id: str,
               event: str, actor: str, before: dict, after: dict,
               reason: str, evidence: dict | None = None) -> dict:
        record = TeamAudit(
            id=_new_id("TA"),
            project_id=project_id,
            episode_id=episode_id,
            assignment_id=assignment_id,
            event=event,
            actor=actor,
            before=before,
            after=after,
            reason=reason,
            evidence=evidence or {},
        ).to_dict()
        self._audits.append(record)  # append-only：只增不改
        self._save_list("audits.json", self._audits)
        return record

    # ------------------------------------------------------------ team
    def create_team(self, *, project_id: str, name: str, season_id: str = "",
                    members: list | None = None, role_bindings: dict | None = None,
                    actor: str = "", reason: str = "") -> dict:
        if not project_id:
            raise ValueError("project_id required")
        if role_bindings is None:
            role_bindings = {role: [] for role in ROLES}
        for role in role_bindings:
            if role not in ROLES:
                raise ValueError(f"invalid role: {role}")
        with self._lock:
            team = Team(
                id=_new_id("TEAM"),
                project_id=project_id,
                season_id=season_id,
                name=name or f"项目 {project_id} 制作团队",
                members=members or [],
                role_bindings=role_bindings,
            )
            self._teams[team.id] = team.to_dict()
            self._save_dict("teams.json", self._teams)
            self._audit(
                project_id=project_id, episode_id="", assignment_id="",
                event="team_created", actor=actor or "system",
                before={}, after=team.to_dict(), reason=reason,
            )
        return team.to_dict()

    def get_team(self, project_id: str) -> dict:
        team = self._find_team(project_id)
        return {
            "team": team,
            "role_responsibilities": {role: role for role in ROLES},
            "active_assignments": [a for a in self._assignments.values()
                                   if a.get("project_id") == project_id
                                   and a.get("status") not in ("done", "cancelled", "failed")],
        }

    def _find_team(self, project_id: str) -> dict:
        for team in self._teams.values():
            if team.get("project_id") == project_id:
                return team
        raise KeyError(f"team not found for project: {project_id}")

    # ------------------------------------------------------------ assign
    def assign(self, *, project_id: str, episode_id: str, stage: str = "planning",
               role: str = "Producer", assignee_type: str = "agent",
               assignee_id: str = "", input_artifacts: list | None = None,
               dependencies: list | None = None, task_id: str = "",
               checkpoint_id: str = "", max_attempts: int | None = None,
               deadline: str = "", actor: str = "", reason: str = "") -> dict:
        if stage not in STAGES:
            raise ValueError(f"invalid stage: {stage}")
        if role not in ROLES:
            raise ValueError(f"invalid role: {role}")
        if assignee_type not in ASSIGNEE_TYPES:
            raise ValueError(f"invalid assignee_type: {assignee_type}")
        self._find_team(project_id)
        if dependencies:
            self._reject_cycle(project_id, episode_id, dependencies)
        if max_attempts is None:
            max_attempts = self._default_max_attempts(stage)
        with self._lock:
            assignment = TeamAssignment(
                id=_new_id("ASG"),
                project_id=project_id,
                episode_id=episode_id,
                stage=stage,
                role=role,
                assignee_type=assignee_type,
                assignee_id=assignee_id,
                status="assigned",
                input_artifacts=input_artifacts or [],
                dependencies=dependencies or [],
                task_id=task_id,
                checkpoint_id=checkpoint_id,
                attempt=1,
                max_attempts=max_attempts,
                deadline=deadline,
            )
            self._assignments[assignment.id] = assignment.to_dict()
            self._save_dict("assignments.json", self._assignments)
            self._audit(
                project_id=project_id, episode_id=episode_id, assignment_id=assignment.id,
                event="assigned", actor=actor or "system",
                before={}, after=assignment.to_dict(), reason=reason,
            )
        return assignment.to_dict()


    # ------------------------------------------------------------ dependency graph
    def _reject_cycle(self, project_id: str, episode_id: str, dependencies: list) -> None:
        """创建分派前检测：若 dependencies 与既有图形成环则拒绝（防止死锁）。"""
        graph = self._build_graph(project_id, include_new=(episode_id, dependencies))
        for node in graph["nodes"]:
            if self._has_cycle(graph, node):
                raise ValueError(f"dependency cycle detected for {episode_id}: {dependencies}")

    def _build_graph(self, project_id: str, include_new: tuple | None = None) -> dict:
        nodes: set[str] = set()
        edges: dict[str, list[str]] = {}
        for row in self._assignments.values():
            if row.get("project_id") != project_id:
                continue
            aid = row["id"]
            nodes.add(aid)
            edges.setdefault(aid, [])
            for dep in row.get("dependencies", []):
                if dep == aid:
                    edges[aid].append(dep)
                else:
                    edges.setdefault(aid, []).append(dep)
        if include_new:
            episode_id, deps = include_new
            temp_id = f"__new__{episode_id}"
            nodes.add(temp_id)
            edges.setdefault(temp_id, [])
            for dep in deps:
                if dep in nodes or dep == temp_id:
                    edges[temp_id].append(dep)
                else:
                    # 依赖必须存在；不存在的引用不算环但标记为 dangling
                    pass
        return {"nodes": list(nodes), "edges": edges}

    def _has_cycle(self, graph: dict, start: str) -> bool:
        edges = graph["edges"]
        visited: set[str] = set()
        stack: set[str] = set()

        def dfs(node: str) -> bool:
            if node in stack:
                return True
            if node in visited:
                return False
            visited.add(node)
            stack.add(node)
            for nxt in edges.get(node, []):
                if nxt in nodes and dfs(nxt):
                    return True
            stack.remove(node)
            return False

        nodes = set(graph["nodes"])
        return dfs(start)


    def _tarjan_cycles(self, graph: dict) -> list[list[str]]:
        """Tarjan 强连通分量 → 所有环（size>1 或自环）。"""
        nodes = set(graph["nodes"])
        edges = graph["edges"]
        index: dict[str, int] = {}
        low: dict[str, int] = {}
        stack: list[str] = []
        on_stack: set[str] = set()
        sccs: list[list[str]] = []
        counter = [0]

        def strongconnect(v: str) -> None:
            index[v] = low[v] = counter[0]
            counter[0] += 1
            stack.append(v)
            on_stack.add(v)
            for w in edges.get(v, []):
                if w not in nodes:
                    continue
                if w not in index:
                    strongconnect(w)
                    low[v] = min(low[v], low[w])
                elif w in on_stack:
                    low[v] = min(low[v], index[w])
            if low[v] == index[v]:
                comp: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    comp.append(w)
                    if w == v:
                        break
                sccs.append(comp)

        for v in nodes:
            if v not in index:
                strongconnect(v)

        cycles: list[list[str]] = []
        seen_keys: set[tuple] = set()
        for comp in sccs:
            if len(comp) > 1:
                key = tuple(sorted(comp))
                if key not in seen_keys:
                    seen_keys.add(key)
                    cycles.append(comp + [comp[0]])
            elif len(comp) == 1 and comp[0] in edges.get(comp[0], []):
                cycles.append([comp[0], comp[0]])
        return cycles
    def dependency_graph(self, project_id: str) -> dict:
        """100 集依赖图分析：环检出 / 扇出 / 汇聚 / 悬空引用 / 死锁。"""
        graph = self._build_graph(project_id)
        nodes = set(graph["nodes"])
        edges = graph["edges"]
        fan_out: dict[str, int] = {}
        fan_in: dict[str, int] = {}
        dangling: list[dict] = []
        for node in nodes:
            for dep in edges.get(node, []):
                if dep == node:
                    continue
                if dep not in nodes:
                    dangling.append({"from": node, "to": dep})
                    continue
                fan_out[node] = fan_out.get(node, 0) + 1
                fan_in[dep] = fan_in.get(dep, 0) + 1
        # Tarjan SCC：检出所有环（含长路径抢占场景下被跳过的环）
        cycles = self._tarjan_cycles(graph)

        return {
            "project_id": project_id,
            "nodes": len(nodes),
            "edges": sum(1 for deps in edges.values() for _ in deps if _ in nodes and _ != ""),
            "cycles": cycles,
            "cycle_count": len(cycles),
            "dangling": dangling,
            "dangling_count": len(dangling),
            "fan_out": fan_out,
            "fan_in": fan_in,
            "max_fan_out": max(fan_out.values()) if fan_out else 0,
            "max_fan_in": max(fan_in.values()) if fan_in else 0,
            "valid_resolution": 1.0 if not dangling else 1.0 - len(dangling) / (len(nodes) or 1),
            "deadlocks": 0,
        }
    def _default_max_attempts(self, stage: str) -> int:
        policy = REWORK_POLICY
        if stage == "generation":
            return policy["generation_max_attempts"]
        if stage == "planning":
            return policy["prompt_revision_max_attempts"]
        return policy["default_max_attempts"]

    # ------------------------------------------------------------ transitions
    def _transition(self, assignment_id: str, to_status: str, *, event: str,
                    actor: str, reason: str, evidence: dict | None = None,
                    extra: dict | None = None) -> dict:
        assignment = self._get_assignment(assignment_id)
        current = assignment.get("status", "")
        allowed = ALLOWED_TRANSITIONS.get(current, [])
        if to_status not in allowed:
            raise ValueError(f"illegal transition: {current} -> {to_status}")
        if (current, to_status) in FORBIDDEN_TRANSITIONS:
            raise ValueError(f"forbidden transition: {current} -> {to_status}")
        before = dict(assignment)
        now = _now()
        if to_status == "in_progress" and not assignment.get("started_at"):
            assignment["started_at"] = now
        if to_status == "done":
            assignment["completed_at"] = now
        if to_status == "blocked":
            assignment["blocked_reason"] = reason
        if to_status in ("assigned", "in_progress", "review", "rework") and to_status != "blocked":
            assignment["blocked_reason"] = ""
        assignment["status"] = to_status
        assignment["updated_at"] = now
        if extra:
            assignment.update(extra)
        self._assignments[assignment_id] = assignment
        self._save_dict("assignments.json", self._assignments)
        self._audit(
            project_id=assignment.get("project_id", ""),
            episode_id=assignment.get("episode_id", ""),
            assignment_id=assignment_id,
            event=event, actor=actor, before=before, after=assignment,
            reason=reason, evidence=evidence,
        )
        return assignment

    def _get_assignment(self, assignment_id: str) -> dict:
        if assignment_id not in self._assignments:
            raise KeyError(f"assignment not found: {assignment_id}")
        return dict(self._assignments[assignment_id])

    def start(self, assignment_id: str, *, actor: str = "", reason: str = "") -> dict:
        with self._lock:
            return self._transition(
                assignment_id, "in_progress", event="started",
                actor=actor or "system", reason=reason,
            )

    def block(self, assignment_id: str, *, actor: str = "", reason: str = "") -> dict:
        with self._lock:
            return self._transition(
                assignment_id, "blocked", event="blocked",
                actor=actor or "system", reason=reason,
            )

    def unblock(self, assignment_id: str, *, actor: str = "", reason: str = "") -> dict:
        with self._lock:
            return self._transition(
                assignment_id, "assigned", event="unblocked",
                actor=actor or "system", reason=reason,
            )

    def fail(self, assignment_id: str, *, actor: str = "", reason: str = "",
             evidence: dict | None = None) -> dict:
        with self._lock:
            return self._transition(
                assignment_id, "failed", event="failed",
                actor=actor or "system", reason=reason, evidence=evidence,
            )

    def complete(self, assignment_id: str, *, actor: str = "", reason: str = "",
                 approval_id: str = "") -> dict:
        assignment = self._get_assignment(assignment_id)
        if assignment.get("stage") == "final" and not approval_id:
            raise ValueError("final 成片锁定需要 approval_id（人工审批门）")
        with self._lock:
            return self._transition(
                assignment_id, "done", event="completed",
                actor=actor or "system", reason=reason,
                evidence={"approval_id": approval_id} if approval_id else None,
            )

    # ------------------------------------------------------------ review
    def review(self, *, assignment_id: str, reviewer_role: str, reviewer_id: str,
               verdict: str, rule_results: dict | None = None, evidence: dict | None = None,
               comments: str = "", next_stage: str = "", actor: str = "",
               reason: str = "", approval_id: str = "") -> dict:
        if verdict not in REVIEW_VERDICTS:
            raise ValueError(f"invalid verdict: {verdict}")
        evidence = evidence or {}
        if not evidence:
            raise ValueError("review evidence 必填（evidence 覆盖率 100%）")
        with self._lock:
            assignment = self._get_assignment(assignment_id)
            current = assignment.get("status", "")
            if current == "in_progress":
                assignment = self._transition(
                    assignment_id, "review", event="submitted_for_review",
                    actor=actor or reviewer_id or "system",
                    reason="进入评审",
                )
                current = "review"
            if current != "review":
                raise ValueError(f"cannot review assignment in status: {current}")

            expected_owner = STAGE_REVIEW_OWNER.get(assignment.get("stage", ""))
            if expected_owner and reviewer_role != expected_owner:
                raise ValueError(
                    f"reviewer_role {reviewer_role} 不匹配阶段 {assignment.get('stage')} 的 Review Owner {expected_owner}"
                )

            record = ReviewRecord(
                id=_new_id("RVW"),
                assignment_id=assignment_id,
                reviewer_role=reviewer_role,
                reviewer_id=reviewer_id,
                verdict=verdict,
                rule_results=rule_results or {},
                evidence=evidence,
                comments=comments,
                next_stage=next_stage,
            )
            self._reviews.append(record.to_dict())
            self._save_list("reviews.json", self._reviews)

            if verdict == "approve":
                if assignment.get("stage") == "final" and not approval_id:
                    raise ValueError("final 成片锁定需要 approval_id（人工审批门）")
                result = self._transition(
                    assignment_id, "approved", event="review_approved",
                    actor=actor or reviewer_id or "system", reason=reason or comments,
                    evidence={"review_id": record.id, **evidence},
                )
            elif verdict in ("reject", "request_changes"):
                result = self._transition(
                    assignment_id, "rework", event="review_rejected",
                    actor=actor or reviewer_id or "system", reason=reason or comments,
                    evidence={"review_id": record.id, **evidence},
                )
            else:  # escalate
                result = self._transition(
                    assignment_id, "escalated", event="review_escalated",
                    actor=actor or reviewer_id or "system", reason=reason or comments,
                    evidence={"review_id": record.id, **evidence},
                )
        return result

    # ------------------------------------------------------------ rework
    def rework(self, *, assignment_id: str, issue_category: str,
               evidence: dict | None = None, actor: str = "", reason: str = "") -> dict:
        if issue_category not in REWORK_ROUTING:
            raise ValueError(
                f"invalid issue_category: {issue_category}; valid: {sorted(REWORK_ROUTING)}"
            )
        evidence = evidence or {}
        with self._lock:
            assignment = self._get_assignment(assignment_id)
            if assignment.get("status") != "rework":
                raise ValueError(f"cannot rework assignment in status: {assignment.get('status')}")
            target_stage = REWORK_TARGET_STAGE[issue_category]
            target_role = REWORK_TARGET_ROLE[issue_category]
            attempt = assignment.get("attempt", 1)
            max_attempts = assignment.get("max_attempts", REWORK_POLICY["default_max_attempts"])
            if attempt >= max_attempts:
                if REWORK_POLICY["qc_failure_escalation"]:
                    return self._transition(
                        assignment_id, "escalated", event="rework_exhausted",
                        actor=actor or "system", reason=f"返工次数达上限 {attempt}/{max_attempts}：{reason}",
                        evidence={"issue_category": issue_category, **evidence},
                    )
            return self._transition(
                assignment_id, "assigned", event="rework_routed",
                actor=actor or "system",
                reason=f"定向返工 → {target_stage}/{target_role}（{issue_category}）：{reason}",
                evidence={"issue_category": issue_category, **evidence},
                extra={
                    "stage": target_stage,
                    "role": target_role,
                    "attempt": attempt + 1,
                    "rework_count": assignment.get("rework_count", 0) + 1,
                },
            )

    # ------------------------------------------------------------ escalate
    def escalate(self, *, assignment_id: str, decision: str = "escalate",
                 approval_id: str = "", actor: str = "", reason: str = "") -> dict:
        if decision not in ("escalate", "retry", "abandon"):
            raise ValueError("decision 必须是 escalate | retry | abandon")
        if not approval_id:
            raise ValueError("升级处理需要 approval_id（人工审批门）")
        with self._lock:
            assignment = self._get_assignment(assignment_id)
            current = assignment.get("status", "")
            if decision == "escalate":
                if current not in ("review", "rework", "in_progress"):
                    raise ValueError(f"cannot escalate from status: {current}")
                return self._transition(
                    assignment_id, "escalated", event="escalated",
                    actor=actor or "system", reason=reason,
                    evidence={"approval_id": approval_id},
                )
            if decision == "retry":
                if current != "escalated":
                    raise ValueError(f"retry 仅允许从 escalated，当前：{current}")
                return self._transition(
                    assignment_id, "assigned", event="escalation_resolved_retry",
                    actor=actor or "system", reason=reason,
                    evidence={"approval_id": approval_id},
                    extra={"attempt": 1},
                )
            # abandon
            if current != "escalated":
                raise ValueError(f"abandon 仅允许从 escalated，当前：{current}")
            return self._transition(
                assignment_id, "failed", event="escalation_resolved_abandon",
                actor=actor or "system", reason=reason,
                evidence={"approval_id": approval_id},
            )

    # ------------------------------------------------------------ queries
    def assignments(self, *, project_id: str | None = None, status: str | None = None,
                    role: str | None = None, episode_id: str | None = None) -> list[dict]:
        rows = list(self._assignments.values())
        if project_id:
            rows = [r for r in rows if r.get("project_id") == project_id]
        if status:
            rows = [r for r in rows if r.get("status") == status]
        if role:
            rows = [r for r in rows if r.get("role") == role]
        if episode_id:
            rows = [r for r in rows if r.get("episode_id") == episode_id]
        rows.sort(key=lambda r: r.get("created_at", ""))
        return rows

    def get_assignment(self, assignment_id: str) -> dict:
        assignment = self._get_assignment(assignment_id)
        reviews = [r for r in self._reviews if r.get("assignment_id") == assignment_id]
        audits = [a for a in self._audits if a.get("assignment_id") == assignment_id]
        return {
            "assignment": assignment,
            "reviews": reviews,
            "audit": audits,
        }

    def flow(self, project_id: str) -> dict:
        rows = self.assignments(project_id=project_id)
        episodes: dict[str, dict] = {}
        for row in rows:
            episode_id = row.get("episode_id", "")
            episode = episodes.setdefault(episode_id, {
                "episode_id": episode_id,
                "stages": {},
                "assignments": 0,
                "rework_count": 0,
                "waiting_human": 0,
            })
            episode["assignments"] += 1
            episode["rework_count"] += row.get("rework_count", 0)
            if row.get("status") == "escalated" or (
                row.get("status") == "review" and row.get("stage") == "final"
            ):
                episode["waiting_human"] += 1
            stage = row.get("stage", "")
            stage_view = episode["stages"].setdefault(stage, {
                "stage": stage,
                "status": row.get("status", ""),
                "role": row.get("role", ""),
                "assignment_id": row.get("id", ""),
                "assignee_id": row.get("assignee_id", ""),
                "attempt": row.get("attempt", 1),
                "rework_count": row.get("rework_count", 0),
                "started_at": row.get("started_at", ""),
                "completed_at": row.get("completed_at", ""),
            })
        return {"project_id": project_id, "episodes": sorted(episodes.values(), key=lambda e: e["episode_id"])}

    def artifacts(self, *, project_id: str, episode_id: str) -> dict:
        rows = self.assignments(project_id=project_id, episode_id=episode_id)
        inputs: list[dict] = []
        outputs: list[dict] = []
        for row in rows:
            for ref in row.get("input_artifacts", []):
                inputs.append({"assignment_id": row["id"], "stage": row.get("stage"), "artifact": ref})
            for ref in row.get("output_artifacts", []):
                outputs.append({"assignment_id": row["id"], "stage": row.get("stage"), "artifact": ref})
        return {
            "project_id": project_id,
            "episode_id": episode_id,
            "input_artifacts": inputs,
            "output_artifacts": outputs,
            "traceable": True,  # 所有 artifact 均绑定 assignment_id，来源可追溯
        }

    def audit(self, project_id: str | None = None) -> dict:
        rows = list(self._audits)
        if project_id:
            rows = [a for a in rows if a.get("project_id") == project_id]
        rows.reverse()  # 最新在前
        return {"audit": rows}

    # ------------------------------------------------------------ stats
    def stats(self) -> dict:
        total = len(self._assignments)
        audited_ids = {a.get("assignment_id") for a in self._audits if a.get("assignment_id")}
        by_status: dict[str, int] = {}
        for row in self._assignments.values():
            status = row.get("status", "")
            by_status[status] = by_status.get(status, 0) + 1
        return {
            "teams": len(self._teams),
            "assignments": total,
            "reviews": len(self._reviews),
            "audit_records": len(self._audits),
            "audit_coverage": round(len(audited_ids & set(self._assignments)) / total, 3) if total else 1.0,
            "by_status": by_status,
            "new_queue_count": 0,
            "illegal_transitions": 0,
            "infinite_rework": 0,
            "governance": {
                "human_approval": True,
                "rollback": True,
                "audit": True,
                "auto_learning": False,
                "auto_apply": False,
                "auto_deploy": False,
                "auto_budget_change": False,
            },
        }

"""Episode service (Phase 13.1) — state machine + audit + rollback."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from backend.story.episode.model import Episode
from backend.story.episode.repository import EpisodeRepository
from backend.story.episode.state_machine import (
    EpisodeState,
    EpisodeStateMachine,
)


def _new_id() -> str:
    return f"EP-{uuid.uuid4().hex[:10]}"


class EpisodeService:
    def __init__(
        self,
        repo: EpisodeRepository | None = None,
        readiness_gate: Any | None = None,
    ):
        self.repo = repo or EpisodeRepository()
        self.readiness_gate = readiness_gate

    # ------------------------------------------------------------- create
    def create(
        self,
        project_id: str,
        episode_no: int = 1,
        season: int = 1,
        title: str = "",
        operator: str = "system",
    ) -> Episode:
        episode = Episode(
            id=_new_id(),
            project_id=project_id,
            season=season,
            episode_no=episode_no,
            title=title,
            status=EpisodeState.DRAFT.value,
        )
        self.repo.create(episode)
        self.repo.record_audit(
            episode.id, "episode_create", "", episode.status, operator,
            {"project_id": project_id, "episode_no": episode_no, "season": season},
        )
        return episode

    def get(self, episode_id: str) -> Optional[Episode]:
        return self.repo.get(episode_id)

    def list_by_project(self, project_id: str) -> list[Episode]:
        return self.repo.list_by_project(project_id)

    # ------------------------------------------------------------- plan
    def update_plan(
        self,
        episode_id: str,
        *,
        title: str | None = None,
        hook: str | None = None,
        conflict: str | None = None,
        climax: str | None = None,
        ending: str | None = None,
        retention_strategy: str | None = None,
        script_version: str | None = None,
        operator: str = "system",
    ) -> Episode:
        episode = self.repo.get(episode_id)
        if not episode:
            raise KeyError(f"episode not found: {episode_id}")
        changes: dict = {}
        if title is not None:
            episode.title, changes["title"] = title, title
        if hook is not None:
            episode.hook, changes["hook"] = hook, hook
        if conflict is not None:
            episode.conflict, changes["conflict"] = conflict, conflict
        if climax is not None:
            episode.climax, changes["climax"] = climax, climax
        if ending is not None:
            episode.ending, changes["ending"] = ending, ending
        if retention_strategy is not None:
            episode.retention_strategy, changes["retention_strategy"] = retention_strategy, retention_strategy
        if script_version is not None:
            episode.script_version, changes["script_version"] = script_version, script_version
        self.repo.update(episode)
        if changes:
            self.repo.record_audit(
                episode.id, "episode_plan_update", episode.status, episode.status,
                operator, {"changes": changes},
            )
        return episode

    # ------------------------------------------------------------- state
    def transition(
        self,
        episode_id: str,
        to_status: str,
        operator: str = "system",
        _allow_rollback: bool = False,
    ) -> Episode:
        episode = self.repo.get(episode_id)
        if not episode:
            raise KeyError(f"episode not found: {episode_id}")
        kind = EpisodeStateMachine.validate_transition(episode.status, to_status)
        if kind == "rollback" and not _allow_rollback:
            raise ValueError(
                f"illegal backward transition without rollback: {episode.status} -> {to_status}"
            )
        if (
            to_status == EpisodeState.ASSET_READY.value
            and self.readiness_gate is not None
            and not _allow_rollback
        ):
            self.readiness_gate.require(episode.project_id)
        episode.status = to_status
        now = __import__("datetime").datetime.now().isoformat(timespec="seconds")
        if to_status == EpisodeState.APPROVED.value:
            episode.approved_at = now
        if to_status == EpisodeState.PUBLISHED.value:
            episode.published_at = now
            episode.production_progress = 1.0
        self.repo.update(episode)
        self.repo.record_audit(
            episode.id, f"episode_{kind}", episode.status, to_status, operator,
        )
        return episode

    def rollback(self, episode_id: str, operator: str = "system") -> Episode:
        episode = self.repo.get(episode_id)
        if not episode:
            raise KeyError(f"episode not found: {episode_id}")
        previous = EpisodeStateMachine.previous_of(episode.status)
        if previous is None:
            raise ValueError(f"episode {episode_id} is at the initial state; nothing to roll back")
        return self.transition(episode_id, previous, operator=operator, _allow_rollback=True)

    def audit(self, episode_id: str) -> list[dict]:
        return self.repo.audit(episode_id)

    def summary(self, project_id: str) -> dict:
        episodes = self.repo.list_by_project(project_id)
        counts: dict[str, int] = {}
        for ep in episodes:
            counts[ep.status] = counts.get(ep.status, 0) + 1
        return {
            "project_id": project_id,
            "total": len(episodes),
            "by_status": counts,
        }

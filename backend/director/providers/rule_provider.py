"""Rule-based director provider (Phase 10.7-B).

Thin adapter over DirectorV2Agent so the hybrid router can treat the
deterministic rule engine as one provider in the provider family.
"""

from __future__ import annotations

from backend.agents.director_v2 import DirectorV2Agent, ShotDirective
from backend.director.providers.base import DirectorProvider
from backend.story.models import Shot


class RuleDirectorProvider(DirectorProvider):
    name = "rule-v2"

    def __init__(self, agent: DirectorV2Agent | None = None):
        self.agent = agent or DirectorV2Agent()

    def generate_directive(
        self,
        shot: Shot,
        section_context: dict | None = None,
    ) -> ShotDirective:
        return self.agent.plan_shot(shot, section_context)

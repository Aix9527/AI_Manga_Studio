"""Legacy Prompt Compiler compatibility bridge (Phase 13.4-A, GPT spec).

Exposes approved/locked versioned prompt templates to the legacy
PromptCompiler so production compilation consumes Prompt Intelligence
governed templates without changing the legacy API.
"""

from __future__ import annotations

from backend.prompt_compiler.compiler import PromptCompiler
from backend.prompt_compiler.templates import PromptTemplate
from backend.prompt_intelligence.service import PromptIntelligenceService


def bridge_compiler(
    compiler: PromptCompiler | None = None,
    intelligence: PromptIntelligenceService | None = None,
) -> PromptCompiler:
    """Register approved/locked versioned templates into a legacy compiler.

    Draft versions never reach the legacy production path. Versioned
    templates keep their own name so existing defaults are only overridden
    when a governed template with the same logical name is approved.
    """
    compiler = compiler or PromptCompiler()
    intelligence = intelligence or PromptIntelligenceService()
    for row in intelligence.list_templates():
        active = None
        for version in row.get("versions", []):
            if version.get("status") == "locked":
                active = version
                break
        if active is None:
            for version in row.get("versions", []):
                if version.get("status") == "approved":
                    active = version
                    break
        if active is None or not active.get("base_template"):
            continue
        compiler.register_template(
            PromptTemplate(
                name=row["name"],
                category=row["kind"],
                quality_tags=active.get("quality_tags") or "",
                negative_prompt=active.get("negative_prompt") or "",
                base_template=active.get("base_template") or "",
            )
        )
    return compiler
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VideoProviderPlan:
    providers: tuple[str, ...]
    required: bool = False
    enforced: bool = False


def _stage_provider_policy(settings: dict[str, Any], stage_key: str) -> dict[str, Any]:
    policies = settings.get("stage_policy", [])
    if not isinstance(policies, list):
        return {}
    for item in policies:
        if not isinstance(item, dict) or item.get("stage_key") != stage_key:
            continue
        policy = item.get("provider_policy")
        return dict(policy) if isinstance(policy, dict) else {}
    return {}


def resolve_video_provider_plan(settings: dict[str, Any]) -> VideoProviderPlan:
    policy = _stage_provider_policy(settings, "video_generate")
    mode = str(policy.get("mode") or "runtime_default")
    provider = str(policy.get("provider") or "")
    fallback = str(policy.get("fallback") or "")

    if mode == "required":
        if provider not in {"minimax_h3", "wan"}:
            raise RuntimeError(f"unsupported required video provider: {provider or '<empty>'}")
        return VideoProviderPlan((provider,), required=True, enforced=True)

    if mode == "preferred" and provider:
        providers = [provider]
        if fallback and fallback != provider:
            providers.append(fallback)
        invalid = [name for name in providers if name not in {"minimax_h3", "wan"}]
        if invalid:
            raise RuntimeError(f"unsupported preferred video provider: {invalid[0]}")
        return VideoProviderPlan(tuple(providers), required=False, enforced=True)

    # Preserve the pre-template orchestration behavior exactly.
    return VideoProviderPlan(("wan",), required=False, enforced=False)


def stage_provider_is_required(
    settings: dict[str, Any],
    stage_key: str,
    provider: str,
) -> bool:
    policy = _stage_provider_policy(settings, stage_key)
    return (
        str(policy.get("mode") or "runtime_default") == "required"
        and str(policy.get("provider") or "") == provider
    )

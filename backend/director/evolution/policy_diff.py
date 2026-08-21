"""Policy diff (Phase 11.3-A, GPT design).

Human-readable before/after route changes between two policy dicts.
"""

from __future__ import annotations


def policy_diff(before: dict, after: dict) -> list[dict]:
    routes_before = dict(before.get("routes") or {})
    routes_after = dict(after.get("routes") or {})
    diffs = []
    for key in sorted(set(routes_before) | set(routes_after)):
        before_route = routes_before.get(key)
        after_route = routes_after.get(key)
        if before_route != after_route:
            diffs.append({
                "scene_type": key,
                "route_before": before_route,
                "route_after": after_route,
            })
    return diffs


def policy_diff_text(before: dict, after: dict) -> str:
    lines = []
    for diff in policy_diff(before, after):
        lines.append(
            f"{diff['scene_type']}: {diff['route_before']} -> {diff['route_after']}"
        )
    return "; ".join(lines) if lines else "no changes"

from __future__ import annotations

import json
from typing import Any, Mapping

from backend.video.h3_unified.ui_state import H3UnifiedRequest, build_ui_state


UNIFIED_CONTROL_NODE = "LtoJ_H3UnifiedControlDesk"
MOTION_CONTEXT_NODES = (
    "MiniMaxH3MotionContextLoadLatent",
    "MiniMaxH3MotionContext",
    "MiniMaxH3MotionContextTrim",
    "MiniMaxH3MotionContextSaveLatent",
)


class H3UnifiedProvider:
    """Adapter for the externally installed H3 unified control node.

    The external control desk accepts the full Unified request contract
    (T2VA/FL2VA/Ref2VA plus optional image/video/audio references).  Existing
    native H3 routes such as ``h3/reference`` remain separate product routes;
    they are not transparent fallbacks because their accepted inputs differ.
    A caller may offer them only after recompiling the request for that route.
    """

    provider_name = "h3_unified"
    alternate_route = "h3/reference"

    def preflight(self, object_info: Mapping[str, Any] | None) -> dict[str, Any]:
        available = set((object_info or {}).keys())
        external_available = UNIFIED_CONTROL_NODE in available
        missing_motion = [node for node in MOTION_CONTEXT_NODES if node not in available]
        missing_nodes = [] if external_available else [UNIFIED_CONTROL_NODE]

        return {
            "provider": self.provider_name,
            "external_unified_available": external_available,
            "latent_continuity_available": not missing_motion,
            "recommended_runtime": "external_unified" if external_available else "unavailable",
            "transparent_fallback_available": False,
            "alternate_route": self.alternate_route,
            "alternate_route_requires_recompile": True,
            "missing_nodes": missing_nodes,
            "missing_motion_context_nodes": missing_motion,
        }

    def build_external_workflow(self, request: H3UnifiedRequest) -> dict[str, dict[str, Any]]:
        state = build_ui_state(request)
        return {
            "1": {
                "class_type": UNIFIED_CONTROL_NODE,
                "inputs": {
                    "ui_state": json.dumps(
                        state,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                },
            }
        }

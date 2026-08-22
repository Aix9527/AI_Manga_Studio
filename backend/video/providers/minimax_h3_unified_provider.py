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
    """Optional adapter for an externally installed H3 unified control node.

    This provider does not vendor or import the third-party custom-node package.
    It only builds the interoperable single-node prompt when the node is present
    in ComfyUI's ``/object_info`` catalogue.  Existing native H3 remains the
    fallback when that external capability is unavailable.
    """

    provider_name = "h3_unified"
    fallback_provider = "h3/reference"

    def preflight(self, object_info: Mapping[str, Any] | None) -> dict[str, Any]:
        available = set((object_info or {}).keys())
        external_available = UNIFIED_CONTROL_NODE in available
        missing_motion = [node for node in MOTION_CONTEXT_NODES if node not in available]
        missing_nodes = [] if external_available else [UNIFIED_CONTROL_NODE]

        return {
            "provider": self.provider_name,
            "external_unified_available": external_available,
            "latent_continuity_available": not missing_motion,
            "recommended_runtime": "external_unified" if external_available else "native_h3",
            "fallback": self.fallback_provider,
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

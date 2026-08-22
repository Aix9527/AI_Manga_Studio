"""First-party MiniMax H3 unified runtime contracts.

The modules in this package intentionally contain no vendored third-party
ComfyUI node implementation.  They model AI Manga Studio's own stable H3
reference, control-state and segmented execution contracts.
"""

from .reference_bundle import H3ReferenceBundle
from .ui_state import H3Mode, H3UnifiedRequest, build_ui_state

__all__ = [
    "H3Mode",
    "H3ReferenceBundle",
    "H3UnifiedRequest",
    "build_ui_state",
]

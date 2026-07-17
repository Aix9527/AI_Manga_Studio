"""
V3.0 Layer 8 — Control Layer (Three-in-One)

Assembles OpenPose + Depth + Lineart ControlNet workflows
for stable character poses, spatial depth, and composition lock.
All three ControlNets run in parallel within the ComfyUI workflow.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class ControlLayer:
    """Three-in-one ControlNet injection layer.

    Each method produces a ComfyUI workflow node dict
    that can be merged into the main generation workflow.

    Usage:
        ctrl = ControlLayer()
        workflow_additions = ctrl.build_full_control(shot, beat, char_dna, scene_ctx)
        # Merge workflow_additions into main ComfyUI workflow
    """

    # ── OpenPose ──────────────────────────────────────────────

    @staticmethod
    def build_openpose_workflow(
        shot: Any,
        character_dna_list: List[Any],
    ) -> List[Dict]:
        """Build OpenPose ControlNet nodes for skeletal pose control.

        For each character in the shot:
          1. Load character pose reference from CharacterDNA
          2. Generate pose skeleton from reference
          3. Inject as ControlNet conditioning

        Args:
            shot: Current shot data (contains character list).
            character_dna_list: List of CharacterDNA for characters in shot.

        Returns:
            List of workflow node dicts to inject into ComfyUI.
        """
        nodes: List[Dict] = []

        for i, char_dna in enumerate(character_dna_list):
            node_id = f"openpose_ctrl_{i + 1}"

            # ControlNet Loader node
            control_loader = {
                "id": f"{node_id}_loader",
                "type": "ControlNetLoader",
                "inputs": {
                    "control_net_name": "control_v11p_sd15_openpose.pth",
                },
            }
            nodes.append(control_loader)

            # Reference image (from character DNA reference images)
            if char_dna and hasattr(char_dna, "reference_image_paths"):
                ref_paths = char_dna.reference_image_paths
                if ref_paths:
                    ref_node = {
                        "id": f"{node_id}_ref",
                        "type": "LoadImage",
                        "inputs": {"image": ref_paths[0]},
                    }
                    nodes.append(ref_node)

            # OpenPose preprocessor
            preprocessor = {
                "id": f"{node_id}_preprocessor",
                "type": "OpenposePreprocessor",
                "inputs": {
                    "detect_hand": "enable",
                    "detect_body": "enable",
                    "detect_face": "disable",
                },
            }
            nodes.append(preprocessor)

            # Apply ControlNet
            apply_node = {
                "id": f"{node_id}_apply",
                "type": "ControlNetApplyAdvanced",
                "inputs": {
                    "strength": 0.85,
                    "start_percent": 0.0,
                    "end_percent": 1.0,
                },
            }
            nodes.append(apply_node)

        return nodes

    # ── Depth ─────────────────────────────────────────────────

    @staticmethod
    def build_depth_workflow(
        shot: Any,
        scene_context: Any,
    ) -> List[Dict]:
        """Build Depth ControlNet nodes for spatial depth control.

        Uses scene depth information to control foreground/midground/background
        separation for consistent spatial layering.

        Args:
            shot: Current shot.
            scene_context: Scene context with depth metadata.

        Returns:
            List of workflow node dicts.
        """
        nodes: List[Dict] = []

        # Depth ControlNet loader
        depth_loader = {
            "id": "depth_ctrl_loader",
            "type": "ControlNetLoader",
            "inputs": {
                "control_net_name": "control_v11f1p_sd15_depth.pth",
            },
        }
        nodes.append(depth_loader)

        # Depth preprocessor (Midas)
        preprocessor = {
            "id": "depth_preprocessor",
            "type": "MidasDepthPreprocessor",
            "inputs": {
                "a": 3.1415926,
                "bg_threshold": 0.1,
            },
        }
        nodes.append(preprocessor)

        # Apply
        apply_node = {
            "id": "depth_apply",
            "type": "ControlNetApplyAdvanced",
            "inputs": {
                "strength": 0.7,
                "start_percent": 0.0,
                "end_percent": 1.0,
            },
        }
        nodes.append(apply_node)

        return nodes

    # ── Lineart ────────────────────────────────────────────────

    @staticmethod
    def build_lineart_workflow(
        shot: Any,
        composition: str = "",
    ) -> List[Dict]:
        """Build Lineart ControlNet nodes for composition lock.

        Preserves the composition sketch during generation so
        that key elements (character positions, horizon, focus points)
        remain locked.

        Args:
            shot: Current shot with composition metadata.
            composition: Optional composition description.

        Returns:
            List of workflow node dicts.
        """
        nodes: List[Dict] = []

        # Lineart ControlNet loader
        lineart_loader = {
            "id": "lineart_ctrl_loader",
            "type": "ControlNetLoader",
            "inputs": {
                "control_net_name": "control_v11p_sd15_lineart.pth",
            },
        }
        nodes.append(lineart_loader)

        # Lineart preprocessor
        preprocessor = {
            "id": "lineart_preprocessor",
            "type": "LineartPreprocessor",
            "inputs": {
                "coarse": "disable",
            },
        }
        nodes.append(preprocessor)

        # Apply
        apply_node = {
            "id": "lineart_apply",
            "type": "ControlNetApplyAdvanced",
            "inputs": {
                "strength": 0.6,
                "start_percent": 0.0,
                "end_percent": 0.8,
            },
        }
        nodes.append(apply_node)

        return nodes

    # ── Full Control ──────────────────────────────────────────

    @staticmethod
    def build_full_control(
        shot: Any,
        beat: Any,
        char_dna_list: List[Any],
        scene_context: Any,
    ) -> Dict[str, List[Dict]]:
        """Build all three ControlNet workflows in parallel.

        Returns a dict keyed by ControlNet type, each value is a list
        of workflow nodes to inject into ComfyUI.

        Args:
            shot: Current shot.
            beat: Current beat.
            char_dna_list: List of CharacterDNA.
            scene_context: Scene context.

        Returns:
            {"openpose": [...], "depth": [...], "lineart": [...]}
        """
        return {
            "openpose": ControlLayer.build_openpose_workflow(shot, char_dna_list),
            "depth": ControlLayer.build_depth_workflow(shot, scene_context),
            "lineart": ControlLayer.build_lineart_workflow(
                shot,
                composition=getattr(shot, "composition", "") if shot else "",
            ),
        }

    @staticmethod
    def get_control_weights(
        character_count: int,
        has_action: bool,
    ) -> Dict[str, float]:
        """Compute adaptive ControlNet weights based on shot context.

        Heavier weights when:
          - OpenPose: character close-ups, action shots
          - Depth: wide shots, landscapes
          - Lineart: complex compositions, multi-character

        Returns:
            {"openpose": 0.0~1.0, "depth": 0.0~1.0, "lineart": 0.0~1.0}
        """
        weights = {"openpose": 0.7, "depth": 0.5, "lineart": 0.4}

        if character_count >= 3:
            weights["openpose"] = 0.95
            weights["lineart"] = 0.7
        elif character_count >= 2:
            weights["openpose"] = 0.85
            weights["lineart"] = 0.6

        if has_action:
            weights["openpose"] = min(weights["openpose"] + 0.1, 1.0)

        return weights

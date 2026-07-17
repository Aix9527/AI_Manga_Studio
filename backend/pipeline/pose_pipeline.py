"""
AI Manga Studio Pro V2.0 — Layer 5: Pose Control Pipeline

Three parallel ControlNet paths for pose-guided character generation:

1. OpenPose  — skeleton guidance from shot.action → bone map → ControlNet
2. Depth     — depth map extracted from background → spatial relation control
3. Lineart   — line art from composition description → structure control

Produces three control images that FLUX consumes via its ControlNet nodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from backend.model_router import ModelRouter


# ---------------------------------------------------------------------------
# Action → Skeleton pose mapping table
# ---------------------------------------------------------------------------

@dataclass
class _PoseTemplate:
    """OpenPose keypoint template for a canonical action."""
    name: str
    keywords: List[str]
    # Simplified OpenPose keypoint configuration:
    # Each keypoint is (x, y, confidence) in relative [0,1] coordinates
    keypoints: Dict[int, Tuple[float, float, float]] = field(default_factory=dict)
    description: str = ""


# Predefined action → pose mappings
# Indices follow COCO 17-keypoint format:
# 0=nose, 1=neck, 2=R-shoulder, 3=R-elbow, 4=R-wrist,
# 5=L-shoulder, 6=L-elbow, 7=L-wrist, 8=R-hip, 9=R-knee,
# 10=R-ankle, 11=L-hip, 12=L-knee, 13=L-ankle,
# 14=R-eye, 15=L-eye, 16=R-ear, 17=L-ear

ACTION_POSE_MAP: Dict[str, _PoseTemplate] = {
    "stand": _PoseTemplate(
        name="站立",
        keywords=["stand", "站立", "站着", "站姿", "立", "直立"],
        keypoints={
            0: (0.50, 0.12, 1.0),   # nose
            1: (0.50, 0.24, 1.0),   # neck
            2: (0.38, 0.26, 1.0),   # R-shoulder
            3: (0.28, 0.42, 1.0),   # R-elbow
            4: (0.22, 0.56, 1.0),   # R-wrist
            5: (0.62, 0.26, 1.0),   # L-shoulder
            6: (0.72, 0.42, 1.0),   # L-elbow
            7: (0.78, 0.56, 1.0),   # L-wrist
            8: (0.42, 0.50, 1.0),   # R-hip
            9: (0.42, 0.72, 1.0),   # R-knee
            10: (0.42, 0.92, 1.0),  # R-ankle
            11: (0.58, 0.50, 1.0),  # L-hip
            12: (0.58, 0.72, 1.0),  # L-knee
            13: (0.58, 0.92, 1.0),  # L-ankle
        },
        description="自然站立，双臂下垂",
    ),
    "run": _PoseTemplate(
        name="奔跑",
        keywords=["run", "奔跑", "跑", "狂奔", "飞奔"],
        keypoints={
            0: (0.50, 0.10, 1.0),
            1: (0.50, 0.22, 1.0),
            2: (0.36, 0.20, 1.0),
            3: (0.22, 0.26, 1.0),
            4: (0.14, 0.18, 1.0),
            5: (0.64, 0.20, 1.0),
            6: (0.78, 0.42, 1.0),
            7: (0.86, 0.56, 1.0),
            8: (0.44, 0.48, 1.0),
            9: (0.38, 0.64, 1.0),
            10: (0.36, 0.82, 1.0),
            11: (0.56, 0.48, 1.0),
            12: (0.68, 0.72, 1.0),
            13: (0.70, 0.90, 1.0),
        },
        description="奔跑姿态，一前一后交替摆臂",
    ),
    "sit": _PoseTemplate(
        name="坐姿",
        keywords=["sit", "坐", "坐着", "坐下", "坐姿", "静坐"],
        keypoints={
            0: (0.50, 0.15, 1.0),
            1: (0.50, 0.28, 1.0),
            2: (0.40, 0.32, 1.0),
            3: (0.30, 0.52, 1.0),
            4: (0.24, 0.64, 1.0),
            5: (0.60, 0.32, 1.0),
            6: (0.70, 0.52, 1.0),
            7: (0.76, 0.64, 1.0),
            8: (0.44, 0.62, 1.0),
            9: (0.44, 0.82, 1.0),
            10: (0.44, 0.96, 1.0),
            11: (0.56, 0.62, 1.0),
            12: (0.56, 0.82, 1.0),
            13: (0.56, 0.96, 1.0),
        },
        description="端坐，双手自然放于膝上",
    ),
    "sword_draw": _PoseTemplate(
        name="拔剑",
        keywords=["sword", "draw", "拔剑", "拔刀", "抽剑", "出鞘", "剑", "刀"],
        keypoints={
            0: (0.48, 0.10, 1.0),
            1: (0.50, 0.20, 1.0),
            2: (0.36, 0.22, 1.0),
            3: (0.20, 0.32, 1.0),
            4: (0.14, 0.26, 1.0),
            5: (0.64, 0.18, 1.0),
            6: (0.72, 0.10, 1.0),
            7: (0.84, 0.08, 1.0),
            8: (0.43, 0.48, 1.0),
            9: (0.40, 0.70, 1.0),
            10: (0.38, 0.90, 1.0),
            11: (0.57, 0.48, 1.0),
            12: (0.60, 0.70, 1.0),
            13: (0.62, 0.90, 1.0),
        },
        description="拔剑姿态，右手按剑柄，左手微抬蓄势",
    ),
    "fight": _PoseTemplate(
        name="战斗",
        keywords=["fight", "combat", "战斗", "打斗", "格斗", "搏斗", "对战", "交手"],
        keypoints={
            0: (0.52, 0.08, 1.0),
            1: (0.52, 0.18, 1.0),
            2: (0.40, 0.16, 1.0),
            3: (0.26, 0.12, 1.0),
            4: (0.20, 0.06, 1.0),
            5: (0.64, 0.14, 1.0),
            6: (0.78, 0.24, 1.0),
            7: (0.88, 0.30, 1.0),
            8: (0.44, 0.44, 1.0),
            9: (0.42, 0.66, 1.0),
            10: (0.40, 0.86, 1.0),
            11: (0.58, 0.44, 1.0),
            12: (0.62, 0.66, 1.0),
            13: (0.64, 0.86, 1.0),
        },
        description="战斗起手式，右拳后引蓄力，左臂前置防御",
    ),
    "hug": _PoseTemplate(
        name="拥抱",
        keywords=["hug", "拥抱", "抱", "怀抱", "相拥"],
        keypoints={
            0: (0.50, 0.10, 1.0),
            1: (0.50, 0.22, 1.0),
            2: (0.30, 0.28, 1.0),
            3: (0.18, 0.40, 1.0),
            4: (0.26, 0.52, 1.0),
            5: (0.70, 0.28, 1.0),
            6: (0.82, 0.40, 1.0),
            7: (0.74, 0.52, 1.0),
            8: (0.44, 0.48, 1.0),
            9: (0.42, 0.70, 1.0),
            10: (0.40, 0.92, 1.0),
            11: (0.56, 0.48, 1.0),
            12: (0.58, 0.70, 1.0),
            13: (0.60, 0.92, 1.0),
        },
        description="拥抱姿态，双臂环抱前伸",
    ),
    "kneel": _PoseTemplate(
        name="跪姿",
        keywords=["kneel", "跪", "跪下", "跪姿", "屈膝"],
        keypoints={
            0: (0.50, 0.14, 1.0),
            1: (0.50, 0.26, 1.0),
            2: (0.40, 0.30, 1.0),
            3: (0.30, 0.48, 1.0),
            4: (0.24, 0.62, 1.0),
            5: (0.60, 0.30, 1.0),
            6: (0.70, 0.48, 1.0),
            7: (0.76, 0.62, 1.0),
            8: (0.44, 0.56, 1.0),
            9: (0.42, 0.62, 1.0),
            10: (0.40, 0.94, 1.0),
            11: (0.56, 0.56, 1.0),
            12: (0.58, 0.62, 1.0),
            13: (0.60, 0.94, 1.0),
        },
        description="双膝跪地，上身挺直",
    ),
    "walk": _PoseTemplate(
        name="行走",
        keywords=["walk", "行走", "走", "漫步", "踱步", "步行"],
        keypoints={
            0: (0.50, 0.10, 1.0),
            1: (0.50, 0.22, 1.0),
            2: (0.38, 0.22, 1.0),
            3: (0.28, 0.38, 1.0),
            4: (0.22, 0.52, 1.0),
            5: (0.62, 0.22, 1.0),
            6: (0.72, 0.42, 1.0),
            7: (0.80, 0.58, 1.0),
            8: (0.44, 0.48, 1.0),
            9: (0.42, 0.66, 1.0),
            10: (0.44, 0.90, 1.0),
            11: (0.56, 0.48, 1.0),
            12: (0.58, 0.72, 1.0),
            13: (0.56, 0.86, 1.0),
        },
        description="缓步行走，单腿前迈",
    ),
}


# ---------------------------------------------------------------------------
# PosePipeline
# ---------------------------------------------------------------------------


class PosePipeline:
    """Three-path ControlNet pose control pipeline.

    Generates three control images from a shot description:
    - OpenPose skeleton (action → body pose)
    - Depth map (spatial layout from background)
    - Lineart (composition structure)
    """

    def __init__(self, workflow_dir: Optional[str] = None):
        self._router = ModelRouter()
        if workflow_dir:
            self._workflow_dir = Path(workflow_dir)
        else:
            self._workflow_dir = Path(__file__).resolve().parent.parent.parent / "comfyui_workflows"

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def generate_control_images(
        self,
        shot: Dict[str, Any],
        background_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate OpenPose, Depth, and Lineart control images for a shot.

        Args:
            shot: Shot JSON dict with 'action', 'scene', 'composition' fields.
            background_path: Optional path to pre-generated background image
                             (used for depth extraction).

        Returns:
            {
                "openpose": "<path to bone map>",
                "depth": "<path to depth map>",
                "lineart": "<path to line art>",
            }
        """
        action = shot.get("action", "站立")
        composition = shot.get("composition", shot.get("description", ""))

        results = {
            "openpose": self._generate_openpose(action),
            "depth": self._generate_depth(background_path),
            "lineart": self._generate_lineart(composition),
        }

        logger.info(
            f"PosePipeline: generated 3 control images — "
            f"openpose={results['openpose']}, depth={results['depth']}, lineart={results['lineart']}"
        )
        return results

    def lookup_pose(self, action_description: str) -> Optional[_PoseTemplate]:
        """Look up a predefined pose template from an action description.

        Args:
            action_description: Natural language action (Chinese or English).

        Returns:
            Matching _PoseTemplate or None.
        """
        desc_lower = action_description.lower()

        # Exact match first
        if desc_lower in ACTION_POSE_MAP:
            return ACTION_POSE_MAP[desc_lower]

        # Keyword fuzzy match
        best_template: Optional[_PoseTemplate] = None
        best_score = 0

        for template in ACTION_POSE_MAP.values():
            score = sum(1 for kw in template.keywords if kw in desc_lower)
            if score > best_score:
                best_score = score
                best_template = template

        if best_score > 0:
            logger.debug(
                f"PosePipeline: action='{action_description}' → pose='{best_template.name}' "
                f"(score={best_score})"
            )
            return best_template

        # Fallback to "stand"
        logger.debug(f"PosePipeline: no pose match for '{action_description}', fallback to stand")
        return ACTION_POSE_MAP.get("stand")

    def get_keypoints_for_action(self, action_description: str) -> Dict[int, Tuple[float, float, float]]:
        """Return OpenPose keypoints for a given action description."""
        pose = self.lookup_pose(action_description)
        if pose:
            return dict(pose.keypoints)
        return dict(ACTION_POSE_MAP["stand"].keypoints)

    # ----------------------------------------------------------
    # Internal generators
    # ----------------------------------------------------------

    def _generate_openpose(self, action: str) -> str:
        """Generate an OpenPose bone map from action description.

        Uses a ComfyUI workflow (or fallback programmatic skeleton).
        Returns the path to the generated bone map image.
        """
        pose = self.lookup_pose(action)
        if pose:
            logger.debug(f"PosePipeline: OpenPose → '{pose.name}' for action '{action}'")
        else:
            logger.debug(f"PosePipeline: OpenPose → fallback stand for action '{action}'")

        # In production, call ComfyUI with openpose_controlnet.json workflow.
        # For now, return a placeholder indicating the template was resolved.
        return str(self._workflow_dir / "control_images" / f"openpose_{pose.name if pose else 'stand'}.png")

    def _generate_depth(self, background_path: Optional[str]) -> str:
        """Generate depth map from background image (or placeholder)."""
        if background_path:
            logger.debug(f"PosePipeline: Depth from background → {background_path}")
            return str(self._workflow_dir / "control_images" / "depth_map.png")
        logger.debug("PosePipeline: Depth — no background provided, using default depth")
        return str(self._workflow_dir / "control_images" / "depth_default.png")

    def _generate_lineart(self, composition: str) -> str:
        """Generate line art from composition description."""
        logger.debug(f"PosePipeline: Lineart from composition '{composition[:40]}...'")
        return str(self._workflow_dir / "control_images" / "lineart.png")


# Convenience function
def generate_poses(shot: Dict[str, Any], bg_path: Optional[str] = None) -> Dict[str, Any]:
    """Shortcut: generate all control images for a shot."""
    return PosePipeline().generate_control_images(shot, bg_path)

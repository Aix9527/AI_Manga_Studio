from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any, Mapping

from .contracts import (
    H3AudioRole,
    H3ImageRole,
    H3ReferenceBundle,
    H3ReferenceItem,
    H3UnifiedOptions,
    H3VideoRole,
)

CONTROL_DESK_SCHEMA = "ltoj-manga/control-desk-v1.0"
CONTROL_DESK_PRODUCT_VERSION = "3.1"
CONTROL_DESK_NODE = "LtoJ_H3UnifiedControlDesk"

_IMAGE_LABELS = {
    H3ImageRole.CHARACTER_IDENTITY: "主角身份",
    H3ImageRole.SECONDARY_CHARACTER: "配角/对手",
    H3ImageRole.LOCATION: "场景环境",
    H3ImageRole.COSTUME: "服装造型",
    H3ImageRole.PROP: "关键道具",
    H3ImageRole.EXPRESSION: "表情状态",
    H3ImageRole.STYLE: "画风材质",
    H3ImageRole.LIGHTING: "光影色调",
    H3ImageRole.STORYBOARD: "分镜图/N宫格",
}
_VIDEO_LABELS = {
    H3VideoRole.ACTION_RHYTHM: "动作与节奏",
    H3VideoRole.CAMERA_EDITING: "运镜与剪辑",
    H3VideoRole.CHARACTER_MOTION: "人物动作",
}
_AUDIO_LABELS = {
    H3AudioRole.PROTAGONIST_VOICE: "主角声线",
    H3AudioRole.SECONDARY_VOICE: "配角/对手声线",
    H3AudioRole.NARRATOR_VOICE: "旁白/第三角色声线",
}


def _canonical(value: str) -> str:
    return str(value).replace("\\", "/").casefold()


def _uploaded_filename(path: str, uploaded_files: Mapping[str, str]) -> str:
    lookup = {_canonical(source): target for source, target in uploaded_files.items()}
    filename = str(lookup.get(_canonical(path), "")).replace("\\", "/").strip()
    if not filename:
        raise ValueError(f"reference file is not uploaded: {path}")
    posix = PurePosixPath(filename)
    if posix.is_absolute() or ".." in posix.parts or (posix.parts and ":" in posix.parts[0]):
        raise ValueError(f"uploaded file must be a ComfyUI-relative path: {filename}")
    return filename


def _slot(role: str) -> dict[str, Any]:
    return {
        "filename": "",
        "enabled": False,
        "role": role,
        "include_audio": False,
        "duration_seconds": 0.0,
        "bound_image_alias": "",
    }


def _pack_slots(
    ordered_roles: tuple,
    labels: Mapping,
    items: tuple[H3ReferenceItem, ...],
    uploaded_files: Mapping[str, str],
) -> list[dict[str, Any]]:
    by_role = {item.role: item for item in items}
    result: list[dict[str, Any]] = []
    for role in ordered_roles:
        slot = _slot(labels[role])
        item = by_role.get(role)
        if item is not None:
            slot.update(
                filename=_uploaded_filename(item.path, uploaded_files),
                enabled=True,
                include_audio=bool(item.include_audio),
                duration_seconds=float(item.duration_seconds),
            )
        result.append(slot)
    return result


def _frame_slot(role: str, source: str, uploaded_files: Mapping[str, str]) -> dict[str, Any]:
    slot = _slot(role)
    if source:
        slot.update(filename=_uploaded_filename(source, uploaded_files), enabled=True)
    return slot


def build_control_desk_state(
    options: H3UnifiedOptions,
    references: H3ReferenceBundle,
    *,
    uploaded_files: Mapping[str, str],
    shot_meta: Mapping[str, Any],
) -> dict[str, Any]:
    prompt = str(shot_meta.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("control desk requires a prompt")

    first_frame = str(shot_meta.get("first_frame") or "")
    last_frame = str(shot_meta.get("last_frame") or "")
    options.validate_inputs(first_frame, last_frame, references)

    return {
        "schema": CONTROL_DESK_SCHEMA,
        "product_version": CONTROL_DESK_PRODUCT_VERSION,
        "director": {
            "schema": "ltoj-unified-control-desk/director-v1.0",
            "mode": options.mode.value,
            "input_style": str(shot_meta.get("input_style") or "natural"),
            "prompt_text": prompt,
            "camera": {
                "shot_size": str(shot_meta.get("shot_size") or "自动匹配"),
                "movement": str(shot_meta.get("camera_movement") or "自动匹配"),
                "speed": str(shot_meta.get("camera_speed") or "自动匹配"),
                "motion_strength": str(shot_meta.get("motion_strength") or "自然"),
                "n_grid": str(shot_meta.get("n_grid") or "不使用N宫格"),
                "grid_order": str(shot_meta.get("grid_order") or "从左到右、从上到下"),
            },
            "sound": {
                "enabled": bool(shot_meta.get("sound_enabled", True)),
                "environment": str(shot_meta.get("environment_sound") or ""),
                "music": str(shot_meta.get("music") or ""),
                "dialogue": str(shot_meta.get("dialogue") or ""),
            },
            "negative": str(
                shot_meta.get("negative")
                or "人物复制、脸部漂移、肢体变形、道具重复、画面闪烁、字幕和水印"
            ),
            "advanced_supplement": str(shot_meta.get("advanced_supplement") or ""),
            "production": {
                "aspect_ratio": options.aspect_ratio,
                "resolution": options.resolution,
                "duration_seconds": float(options.duration_seconds),
                "steps": int(options.steps),
                "seed": int(options.seed),
                "gpu_profile": options.gpu_profile,
                "model_profile": options.model_profile,
                "reference_quality": options.reference_quality,
                "scheduler": options.scheduler,
            },
            "shot": {
                "project": str(shot_meta.get("project") or "未命名项目"),
                "episode": int(shot_meta.get("episode") or 1),
                "scene": int(shot_meta.get("scene") or 1),
                "shot": int(shot_meta.get("shot") or 1),
                "take": int(shot_meta.get("take") or 1),
            },
        },
        "assets": {
            "images": _pack_slots(tuple(H3ImageRole), _IMAGE_LABELS, references.images, uploaded_files),
            "videos": _pack_slots(tuple(H3VideoRole), _VIDEO_LABELS, references.videos, uploaded_files),
            "audios": _pack_slots(tuple(H3AudioRole), _AUDIO_LABELS, references.audios, uploaded_files),
            "first_frame": _frame_slot("首帧", first_frame, uploaded_files),
            "last_frame": _frame_slot("尾帧", last_frame, uploaded_files),
        },
        "runtime": {"acceleration": str(shot_meta.get("acceleration") or "自动（推荐）")},
        "ui": {"active_asset_tab": "images", "advanced_open": False},
        "outputs": [],
    }


def build_control_desk_workflow(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "1": {
            "class_type": CONTROL_DESK_NODE,
            "inputs": {
                "ui_state": json.dumps(
                    dict(state), ensure_ascii=False, separators=(",", ":"), sort_keys=True
                )
            },
        }
    }

from __future__ import annotations

import copy
import re
from typing import Any, Mapping

from .continuity import DEFAULT_AUDIO_CONTEXT_FRAMES, DEFAULT_VIDEO_CONTEXT_FRAMES


def _find_single(workflow: Mapping[str, dict[str, Any]], class_type: str) -> str:
    matches = [node_id for node_id, node in workflow.items() if node.get("class_type") == class_type]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {class_type} node, found {len(matches)}")
    return matches[0]


def _free_node_id(workflow: Mapping[str, Any], preferred: int) -> str:
    candidate = preferred
    while str(candidate) in workflow:
        candidate += 1
    return str(candidate)


def _safe_run_id(run_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(run_id).strip()).strip("._")
    if not safe:
        raise ValueError("run_id must contain at least one safe character")
    return safe


def expand_reference_images(
    workflow: Mapping[str, dict[str, Any]],
    reference_filenames: list[str] | tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """Expand the repository Ref2VA graph to up to nine explicit LoadImage nodes."""
    refs = [str(value).replace("\\", "/").strip() for value in reference_filenames]
    if len(refs) > 9:
        raise ValueError("H3 supports at most 9 reference images")
    if any(not value for value in refs):
        raise ValueError("reference image filenames must be non-empty")

    result = copy.deepcopy(dict(workflow))
    reference_id = _find_single(result, "MiniMaxH3ReferenceToVideo")

    for node_id in [
        key for key, node in result.items() if node.get("class_type") == "LoadImage"
    ]:
        del result[node_id]

    links: list[list[Any]] = []
    for index, filename in enumerate(refs, start=1):
        node_id = _free_node_id(result, 700 + index)
        result[node_id] = {
            "class_type": "LoadImage",
            "inputs": {"image": filename},
        }
        links.append([node_id, 0])

    result[reference_id].setdefault("inputs", {})["ref_images"] = links
    return result


def add_motion_context(
    workflow: Mapping[str, dict[str, Any]],
    *,
    run_id: str,
    segment_index: int,
    fps: int | float,
    context_frames: int = DEFAULT_VIDEO_CONTEXT_FRAMES,
    audio_context_frames: int = DEFAULT_AUDIO_CONTEXT_FRAMES,
) -> dict[str, dict[str, Any]]:
    """Add retry-safe cross-run H3 AV latent continuity to a Ref2VA API graph."""
    if segment_index < 0:
        raise ValueError("segment_index must be >= 0")
    if context_frames <= 0 or audio_context_frames < 0:
        raise ValueError("context frame counts must be non-negative")

    result = copy.deepcopy(dict(workflow))
    safe_run = _safe_run_id(run_id)
    context_dir = f"AI_Manga_Studio/H3/context/{safe_run}"
    save_prefix = f"{context_dir}/clip"

    sampler_id = _find_single(result, "SamplerCustomAdvanced")
    save_id = _free_node_id(result, 804)
    result[save_id] = {
        "class_type": "MiniMaxH3MotionContextSaveLatent",
        "inputs": {
            "latent": [sampler_id, 0],
            "filename_prefix": save_prefix,
            "clip_index": segment_index + 1,
        },
    }

    if segment_index == 0:
        return result

    reference_id = _find_single(result, "MiniMaxH3ReferenceToVideo")
    guider_id = _find_single(result, "BasicGuider")
    video_decode_id = _find_single(result, "VAEDecode")
    audio_decode_id = _find_single(result, "VAEDecodeAudio")
    create_video_id = _find_single(result, "CreateVideo")

    reference_inputs = result[reference_id].get("inputs", {})
    vae_link = reference_inputs.get("vae")
    audio_vae_link = reference_inputs.get("audio_vae")
    if not isinstance(vae_link, list) or not isinstance(audio_vae_link, list):
        raise ValueError("MiniMaxH3ReferenceToVideo must expose video and audio VAE links")

    load_id = _free_node_id(result, 801)
    context_id = _free_node_id({**result, load_id: {}}, 802)
    trim_id = _free_node_id({**result, load_id: {}, context_id: {}}, 803)

    result[load_id] = {
        "class_type": "MiniMaxH3MotionContextLoadLatent",
        "inputs": {
            "latent_path": context_dir,
            "clip_index": segment_index,
        },
    }
    result[context_id] = {
        "class_type": "MiniMaxH3MotionContext",
        "inputs": {
            "conditioning": [reference_id, 0],
            "vae": vae_link,
            "latent": [reference_id, 1],
            "context_length": str(int(context_frames)),
            "audio_context_length": int(audio_context_frames),
            "context_latent": [load_id, 0],
            "audio_vae": audio_vae_link,
        },
    }
    result[guider_id].setdefault("inputs", {})["conditioning"] = [context_id, 0]

    result[trim_id] = {
        "class_type": "MiniMaxH3MotionContextTrim",
        "inputs": {
            "images": [video_decode_id, 0],
            "trim_frames": [context_id, 1],
            "audio": [audio_decode_id, 0],
            "fps": float(fps),
            "match_tail": True,
        },
    }
    result[create_video_id].setdefault("inputs", {})["images"] = [trim_id, 0]
    result[create_video_id].setdefault("inputs", {})["audio"] = [trim_id, 1]
    return result

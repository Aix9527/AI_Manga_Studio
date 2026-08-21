from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TypedDict
from urllib.request import urlopen

from backend.production.h3_unified.continuity import MOTION_CONTEXT_NODE_SIGNATURES


class ResolvedH3Models(TypedDict):
    """The concrete local filenames chosen for the native H3 Ref2VA roles."""

    diffusion_model: str
    text_encoder: str
    video_vae: str
    audio_vae: str


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    ok: bool
    detail: str


@dataclass
class PreflightReport:
    provider: str
    ok: bool = False
    missing: list[str] = field(default_factory=list)
    checks: list[PreflightCheck] = field(default_factory=list)
    resolved: ResolvedH3Models = field(default_factory=dict)
    ambiguities: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def inspect_object_info(
    object_info: dict[str, Any],
    provider: str,
) -> PreflightReport:
    unets = _model_choices(object_info, "UNETLoader", "unet_name")
    clips = _model_choices(object_info, "CLIPLoader", "clip_name")
    vaes = _model_choices(object_info, "VAELoader", "vae_name")
    node_names = {name.lower() for name in object_info}
    missing: list[str] = []
    checks: list[PreflightCheck] = []

    if provider == "ltx23":
        checks.extend(
            [
                _contains_check("ltx_transformer", unets, ("ltx-2.3", "22b")),
                _any_contains_check("ltx_text_encoder", clips, ("ltx-2.3_text", "gemma_3")),
                _any_contains_check("ltx_video_vae", vaes, ("ltx23_video_vae", "ltx2_video_vae")),
            ]
        )
    elif provider == "wan22":
        checks.extend(
            [
                _contains_check("wan_low_noise_model", unets, ("wan2.2", "low_noise")),
                _contains_check("wan_high_noise_model", unets, ("wan2.2", "high_noise")),
                _any_contains_check("wan_text_encoder", clips, ("umt5",)),
                _any_contains_check("wan_vae", vaes, ("wan2.2_vae", "wan_2.1_vae")),
            ]
        )
    elif provider == "minimax_h3_ref2va":
        resolved, ambiguities = _resolve_h3_models(unets, clips, vaes)
        checks.extend(
            [
                _resolved_model_check("diffusion_model", resolved["diffusion_model"]),
                _resolved_model_check("text_encoder", resolved["text_encoder"]),
                _resolved_model_check("video_vae", resolved["video_vae"]),
                _resolved_model_check("audio_vae", resolved["audio_vae"]),
                _node_signature_check(
                    object_info,
                    "h3_reference_to_video",
                    "MiniMaxH3ReferenceToVideo",
                    {
                        "clip": "CLIP", "vae": "VAE", "audio_vae": "VAE",
                        "prompt": "STRING", "width": "INT", "height": "INT", "length": "INT",
                        "ref_image_size": "COMBO",
                    },
                ),
                _node_signature_check(
                    object_info, "h3_audio_decode", "VAEDecodeAudio", {"samples": "LATENT", "vae": "VAE"}
                ),
                _node_signature_check(
                    object_info,
                    "h3_create_video",
                    "CreateVideo",
                    {"images": "IMAGE", "fps": "FLOAT"},
                ),
                _node_signature_check(
                    object_info,
                    "h3_save_video",
                    "SaveVideo",
                    {"video": "VIDEO", "filename_prefix": "STRING", "format": "COMBO"},
                ),
            ]
        )
        checks.extend(
            PreflightCheck(
                name=f"ambiguous_{role}",
                ok=False,
                detail=f"Ambiguous H3 {role} candidates: {', '.join(candidates)}",
            )
            for role, candidates in ambiguities.items()
        )
    elif provider == "minimax_h3_control_desk":
        checks.append(
            _node_contract_names_check(
                object_info,
                "h3_control_desk",
                "LtoJ_H3UnifiedControlDesk",
                required_inputs={"ui_state"},
            )
        )
    elif provider == "minimax_h3_motion_context":
        check_names = {
            "MiniMaxH3MotionContext": "h3_motion_context",
            "MiniMaxH3MotionContextTrim": "h3_motion_context_trim",
            "MiniMaxH3MotionContextSaveLatent": "h3_motion_context_save_latent",
            "MiniMaxH3MotionContextLoadLatent": "h3_motion_context_load_latent",
        }
        checks.extend(
            _node_contract_names_check(
                object_info,
                check_names[node_name],
                node_name,
                required_inputs=signature["required"],
                optional_inputs=signature["optional"],
            )
            for node_name, signature in MOTION_CONTEXT_NODE_SIGNATURES.items()
        )
    else:
        raise ValueError(f"Unsupported video provider: {provider}")

    capability_only = provider in {"minimax_h3_control_desk", "minimax_h3_motion_context"}
    if not capability_only:
        has_save_node = any(
            candidate in node_names
            for candidate in ("savevideo", "decodeandsavevideo", "vhs_videocombine")
        )
        checks.append(
            PreflightCheck(
                name="video_save_node",
                ok=has_save_node,
                detail="ComfyUI has a video output node" if has_save_node else "No video output node installed",
            )
        )

    missing.extend(check.name for check in checks if not check.ok)
    report = PreflightReport(
        provider=provider,
        ok=not missing,
        missing=missing,
        checks=checks,
    )
    if provider == "minimax_h3_ref2va":
        report.resolved = resolved
        report.ambiguities = ambiguities
    return report


async def run_preflight(
    provider: str = "ltx23",
    comfy_url: str = "http://127.0.0.1:8188",
    output_root: str | Path = "projects",
) -> PreflightReport:
    object_info = await asyncio.to_thread(_fetch_json, f"{comfy_url}/object_info")
    report = inspect_object_info(object_info, provider)

    for executable in ("ffmpeg", "ffprobe"):
        resolved = shutil.which(executable)
        check = PreflightCheck(
            name=executable,
            ok=resolved is not None,
            detail=resolved or f"{executable} is not on PATH",
        )
        report.checks.append(check)
        if not check.ok:
            report.missing.append(executable)

    output = Path(output_root)
    try:
        output.mkdir(parents=True, exist_ok=True)
        probe = output / ".write-probe"
        probe.write_bytes(b"ok")
        probe.unlink()
        writable = True
        detail = str(output.resolve())
    except OSError as error:
        writable = False
        detail = str(error)

    report.checks.append(PreflightCheck("output_writable", writable, detail))
    if not writable:
        report.missing.append("output_writable")
    report.ok = not report.missing
    return report


def _fetch_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=20) as response:
        return json.load(response)


def _model_choices(
    object_info: dict[str, Any],
    node_name: str,
    input_name: str,
) -> list[str]:
    value = (
        object_info.get(node_name, {})
        .get("input", {})
        .get("required", {})
        .get(input_name, [])
    )
    if isinstance(value, list) and value and isinstance(value[0], list):
        return [str(item) for item in value[0]]
    return []


def _contains_check(
    name: str,
    choices: list[str],
    required_parts: tuple[str, ...],
) -> PreflightCheck:
    lowered = [choice.lower() for choice in choices]
    match = next(
        (
            choice
            for choice, original in zip(lowered, choices)
            if all(part.lower() in choice for part in required_parts)
        ),
        "",
    )
    return PreflightCheck(
        name=name,
        ok=bool(match),
        detail=match or f"Missing model containing: {', '.join(required_parts)}",
    )


def _any_contains_check(
    name: str,
    choices: list[str],
    alternatives: tuple[str, ...],
) -> PreflightCheck:
    lowered = [choice.lower() for choice in choices]
    match = next(
        (
            original
            for choice, original in zip(lowered, choices)
            if any(part.lower() in choice for part in alternatives)
        ),
        "",
    )
    return PreflightCheck(
        name=name,
        ok=bool(match),
        detail=match or f"Missing model containing one of: {', '.join(alternatives)}",
    )


def _resolve_h3_models(
    unets: list[str], clips: list[str], vaes: list[str]
) -> tuple[ResolvedH3Models, dict[str, list[str]]]:
    """Resolve stable H3 capability roles, refusing equal-preference local alternatives."""
    rules = {
        "diffusion_model": (unets, ("minimax", "h3", "ref2va"), ("pruned", "int8", "convrot")),
        "text_encoder": (clips, ("qwen", "h3"), ("qwen3vl", "32b", "nvfp4", "awq")),
        "video_vae": (vaes, ("minimax", "h3", "video", "vae"), ("fp16",)),
        "audio_vae": (vaes, ("minimax", "h3", "audio", "vae"), ("fp32",)),
    }
    resolved: ResolvedH3Models = {
        "diffusion_model": "", "text_encoder": "", "video_vae": "", "audio_vae": "",
    }
    ambiguities: dict[str, list[str]] = {}
    for role, (choices, required, preferred) in rules.items():
        selected, tied = _resolve_model_role(choices, required, preferred)
        resolved[role] = selected
        if tied:
            ambiguities[role] = tied
    return resolved, ambiguities


def _resolve_model_role(
    choices: list[str], required_parts: tuple[str, ...], preferred_parts: tuple[str, ...]
) -> tuple[str, list[str]]:
    candidates = sorted(
        (choice for choice in choices if all(part in _normalise_model_name(choice) for part in required_parts)),
        key=_normalise_model_name,
    )
    if not candidates:
        return "", []
    scores = {choice: sum(part in _normalise_model_name(choice) for part in preferred_parts) for choice in candidates}
    best_score = max(scores.values())
    best = [choice for choice in candidates if scores[choice] == best_score]
    if len(best) != 1:
        return "", best
    return best[0], []


def _normalise_model_name(value: str) -> str:
    return value.replace("\\", "/").casefold()


def _resolved_model_check(name: str, filename: str) -> PreflightCheck:
    return PreflightCheck(
        name=name,
        ok=bool(filename),
        detail=filename or f"No installed model matches the H3 {name} role",
    )


def _node_contract_names_check(
    object_info: dict[str, Any],
    check_name: str,
    node_name: str,
    *,
    required_inputs: set[str],
    optional_inputs: set[str] | None = None,
) -> PreflightCheck:
    node_input = object_info.get(node_name, {}).get("input", {})
    required = node_input.get("required", {})
    optional = node_input.get("optional", {})
    if not isinstance(required, dict) or not isinstance(optional, dict):
        return PreflightCheck(check_name, False, f"ComfyUI node {node_name} is unavailable")

    absent_required = sorted(set(required_inputs) - set(required))
    absent_optional = sorted(set(optional_inputs or ()) - set(optional))
    if absent_required or absent_optional:
        problems: list[str] = []
        if absent_required:
            problems.append(f"missing required inputs: {', '.join(absent_required)}")
        if absent_optional:
            problems.append(f"missing optional inputs: {', '.join(absent_optional)}")
        return PreflightCheck(check_name, False, f"{node_name} has {'; '.join(problems)}")

    return PreflightCheck(check_name, True, f"{node_name} exposes the expected H3 capability inputs")


def _node_signature_check(
    object_info: dict[str, Any],
    check_name: str,
    node_name: str,
    required_inputs: dict[str, str],
) -> PreflightCheck:
    """Require the native Ref2VA node and the inputs the approved workflow binds."""
    required = (
        object_info.get(node_name, {})
        .get("input", {})
        .get("required", {})
    )
    if not isinstance(required, dict):
        return PreflightCheck(check_name, False, f"ComfyUI node {node_name} is unavailable")
    absent = sorted(set(required_inputs) - set(required))
    mismatched = sorted(
        f"{name}={_input_descriptor(required[name])!r} (expected {expected})"
        for name, expected in required_inputs.items()
        if name in required and _input_descriptor(required[name]) != expected
    )
    if absent or mismatched:
        problems = []
        if absent:
            problems.append(f"missing required inputs: {', '.join(absent)}")
        if mismatched:
            problems.append(f"wrong descriptors: {', '.join(mismatched)}")
        return PreflightCheck(
            check_name,
            False,
            f"{node_name} has {'; '.join(problems)}",
        )
    return PreflightCheck(check_name, True, f"{node_name} exposes the native H3 input signature")


def _input_descriptor(spec: Any) -> str:
    if not isinstance(spec, list) or not spec:
        return ""
    value = spec[0]
    return str(value).upper() if isinstance(value, str) else ""

from __future__ import annotations

import hashlib
import json
from typing import Any


CANONICAL_STAGES = [
    "load_input",
    "planning",
    "character_design",
    "visual_generate",
    "video_generate",
    "audio_tts",
    "composition_compose",
]

_REQUIRED_STAGES = {
    "load_input",
    "planning",
    "character_design",
    "visual_generate",
    "video_generate",
    "composition_compose",
}

_KNOWN_PROVIDERS = {"minimax_h3", "wan", "flux", "cosyvoice"}
_PROVIDER_MODES = {"runtime_default", "preferred", "required"}
_FORBIDDEN_KEYS = {
    "skip_qc",
    "bypass_qc",
    "disable_qc",
    "skip_review",
    "bypass_review",
    "auto_approve_review",
    "auto_approve",
}
_PRODUCTION_KEYS = {"shot_duration", "width", "height", "fps", "options"}
_OPTION_KEYS = {"style", "local_first"}


class TemplateValidationError(ValueError):
    def __init__(self, message: str, code: str = "TEMPLATE_VALIDATION_FAILED"):
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(normalize_json(value).encode("utf-8")).hexdigest()


class CanonicalTemplateCompiler:
    def __init__(self, available_providers: set[str] | None = None):
        self.available_providers = set(available_providers or _KNOWN_PROVIDERS)

    def compile(self, value: dict[str, object]) -> dict[str, object]:
        if int(value.get("schema_version") or 0) != 1:
            raise TemplateValidationError("unsupported schema version")
        self._reject_forbidden(value)

        canvas = value.get("canvas")
        if not isinstance(canvas, dict):
            raise TemplateValidationError("canvas must be an object")
        nodes = canvas.get("nodes")
        edges = canvas.get("edges")
        if not isinstance(nodes, list) or not isinstance(edges, list):
            raise TemplateValidationError("canvas nodes and edges must be lists")

        node_stages: dict[str, str] = {}
        stage_counts: dict[str, int] = {}
        for node in nodes:
            if not isinstance(node, dict):
                raise TemplateValidationError("canvas node must be an object")
            node_id = str(node.get("id") or "")
            data = node.get("data")
            stage_key = str(data.get("stageKey") or "") if isinstance(data, dict) else ""
            if not node_id or not stage_key:
                continue
            if stage_key not in CANONICAL_STAGES:
                raise TemplateValidationError(f"unknown stage: {stage_key}")
            node_stages[node_id] = stage_key
            stage_counts[stage_key] = stage_counts.get(stage_key, 0) + 1

        present = set(node_stages.values())
        missing_required = sorted(_REQUIRED_STAGES - present)
        if missing_required:
            raise TemplateValidationError(
                f"required stage missing: {', '.join(missing_required)}",
                code="TEMPLATE_STAGE_POLICY_INVALID",
            )

        self._validate_dependencies(edges, node_stages, stage_counts)
        stage_policy = self._compile_stage_policy(value.get("stage_policy"))
        production = self._compile_production(value.get("production"))

        return {
            "schema_version": 1,
            "production": production,
            "canonical_stages": [stage for stage in CANONICAL_STAGES if stage in present],
            "stage_policy": stage_policy,
        }

    def _validate_dependencies(
        self,
        edges: list[object],
        node_stages: dict[str, str],
        stage_counts: dict[str, int],
    ) -> None:
        order = {stage: index for index, stage in enumerate(CANONICAL_STAGES)}
        for edge in edges:
            if not isinstance(edge, dict):
                raise TemplateValidationError("canvas edge must be an object")
            source_id = str(edge.get("source") or "")
            target_id = str(edge.get("target") or "")
            source_stage = node_stages.get(source_id)
            target_stage = node_stages.get(target_id)
            if not source_stage or not target_stage or source_stage == target_stage:
                continue

            # The current Canvas exposes two UI views of the single planning
            # stage: scene before character design and storyboard after it.
            # Only that known alias bridge may look reverse relative to the
            # canonical pipeline. Do not broadly exempt every edge touching a
            # duplicated stage, because that would allow video -> scene/planning.
            if (
                target_id == "storyboard"
                and target_stage == "planning"
                and source_stage == "character_design"
                and stage_counts.get("planning", 0) > 1
            ):
                continue

            if order[source_stage] > order[target_stage]:
                raise TemplateValidationError(
                    f"invalid canonical dependency: {source_stage} -> {target_stage}",
                    code="TEMPLATE_STAGE_POLICY_INVALID",
                )

    def _compile_stage_policy(self, raw: object) -> list[dict[str, object]]:
        if raw is None:
            return []
        if not isinstance(raw, dict):
            raise TemplateValidationError("stage_policy must be an object")
        stages = raw.get("stages", [])
        if not isinstance(stages, list):
            raise TemplateValidationError("stage_policy.stages must be a list")

        compiled: list[dict[str, object]] = []
        seen: set[str] = set()
        for item in stages:
            if not isinstance(item, dict):
                raise TemplateValidationError("stage policy entry must be an object")
            stage_key = str(item.get("stage_key") or "")
            if stage_key not in CANONICAL_STAGES:
                raise TemplateValidationError(f"unknown stage: {stage_key}")
            if stage_key in seen:
                raise TemplateValidationError(f"duplicate stage policy: {stage_key}")
            seen.add(stage_key)

            enabled = bool(item.get("enabled", True))
            if not enabled and stage_key in _REQUIRED_STAGES:
                raise TemplateValidationError(
                    f"required stage cannot be disabled: {stage_key}",
                    code="TEMPLATE_STAGE_POLICY_INVALID",
                )

            entry: dict[str, object] = {"stage_key": stage_key, "enabled": enabled}
            provider_policy = item.get("provider_policy")
            if provider_policy is not None:
                entry["provider_policy"] = self._compile_provider_policy(provider_policy)
            compiled.append(entry)
        return compiled

    def _compile_provider_policy(self, raw: object) -> dict[str, object]:
        if not isinstance(raw, dict):
            raise TemplateValidationError("provider_policy must be an object")
        mode = str(raw.get("mode") or "runtime_default")
        if mode not in _PROVIDER_MODES:
            raise TemplateValidationError(f"unsupported provider mode: {mode}")
        provider = str(raw.get("provider") or "")
        fallback = str(raw.get("fallback") or "")
        if provider and provider not in _KNOWN_PROVIDERS:
            raise TemplateValidationError(
                f"unknown provider: {provider}", code="TEMPLATE_PROVIDER_POLICY_UNSUPPORTED"
            )
        if fallback and fallback not in _KNOWN_PROVIDERS:
            raise TemplateValidationError(
                f"unknown provider fallback: {fallback}",
                code="TEMPLATE_PROVIDER_POLICY_UNSUPPORTED",
            )

        result: dict[str, object] = {"mode": mode}
        if provider:
            result["provider"] = provider
        if fallback:
            result["fallback"] = fallback

        if mode == "required":
            if not provider:
                raise TemplateValidationError("required provider must be specified")
            if provider not in self.available_providers:
                raise TemplateValidationError(
                    f"required provider unavailable: {provider}",
                    code="TEMPLATE_PROVIDER_POLICY_UNSUPPORTED",
                )
        elif mode == "preferred" and provider and provider not in self.available_providers:
            if not fallback or fallback not in self.available_providers:
                raise TemplateValidationError(
                    f"preferred provider unavailable without supported fallback: {provider}",
                    code="TEMPLATE_PROVIDER_POLICY_UNSUPPORTED",
                )
        return result

    def _compile_production(self, raw: object) -> dict[str, object]:
        if not isinstance(raw, dict):
            raise TemplateValidationError("production must be an object")
        unknown = set(raw) - _PRODUCTION_KEYS
        if unknown:
            raise TemplateValidationError(f"unknown production field: {sorted(unknown)[0]}")

        options_raw = raw.get("options", {})
        if not isinstance(options_raw, dict):
            raise TemplateValidationError("production.options must be an object")
        unknown_options = set(options_raw) - _OPTION_KEYS
        if unknown_options:
            raise TemplateValidationError(f"unknown production option: {sorted(unknown_options)[0]}")

        shot_duration = int(raw.get("shot_duration") or 5)
        width = int(raw.get("width") or 1080)
        height = int(raw.get("height") or 1920)
        fps = int(raw.get("fps") or 24)
        if shot_duration <= 0 or width <= 0 or height <= 0 or fps <= 0:
            raise TemplateValidationError("production numeric values must be positive")

        return {
            "shot_duration": shot_duration,
            "width": width,
            "height": height,
            "fps": fps,
            "options": {
                "style": str(options_raw.get("style") or "anime"),
                "local_first": bool(options_raw.get("local_first", True)),
            },
        }

    def _reject_forbidden(self, value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if str(key) in _FORBIDDEN_KEYS:
                    raise TemplateValidationError(f"forbidden template field: {key}")
                self._reject_forbidden(nested)
        elif isinstance(value, list):
            for nested in value:
                self._reject_forbidden(nested)

"""OpenMontage-inspired provider scoring and tool registry for AI Manga Studio.

Reimplements OpenMontage's 7-dimensional provider scoring engine and tool
registry pattern as a self-contained integration. The scoring engine replaces
naive "first available provider" selection with weighted multi-dimensional
scoring -- every provider choice is explainable, not just "it was available."

This module does NOT import from OpenMontage directly. The scoring logic is
reimplemented here so AI Manga Studio carries no hard dependency on the
external repo.

Scoring dimensions (higher is better, each normalized 0-1):

    task_fit        30%  -- how well the provider matches the task type
    output_quality  20%  -- expected fidelity for the brief
    control         15%  -- user controllability (reference / style directability)
    reliability     15%  -- runtime confidence / uptime stability
    cost_efficiency 10%  -- quality per dollar
    latency          5%  -- acceptable turnaround
    continuity       5%  -- fits already-locked decisions (shot consistency)

Default video providers registered for AI Manga Studio:

    wan22      ComfyUI + Wan2.2 image-to-video (cinematic, GPU-bound)
    ltx23      ComfyUI + LTX-Video image-to-video (faster, lighter GPU)
    ken_burns   FFmpeg Ken Burns zoom/pan on static images (registered but disabled —
                not a real AI video, never used as fallback)
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ProviderStatus(str, Enum):
    """Live availability state of a registered provider."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


class ProviderRuntime(str, Enum):
    """Where and how a provider executes."""

    LOCAL = "local"          # runs entirely on-device, free, no network
    LOCAL_GPU = "local_gpu"  # runs on-device but needs GPU (VRAM)
    API = "api"              # calls an external API, requires key, costs money
    HYBRID = "hybrid"        # can run locally OR via API


class ProviderStability(str, Enum):
    """Maturity / stability tier of a provider."""

    EXPERIMENTAL = "experimental"
    BETA = "beta"
    PRODUCTION = "production"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ProviderCapabilities(BaseModel):
    """Declared capability envelope for a provider (the "contract")."""

    best_for: list[str] = Field(
        default_factory=list,
        description="Short descriptors of what this provider excels at.",
    )
    not_good_for: list[str] = Field(
        default_factory=list,
        description="Descriptors of tasks this provider handles poorly.",
    )
    supports: dict[str, Any] = Field(
        default_factory=dict,
        description="Feature flags, e.g. reference_image, motion_control, seed.",
    )

    model_config = {"extra": "allow"}


class ProviderConfig(BaseModel):
    """Runtime / operational configuration for a registered provider."""

    provider: str = "unknown"
    runtime: ProviderRuntime = ProviderRuntime.LOCAL
    stability: ProviderStability = ProviderStability.EXPERIMENTAL
    cost_per_shot_usd: float = 0.0
    latency_p50_seconds: float | None = None
    quality_score: float | None = None
    historical_success_rate: float | None = None
    dependencies: list[str] = Field(
        default_factory=list,
        description="Required deps, e.g. 'env:COMFYUI_URL', 'cmd:ffmpeg'.",
    )
    install_instructions: str = ""
    fallback: str | None = None
    fallback_tools: list[str] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class RegisteredProvider(BaseModel):
    """A fully registered provider: identity + capabilities + config + status."""

    name: str
    capabilities: ProviderCapabilities = Field(default_factory=ProviderCapabilities)
    config: ProviderConfig = Field(default_factory=ProviderConfig)
    status: ProviderStatus = ProviderStatus.AVAILABLE

    model_config = {"extra": "allow"}


class TaskParams(BaseModel):
    """Normalized task context passed to the scoring engine.

    Maps directly to OpenMontage's task_context dict but typed.
    """

    task_type: str = "video"
    intent: str = ""
    style_keywords: list[str] = Field(default_factory=list)
    motion_required: bool = True
    asset_type: str = "video"
    budget_remaining_usd: float | None = None
    locked_providers: list[str] = Field(default_factory=list)
    shot_id: str = ""
    duration: float = 5.0

    model_config = {"extra": "allow"}


class ProviderScoreBreakdown(BaseModel):
    """Full scored evaluation of one provider against a task context."""

    provider_name: str
    task_fit: float = 0.0
    output_quality: float = 0.0
    control: float = 0.0
    reliability: float = 0.0
    cost_efficiency: float = 0.0
    latency: float = 0.0
    continuity: float = 0.0
    weighted_score: float = 0.0  # 0-1

    def to_dict(self) -> dict[str, Any]:
        data = self.model_dump()
        data["score_100"] = round(self.weighted_score * 100, 2)
        return data


class CostEstimate(BaseModel):
    """Result of the estimate phase in the cost lifecycle."""

    shot_id: str
    provider: str
    estimated_cost_usd: float
    budget_remaining_usd: float
    within_budget: bool


class CostRecord(BaseModel):
    """A reconciled per-shot cost entry."""

    shot_id: str
    provider: str
    estimated_cost_usd: float = 0.0
    reserved_usd: float = 0.0
    actual_cost_usd: float = 0.0
    status: str = "estimated"  # estimated | reserved | reconciled


class ProviderStatusEntry(BaseModel):
    """One row of the provider status report."""

    name: str
    provider: str
    status: str
    runtime: str
    stability: str
    best_for: list[str] = Field(default_factory=list)
    cost_per_shot_usd: float = 0.0

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Provider scoring engine
# ---------------------------------------------------------------------------

# Semantic synonym clusters: when intent says "cinematic" and a provider's
# best_for says "film" or "movie", that's a match even without literal keyword
# overlap. Adapted from OpenMontage with manga/anime-specific additions.
_SYNONYM_CLUSTERS: list[set[str]] = [
    {"cinematic", "film", "movie", "trailer", "dramatic", "epic"},
    {"action", "fight", "combat", "chase", "dynamic", "movement"},
    {"dialogue", "talking", "conversation", "speech", "talking-head"},
    {"narration", "voiceover", "narrator", "monologue"},
    {"static", "still", "portrait", "close-up", "subtle"},
    {"animation", "animated", "motion-graphics", "motion", "kinetic"},
    {"anime", "manga", "stylized", "cel-shaded", "illustration"},
    {"realistic", "photorealistic", "lifelike", "natural"},
    {"social", "tiktok", "instagram", "reels", "shorts", "viral"},
]

_TOKEN_RE = re.compile(r"[a-z0-9](?:[a-z0-9+._-]*[a-z0-9])?")

# Control features weighted by creative impact. Higher weight = more control.
# Adapted for video generation: reference_image and motion_control are the
# most valuable levers; seed/custom_resolution are nice-to-haves.
_CONTROL_FEATURES: list[tuple[str, float]] = [
    ("reference_image", 2.0),
    ("motion_control", 1.8),
    ("img2img", 1.6),
    ("style_transfer", 1.5),
    ("inpainting", 1.5),
    ("negative_prompt", 1.0),
    ("custom_resolution", 0.8),
    ("multi_shot", 0.7),
    ("seed", 0.5),
]


def _tokenize_text(value: str) -> list[str]:
    """Tokenize a string into lowercase alphanumeric tokens."""
    return _TOKEN_RE.findall((value or "").lower())


def _expand_synonyms(words: set[str]) -> set[str]:
    """Expand a word set with synonyms from known clusters."""
    expanded = set(words)
    for cluster in _SYNONYM_CLUSTERS:
        if expanded & cluster:
            expanded |= cluster
    return expanded


def _keyword_overlap(set_a: set[str], set_b: set[str]) -> float:
    """Overlap coefficient between two keyword sets.

    Uses |A & B| / min(|A|, |B|) rather than Jaccard. Jaccard over-penalizes
    providers whose best_for describes many strengths -- a premium provider
    with seven rich descriptors ends up with a smaller Jaccard than a narrowly
    scoped provider, even when the premium provider fully covers the intent.
    Overlap coefficient answers: "is the intent a subset of what this provider
    advertises?" which is what we actually care about for scoring.
    """
    if not set_a or not set_b:
        return 0.0
    a = {s.lower().strip() for s in set_a}
    b = {s.lower().strip() for s in set_b}
    intersection = len(a & b)
    smaller = min(len(a), len(b))
    return intersection / smaller if smaller > 0 else 0.0


class ProviderScoring:
    """7-dimensional provider scoring engine.

    Reimplements OpenMontage's ``lib/scoring.py`` scoring logic. Scores are
    normalized 0-1 internally; :meth:`score_provider` returns 0-100 for
    consumer-facing convenience.
    """

    # Dimension weights -- must sum to 1.0.
    WEIGHTS: dict[str, float] = {
        "task_fit": 0.30,
        "output_quality": 0.20,
        "control": 0.15,
        "reliability": 0.15,
        "cost_efficiency": 0.10,
        "latency": 0.05,
        "continuity": 0.05,
    }

    def __init__(self, providers: dict[str, RegisteredProvider] | None = None) -> None:
        # Use ``is not None`` rather than ``or`` so that an empty dict passed
        # by reference (e.g. from a registry that hasn't registered providers
        # yet) keeps the SAME dict object -- later mutations are visible here.
        self._providers: dict[str, RegisteredProvider] = (
            providers if providers is not None else {}
        )

    # -- wiring ----------------------------------------------------------

    def bind(self, providers: dict[str, RegisteredProvider]) -> None:
        """Bind the scoring engine to a live provider map (registry-owned)."""
        self._providers = providers

    # -- public API ------------------------------------------------------

    def score_provider(self, provider_name: str, task_params: TaskParams) -> float:
        """Score a single provider against a task context, returning 0-100.

        Args:
            provider_name: Registered provider name (e.g. ``"wan22"``).
            task_params: Normalized task context.

        Returns:
            Weighted score in the range 0-100. Returns 0.0 if the provider is
            unknown or unavailable.
        """
        breakdown = self.score_provider_detailed(provider_name, task_params)
        return round(breakdown.weighted_score * 100, 2)

    def score_provider_detailed(
        self,
        provider_name: str,
        task_params: TaskParams,
    ) -> ProviderScoreBreakdown:
        """Score a provider and return the full dimensional breakdown (0-1)."""
        provider = self._providers.get(provider_name)
        if provider is None:
            return ProviderScoreBreakdown(provider_name=provider_name)

        caps = provider.capabilities
        cfg = provider.config

        # --- task_fit ---
        best_for = set(caps.best_for)
        # Fold task_type into intent so it participates in keyword matching.
        intent = " ".join(part for part in (task_params.task_type, task_params.intent) if part)
        style_keywords = set(task_params.style_keywords)
        task_fit = self._compute_task_fit(best_for, intent, style_keywords)

        # --- reliability ---
        reliability = self._compute_reliability(provider.status, cfg)

        # --- control ---
        control = self._compute_control(caps.supports)

        # --- cost_efficiency ---
        cost_efficiency = self._compute_cost_efficiency(
            cfg.cost_per_shot_usd, task_params.budget_remaining_usd
        )

        # --- latency ---
        latency = self._compute_latency(cfg)

        # --- continuity ---
        continuity = self._compute_continuity(
            cfg.provider, set(task_params.locked_providers)
        )

        # --- output_quality ---
        output_quality = self._compute_output_quality(cfg)

        # --- conditional adjustments (mirror OpenMontage) ---

        # Motion-required penalty: if the task needs motion but the provider
        # is image-only (no video capability), heavily penalize task_fit.
        if task_params.motion_required and task_params.asset_type == "video":
            if not caps.supports.get("video_generation") and not caps.supports.get("img2video"):
                task_fit *= 0.2

        # Reference-conditioning bonus: when the task wants reference image
        # conditioning, reward providers that support it.
        wants_reference = bool(
            style_keywords & {"character", "consistency", "identity", "reference", "preserve"}
        )
        if wants_reference and task_params.asset_type == "video":
            if caps.supports.get("reference_image") or caps.supports.get("img2img"):
                task_fit = min(1.0, task_fit + 0.18)
                control = min(1.0, control + 0.12)
            else:
                task_fit *= 0.7

        # Cinematic bonus: reward providers with premium cinematic features
        # (motion control, multi-shot, camera direction) when intent is cinematic.
        intent_words = _expand_synonyms(set(_tokenize_text(intent))) | set(style_keywords)
        cinematic_signal = bool(
            intent_words & {"cinematic", "film", "movie", "trailer", "dramatic", "epic", "action"}
        )
        if cinematic_signal and task_params.asset_type == "video":
            premium_features = [
                caps.supports.get("motion_control"),
                caps.supports.get("multi_shot"),
                caps.supports.get("camera_direction"),
                caps.supports.get("cinematic_quality"),
            ]
            matched = sum(1 for f in premium_features if f)
            if matched >= 3:
                task_fit = min(1.0, task_fit + 0.15)
                output_quality = min(1.0, output_quality + 0.10)
            elif matched >= 1:
                task_fit = min(1.0, task_fit + 0.05)

        # Unavailable providers score zero on the weighted total -- a provider
        # that cannot run should never win selection, even if its theoretical
        # fit is high. We zero the final weighted score rather than each dim
        # so the breakdown still explains *why* it would have been good.
        if provider.status == ProviderStatus.UNAVAILABLE:
            weighted = 0.0
        else:
            weighted = (
                task_fit * self.WEIGHTS["task_fit"]
                + output_quality * self.WEIGHTS["output_quality"]
                + control * self.WEIGHTS["control"]
                + reliability * self.WEIGHTS["reliability"]
                + cost_efficiency * self.WEIGHTS["cost_efficiency"]
                + latency * self.WEIGHTS["latency"]
                + continuity * self.WEIGHTS["continuity"]
            )

        return ProviderScoreBreakdown(
            provider_name=provider_name,
            task_fit=round(task_fit, 4),
            output_quality=round(output_quality, 4),
            control=round(control, 4),
            reliability=round(reliability, 4),
            cost_efficiency=round(cost_efficiency, 4),
            latency=round(latency, 4),
            continuity=round(continuity, 4),
            weighted_score=round(weighted, 4),
        )

    def rank_providers(
        self,
        provider_names: list[str],
        task_params: TaskParams,
    ) -> list[ProviderScoreBreakdown]:
        """Rank a list of providers by weighted score, best-first."""
        scores = [self.score_provider_detailed(name, task_params) for name in provider_names]
        return sorted(scores, key=lambda s: s.weighted_score, reverse=True)

    def explain(self, provider_name: str, task_params: TaskParams) -> str:
        """Human-readable explanation of a provider's score."""
        b = self.score_provider_detailed(provider_name, task_params)
        parts = [f"{provider_name}: {b.weighted_score * 100:.1f}/100"]
        top = sorted(
            [
                ("task_fit", b.task_fit, self.WEIGHTS["task_fit"]),
                ("output_quality", b.output_quality, self.WEIGHTS["output_quality"]),
                ("control", b.control, self.WEIGHTS["control"]),
                ("reliability", b.reliability, self.WEIGHTS["reliability"]),
                ("cost_efficiency", b.cost_efficiency, self.WEIGHTS["cost_efficiency"]),
                ("latency", b.latency, self.WEIGHTS["latency"]),
                ("continuity", b.continuity, self.WEIGHTS["continuity"]),
            ],
            key=lambda x: x[1] * x[2],
            reverse=True,
        )
        for name, val, weight in top[:3]:
            parts.append(f"  {name}={val:.2f} (w={weight})")
        return "\n".join(parts)

    # -- dimension calculators ------------------------------------------

    @staticmethod
    def _compute_task_fit(
        best_for: set[str],
        intent: str,
        style_keywords: set[str],
    ) -> float:
        """Score how well a provider's best_for matches intent and style.

        Uses synonym expansion and tokenization so semantic near-misses
        (e.g. "cinematic" vs "film") still score well.
        """
        if not best_for:
            return 0.3  # Unknown capability -- modest default

        intent_words = _expand_synonyms(set(_tokenize_text(intent)))
        best_for_words: set[str] = set()
        for desc in best_for:
            best_for_words.update(_tokenize_text(desc))
        best_for_words = _expand_synonyms(best_for_words)

        intent_score = _keyword_overlap(intent_words, best_for_words)

        style_expanded = _expand_synonyms({kw.lower() for kw in style_keywords})
        style_score = _keyword_overlap(style_expanded, best_for_words)

        return min(1.0, intent_score * 0.7 + style_score * 0.3 + 0.1)

    @staticmethod
    def _compute_reliability(
        status: ProviderStatus,
        cfg: ProviderConfig,
    ) -> float:
        """Score runtime confidence. Uses historical success rate if tracked."""
        if cfg.historical_success_rate is not None:
            return float(cfg.historical_success_rate)
        if status == ProviderStatus.AVAILABLE:
            # Production-stable providers get a higher baseline than experimental.
            return 0.95 if cfg.stability == ProviderStability.PRODUCTION else 0.8
        if status == ProviderStatus.DEGRADED:
            return 0.4
        return 0.0

    @staticmethod
    def _compute_control(supports: dict[str, Any]) -> float:
        """Score controllability from the supports dict.

        Features are weighted by creative impact -- reference_image and
        motion_control are worth more than seed or custom_resolution.
        """
        if not supports:
            return 0.3
        total_weight = sum(w for _, w in _CONTROL_FEATURES)
        earned = sum(w for f, w in _CONTROL_FEATURES if supports.get(f))
        return min(1.0, earned / (total_weight * 0.5))

    @staticmethod
    def _compute_cost_efficiency(
        estimated_cost: float,
        budget_remaining: float | None,
    ) -> float:
        """Score cost efficiency. Free is 1.0, over-budget is 0.0."""
        if estimated_cost <= 0:
            return 1.0
        if budget_remaining is not None and budget_remaining <= 0:
            return 0.0
        if budget_remaining is not None:
            ratio = estimated_cost / budget_remaining if budget_remaining > 0 else 1.0
            if ratio > 0.5:
                return 0.1
            if ratio > 0.2:
                return 0.5
            return 0.8
        # No budget info -- use absolute cost heuristic.
        if estimated_cost < 0.05:
            return 0.9
        if estimated_cost < 0.20:
            return 0.7
        if estimated_cost < 1.00:
            return 0.5
        return 0.3

    @staticmethod
    def _compute_latency(cfg: ProviderConfig) -> float:
        """Score latency. Uses measured p50 if available, else runtime heuristic."""
        if cfg.latency_p50_seconds is not None:
            p50 = cfg.latency_p50_seconds
            if p50 <= 1.0:
                return 1.0
            if p50 <= 10.0:
                return 0.8
            if p50 <= 30.0:
                return 0.6
            if p50 <= 60.0:
                return 0.4
            return 0.2
        runtime = cfg.runtime
        if runtime in (ProviderRuntime.LOCAL, ProviderRuntime.LOCAL_GPU):
            return 0.9
        if runtime == ProviderRuntime.HYBRID:
            return 0.6
        return 0.4

    @staticmethod
    def _compute_continuity(
        provider_label: str,
        locked_providers: set[str],
    ) -> float:
        """Score how well this provider fits already-locked decisions."""
        if not locked_providers:
            return 0.5  # No prior context
        if provider_label in locked_providers:
            return 0.9  # Same provider = likely consistent style
        return 0.4  # Different provider = possible style break

    @staticmethod
    def _compute_output_quality(cfg: ProviderConfig) -> float:
        """Score expected output quality. Uses measured score if tracked."""
        if cfg.quality_score is not None:
            return float(cfg.quality_score)
        quality_map = {
            ProviderStability.PRODUCTION: 0.9,
            ProviderStability.BETA: 0.7,
            ProviderStability.EXPERIMENTAL: 0.4,
        }
        return quality_map.get(cfg.stability, 0.5)


# ---------------------------------------------------------------------------
# Video provider registry
# ---------------------------------------------------------------------------

# Default fallback chains per task type. Ordered best-quality-first so the
# orchestrator can try each in turn until one succeeds.
# GPT P0: Ken Burns (静态缩放) 已从兜底链移除——真实视频失败必须 FAILED，
# 不允许用"静态图缩放"冒充 AI 短剧视频。
_DEFAULT_FALLBACK_CHAINS: dict[str, list[str]] = {
    "cinematic": ["minimax_h3", "seedance", "wan22", "ltx23"],
    "action": ["minimax_h3", "seedance", "wan22", "ltx23"],
    "dialogue": ["seedance", "minimax_h3", "ltx23", "wan22"],
    "narration": ["seedance", "minimax_h3", "ltx23", "wan22"],
    "static": ["ltx23", "wan22", "seedance", "minimax_h3"],
    "default": ["minimax_h3", "seedance", "wan22", "ltx23"],
}


class VideoProviderRegistry:
    """Central registry of video generation providers for AI Manga Studio.

    Mirrors OpenMontage's ``ToolRegistry`` pattern: register providers, score
    them against a task, select the best, and expose a fallback chain.
    """

    def __init__(self) -> None:
        self._providers: dict[str, RegisteredProvider] = {}
        self._scoring = ProviderScoring(self._providers)
        self._fallback_chains: dict[str, list[str]] = dict(_DEFAULT_FALLBACK_CHAINS)
        self._register_defaults()

    # -- registration ----------------------------------------------------

    def register_provider(
        self,
        name: str,
        capabilities: ProviderCapabilities | dict[str, Any] | None = None,
        config: ProviderConfig | dict[str, Any] | None = None,
    ) -> None:
        """Register or replace a video provider.

        Args:
            name: Unique provider key (e.g. ``"wan22"``).
            capabilities: ``ProviderCapabilities`` or dict.
            config: ``ProviderConfig`` or dict.
        """
        if not name:
            raise ValueError("Provider name must be non-empty")

        caps = (
            capabilities
            if isinstance(capabilities, ProviderCapabilities)
            else ProviderCapabilities(**(capabilities or {}))
        )
        cfg = (
            config
            if isinstance(config, ProviderConfig)
            else ProviderConfig(**(config or {}))
        )
        self._providers[name] = RegisteredProvider(
            name=name,
            capabilities=caps,
            config=cfg,
            status=ProviderStatus.AVAILABLE,
        )

    def unregister_provider(self, name: str) -> None:
        """Remove a provider from the registry."""
        self._providers.pop(name, None)

    def set_provider_status(self, name: str, status: ProviderStatus) -> None:
        """Update the live status of a registered provider."""
        provider = self._providers.get(name)
        if provider is None:
            raise KeyError(f"Provider not registered: {name!r}")
        provider.status = status

    def set_fallback_chain(self, task_type: str, chain: list[str]) -> None:
        """Override the fallback chain for a task type."""
        self._fallback_chains[task_type] = list(chain)

    # -- lookup ----------------------------------------------------------

    def get_provider(self, name: str) -> RegisteredProvider | None:
        """Get a registered provider by name, or ``None``."""
        return self._providers.get(name)

    def list_all(self) -> list[str]:
        """List all registered provider names."""
        return list(self._providers.keys())

    def list_available(self) -> list[str]:
        """List provider names that are currently available (not unavailable)."""
        return [
            name
            for name, p in self._providers.items()
            if p.status != ProviderStatus.UNAVAILABLE
        ]

    # -- selection -------------------------------------------------------

    def select_best_provider(
        self,
        task_type: str,
        requirements: dict[str, Any] | TaskParams | None = None,
    ) -> str:
        """Select the highest-scoring available provider for a task.

        Args:
            task_type: e.g. ``"cinematic"``, ``"action"``, ``"static"``.
            requirements: Additional task context (budget, style, locked
                providers, etc.). Accepts a dict or ``TaskParams``.

        Returns:
            The name of the best provider. If no provider is available,
            returns ``""``.
        """
        task_params = self._normalize_task_params(task_type, requirements)

        candidates = [
            name
            for name, p in self._providers.items()
            if p.status != ProviderStatus.UNAVAILABLE
        ]
        if not candidates:
            return ""

        ranked = self._scoring.rank_providers(candidates, task_params)
        return ranked[0].provider_name

    def score_all(
        self,
        task_type: str,
        requirements: dict[str, Any] | TaskParams | None = None,
    ) -> list[ProviderScoreBreakdown]:
        """Score every registered provider for a task, best-first."""
        task_params = self._normalize_task_params(task_type, requirements)
        return self._scoring.rank_providers(list(self._providers.keys()), task_params)

    def get_fallback_chain(self, task_type: str) -> list[str]:
        """Return the ordered fallback chain for a task type.

        Filters the declared chain to only include currently-available
        providers. If the declared chain is exhausted, appends any remaining
        available providers ranked by score.
        """
        declared = self._fallback_chains.get(task_type) or self._fallback_chains["default"]
        available = set(self.list_available())

        chain = [name for name in declared if name in available]

        # If the declared chain has no available providers, dynamically build
        # one from all available providers ranked by a neutral task context.
        if not chain and available:
            neutral = TaskParams(task_type=task_type)
            ranked = self._scoring.rank_providers(list(available), neutral)
            chain = [r.provider_name for r in ranked]

        return chain

    # -- reporting -------------------------------------------------------

    def get_provider_status(self) -> list[dict[str, Any]]:
        """Return a list of provider status dicts for all providers."""
        entries: list[dict[str, Any]] = []
        for name, p in self._providers.items():
            entries.append(
                ProviderStatusEntry(
                    name=name,
                    provider=p.config.provider,
                    status=p.status.value,
                    runtime=p.config.runtime.value,
                    stability=p.config.stability.value,
                    best_for=p.capabilities.best_for,
                    cost_per_shot_usd=p.config.cost_per_shot_usd,
                ).model_dump()
            )
        return entries

    def get_provider_menu(self) -> dict[str, Any]:
        """Generate a provider menu for the frontend.

        Returns a dict shaped for UI display::

            {
              "available": [
                {"name": ..., "provider": ..., "best_for": ..., "runtime": ...},
                ...
              ],
              "unavailable": [ ... ],
              "total": 3,
              "configured": 2,
            }
        """
        available: list[dict[str, Any]] = []
        unavailable: list[dict[str, Any]] = []

        for name, p in self._providers.items():
            entry = {
                "name": name,
                "provider": p.config.provider,
                "runtime": p.config.runtime.value,
                "stability": p.config.stability.value,
                "best_for": p.capabilities.best_for,
                "cost_per_shot_usd": p.config.cost_per_shot_usd,
                "dependencies": p.config.dependencies,
                "install_instructions": p.config.install_instructions,
                "status": p.status.value,
            }
            if p.status == ProviderStatus.AVAILABLE:
                available.append(entry)
            else:
                unavailable.append(entry)

        available.sort(key=lambda e: (e["provider"], e["name"]))
        unavailable.sort(key=lambda e: (e["provider"], e["name"]))

        return {
            "available": available,
            "unavailable": unavailable,
            "total": len(self._providers),
            "configured": len(available),
        }

    def support_envelope(self) -> dict[str, Any]:
        """Full contract report for all providers (mirrors OpenMontage)."""
        return {
            name: {
                "name": name,
                "provider": p.config.provider,
                "status": p.status.value,
                "runtime": p.config.runtime.value,
                "stability": p.config.stability.value,
                "best_for": p.capabilities.best_for,
                "not_good_for": p.capabilities.not_good_for,
                "supports": p.capabilities.supports,
                "cost_per_shot_usd": p.config.cost_per_shot_usd,
                "latency_p50_seconds": p.config.latency_p50_seconds,
                "quality_score": p.config.quality_score,
                "historical_success_rate": p.config.historical_success_rate,
                "dependencies": p.config.dependencies,
                "fallback": p.config.fallback,
                "fallback_tools": p.config.fallback_tools,
            }
            for name, p in self._providers.items()
        }

    # -- internals -------------------------------------------------------

    @staticmethod
    def _normalize_task_params(
        task_type: str,
        requirements: dict[str, Any] | TaskParams | None,
    ) -> TaskParams:
        """Coerce loose requirements into a typed TaskParams."""
        if isinstance(requirements, TaskParams):
            if not requirements.task_type or requirements.task_type == "video":
                requirements = requirements.model_copy(update={"task_type": task_type})
            return requirements
        if requirements is None:
            requirements = {}
        data = dict(requirements)
        data.setdefault("task_type", task_type)
        return TaskParams(**data)

    def _register_defaults(self) -> None:
        """Register the three built-in video providers for AI Manga Studio."""
        # -- Wan2.2 via ComfyUI (cinematic, high quality, GPU-bound) --
        self.register_provider(
            name="wan22",
            capabilities=ProviderCapabilities(
                best_for=[
                    "cinematic video",
                    "action shots",
                    "dramatic motion",
                    "high-quality animation",
                    "anime style",
                ],
                not_good_for=["fast turnaround", "low-resource environments"],
                supports={
                    "img2img": True,
                    "reference_image": True,
                    "motion_control": True,
                    "negative_prompt": True,
                    "seed": True,
                    "custom_resolution": True,
                    "multi_shot": False,
                    "camera_direction": False,
                    "video_generation": True,
                    "img2video": True,
                    "cinematic_quality": True,
                },
            ),
            config=ProviderConfig(
                provider="comfyui-wan22",
                runtime=ProviderRuntime.LOCAL_GPU,
                stability=ProviderStability.BETA,
                cost_per_shot_usd=0.0,
                latency_p50_seconds=45.0,
                quality_score=0.88,
                historical_success_rate=0.85,
                dependencies=["env:COMFYUI_URL"],
                install_instructions="Start ComfyUI with Wan2.2 custom nodes installed.",
                fallback="ltx23",
                fallback_tools=["ltx23"],
            ),
        )

        # -- LTX-Video via ComfyUI (faster, lighter GPU) --
        self.register_provider(
            name="ltx23",
            capabilities=ProviderCapabilities(
                best_for=[
                    "fast video generation",
                    "dialogue scenes",
                    "narration",
                    "lightweight motion",
                ],
                not_good_for=["intense action", "cinematic trailers"],
                supports={
                    "img2img": True,
                    "reference_image": True,
                    "motion_control": False,
                    "negative_prompt": True,
                    "seed": True,
                    "custom_resolution": True,
                    "multi_shot": False,
                    "camera_direction": False,
                    "video_generation": True,
                    "img2video": True,
                    "cinematic_quality": False,
                },
            ),
            config=ProviderConfig(
                provider="comfyui-ltx",
                runtime=ProviderRuntime.LOCAL_GPU,
                stability=ProviderStability.BETA,
                cost_per_shot_usd=0.0,
                latency_p50_seconds=20.0,
                quality_score=0.72,
                historical_success_rate=0.82,
                dependencies=["env:COMFYUI_URL"],
                install_instructions="Start ComfyUI with LTX-Video custom nodes installed.",
                fallback=None,
                fallback_tools=[],
            ),
        )

        # -- FFmpeg Ken Burns (always available, free, fast) --
        self.register_provider(
            name="ken_burns",
            capabilities=ProviderCapabilities(
                best_for=[
                    "static scenes",
                    "portrait shots",
                    "fast turnaround",
                    "budget-friendly",
                    "subtle motion",
                ],
                not_good_for=["dynamic action", "cinematic motion", "character animation"],
                supports={
                    "reference_image": True,
                    "motion_control": False,
                    "negative_prompt": False,
                    "seed": True,
                    "custom_resolution": True,
                    "multi_shot": False,
                    "camera_direction": True,
                    "video_generation": False,
                    "img2video": False,
                    "cinematic_quality": False,
                },
            ),
            config=ProviderConfig(
                provider="ffmpeg",
                runtime=ProviderRuntime.LOCAL,
                stability=ProviderStability.PRODUCTION,
                cost_per_shot_usd=0.0,
                latency_p50_seconds=2.0,
                quality_score=0.5,
                historical_success_rate=0.98,
                dependencies=["cmd:ffmpeg"],
                install_instructions="Install FFmpeg or imageio-ffmpeg.",
                fallback=None,
                fallback_tools=[],
            ),
        )

        # -- MiniMax H3 (API-based, 2K/15s, native audio, tail-frame) --
        self.register_provider(
            name="minimax_h3",
            capabilities=ProviderCapabilities(
                best_for=[
                    "cinematic video",
                    "high-quality animation",
                    "long duration shots",
                    "native audio generation",
                    "tail-frame linking",
                    "2K resolution",
                    "short drama",
                ],
                not_good_for=["free generation", "offline use", "low-budget projects"],
                supports={
                    "img2img": True,
                    "reference_image": True,
                    "motion_control": True,
                    "negative_prompt": True,
                    "seed": False,
                    "custom_resolution": True,
                    "multi_shot": True,
                    "camera_direction": True,
                    "video_generation": True,
                    "img2video": True,
                    "cinematic_quality": True,
                    "tail_frame_linking": True,
                    "native_audio": True,
                    "first_last_frame": True,
                },
            ),
            config=ProviderConfig(
                provider="minimax-api",
                runtime=ProviderRuntime.API,
                stability=ProviderStability.BETA,
                cost_per_shot_usd=0.13,  # ~0.8 CNY/s * 10s / 7.2
                latency_p50_seconds=180.0,
                quality_score=0.95,
                historical_success_rate=0.90,
                dependencies=["env:MINIMAX_API_KEY"],
                install_instructions="Get API key from platform.minimax.io",
                fallback="seedance",
                fallback_tools=["seedance", "wan22"],
            ),
        )

        # -- Seedance 2.0 via Volcengine Ark (API, 1080p/15s, tail-frame) --
        self.register_provider(
            name="seedance",
            capabilities=ProviderCapabilities(
                best_for=[
                    "cinematic video",
                    "action shots",
                    "dramatic motion",
                    "tail-frame linking",
                    "1080p resolution",
                    "short drama",
                    "multi-shot continuity",
                ],
                not_good_for=["free generation", "offline use", "low-budget projects"],
                supports={
                    "img2img": True,
                    "reference_image": True,
                    "motion_control": True,
                    "negative_prompt": True,
                    "seed": False,
                    "custom_resolution": True,
                    "multi_shot": True,
                    "camera_direction": True,
                    "video_generation": True,
                    "img2video": True,
                    "cinematic_quality": True,
                    "tail_frame_linking": True,
                    "native_audio": True,
                    "first_last_frame": True,
                    "return_last_frame": True,
                },
            ),
            config=ProviderConfig(
                provider="volcengine-ark",
                runtime=ProviderRuntime.API,
                stability=ProviderStability.BETA,
                cost_per_shot_usd=0.10,  # ~0.7 CNY/s * 10s / 7.2
                latency_p50_seconds=120.0,
                quality_score=0.92,
                historical_success_rate=0.88,
                dependencies=["env:ARK_API_KEY"],
                install_instructions="Get API key from volcengine ark console",
                fallback="wan22",
                fallback_tools=["wan22", "ltx23"],
            ),
        )


# ---------------------------------------------------------------------------
# Cost tracker (simplified)
# ---------------------------------------------------------------------------

class CostTracker:
    """Simplified per-shot cost tracker with budget enforcement.

    Implements a three-phase lifecycle:

        1. **estimate** -- predict the cost of a shot before generation.
        2. **reserve**  -- earmark budget so concurrent shots don't overspend.
        3. **reconcile** -- settle the actual cost after generation completes.

    Budget enforcement: ``reserve`` and ``estimate`` both check whether the
    requested amount fits within the remaining budget (total budget minus
    already-spent minus already-reserved).
    """

    def __init__(self, total_budget_usd: float = 0.0) -> None:
        self._total_budget: float = total_budget_usd
        self._records: dict[str, CostRecord] = {}

    # -- lifecycle -------------------------------------------------------

    def estimate(
        self,
        shot_id: str,
        provider: str,
        cost_usd: float,
    ) -> CostEstimate:
        """Phase 1: estimate the cost of generating a shot.

        Does NOT deduct from budget. Use :meth:`reserve` to earmark funds.
        """
        remaining = self.get_remaining()
        within = cost_usd <= remaining
        return CostEstimate(
            shot_id=shot_id,
            provider=provider,
            estimated_cost_usd=cost_usd,
            budget_remaining_usd=remaining,
            within_budget=within,
        )

    def reserve(self, shot_id: str, amount: float) -> bool:
        """Phase 2: reserve budget for a shot.

        Returns ``True`` if the reservation succeeded (enough budget),
        ``False`` if it would exceed the remaining budget.
        """
        if amount < 0:
            raise ValueError("Reserve amount must be non-negative")

        existing = self._records.get(shot_id)
        previously_reserved = existing.reserved_usd if existing else 0.0
        previously_spent = existing.actual_cost_usd if existing and existing.status == "reconciled" else 0.0

        # The net new commitment is `amount` minus what was already reserved.
        net_new = amount - previously_reserved
        if not self.check_budget(net_new):
            return False

        if existing is None:
            self._records[shot_id] = CostRecord(
                shot_id=shot_id,
                provider="",
                estimated_cost_usd=amount,
                reserved_usd=amount,
                status="reserved",
            )
        else:
            existing.reserved_usd = amount
            existing.status = "reserved"
        return True

    def reconcile(self, shot_id: str, actual_cost: float) -> CostRecord:
        """Phase 3: settle the actual cost of a completed shot.

        Releases any over-reserved budget and records the true spend.
        """
        if actual_cost < 0:
            raise ValueError("Actual cost must be non-negative")

        record = self._records.get(shot_id)
        if record is None:
            # Reconcile without a prior estimate/reserve -- create on the fly.
            record = CostRecord(shot_id=shot_id, provider="")
            self._records[shot_id] = record

        record.actual_cost_usd = actual_cost
        record.status = "reconciled"
        return record

    # -- queries ---------------------------------------------------------

    def check_budget(self, amount: float) -> bool:
        """Return ``True`` if *amount* fits within the remaining budget."""
        return amount <= self.get_remaining()

    def get_remaining(self) -> float:
        """Budget remaining after subtracting spent and reserved amounts."""
        spent = sum(
            r.actual_cost_usd for r in self._records.values() if r.status == "reconciled"
        )
        reserved = sum(
            r.reserved_usd for r in self._records.values() if r.status == "reserved"
        )
        return max(0.0, self._total_budget - spent - reserved)

    def get_total_spent(self) -> float:
        """Sum of all reconciled (actual) costs."""
        return sum(
            r.actual_cost_usd for r in self._records.values() if r.status == "reconciled"
        )

    def get_total_reserved(self) -> float:
        """Sum of all currently-reserved (not yet reconciled) amounts."""
        return sum(
            r.reserved_usd for r in self._records.values() if r.status == "reserved"
        )

    def get_shot_costs(self) -> list[CostRecord]:
        """Return all per-shot cost records."""
        return list(self._records.values())

    def get_shot_cost(self, shot_id: str) -> CostRecord | None:
        """Return the cost record for a single shot, or ``None``."""
        return self._records.get(shot_id)

    def get_summary(self) -> dict[str, Any]:
        """Return a budget summary dict."""
        return {
            "total_budget_usd": self._total_budget,
            "spent_usd": self.get_total_spent(),
            "reserved_usd": self.get_total_reserved(),
            "remaining_usd": self.get_remaining(),
            "shot_count": len(self._records),
        }


# ---------------------------------------------------------------------------
# Module-level singleton (convenience)
# ---------------------------------------------------------------------------

#: Shared registry instance for the application.
registry = VideoProviderRegistry()

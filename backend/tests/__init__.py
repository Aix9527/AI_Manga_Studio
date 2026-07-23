"""
Testing Framework — Unit, Integration, E2E, and AI Evaluation (Part 21)

Provides base test classes, fixtures, mocks, and AI generation
quality evaluation tools.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable


# ── Base Test Classes ─────────────────────────────────────────────────

class AsyncTestCase:
    """Base class for async test cases."""

    @staticmethod
    async def assert_async_equal(first: Any, second: Any, msg: str = "") -> None:
        assert first == second, msg or f"{first} != {second}"

    @staticmethod
    async def assert_async_raises(exc_type: type[Exception], coro: Any) -> None:
        try:
            if asyncio.iscoroutine(coro):
                await coro
            else:
                coro()
            assert False, f"Expected {exc_type.__name__} but no exception raised"
        except exc_type:
            pass  # Expected


# ── Fixtures & Mocks ──────────────────────────────────────────────────

class MockProvider:
    """Mock LLM/Image/Video provider for testing."""
    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self._responses = responses or {}
        self._calls: list[dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        return len(self._calls)

    async def invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        self._calls.append(request)
        return self._responses.get("default", {"status": "ok", "data": {}})

    def get_last_call(self) -> dict[str, Any] | None:
        return self._calls[-1] if self._calls else None


class MockAgent:
    """Mock Agent for testing pipeline stages."""
    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self._result = result or {}
        self._call_count = 0

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        self._call_count += 1
        return self._result


# ── Fixture Factory ───────────────────────────────────────────────────

def mock_factory(base_class: type, **overrides: Any) -> Any:
    """Dynamically create a mock based on any class."""
    class DynamicMock(base_class):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **{**kwargs, **overrides})
    return DynamicMock


# ── AI Quality Evaluation ─────────────────────────────────────────────

@dataclass
class QualityScore:
    """AI generation quality evaluation score."""
    category: str
    score: float  # 0.0 - 1.0
    details: str = ""
    pass_threshold: float = 0.6

    @property
    def passed(self) -> bool:
        return self.score >= self.pass_threshold


@dataclass
class CharacterConsistencyScore(QualityScore):
    """Evaluates how consistent a generated character appears across frames."""
    identity_match: float = 0.0
    pose_variance: float = 0.0
    color_consistency: float = 0.0

    def __post_init__(self) -> None:
        self.category = "character_consistency"
        self.score = (self.identity_match + self.pose_variance + self.color_consistency) / 3.0


@dataclass
class ImageQualityScore(QualityScore):
    """Evaluates image generation quality metrics."""
    aesthetic: float = 0.0
    technical: float = 0.0
    prompt_alignment: float = 0.0

    def __post_init__(self) -> None:
        self.category = "image_quality"
        self.score = (self.aesthetic + self.technical + self.prompt_alignment) / 3.0


@dataclass
class GenerationQualityReport:
    """Aggregated quality report for a generation run."""
    run_id: str = ""
    scores: list[QualityScore] = field(default_factory=list)
    overall_score: float = 0.0

    def add_score(self, score: QualityScore) -> None:
        self.scores.append(score)
        self._recalculate()

    def _recalculate(self) -> None:
        if self.scores:
            self.overall_score = sum(s.score for s in self.scores) / len(self.scores)

    @property
    def passed(self) -> bool:
        return self.overall_score >= 0.6


class QualityEvaluator:
    """Evaluates AI generation quality across multiple dimensions."""

    def evaluate_character_consistency(
        self,
        reference_features: dict[str, Any],
        generated_image_path: str,
    ) -> CharacterConsistencyScore:
        """Evaluate character consistency between reference and generated image."""
        return CharacterConsistencyScore(
            identity_match=0.85,
            pose_variance=0.70,
            color_consistency=0.90,
            details="Simulated evaluation (replace with CV model)",
        )

    def evaluate_image_quality(
        self,
        image_path: str,
        prompt: str,
    ) -> ImageQualityScore:
        """Evaluate image quality metrics."""
        return ImageQualityScore(
            aesthetic=0.78,
            technical=0.82,
            prompt_alignment=0.75,
            details="Simulated evaluation",
        )


# ── Test Data Generators ──────────────────────────────────────────────

def generate_test_project(name: str = "Test Project") -> dict[str, Any]:
    """Generate a minimal test project dict."""
    return {
        "project_id": f"test-{name.lower().replace(' ', '-')}",
        "name": name,
        "description": "Auto-generated test project",
        "settings": {"resolution": {"width": 1920, "height": 1080}, "fps": 24},
    }


def generate_test_character(name: str = "Test Character") -> dict[str, Any]:
    """Generate a minimal test character dict."""
    return {
        "character_id": f"char-{name.lower().replace(' ', '-')}",
        "name": name,
        "role": "protagonist",
        "appearance": "A test character",
        "personality": "Test personality",
    }


def generate_test_scene(number: int = 1) -> dict[str, Any]:
    """Generate a minimal test scene dict."""
    return {
        "scene_id": f"scene-{number:03d}",
        "scene_number": number,
        "description": f"Test scene {number}",
        "location": "Test location",
        "time_of_day": "day",
        "mood": "neutral",
    }

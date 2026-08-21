"""Identity Verification Gate (Phase 10.5-C).

Post-generation check between ComfyUI output and the Vision Critic:

    Generate -> Identity Check (this module) -> Vision Critic -> Approve/Retry

Samples frames from the generated video and runs the multi-character
IdentityEngine lock per frame, then aggregates a per-character presence
ratio.  A character passes when it appears in enough sampled frames;
the shot passes when every expected character passes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from backend.characters.identity import IdentityEngine

FrameExtractor = Callable[[Path, Path, int], list[Path]]


def _default_frame_extractor(video_path: Path, out_dir: Path, num_frames: int) -> list[Path]:
    from backend.video.quality_gate import _extract_sample_frames

    return _extract_sample_frames(video_path, out_dir, num_frames=num_frames)


@dataclass
class IdentityGateReport:
    """Aggregated identity verification result for one generated video."""

    video_path: str = ""
    frames_checked: int = 0
    per_character: dict = field(default_factory=dict)  # cid -> verdict dict
    overall_verdict: str = "pass"
    threshold: float = 0.75
    presence_threshold: float = 0.6
    detail: list[dict] = field(default_factory=list)


class IdentityVerifier:
    """Verifies expected characters appear across sampled video frames."""

    def __init__(
        self,
        engine: IdentityEngine | None = None,
        presence_threshold: float = 0.6,
        sample_frames: int = 5,
        frame_extractor: FrameExtractor | None = None,
    ):
        self.engine = engine or IdentityEngine()
        self.presence_threshold = presence_threshold
        self.sample_frames = sample_frames
        self.frame_extractor = frame_extractor or _default_frame_extractor

    def verify_video(
        self,
        video_path: str | Path,
        references: dict[str, Sequence[float]],
        workdir: str | Path | None = None,
    ) -> IdentityGateReport:
        """Check every expected character across sampled frames."""
        video_path = Path(video_path)
        out_dir = Path(workdir) if workdir else video_path.parent / "_identity_frames"
        frames = self.frame_extractor(video_path, out_dir, self.sample_frames)

        report = IdentityGateReport(
            video_path=str(video_path),
            frames_checked=len(frames),
            threshold=self.engine.threshold,
            presence_threshold=self.presence_threshold,
        )

        # frame_index -> per-character verdicts
        frame_verdicts: list[dict] = []
        for i, frame in enumerate(frames):
            result = self.engine.multi_character_lock(references, str(frame))
            frame_verdicts.append(
                {v["character_id"]: v["verdict"] for v in result.get("per_character", [])}
            )
            report.detail.append(
                {
                    "frame_index": i,
                    "frame_path": str(frame),
                    "per_character": [
                        {"character_id": v["character_id"], "score": v["score"], "verdict": v["verdict"]}
                        for v in result.get("per_character", [])
                    ],
                }
            )

        # Aggregate per character
        failures: list[str] = []
        for cid in references:
            present = sum(
                1 for fv in frame_verdicts if fv.get(cid) == "pass"
            )
            ratio = present / len(frame_verdicts) if frame_verdicts else 0.0
            ok = ratio >= self.presence_threshold
            report.per_character[cid] = {
                "frames_checked": len(frame_verdicts),
                "frames_present": present,
                "presence_ratio": round(ratio, 3),
                "verdict": "pass" if ok else "fail",
            }
            if not ok:
                failures.append(cid)

        report.overall_verdict = "pass" if not failures else "fail"
        return report

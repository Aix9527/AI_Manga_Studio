from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Optional


@dataclass
class ChainLink:
    """One link of the long-video chain plan (ttv-pipeline-inspired)."""
    shot_id: str
    mode: str = "keyframe"            # keyframe | last_frame | reset
    start_image: str = ""
    last_frame: str = ""
    continuity_score: float = 1.0
    note: str = ""


class KeyframeMemory:
    """Remembers the last frame + shot bible of the previous link."""

    def __init__(self, root: str | Path = "storage/keyframe_memory"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._last: dict = {}

    def remember(self, shot_id: str, last_frame: str, shot_bible: dict) -> None:
        self._last = {
            "shot_id": shot_id,
            "last_frame": last_frame,
            "shot_bible": dict(shot_bible),
            "updated_at": datetime.now().isoformat(),
        }

    def last(self) -> dict:
        return dict(self._last)

    def reset(self) -> None:
        self._last = {}


def _same_space(prev: dict, cur: dict) -> bool:
    """Continuity heuristic: same location & time-of-day => chainable."""
    if not prev:
        return False
    return (
        prev.get("location") == cur.get("location")
        and prev.get("time_of_day") == cur.get("time_of_day")
    )


class ChainManager:
    """Decides chaining strategy per shot and advances the keyframe memory.

    - same space + short elapsed shots  -> ``last_frame`` chaining (I2V from tail)
    - scene/location change or black gap -> ``keyframe`` (fresh keyframe) or ``reset``
    """

    def __init__(self, memory: KeyframeMemory | None = None, score_threshold: float = 0.8):
        self.memory = memory or KeyframeMemory()
        self.score_threshold = score_threshold

    def plan_chain(self, shots: list[dict]) -> list[ChainLink]:
        links: list[ChainLink] = []
        prev = None
        for shot in shots:
            sid = shot.get("id", shot.get("shot_id", ""))
            if not prev or not _same_space(prev, shot):
                mode = "keyframe" if not prev else "reset"
                links.append(ChainLink(shot_id=sid, mode=mode, note="scene_break" if prev else "first_shot"))
            else:
                last = self.memory.last()
                links.append(
                    ChainLink(
                        shot_id=sid,
                        mode="last_frame",
                        start_image=last.get("last_frame", ""),
                        continuity_score=self.score_threshold,
                        note="tail_chain",
                    )
                )
            prev = shot
        return links

    def advance(self, shot_id: str, last_frame: str, shot_bible: dict) -> None:
        self.memory.remember(shot_id, last_frame, shot_bible)

    def chain_report(self, links: list[ChainLink]) -> dict:
        counts: dict[str, int] = {}
        for link in links:
            counts[link.mode] = counts.get(link.mode, 0) + 1
        return {"total": len(links), "by_mode": counts}


@dataclass
class ChainState:
    """Per-shot state inside the long-video runtime (Phase 10.3-B).

    Mirrors the ChainLink plan plus the execution result so a worker can
    resume an interrupted run from the checkpoint manifest.
    """
    project_id: str = ""
    shot_id: str = ""
    mode: str = ""                    # keyframe | last_frame | reset
    keyframe: str = ""                # fresh keyframe image for this shot
    start_image: str = ""             # actual start image used (keyframe or inherited tail frame)
    end_frame: str = ""               # optional FLF2V target end frame
    workflow_id: str = ""             # ComfyUI workflow id used (native/ltx/wrapper)
    status: str = "pending"           # pending | running | completed | failed
    retry_count: int = 0
    output_video: str = ""
    last_frame: str = ""              # extracted tail frame after generation
    identity_report: dict = field(default_factory=dict)  # Phase 10.5-C gate result
    cost: dict = field(default_factory=dict)              # Stage-A cost meter
    error: str = ""


class ChainCheckpoint:
    """Persistent checkpoint manifest for long video runs.

    Layout: ``<root>/<project>/video_checkpoint_manifest.json`` with the
    GPT-approved shape: ``{project, completed[], current, last_frame,
    resume_from, states{}}``.  ``completed`` keeps shot ids that finished,
    ``current`` is the in-flight shot and ``resume_from`` the next one to run.
    """

    def __init__(self, project_id: str, root: str | Path = "storage/chains"):
        self.project_id = project_id
        self.path = Path(root) / project_id / "video_checkpoint_manifest.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict = {
            "project": project_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "completed": [],
            "current": "",
            "last_frame": "",
            "resume_from": "",
            "states": {},
        }

    def load(self) -> "ChainCheckpoint":
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._data.update(data)
            except Exception:
                pass
        return self

    def save(self) -> None:
        self._data["updated_at"] = datetime.now().isoformat()
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # -- mutations ---------------------------------------------------------
    def mark_running(self, state: ChainState) -> None:
        self._data["current"] = state.shot_id
        self._data["resume_from"] = state.shot_id
        self._data["states"][state.shot_id] = asdict(state)
        self.save()

    def mark_completed(self, state: ChainState) -> None:
        if state.shot_id not in self._data["completed"]:
            self._data["completed"].append(state.shot_id)
        self._data["current"] = ""
        self._data["resume_from"] = ""
        if state.last_frame:
            self._data["last_frame"] = state.last_frame
        self._data["states"][state.shot_id] = asdict(state)
        self.save()

    def mark_failed(self, state: ChainState) -> None:
        if not state.status or state.status == "running":
            state.status = "failed"
        self._data["current"] = state.shot_id
        self._data["resume_from"] = state.shot_id
        self._data["states"][state.shot_id] = asdict(state)
        self.save()

    def completed_ids(self) -> list[str]:
        return list(self._data.get("completed", []))

    def last_frame(self) -> str:
        return self._data.get("last_frame", "")

    def state_for(self, shot_id: str) -> ChainState | None:
        raw = self._data.get("states", {}).get(shot_id)
        if not raw:
            return None
        return ChainState(**{k: raw.get(k, "") for k in ChainState.__dataclass_fields__})

    def summary(self) -> dict:
        states = self._data.get("states", {})
        return {
            "project": self.project_id,
            "completed": list(self._data.get("completed", [])),
            "current": self._data.get("current", ""),
            "resume_from": self._data.get("resume_from", ""),
            "last_frame": self._data.get("last_frame", ""),
            "total_shots": len(states),
            "pending": [sid for sid, st in states.items() if st.get("status") == "pending"],
            "failed": [
                sid for sid, st in states.items()
                if st.get("status") not in ("pending", "completed", "skipped")
            ],
            "manifest_path": str(self.path),
        }

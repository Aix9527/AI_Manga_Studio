import json
from pathlib import Path

import pytest

from backend.production.h3_unified.continuity import MOTION_CONTEXT_NODE_SIGNATURES
from backend.production.h3_unified.workflow_builder import (
    add_motion_context,
    expand_reference_images,
)


ROOT = Path(__file__).resolve().parents[2]


def _reference_workflow():
    payload = json.loads(
        (ROOT / "backend/production/workflows/h3/reference.json").read_text(encoding="utf-8")
    )
    return payload["workflow"]


def _nodes_by_type(workflow, class_type):
    return {
        node_id: node for node_id, node in workflow.items()
        if node.get("class_type") == class_type
    }


def test_expand_reference_images_supports_nine_slots_without_empty_loaders():
    refs = [f"h3/ref_{index}.png" for index in range(1, 10)]

    workflow = expand_reference_images(_reference_workflow(), refs)

    loaders = _nodes_by_type(workflow, "LoadImage")
    assert len(loaders) == 9
    assert [loaders[node_id]["inputs"]["image"] for node_id in sorted(loaders, key=int)] == refs

    reference_node = next(iter(_nodes_by_type(workflow, "MiniMaxH3ReferenceToVideo").values()))
    assert reference_node["inputs"]["ref_images"] == [
        [node_id, 0] for node_id in sorted(loaders, key=int)
    ]
    assert all(node["inputs"]["image"] for node in loaders.values())


def test_expand_reference_images_rejects_more_than_nine_references():
    with pytest.raises(ValueError, match="at most 9 reference images"):
        expand_reference_images(_reference_workflow(), [f"ref-{i}.png" for i in range(10)])


def test_first_segment_only_saves_its_av_latent_to_fixed_slot():
    workflow = add_motion_context(
        _reference_workflow(), run_id="gx-episode-01", segment_index=0, fps=24
    )

    save = next(iter(_nodes_by_type(workflow, "MiniMaxH3MotionContextSaveLatent").values()))
    assert save["inputs"]["clip_index"] == 1
    assert save["inputs"]["filename_prefix"] == "AI_Manga_Studio/H3/context/gx-episode-01/clip"
    assert save["inputs"]["latent"] == ["20", 0]
    assert not _nodes_by_type(workflow, "MiniMaxH3MotionContextLoadLatent")
    assert not _nodes_by_type(workflow, "MiniMaxH3MotionContext")
    assert not _nodes_by_type(workflow, "MiniMaxH3MotionContextTrim")


def test_continuation_loads_previous_slot_injects_context_trims_head_and_saves_current_slot():
    workflow = add_motion_context(
        _reference_workflow(),
        run_id="gx-episode-01",
        segment_index=1,
        fps=24,
        context_frames=22,
        audio_context_frames=24,
    )

    load_id, load = next(iter(_nodes_by_type(workflow, "MiniMaxH3MotionContextLoadLatent").items()))
    context_id, context = next(iter(_nodes_by_type(workflow, "MiniMaxH3MotionContext").items()))
    trim_id, trim = next(iter(_nodes_by_type(workflow, "MiniMaxH3MotionContextTrim").items()))
    save = next(iter(_nodes_by_type(workflow, "MiniMaxH3MotionContextSaveLatent").values()))

    assert load["inputs"] == {
        "latent_path": "AI_Manga_Studio/H3/context/gx-episode-01",
        "clip_index": 1,
    }
    assert context["inputs"] == {
        "conditioning": ["15", 0],
        "vae": ["2", 0],
        "latent": ["15", 1],
        "context_length": "22",
        "audio_context_length": 24,
        "context_latent": [load_id, 0],
        "audio_vae": ["3", 0],
    }
    assert workflow["19"]["inputs"]["conditioning"] == [context_id, 0]
    assert trim["inputs"] == {
        "images": ["21", 0],
        "trim_frames": [context_id, 1],
        "audio": ["22", 0],
        "fps": 24.0,
        "match_tail": True,
    }
    assert workflow["23"]["inputs"]["images"] == [trim_id, 0]
    assert workflow["23"]["inputs"]["audio"] == [trim_id, 1]
    assert save["inputs"]["clip_index"] == 2
    assert save["inputs"]["latent"] == ["20", 0]


def test_motion_context_signatures_cover_all_optional_external_nodes():
    assert set(MOTION_CONTEXT_NODE_SIGNATURES) == {
        "MiniMaxH3MotionContext",
        "MiniMaxH3MotionContextTrim",
        "MiniMaxH3MotionContextSaveLatent",
        "MiniMaxH3MotionContextLoadLatent",
    }
    assert "context_latent" in MOTION_CONTEXT_NODE_SIGNATURES["MiniMaxH3MotionContext"]["optional"]
    assert "clip_index" in MOTION_CONTEXT_NODE_SIGNATURES["MiniMaxH3MotionContextSaveLatent"]["required"]

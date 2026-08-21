import pytest

from backend.production.comfy_adapter import ProductionError, ProductionErrorCode
from backend.production.comfy_video import validate_workflow_schema


def test_workflow_schema_rejects_missing_node_before_queue_submission():
    workflow = {
        "1": {"class_type": "LoadImage", "inputs": {"image": "input/keyframe.png"}},
        "2": {"class_type": "MissingLtxNode", "inputs": {}},
    }
    object_info = {
        "LoadImage": {
            "input": {"required": {"image": ["STRING", {}]}},
        }
    }

    with pytest.raises(ProductionError) as captured:
        validate_workflow_schema(workflow, object_info)

    assert captured.value.code is ProductionErrorCode.COMFY_WORKFLOW_INVALID
    assert captured.value.details["missing_nodes"] == ["MissingLtxNode"]

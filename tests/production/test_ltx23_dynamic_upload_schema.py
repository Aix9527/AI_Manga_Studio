from backend.production.comfy_video import validate_workflow_schema


def test_workflow_schema_accepts_new_dynamic_upload_reference():
    workflow = {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": "novel_video/new-keyframe.png"},
        }
    }
    object_info = {
        "LoadImage": {
            "input": {
                "required": {
                    "image": [
                        ["previous-upload.png"],
                        {"image_upload": True},
                    ]
                }
            }
        }
    }

    validate_workflow_schema(workflow, object_info)

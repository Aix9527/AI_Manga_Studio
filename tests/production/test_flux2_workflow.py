from backend.production.workflow_templates import WorkflowTemplate


def test_template_applies_one_value_to_multiple_workflow_inputs():
    template = WorkflowTemplate.from_dict(
        {
            "workflow": {
                "6": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": 0}},
                "10": {"class_type": "Flux2Scheduler", "inputs": {"width": 0}},
            },
            "bindings": {"width": [["6", "width"], ["10", "width"]]},
        }
    )

    workflow = template.render(width=768)

    assert workflow["6"]["inputs"]["width"] == 768
    assert workflow["10"]["inputs"]["width"] == 768


def test_flux_ipadapter_faceid_output_feeds_generation_graph():
    template = WorkflowTemplate.load(
        "backend/production/workflows/flux_ipadapter_faceid.json"
    )
    workflow = template.render(
        prompt="cinematic close-up",
        seed=42,
        width=512,
        height=896,
        reference_image="characters/hero.png",
        ipadapter_weight=0.85,
        filename_prefix="novel_video/keyframe",
    )

    ipadapter_node_ids = [
        node_id
        for node_id, node in workflow.items()
        if node.get("class_type") == "IPAdapterFaceID"
    ]
    assert ipadapter_node_ids == ["17"]
    assert any(
        value == ["17", 0]
        for node_id, node in workflow.items()
        if node_id != "17"
        for value in node.get("inputs", {}).values()
    )

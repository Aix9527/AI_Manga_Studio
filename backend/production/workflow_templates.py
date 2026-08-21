from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BindingTarget = tuple[str, str]


@dataclass(frozen=True)
class WorkflowTemplate:
    workflow: dict[str, dict[str, Any]]
    bindings: dict[str, tuple[BindingTarget, ...]]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkflowTemplate":
        workflow = copy.deepcopy(payload.get("workflow", {}))
        raw_bindings = payload.get("bindings", {})
        if not isinstance(workflow, dict) or not workflow:
            raise ValueError("Workflow template has no workflow nodes")
        if not isinstance(raw_bindings, dict):
            raise ValueError("Workflow template bindings must be an object")

        bindings: dict[str, tuple[BindingTarget, ...]] = {}
        for name, target in raw_bindings.items():
            targets = (
                target
                if isinstance(target, list)
                and target
                and isinstance(target[0], list)
                else [target]
            )
            parsed_targets: list[BindingTarget] = []
            for item in targets:
                if not isinstance(item, list) or len(item) != 2:
                    raise ValueError(
                        f"Binding {name} must be [node_id, input_name] "
                        "or a list of those targets"
                    )
                node_id, input_name = str(item[0]), str(item[1])
                if node_id not in workflow:
                    raise ValueError(f"Binding {name} references missing node {node_id}")
                if input_name not in workflow[node_id].get("inputs", {}):
                    raise ValueError(
                        f"Binding {name} references missing input "
                        f"{node_id}.{input_name}"
                    )
                parsed_targets.append((node_id, input_name))
            bindings[str(name)] = tuple(parsed_targets)

        return cls(workflow=workflow, bindings=bindings)

    @classmethod
    def load(cls, path: str | Path) -> "WorkflowTemplate":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(payload)

    def render(self, **values: Any) -> dict[str, dict[str, Any]]:
        missing = sorted(set(self.bindings) - set(values))
        if missing:
            raise ValueError(f"Missing workflow binding values: {', '.join(missing)}")
        unknown = sorted(set(values) - set(self.bindings))
        if unknown:
            raise ValueError(f"Unknown workflow binding values: {', '.join(unknown)}")

        rendered = copy.deepcopy(self.workflow)
        for name, value in values.items():
            for node_id, input_name in self.bindings[name]:
                rendered[node_id]["inputs"][input_name] = value
        return rendered

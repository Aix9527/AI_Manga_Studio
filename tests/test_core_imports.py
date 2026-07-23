"""Core module import checks."""

import importlib

import pytest


CORE_MODULES = [
    "backend.app.main",
    "backend.app.bootstrap",
    "backend.app.container",
    "backend.app.container_builder",
    "backend.app.lifecycle",
    "backend.app.routes",
    "backend.modules.platform.public",
    "backend.modules.projects.public",
    "backend.modules.narrative.public",
    "backend.modules.characters.public",
    "backend.modules.storyboard.public",
    "backend.modules.media.public",
    "backend.modules.generation.public",
    "backend.modules.workflows.public",
]


@pytest.mark.parametrize("module_name", CORE_MODULES)
def test_core_module_imports(module_name: str) -> None:
    module = importlib.import_module(module_name)
    assert module is not None


"""Application command DTOs for Projects."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateProjectCommand:
    title: str
    description: str = ""

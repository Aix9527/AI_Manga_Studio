
"""Project domain aggregate root."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Project:
    """A manga creation project aggregate root."""

    project_id: str
    title: str
    description: str = ""
    status: str = "active"
    settings_json: str = "{}"
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = field(default_factory=lambda: datetime.utcnow())
    revision: int = 1

    def change_title(self, new_title: str) -> None:
        if not new_title.strip():
            raise ValueError("Project title cannot be empty.")
        self.title = new_title.strip()
        self.updated_at = datetime.utcnow()
        self.revision += 1

"""ORM Mixin classes for common entity columns."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class IdMixin:
    """Primary key as a string ID."""

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )


class TimestampMixin:
    """created_at / updated_at timestamps (UTC)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class RevisionMixin:
    """Optimistic concurrency revision counter."""

    revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )


class EntityMixin(IdMixin, TimestampMixin, RevisionMixin):
    """Combined entity mixin with id, timestamps, and revision."""
    pass

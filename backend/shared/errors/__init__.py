"""Unified error model for the application."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppError(Exception):
    """Base application error with structured metadata."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False
    user_action: str | None = None
    correlation_id: str | None = None

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class NotFoundError(AppError):
    """Resource not found."""

    def __init__(
        self,
        resource_type: str,
        resource_id: str,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(
            code=f"{resource_type.upper()}_NOT_FOUND",
            message=f"{resource_type} was not found.",
            details={"resourceType": resource_type, "resourceId": resource_id},
            correlation_id=correlation_id,
        )


class ConflictError(AppError):
    """Resource conflict (e.g., duplicate)."""

    pass


class ValidationError(AppError):
    """Domain validation error."""

    pass


class RevisionConflictError(AppError):
    """Optimistic lock conflict."""

    def __init__(
        self,
        resource_type: str,
        resource_id: str,
        expected_revision: int,
    ) -> None:
        super().__init__(
            code="REVISION_CONFLICT",
            message="The resource was modified by another operation.",
            details={
                "resourceType": resource_type,
                "resourceId": resource_id,
                "expectedRevision": expected_revision,
            },
            retryable=False,
            user_action="Reload the resource and reapply your changes.",
        )


class ProviderNotFoundError(AppError):
    """Provider not registered."""

    def __init__(self, provider_id: str) -> None:
        super().__init__(
            code="PROVIDER_NOT_FOUND",
            message=f"Provider '{provider_id}' is not registered.",
            details={"providerId": provider_id},
        )

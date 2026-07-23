"""Global error handlers that map domain errors to HTTP responses."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.requests import Request

from backend.shared.errors import (
    AppError,
    ConflictError,
    NotFoundError,
    RevisionConflictError,
    ValidationError,
)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:  # noqa: ARG001
        status_map = {
            "NOT_FOUND": 404,
            "VALIDATION": 422,
            "CONFLICT": 409,
            "REVISION_CONFLICT": 409,
            "PROVIDER_UNAVAILABLE": 503,
            "BUDGET_EXCEEDED": 409,
        }

        status_code = 500
        for key, code in status_map.items():
            if key in exc.code:
                status_code = code
                break

        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "retryable": exc.retryable,
                    "userAction": exc.user_action,
                    "correlationId": exc.correlation_id,
                }
            },
        )

    # Register specific subtypes for more precise status codes
    app.exception_handler(NotFoundError)(_app_error_handler)
    app.exception_handler(ConflictError)(_app_error_handler)
    app.exception_handler(ValidationError)(_app_error_handler)
    app.exception_handler(RevisionConflictError)(_app_error_handler)

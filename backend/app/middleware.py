"""HTTP middleware — correlation ID and request logging."""

import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Assign or propagate a correlation ID for each request."""

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID") or f"corr_{uuid.uuid4()}"
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


def register_middleware(app) -> None:
    """Register all middleware on the FastAPI app."""
    app.add_middleware(CorrelationIdMiddleware)

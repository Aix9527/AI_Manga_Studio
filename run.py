"""Development entry point for AI_Manga_Studio."""

from __future__ import annotations

import uvicorn


def main() -> None:
    """Start the FastAPI development server."""
    uvicorn.run(
        "backend.app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()

"""Application entry point. Keep as thin as possible."""

from backend.app.bootstrap import create_application

app = create_application()

"""
Docs Architecture — Developer experience and open-source governance (Part 23)

Documentation structure and contribution guidelines.
"""

from __future__ import annotations


# ── Documentation Generator ───────────────────────────────────────────

class DocGenerator:
    """Generates API and architecture documentation from code."""

    @staticmethod
    def generate_api_docs(module_paths: list[str]) -> str:
        """Generate API reference documentation."""
        return "# API Reference\n\nAuto-generated API documentation.\n"

    @staticmethod
    def generate_architecture_overview() -> str:
        """Generate architecture overview diagram (Mermaid)."""
        return """```mermaid
graph TD
    A[Frontend] --> B[API Gateway]
    B --> C[Orchestration]
    C --> D[Workflow Engine]
    D --> E[Agents]
    D --> F[Providers]
    E --> G[Memory System]
    F --> H[External APIs]
    D --> I[Export Engine]
```"""


# ── Contribution Guide ────────────────────────────────────────────────

CONTRIBUTING_GUIDE = """# Contributing to AI_Manga_Studio

## Development Setup

1. Clone the repository
2. Create a virtual environment: `python -m venv venv`
3. Install dependencies: `pip install -r requirements-dev.txt`
4. Run tests: `pytest backend/tests/`

## Code Style

- Follow PEP 8
- Type annotations are required for all public APIs
- Docstrings follow Google style

## Pull Request Process

1. Create a feature branch from `main`
2. Write tests for new functionality
3. Update documentation if needed
4. Submit PR with description of changes
"""


# ── Architecture Decision Records ─────────────────────────────────────

class ADR:
    """Architecture Decision Record."""

    def __init__(
        self,
        id: int,
        title: str,
        status: str,  # proposed/accepted/deprecated/superseded
        context: str,
        decision: str,
        consequences: str,
    ) -> None:
        self.id = id
        self.title = title
        self.status = status
        self.context = context
        self.decision = decision
        self.consequences = consequences

    def to_markdown(self) -> str:
        return f"""# ADR-{self.id:03d}: {self.title}

- **Status**: {self.status}
- **Date**: Auto-generated

## Context
{self.context}

## Decision
{self.decision}

## Consequences
{self.consequences}
"""


# Pre-populated ADRs documenting key decisions
ADRS: list[ADR] = [
    ADR(
        id=1,
        title="DDD + Agent + Workflow + Provider Architecture",
        status="accepted",
        context="The platform needs to orchestrate complex AI pipelines. Traditional MVC is insufficient.",
        decision="Adopt Domain-Driven Design with Agent/Workflow/Provider separation for modularity and testability.",
        consequences="Increased initial complexity but enables independent evolution of each layer.",
    ),
    ADR(
        id=2,
        title="Plugin-Based Extension System",
        status="accepted",
        context="The platform must support third-party extensions without compromising stability.",
        decision="Implement an eight-capability plugin system with permission isolation and lifecycle management.",
        consequences="Plugins can extend any part of the system but must declare permissions. Fault isolation prevents cascading failures.",
    ),
    ADR(
        id=3,
        title="DAG-Based Workflow with Checkpoint/Resume",
        status="accepted",
        context="AI generation pipelines are long-running and prone to failure. Users need resume and rollback.",
        decision="Model workflows as DAGs with built-in checkpointing, retry, and rollback. Durable execution from day one.",
        consequences="All pipeline stages must be idempotent. Adds overhead but enables long-running production workflows.",
    ),
]

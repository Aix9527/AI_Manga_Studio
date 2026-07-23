---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: ac05b1368557ee08912a0f1b051adb10_26d6493886a911f18766525400f8a581
    ReservedCode1: VKVnIwVTr9U1okBkTacTQ1P39SW55I1tcL4m6GR+6mrQYQOHTwOWcsrwoJdN3FZJ+q83LIH2XRb6eQM/q9KClIqT/l9ouaRSC5nAd7dtuqmqB3nbTMUtq1C7kzpvgiD03If4H4jIMXRhATfKqrKus/7jsou97tFY5ARiaun8/CYJHmlWBTyMe3NwK4o=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: ac05b1368557ee08912a0f1b051adb10_26d6493886a911f18766525400f8a581
    ReservedCode2: VKVnIwVTr9U1okBkTacTQ1P39SW55I1tcL4m6GR+6mrQYQOHTwOWcsrwoJdN3FZJ+q83LIH2XRb6eQM/q9KClIqT/l9ouaRSC5nAd7dtuqmqB3nbTMUtq1C7kzpvgiD03If4H4jIMXRhATfKqrKus/7jsou97tFY5ARiaun8/CYJHmlWBTyMe3NwK4o=
---

# Architecture | 系统架构

## Overview

AI_Manga_Studio is an AI-native production infrastructure for transforming long-form stories into consistent visual storytelling. It is designed as a **six-layer pipeline architecture**, not a simple tool collection. Each layer has clearly defined responsibilities and communicates through well-defined interfaces.

## Design Philosophy

- **Separation of Concerns**: Each layer handles one aspect of the production pipeline
- **Provider Abstraction**: AI models are plugins, not hard dependencies
- **Stateful Workflow**: Every production stage is tracked, recoverable, and auditable
- **Character as Data**: Characters are database objects with versioned attributes, not ad-hoc prompt strings

## Pipeline Overview

```
Novel → Knowledge Graph → Character Memory → Storyboard → Prompt Engine → Image → Video → Final Drama
```

## Six-Layer Architecture

### 1. UI Layer

**Responsibilities:**
- Web-based user interface
- Project creation and management dashboard
- Timeline view for storyboard and shot planning
- Image and video preview with side-by-side comparison
- Human review and approval workflow

**Key principles:**
- The UI is a pure presentation layer — no business logic
- All state changes go through the API layer
- Real-time updates via WebSocket for job progress

### 2. API Layer

**Responsibilities:**
- REST API endpoints (FastAPI)
- Project CRUD operations
- Job submission, status query, and cancellation
- Asset upload and download
- Authentication and authorization (future)

**Key principles:**
- Stateless request handling
- Async I/O for non-blocking operations
- Standard HTTP status codes and error responses
- OpenAPI/Swagger documentation auto-generated

### 3. Workflow Layer

**Responsibilities:**
- Directed Acyclic Graph (DAG) job orchestration
- Task queue management with priority
- Retry with exponential backoff
- Checkpoint-based resume after failure
- Stage dependency resolution
- Parallel task execution where possible

**Key principles:**
- Every production is a `Project` containing `Jobs`
- Each `Job` is a DAG of `Stages`
- Each `Stage` contains `Tasks` with `Steps`
- State transitions are atomic and persisted

### 4. AI Layer

**Responsibilities:**
- Story Parser: Novel ingestion and structural analysis
- Character Agent: Character extraction, profiling, relationship mapping
- Storyboard Agent: Scene-to-shot decomposition with camera language
- Prompt Agent: Context-aware prompt construction
- Video Agent: Frame assembly, transition, and timing
- Voice Agent: Dialogue-to-speech with character voice profiles

**Key principles:**
- Each agent is an independent, testable module
- Agents rely on the Memory Layer for context, not direct database access
- Agent outputs are structured JSON, not free text
- LLM calls are routed through the Provider Layer

### 5. Memory Layer

**Responsibilities:**
- Character Memory: Persistent character profiles, appearance locks, history
- Scene Memory: Location descriptions, atmosphere, visual references
- Project Memory: Global context, style guides, production notes
- Long Story Context: Sliding window with relevance retrieval for long narratives

**Key principles:**
- Memory is the foundation of consistency
- Character appearance is locked after first visual generation
- Scene descriptions accumulate detail across chapters
- Memory retrieval uses semantic search, not full-context loading

### 6. Provider Layer

**Responsibilities:**
- Abstract interface for all AI model calls
- Provider registry with dynamic loading
- Model capability detection and routing
- Retry, fallback, and load balancing
- Cost tracking (future)

**Supported providers:**
- **LLM**: OpenAI, Ollama, OpenRouter
- **Image**: ComfyUI (Flux, SDXL, etc.)
- **Video**: ComfyUI Video (Wan), future: Runway, Pika
- **Audio**: ElevenLabs, Fish Audio, future: Stable Audio

## Data Flow

```
Novel File → [Story Parser] → Chapter/Scene/Character JSON → [Character Manager] → Character DB
                                                                           ↓
Scene JSON + Character DB → [Storyboard Planner] → Storyboard JSON → [Prompt Engine]
                                                                           ↓
Prompt JSON → [Provider Layer → ComfyUI/OpenAI] → Image/Video Files → [Editor] → Final Output
```

## Future

- Horizontal scaling of workflow workers
- Distributed checkpoint storage (Redis/S3)
- Plugin marketplace with versioning
- Multi-user collaboration and review
- Cloud deployment templates (Docker, Kubernetes)
*（内容由AI生成，仅供参考）*

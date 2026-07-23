---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: ac05b1368557ee08912a0f1b051adb10_27e95aff86a911f18108525400287e28
    ReservedCode1: lsMEyLjFtvVl006Qlhe5n3sou1iZgfm9KETL7rrbfmN94v460MFWb9xcGV1LE3nsSf+jrZAJywFAyijc6FO/U+9eROvXPE+WFc6XWA3K6mNVz9u41OiUNh1643jmfWbb19e2qs8N68aEc5M5aCQFOIveCpKds37cotx57Ufe0TYfMRtRw/ZriXVNZgQ=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: ac05b1368557ee08912a0f1b051adb10_27e95aff86a911f18108525400287e28
    ReservedCode2: lsMEyLjFtvVl006Qlhe5n3sou1iZgfm9KETL7rrbfmN94v460MFWb9xcGV1LE3nsSf+jrZAJywFAyijc6FO/U+9eROvXPE+WFc6XWA3K6mNVz9u41OiUNh1643jmfWbb19e2qs8N68aEc5M5aCQFOIveCpKds37cotx57Ufe0TYfMRtRw/ZriXVNZgQ=
---

# Workflow Engine | 工作流引擎

## Overview

The Workflow Engine is the orchestration brain of AI_Manga_Studio. It converts production plans into executable, monitorable, and recoverable task graphs — ensuring that long-running AI production pipelines (potentially spanning hours or days) can survive individual failures without losing progress.

## Responsibilities

- Define and execute production workflows as Directed Acyclic Graphs (DAGs)
- Manage task queues with priority and concurrency control
- Provide checkpoint-based resume after any stage failure
- Support retry with configurable backoff strategies
- Expose job status and progress for UI polling and WebSocket updates

## Core Concepts

### Hierarchy

```
Project (项目)
  └── Job (作业)
       └── Stage (阶段)
            └── Task (任务)
                 └── Step (步骤)
```

| Level | Description | Example |
|-------|-------------|---------|
| **Project** | Top-level production container | "Heavenly Sword Manga Adaptation" |
| **Job** | One complete production run | "Chapter 1-5 Image Generation" |
| **Stage** | Logical phase within a job | "Character Extraction", "Storyboard", "Image Gen" |
| **Task** | Unit of work within a stage | "Generate shot 12-CU-01" |
| **Step** | Atomic operation | "Call ComfyUI API", "Save image to disk" |

### State Machine

```
Draft → Queued → Running → Waiting Review → Completed
  ↓        ↓        ↓
Failed   Failed   Failed
  └────────┴────────┘
           ↓
       Retrying
           ↓
       Running / Failed
```

| State | Description |
|-------|-------------|
| **Draft** | Job/stage/task has been created but not yet queued |
| **Queued** | Waiting for an available worker slot |
| **Running** | Currently executing |
| **Waiting Review** | Paused for human approval (e.g., storyboard review) |
| **Completed** | Successfully finished |
| **Failed** | Terminated due to unrecoverable error |
| **Retrying** | Failed but scheduled for retry attempt |

### Recovery Mechanisms

- **Retry**: Automatic retry with exponential backoff for transient failures (API timeout, network error)
- **Resume**: After a crash, the engine reads the last completed checkpoint and resumes from that stage — no re-execution of already-completed work
- **Rollback**: Manual rollback to a previous checkpoint when output quality is unacceptable
- **Checkpoint**: After each stage completes, all intermediate results are persisted (JSON manifests, image files, metadata)

## Input

- **Project Configuration**: YAML/JSON defining stages, providers, and parameters
- **Novel Data**: Pre-parsed novel structure (from Story Parser)
- **Character Data**: Character profiles and memory (from Character Manager)

## Output

- **Job Manifest**: Complete execution record with all stage outputs
- **Stage Artifacts**: Storyboard JSON, prompt JSON, generated images/videos
- **Progress Events**: Real-time status updates via WebSocket
- **Error Reports**: Detailed failure diagnostics with context

## Workflow

```
1. Project Created → Define stages and dependencies
2. Job Submitted → Build DAG, validate parameters
3. Queue → Wait for worker availability
4. Execute Stage 1 → Parse novel → Checkpoint
5. Execute Stage 2 → Extract characters → Checkpoint
6. Execute Stage 3 → Generate storyboard → Checkpoint
7. Human Review → Waiting Review state
8. Execute Stage 4 → Generate images (parallel tasks) → Checkpoint
9. Execute Stage 5 → Assemble video → Checkpoint
10. Complete → Final manifest written
```

## API

```python
class WorkflowEngine:
    async def submit_job(self, project_id: str, config: JobConfig) -> Job
    async def get_status(self, job_id: str) -> JobStatus
    async def cancel_job(self, job_id: str) -> None
    async def resume_job(self, job_id: str, from_stage: str = None) -> Job
    async def rollback_job(self, job_id: str, to_stage: str) -> Job
    async def list_jobs(self, project_id: str) -> List[Job]

class JobStatus:
    job_id: str
    state: JobState
    current_stage: str
    progress: float  # 0.0 to 1.0
    stages: List[StageStatus]
    error: Optional[ErrorDetail]
```

## Future

- Distributed workers for horizontal scaling
- Priority queue with fair scheduling
- Webhook callbacks for external system integration
- Cost estimation before job execution
- Dry-run mode for parameter validation without API calls
*（内容由AI生成，仅供参考）*

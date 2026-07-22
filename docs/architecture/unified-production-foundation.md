# Unified Production Foundation

## Canonical path

- CLI: `run.py`
- API application: `backend.main:app`
- Job commands: `/api/jobs`
- Project metadata: `/api/projects`
- Database: `<data_root>/database/orchestration.db`

## Implemented

- Durable jobs, commands, leases, retries, checkpoints and restart recovery
- Persistent projects and source metadata
- Legacy pipeline compatibility through the durable job service
- Portable runtime paths and a local-only configuration guard
- Explicit `PIPELINE_NOT_READY` failure when no production adapter is installed

## Not implemented in this milestone

- Model discovery or download
- ComfyUI workflow execution
- Script, character, scene or storyboard generation
- TTS, lip sync, subtitles, BGM, composition or Jianying export
- Electron desktop packaging

Those capabilities belong to the subsequent sub-projects in the approved
2026-07-22 design. Historical backends and scripts remain reference-only and
must not be used to claim production success.

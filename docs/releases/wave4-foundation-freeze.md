# Wave 4 Foundation Freeze

## Status

Release status: Wave 4 RC1 candidate.
Deterministic code/contract freeze complete.
Final production release is blocked only on Wave 4E.2 live provider gates.

## Database

Latest migration: `007_provider_submissions.sql`

Migration chain: 001 → 002 → 003 → 004 → 005 → 006_provider_binding → 007_provider_submissions

## Contracts

- repository-backed worker lease
- durable provider binding (`jobs.provider_binding_json`, first-write-wins)
- immutable provider binding (replacement raises `ProviderBindingConflictError`)
- process restart recovery (`recover_expired_leases`)
- exact provider execution (no automatic fallback after binding)
- durable provider submission identity (`provider_submissions` table)
- immutable remote submission id (overwrite raises `ProviderSubmissionConflictError`)
- logical-attempt uniqueness: `UNIQUE(job_id, step_id, attempt)` + `UNIQUE submission_key`
- uncertain crash-window protection (`status=uncertain` is never blindly resubmitted)

## Submission State Machine

```
reserved
   ↓
submitting
   ↓
submitted
   ↓
completed

submitting + crash + no remote id
   ↓
uncertain   (requires explicit reconciliation, never auto-retry)
```

## Regression Baseline

Foundation worktree:

- Full pytest: 319 passed, 0 failed (incl. migration acceptance: fresh 001-007, legacy 005/006 upgrades, idempotent reopen)
- Cross-process restart: 10/10 repeated PASS
- Novel E2E (打脸系统 - 左移.txt): PASS

Main repository:

- Non-live pytest: 163 passed, 21 skipped, 0 failed, 0 errors

## Frozen "MUST NOT" Rules

- re-resolve provider after durable binding exists
- fallback to another provider after binding
- overwrite provider binding
- overwrite remote_submission_id
- submit again when remote_submission_id already exists
- blindly resubmit uncertain submission
- replay terminal jobs
- manufacture final_video/artifacts during recovery

## Known Environment-Dependent Tests

`tests/models/smoke/test_comfyui_smoke.py` — marked `live_provider` + `gpu`;
auto-skipped when ComfyUI is unreachable. Not counted as deterministic failure.

## Pending Live Gates (Wave 4E.2)

- [ ] real ComfyUI preflight (0 skip)
- [ ] real supported-provider generation (Wan, and LTX23 if declared supported)
- [ ] persisted binding == actual provider invocation
- [ ] submit → persist prompt_id → worker kill → resume existing remote task
- [ ] submit crash-window behavior against real ComfyUI
- [ ] no duplicate provider submission
## Wave 4E.2 Live Gate Commands (fixed)

Run on a machine with real ComfyUI + CUDA GPU. All commands are executed from `D:\AI_Manga_Studio`.

```
$env:AI_MANGA_LIVE_REQUIRED = "1"

# Gate A: preflight must be 0 failed / 0 skipped
python -m pytest tests/live/test_provider_preflight.py -m live_provider -q -s

# Gate B: at least one real provider generation
python -m pytest tests/live/test_wan_provider_smoke.py -m live_provider -q -s

# Gate C: LTX23 if declared supported
python -m pytest tests/live/test_ltx23_provider_smoke.py -m live_provider -q -s

# Gate D: live restart — submit real prompt -> persist prompt_id -> kill worker
# -> worker B resumes/polls the SAME prompt_id -> submit count == 1
```

Acceptance criteria:

- [ ] real ComfyUI preflight (0 skip, 0 fail)
- [ ] real supported-provider generation (valid media, ffprobe readable, non-zero duration)
- [ ] persisted binding == actual provider invocation
- [ ] submit -> persist prompt_id -> kill -> resume same remote task
- [ ] no duplicate provider submission (same logical attempt submitted once)

Only after all gates pass may `wave4-rc1` be promoted to a final production release.
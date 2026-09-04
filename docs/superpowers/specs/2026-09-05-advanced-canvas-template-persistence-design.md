# Advanced Canvas Template Persistence v0.9.1 — Design

Date: 2026-09-05
Status: Approved design, implementation pending
Scope: Project-local versioned production templates for Advanced Canvas and ProjectCockpit one-click production

## 1. Goal

Turn Advanced Canvas “Save as Template” and “Publish to One-click Production” into real, auditable production features without creating a second workflow engine.

A project may have many immutable template versions but exactly zero or one published version. ProjectCockpit consumes only the published version. If a project has no published template, existing system defaults remain in effect and production is not blocked.

A published template is configuration for the existing JobService/worker/provider/QC/review/export pipeline. It never replaces that pipeline.

## 2. Non-goals

v0.9.1 does not add:

- a cross-project/global template library;
- template marketplace, cloud sync, or multi-user permissions;
- template import/export files;
- arbitrary ComfyUI workflow JSON injection;
- custom Python stages or arbitrary HTTP providers;
- arbitrary executable DAGs;
- media/source-file storage inside templates;
- mutation of already-created or running Jobs;
- QC/review bypasses;
- silent downgrade of a required provider;
- physical deletion of historical template versions.

## 3. Architectural principle

Advanced Canvas is a control/configuration plane over the canonical production pipeline.

```text
Advanced Canvas
    | save
    v
Immutable Project Template Version
    | validate + compile
    v
Compiled Production Policy
    | publish pointer
    v
ProjectCockpit
    | resolve published policy or defaults
    v
createJob()
    v
Existing JobService -> Worker -> Providers -> QC/Review -> Export
```

Canvas layout is editable. Runtime execution semantics remain backend-authoritative.

## 4. Project-local version model

Use project-local immutable versions rather than a global library.

### 4.1 Template head

`project_production_templates`

- `project_id TEXT PRIMARY KEY`
- `published_version_id TEXT NULL`
- `latest_version INTEGER NOT NULL DEFAULT 0`
- `updated_at TEXT NOT NULL`

### 4.2 Immutable versions

`project_production_template_versions`

- `id TEXT PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `version INTEGER NOT NULL`
- `name TEXT NOT NULL DEFAULT ''`
- `schema_version INTEGER NOT NULL`
- `content_json TEXT NOT NULL`
- `content_sha256 TEXT NOT NULL`
- `compiled_json TEXT NOT NULL`
- `compiled_sha256 TEXT NOT NULL`
- `status TEXT NOT NULL DEFAULT 'active'` (`active` or `archived`)
- `created_at TEXT NOT NULL`
- `published_at TEXT NULL`
- `UNIQUE(project_id, version)`

Historical version payloads are never updated. A new save creates a new version.

The published pointer may move backward to a historical compatible version; that is rollback. Rollback does not delete newer versions.

## 5. Save semantics

Saving is independent from publishing.

Within a `BEGIN IMMEDIATE` transaction:

1. Load/create the project template head.
2. Compute `next_version = latest_version + 1`.
3. Normalize and validate the user-facing template payload.
4. Compile it into the backend production policy.
5. Compute SHA256 for normalized source and compiled policy.
6. Insert the immutable version.
7. Update `latest_version`.
8. Commit.

Concurrent saves must never create duplicate project version numbers. `BEGIN IMMEDIATE` plus `UNIQUE(project_id, version)` provides the database guard. A conflicting request returns `409 TEMPLATE_VERSION_CONFLICT`; the client refreshes and may save again.

A save does not alter `published_version_id`.

## 6. Publish and rollback semantics

Publishing atomically changes only the project’s published pointer after verifying the selected version:

- belongs to the project;
- is not archived;
- uses a supported schema version;
- has matching source and compiled hashes;
- has a valid canonical compiled policy;
- contains no forbidden QC/review bypass;
- contains only runtime-supported stage/provider policies.

Publishing an older compatible version is rollback.

Publishing never changes an existing Job. A Job keeps the settings and provenance resolved at creation time.

The currently published version cannot be archived. Another version must be published first.

## 7. Template schema v1

The first schema is explicitly `schema_version: 1`.

Representative shape:

```json
{
  "schema_version": 1,
  "canvas": {
    "nodes": [],
    "edges": []
  },
  "production": {
    "shot_duration": 5,
    "width": 1080,
    "height": 1920,
    "fps": 24,
    "options": {
      "style": "anime",
      "local_first": true
    }
  },
  "stage_policy": {
    "stages": []
  }
}
```

Only backend-whitelisted fields are executable. Canvas positions and presentation metadata may be retained for editing but cannot create runtime semantics by themselves.

Templates never contain media files, arbitrary filesystem paths to models/workflows, arbitrary provider URLs, or executable code.

## 8. Canonical stage contract

The existing Canvas UI maps to canonical orchestration stages:

- 小说文本 -> `load_input`
- 场景拆解 -> `planning`
- 角色 Bible -> `character_design`
- 分镜脚本 -> `planning`
- 关键帧 -> `visual_generate`
- TI2V 视频生成 -> `video_generate`
- 配音/字幕 -> `audio_tts`
- 合成导出 -> `composition_compose`

The Canvas `scene` and `storyboard` nodes are two UI views over the same canonical `planning` stage. Compilation folds them into one planning execution policy; it must not create duplicate Job steps.

Canvas node positions do not determine execution order. User edges express intent, but publication requires backend DAG validation against canonical dependencies.

Invalid examples include `video_generate -> planning` or composition before video generation.

## 9. Required and optional stages

Hard production stages cannot be disabled through a template. At minimum, input, planning, required generation/composition boundaries, QC/review enforcement, and export safety remain backend-controlled.

A stage may be marked disabled only when the backend capability registry explicitly declares that stage optional for the selected production contract.

“Delete node” in the editable Canvas must not physically delete a required runtime stage. For executable policy, optional behavior is represented as an explicit enabled/disabled setting and validated server-side.

Unknown/unregistered stages may exist only as non-executable design nodes. They prevent publication if represented as executable stages.

## 10. Provider policy

Templates express constrained provider policy, never direct provider execution configuration.

Supported modes:

- `runtime_default`: inherit the existing runtime/provider router.
- `preferred`: prefer a named registered provider; fallback is allowed only when explicitly supported by runtime policy.
- `required`: the named registered provider must be used; unavailable/failed provider causes a visible failure/retry state rather than silent downgrade.

Examples of registered policy targets may include `minimax_h3`, `wan`, `flux`, and `cosyvoice`, but the authoritative set comes from the backend runtime registry.

A required MiniMax H3 policy must never silently become Wan. The same rule applies to other required providers.

v0.9.1 does not expose arbitrary checkpoint names, model filesystem paths, sampler/CFG internals, ComfyUI node IDs, or arbitrary workflow JSON as template-executable settings.

## 11. Validation and compilation

Publishing and saving use isolated backend units:

### TemplateValidator

Responsibilities:

- schema validation;
- field/range validation;
- reject unknown executable fields/stages;
- reject forbidden safety/QC/review controls;
- validate canonical dependency constraints;
- validate provider policy syntax.

### CanonicalTemplateCompiler

Responsibilities:

- fold UI nodes into canonical stages;
- collapse scene/storyboard to one `planning` policy;
- resolve only whitelisted production settings;
- validate required/optional stage capability;
- validate provider targets against the runtime registry/capabilities;
- produce deterministic `compiled_json`.

ProjectCockpit consumes `compiled_json`, not raw Canvas `content_json`.

## 12. API contract

Add project-scoped endpoints:

- `POST /api/workspace/{project_id}/production-templates` — save a new immutable version.
- `GET /api/workspace/{project_id}/production-templates` — list versions and latest/published state.
- `GET /api/workspace/{project_id}/production-templates/{version}` — read one version.
- `POST /api/workspace/{project_id}/production-templates/{version}/publish` — publish or rollback to a version.
- `GET /api/workspace/{project_id}/production-template/published` — resolve the current published version for production/UI.

The published endpoint returns an explicit “no published template” result rather than an error, allowing the existing default-production path.

## 13. One-click production resolution

`ProjectCockpit.startOneClick()` keeps its existing input preparation and existing `createJob()` path.

Before Job creation it resolves the project’s published template:

```text
prepare input
  -> resolve published project template
       -> none: use current system defaults
       -> exists: verify and use compiled policy
  -> createJob()
```

Compatibility rule:

- no published template -> current defaults continue unchanged (`shot_duration=5`, `1080x1920`, `24fps`, `style=anime`, `local_first=true`);
- valid published template -> compiled settings are used;
- a published pointer exists but the version/hash/compiler contract is invalid -> fail closed and do not create a Job.

The invalid-published-template case must never silently fall back to defaults.

## 14. Job provenance

The existing Job `settings` JSON stores immutable provenance resolved at Job creation.

For a project template:

```json
{
  "template": {
    "source": "project_published_template",
    "version_id": "ptv_xxx",
    "version": 3,
    "schema_version": 1,
    "sha256": "...",
    "compiled_sha256": "..."
  }
}
```

Without a published template:

```json
{
  "template": {
    "source": "system_default",
    "version_id": null,
    "version": null
  }
}
```

Changing the project’s published pointer after Job A is created cannot mutate Job A. A later Job B uses the newly published version.

## 15. UI behavior

### Advanced Canvas

Show authoritative template state, for example:

- latest saved version;
- published version;
- dirty/clean Canvas state;
- schema version;
- production status text.

Actions:

- **保存为模板** creates a new immutable version and reports the returned version.
- **发布到一键成片** publishes an already-saved clean version.
- **版本历史** exposes saved versions and allows publishing a historical compatible version.

If Canvas has unsaved changes, publish is disabled/fails closed. Publishing must not silently auto-save because save and publish have intentionally separate semantics.

Messages must make the distinction explicit, e.g. “已保存 v8，当前生产仍使用 v5” and “v8 已发布；后续新建任务使用 v8，现有任务不变”.

### ProjectCockpit

Show whether one-click production will use system defaults or a project template, including useful summary metadata such as version and production dimensions/provider policy.

After Job creation, the Job UI can display template provenance from authoritative Job settings.

## 16. Archive semantics

v0.9.1 provides archive semantics instead of physical deletion.

Archived versions remain available for historical Job audit but are hidden from the normal active-version list. A published version cannot be archived. Unarchive may restore visibility.

No historical payload or hash is physically deleted in this release.

## 17. Schema compatibility

Historical source payloads retain their original `schema_version` and hashes.

Future schema migration is explicit and backend-owned. A compatible older version may be compiled through a supported migration/compiler path. An incompatible version becomes viewable/auditable but not publishable until explicitly migrated/copied into a supported new version.

Existing Jobs remain unaffected because they retain creation-time settings and provenance.

## 18. Error contract

Use fail-closed errors with stable machine-readable codes:

- `400 TEMPLATE_VALIDATION_FAILED`
- `404 TEMPLATE_VERSION_NOT_FOUND`
- `409 TEMPLATE_VERSION_CONFLICT`
- `409 TEMPLATE_PUBLISH_CONFLICT`
- `409 TEMPLATE_UNSAVED_CHANGES` (frontend may prevent the request; backend still validates supplied revision/version contract)
- `422 TEMPLATE_PROVIDER_POLICY_UNSUPPORTED`
- `422 TEMPLATE_STAGE_POLICY_INVALID`

A UI success state is shown only after an authoritative backend response.

## 19. Testing requirements

### Persistence/data layer

Cover:

- first save creates v1;
- sequential saves create v1/v2/v3;
- historical payloads remain immutable;
- project/version uniqueness;
- isolation between projects;
- atomic publish pointer changes;
- rollback by publishing an older version;
- published version cannot be archived;
- concurrent save conflict safety;
- save/publish concurrency cannot expose a partial version.

### Validator/compiler

Cover:

- default Canvas compiles;
- unknown executable stage fails;
- missing/disabled required stage fails;
- invalid reverse dependencies fail;
- scene + storyboard fold to one planning stage;
- unknown provider fails;
- H3 required without capability fails;
- preferred provider with explicitly supported fallback passes;
- QC/review bypass fields fail.

### API

Cover successful save/list/read/publish and fail-closed missing, cross-project, incompatible, invalid-hash, and invalid-policy cases.

### Job integration

Cover:

1. no template preserves current default one-click settings;
2. published v3 creates a Job from v3 compiled policy with provenance;
3. Job A created from v3 remains v3 after v4 is published;
4. Job B created afterward uses v4;
5. corrupt/invalid published template prevents Job creation rather than falling back.

### Frontend

Cover:

- publish disabled with no saved version;
- save creates and displays v1;
- dirty Canvas disables publish;
- second save creates v2;
- publish updates authoritative published state;
- historical publish implements rollback;
- ProjectCockpit shows defaults vs published template;
- createJob uses the resolved compiled values;
- a contract test prevents reintroduction of hardcoded one-click settings that bypass the template resolver.

## 20. CI scope

The unified Studio CI must include all new backend workspace/orchestration template tests and all Advanced Canvas/ProjectCockpit frontend template tests. Existing orchestration stage-execution tests remain mandatory to guard against accidental creation of a second execution engine.

## 21. Acceptance criteria

v0.9.1 is complete when:

1. Advanced Canvas can save immutable project-local template versions.
2. A saved clean version can be published and a historical compatible version can be republished as rollback.
3. ProjectCockpit automatically consumes the project’s published compiled policy.
4. Projects without a published template behave exactly as before.
5. Invalid published templates fail closed and never silently use defaults.
6. Job settings record creation-time template provenance.
7. Provider `required` policy cannot silently downgrade.
8. Templates cannot bypass QC/review or create arbitrary executable stages/providers.
9. Existing running/completed Jobs are unaffected by later template publication.
10. Backend/frontend tests and unified CI are green.

## 22. Implementation boundary

This specification adds persistence, validation/compilation, project publication state, one-click resolution, provenance, and UI integration. It deliberately reuses the existing JobService and provider routing. Any requirement that needs a second workflow engine, arbitrary runtime graph execution, or global template sharing is a separate future design.

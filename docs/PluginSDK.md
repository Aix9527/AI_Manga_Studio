---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: ac05b1368557ee08912a0f1b051adb10_2d11d72686a911f18766525400f8a581
    ReservedCode1: fP1fKGf5i/QzNO4GwIxnyMyCjBw5T5WtsvKWPRKH/UJRUnkbiIGOQWJLPcklEFajg1ePcN1m7VcQCruyf35yIpuIalXL2sAiZFFg8k5zXBc6jYdnyjKMBaI5SXycI4tZ0vDafc4VDg48kSKcDOLw1roNEWcquvrNGjYT3aGFBZTuocZvvE1hmivUQE8=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: ac05b1368557ee08912a0f1b051adb10_2d11d72686a911f18766525400f8a581
    ReservedCode2: fP1fKGf5i/QzNO4GwIxnyMyCjBw5T5WtsvKWPRKH/UJRUnkbiIGOQWJLPcklEFajg1ePcN1m7VcQCruyf35yIpuIalXL2sAiZFFg8k5zXBc6jYdnyjKMBaI5SXycI4tZ0vDafc4VDg48kSKcDOLw1roNEWcquvrNGjYT3aGFBZTuocZvvE1hmivUQE8=
---

# Plugin SDK | 插件开发指南

## Overview

The Plugin SDK enables third-party developers to extend AI_Manga_Studio without modifying core code. Plugins can add new AI providers, custom workflow stages, export formats, validators, and post-processors — all through standardized interfaces and lifecycle hooks.

## Responsibilities

- Define plugin interface contracts
- Manage plugin lifecycle (load, initialize, execute, cleanup)
- Provide sandboxed execution environment
- Handle plugin discovery and versioning
- Expose core APIs to plugins via SDK

## Plugin Types

| Type | Interface | Description |
|------|-----------|-------------|
| **AI Provider** | `ImageProvider`, `VideoProvider`, `LLMProvider`, `AudioProvider` | New model integrations |
| **Workflow Stage** | `StagePlugin` | Custom production stages |
| **Exporter** | `ExportPlugin` | New output formats |
| **Validator** | `ValidatorPlugin` | Quality and consistency checks |
| **Post-Processor** | `PostProcessPlugin` | After-generation effects and adjustments |

## Plugin Lifecycle

```
Initialize → Validate → Execute → Report → Cleanup
```

### 1. Initialize

```python
class MyPlugin(BasePlugin):
    async def initialize(self, config: PluginConfig) -> None:
        """Called when the plugin is loaded.
        
        Use this to:
        - Validate configuration
        - Establish connections
        - Load resources (models, templates)
        - Register with internal systems
        """
        self.config = config
        # Validate required settings
        if not config.api_key:
            raise PluginInitError("API key is required")
```

### 2. Validate

```python
    async def validate(self, context: PluginContext) -> ValidationResult:
        """Called before execution to verify preconditions.
        
        Use this to:
        - Check input data integrity
        - Verify dependencies are available
        - Confirm resource availability
        """
        if not context.input_data:
            return ValidationResult(valid=False, errors=["No input data provided"])
        return ValidationResult(valid=True)
```

### 3. Execute

```python
    async def execute(self, context: PluginContext) -> PluginOutput:
        """The main execution method.
        
        Use this to:
        - Perform the plugin's core function
        - Report progress via context.report_progress()
        - Handle errors gracefully
        """
        try:
            result = await self._do_work(context.input_data)
            context.report_progress(1.0, "Complete")
            return PluginOutput(success=True, data=result)
        except Exception as e:
            return PluginOutput(success=False, error=str(e))
```

### 4. Report

```python
    async def report(self, context: PluginContext, output: PluginOutput) -> PluginReport:
        """Generate execution report.
        
        Use this to:
        - Summarize what was done
        - Provide metrics and statistics
        - Log warnings or recommendations
        """
        return PluginReport(
            plugin_name=self.name,
            duration_seconds=context.elapsed,
            items_processed=len(output.data),
            warnings=context.warnings
        )
```

### 5. Cleanup

```python
    async def cleanup(self, context: PluginContext) -> None:
        """Called after execution (success or failure).
        
        Use this to:
        - Close connections
        - Release resources
        - Remove temporary files
        """
        await self._close_connections()
        self._clean_temp_files()
```

## Plugin Manifest

Each plugin requires a `plugin.yaml` manifest:

```yaml
name: "my-custom-provider"
version: "1.0.0"
type: "ai_provider"
provider_type: "image"
author: "Your Name"
description: "Custom image generation provider for MyModel"
dependencies:
  python: ">=3.11"
  packages:
    - "my-model-sdk>=2.0.0"
entry_point: "my_plugin.provider:MyImageProvider"
config_schema:
  api_key:
    type: string
    required: true
    description: "API key for MyModel service"
  model:
    type: string
    default: "v2"
    description: "Model version to use"
```

## Plugin Context

The `PluginContext` object provides plugins with access to core systems:

```python
class PluginContext:
    # Input data for this execution
    input_data: dict

    # Access to project database (read-only by default)
    project: ProjectAccess

    # Access to character memory (read-only by default)
    character_memory: CharacterMemoryAccess

    # File system access (sandboxed to plugin's workspace)
    workspace: Path

    # Progress reporting
    async def report_progress(self, fraction: float, message: str) -> None: ...

    # Logging
    def log_info(self, message: str) -> None: ...
    def log_warning(self, message: str) -> None: ...
    def log_error(self, message: str) -> None: ...

    # Elapsed time since execution start
    elapsed: float
```

## Plugin Registration

```python
# In the plugin's __init__.py
from ai_manga_studio.plugin_sdk import register_plugin
from .provider import MyImageProvider

register_plugin(MyImageProvider)
```

## Security Model

- Plugins run in the same process as the main application
- File system access is sandboxed to the plugin's workspace directory
- Network access is allowed but logged
- Plugins cannot modify core database tables directly — they use provided accessors
- Plugin code is not sandboxed at the Python level (trust-based model for now)

## Future

- Plugin sandboxing with subprocess isolation
- Plugin marketplace with discovery and installation UI
- Plugin dependency resolution and version constraints
- Plugin hot-reloading during development
- Plugin telemetry and usage analytics (opt-in)
- Signed plugin packages for authenticity verification
*（内容由AI生成，仅供参考）*

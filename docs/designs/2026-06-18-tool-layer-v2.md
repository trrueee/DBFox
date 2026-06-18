# DBFox Tool Layer v2 Design

Date: 2026-06-18
Status: implemented

## Goal

Rebuild the DBFox tool layer as a Python-first typed Tool SDK. Built-in tools
are defined by `BaseTool` classes, not YAML files or string-registered handler
functions. The runtime owns validation, policy checks, state projection,
execution, observation building, artifacts, and tracing.

This is a direct refactor to the target architecture. It intentionally removes
legacy handler/YAML paths instead of adding migration compatibility.

## Design Principles

1. Python class definitions are the source of truth for built-in tools.
2. Tool execution has one path through a central runtime gateway.
3. Tools can only read state keys declared by their contract.
4. Tools return typed output; they do not mutate agent state.
5. State updates are applied by one reducer layer.
6. Model-facing tool names may be aliases, but internal canonical names are
   dotted names.
7. Dead abstractions should be deleted, not preserved as future blueprints.

## Target Architecture

```text
Model tool call
  -> PolicyGate
  -> ToolRuntime.invoke(call)
  -> ToolRegistry.require(name)
  -> input validation
  -> state projection
  -> BaseTool.run(input, ToolRunContext)
  -> output validation
  -> StateReducer.apply(tool, output)
  -> ToolObservation + trace events + artifacts
```

## BaseTool Contract

Every built-in tool is an instance of a `BaseTool` subclass:

```python
class BaseTool(Generic[I, O]):
    name: str
    group: str
    description: str
    input_model: type[I]
    output_model: type[O]
    policy: ToolPolicy
    execution: ToolExecutionSpec
    state: ToolStateSpec
    artifacts: ArtifactSpec

    def run(self, tool_input: I, context: ToolRunContext) -> O:
        ...
```

`ToolStateSpec` declares all state interaction:

```python
class ToolStateSpec(BaseModel):
    consumes: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    clear_on_success: tuple[str, ...] = ()
    merge_strategy: Literal["reuse", "new", "always_new"] = "reuse"
```

`ToolRunContext.state` is a read-only projection. It contains only keys listed
in `state.consumes`.

## Canonical Tool Names

The internal tool surface is:

```text
environment.get_profile
schema.list_tables
schema.describe_table
schema.refresh_catalog
semantic.resolve
db.observe
db.search
db.inspect
db.preview
db.query
db.remember
result.profile
chart.suggest
answer.synthesize
memory.search
memory.write
memory.delete
memory.summarize_session
escalate.tool_group
```

The old `analyze_data` name is removed. The equivalent capability is
`result.profile`.

## YAML Position

YAML is not used for built-in tools. Built-in tool contracts live in Python.

Future external plugin tools may use YAML as an extension manifest, but that is
out of scope for this refactor. The internal runtime must not depend on YAML
discovery.

## Runtime Units

New runtime modules live under `engine/tools/runtime/`:

- `base.py` defines `BaseTool` and tool metadata models.
- `context.py` defines `ToolRunContext`.
- `registry.py` owns typed tool registration and lookup.
- `runtime.py` invokes tools and builds observations.
- `state_reducer.py` applies typed tool outputs to agent state updates.
- `manifest.py` exports tool schemas to model-facing `StructuredTool`s.
- `errors.py` defines tool contract/runtime errors.

Built-in tool classes are registered directly in `engine/tools/dbfox_tools.py`.

## State Reducer

Tools return output models. The reducer maps successful outputs into state:

| Tool | State writes |
| --- | --- |
| `environment.get_profile` | `environment_profile`, `database_map` |
| `semantic.resolve` | `semantic_resolution` |
| `db.observe` | `database_map` |
| `db.search` | `db_search_results` |
| `db.inspect` | `db_inspection` |
| `db.preview` | `db_preview` |
| `db.query` | `execution`, `sql` |
| `result.profile` | `result_profile` |
| `chart.suggest` | `chart_suggestion` |
| `answer.synthesize` | `answer`, `final_answer` |
| `workspace.*` | out of scope for this refactor |

On failure, the reducer writes `last_failed_tool_call`, `last_error_telemetry`,
and `error` using one common failure path.

## Required Deletions

The refactor must delete:

- Built-in YAML specs under `engine/tools/builtin/*.yaml`.
- `engine/agent_core/handler_registry.py`.
- String handler registration in `engine/tools/dbfox_tools.py`.
- `RegisteredTool.handler`.
- `RegisteredTool.base_tool`.
- The `_execute_base_tool` / `_execute_legacy_handler` split in
  `engine/agent/nodes/tool_node.py`.
- `ToolRuntimeGateway` as a separate validation-only helper.
- The `analyze_data` canonical tool name.
- Tests that assert legacy YAML/handler behavior.

## Behavior Contract

For database questions, DBFox continues to operate as a single ReAct-style data
analysis agent. The model decides which tool to use, but the runtime enforces
tool boundaries.

Analytical path:

```text
db.query
  -> result.profile
  -> chart.suggest when useful
  -> answer.synthesize
```

Simple lookup path:

```text
db.query
  -> direct interpreted answer
```

The progress guard nudges the model toward `result.profile` only when it is
cycling through repeated successful queries without analysis or an answer.

## Tests

The new architecture is covered by tests for:

1. Registry loads built-in `BaseTool` instances without YAML.
2. Model manifest exports aliases and Pydantic input schemas.
3. Runtime validates input and output models.
4. Runtime projects only declared state keys.
5. State reducer writes expected state for each core tool.
6. Policy gate reads `BaseTool.policy`.
7. `tool_node` executes through one runtime path.
8. `analyze_data` no longer exists.

## Out of Scope

- External plugin YAML support.
- Multi-agent handoff architecture.
- Frontend timeline redesign.
- Changing database safety semantics.
- Backward compatibility for old tool names.

# Tool Layer v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Replace DBFox's legacy YAML/handler tool layer with a Python-first typed `BaseTool` runtime.

**Architecture:** Built-in tools are `BaseTool` classes registered directly in a typed registry. `ToolRuntime` validates input/output, projects state by contract, invokes tools, and passes observations to `StateReducer`.

**Tech Stack:** Python 3.12, Pydantic v2, LangChain `StructuredTool`, pytest.

**Execution Status:** Implemented on 2026-06-18.

---

## File Structure

- Create `engine/tools/runtime/base.py`: tool metadata models and `BaseTool`.
- Create `engine/tools/runtime/context.py`: `ToolRunContext`.
- Create `engine/tools/runtime/registry.py`: typed registry and built-in registration.
- Create `engine/tools/runtime/runtime.py`: single execution gateway.
- Create `engine/tools/runtime/state_reducer.py`: state updates from observations.
- Create `engine/tools/runtime/manifest.py`: model-facing tool export.
- Create `engine/tools/runtime/errors.py`: contract/runtime errors.
- Modify `engine/agent/nodes/tool_node.py`: execute tools through `ToolRuntime`.
- Modify `engine/agent/nodes/policy_node.py`: consume the typed registry.
- Modify `engine/policy/gate.py`: read policy from `BaseTool.spec`.
- Modify `engine/agent/tools/registry_bridge.py`: export tools from runtime registry.
- Modify `engine/agent/model/system_prompt.py`: replace `analyze_data` with `result.profile`.
- Modify `engine/agent/progress/fast_path.py`: use `result_profile` and `result.profile`.
- Modify or replace `engine/tools/dbfox_tools.py`: direct built-in tool registration.
- Delete `engine/tools/builtin/*.yaml`.
- Delete `engine/agent_core/handler_registry.py`.
- Delete `engine/tools/tool_runtime_gateway.py`.
- Update tests under `engine/tests/` and `engine/agent/tests/`.

---

### Task 1: Runtime Contract Foundation

**Files:**
- Create: `engine/tools/runtime/base.py`
- Create: `engine/tools/runtime/context.py`
- Create: `engine/tools/runtime/errors.py`
- Create: `engine/tools/runtime/__init__.py`
- Test: `engine/tests/test_tool_runtime_v2.py`

- [x] **Step 1: Write failing tests**

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from engine.tools.runtime.base import (
    ArtifactSpec,
    BaseTool,
    ToolExecutionSpec,
    ToolPolicy,
    ToolStateSpec,
)
from engine.tools.runtime.context import ToolRunContext


class EchoInput(BaseModel):
    value: str


class EchoOutput(BaseModel):
    value: str
    seen: dict[str, Any]


class EchoTool(BaseTool[EchoInput, EchoOutput]):
    name = "test.echo"
    group = "test"
    description = "Echo a value."
    input_model = EchoInput
    output_model = EchoOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(consumes=("allowed",), produces=("echo",))
    artifacts = ArtifactSpec()

    def run(self, tool_input: EchoInput, context: ToolRunContext) -> EchoOutput:
        return EchoOutput(value=tool_input.value, seen=dict(context.state))


def test_base_tool_exposes_typed_spec():
    tool = EchoTool()

    assert tool.spec.name == "test.echo"
    assert tool.spec.group == "test"
    assert tool.spec.input_model is EchoInput
    assert tool.spec.output_model is EchoOutput
    assert tool.spec.state.consumes == ("allowed",)
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest engine/tests/test_tool_runtime_v2.py::test_base_tool_exposes_typed_spec -q`

Expected: FAIL because `engine.tools.runtime.base` does not exist.

- [x] **Step 3: Implement runtime contract models**

Create minimal Pydantic/dataclass models and `BaseTool.spec` to satisfy the test.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest engine/tests/test_tool_runtime_v2.py::test_base_tool_exposes_typed_spec -q`

Expected: PASS.

---

### Task 2: Registry and Manifest

**Files:**
- Create: `engine/tools/runtime/registry.py`
- Create: `engine/tools/runtime/manifest.py`
- Modify: `engine/agent/tools/registry_bridge.py`
- Test: `engine/tests/test_tool_runtime_v2.py`

- [x] **Step 1: Write failing registry tests**

```python
def test_registry_registers_base_tools_and_rejects_duplicates():
    from engine.tools.runtime.registry import ToolRegistry

    registry = ToolRegistry()
    registry.register(EchoTool())

    assert registry.require("test.echo").name == "test.echo"

    try:
        registry.register(EchoTool())
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate registration should fail")


def test_manifest_exports_model_safe_alias():
    from engine.tools.runtime.manifest import build_langchain_tools
    from engine.tools.runtime.registry import ToolRegistry

    registry = ToolRegistry()
    registry.register(EchoTool())

    tools = build_langchain_tools(registry, allowed_groups=["test"])

    assert [tool.name for tool in tools] == ["test_echo"]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest engine/tests/test_tool_runtime_v2.py::test_registry_registers_base_tools_and_rejects_duplicates engine/tests/test_tool_runtime_v2.py::test_manifest_exports_model_safe_alias -q`

Expected: FAIL because registry/manifest are not implemented.

- [x] **Step 3: Implement registry and manifest**

Implement typed registration, lookup, listing, group filtering, and alias export.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest engine/tests/test_tool_runtime_v2.py::test_registry_registers_base_tools_and_rejects_duplicates engine/tests/test_tool_runtime_v2.py::test_manifest_exports_model_safe_alias -q`

Expected: PASS.

---

### Task 3: ToolRuntime Invocation

**Files:**
- Create: `engine/tools/runtime/runtime.py`
- Test: `engine/tests/test_tool_runtime_v2.py`

- [x] **Step 1: Write failing runtime tests**

```python
def test_runtime_projects_only_declared_state_keys():
    from engine.tools.runtime.registry import ToolRegistry
    from engine.tools.runtime.runtime import ToolRuntime

    registry = ToolRegistry()
    registry.register(EchoTool())
    runtime = ToolRuntime(registry)

    observation = runtime.invoke(
        tool_name="test.echo",
        raw_input={"value": "hello"},
        state={"allowed": 1, "secret": 2},
        request=None,
        db=None,
    )

    assert observation.status == "success"
    assert observation.output == {"value": "hello", "seen": {"allowed": 1}}


def test_runtime_reports_validation_failure_as_failed_observation():
    from engine.tools.runtime.registry import ToolRegistry
    from engine.tools.runtime.runtime import ToolRuntime

    registry = ToolRegistry()
    registry.register(EchoTool())
    runtime = ToolRuntime(registry)

    observation = runtime.invoke(
        tool_name="test.echo",
        raw_input={},
        state={},
        request=None,
        db=None,
    )

    assert observation.status == "failed"
    assert "Input contract failed" in observation.error
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest engine/tests/test_tool_runtime_v2.py::test_runtime_projects_only_declared_state_keys engine/tests/test_tool_runtime_v2.py::test_runtime_reports_validation_failure_as_failed_observation -q`

Expected: FAIL because `ToolRuntime` is not implemented.

- [x] **Step 3: Implement `ToolRuntime.invoke`**

Implement lookup, Pydantic input validation, state projection, context creation,
tool execution, output validation, latency, and failed observations.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest engine/tests/test_tool_runtime_v2.py::test_runtime_projects_only_declared_state_keys engine/tests/test_tool_runtime_v2.py::test_runtime_reports_validation_failure_as_failed_observation -q`

Expected: PASS.

---

### Task 4: StateReducer

**Files:**
- Create: `engine/tools/runtime/state_reducer.py`
- Modify: `engine/agent_core/databinding.py`
- Test: `engine/tests/test_tool_runtime_v2.py`

- [x] **Step 1: Write failing reducer tests**

```python
from engine.agent_core.types import ToolObservation


def test_state_reducer_applies_result_profile():
    from engine.tools.runtime.state_reducer import apply_tool_observation_to_state

    obs = ToolObservation(
        name="result.profile",
        status="success",
        output={"row_count": 3},
        latency_ms=1,
    )

    update = apply_tool_observation_to_state(
        state={},
        tool_name="result.profile",
        observation=obs,
    )

    assert update["result_profile"] == {"row_count": 3}
    assert update["trace_events"][0]["payload"]["tool_name"] == "result.profile"


def test_state_reducer_clears_db_query_errors():
    from engine.tools.runtime.state_reducer import apply_tool_observation_to_state

    obs = ToolObservation(
        name="db.query",
        status="success",
        output={"status": "success", "returned_rows": 1, "safe_sql": "SELECT 1"},
        latency_ms=1,
    )

    update = apply_tool_observation_to_state(
        state={"error": "old"},
        tool_name="db.query",
        observation=obs,
    )

    assert update["error"] is None
    assert update["execution"]["success"] is True
    assert update["sql"] == "SELECT 1"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest engine/tests/test_tool_runtime_v2.py::test_state_reducer_applies_result_profile engine/tests/test_tool_runtime_v2.py::test_state_reducer_clears_db_query_errors -q`

Expected: FAIL because reducer does not exist.

- [x] **Step 3: Implement reducer and delegate old databinding entry point**

Implement `apply_tool_observation_to_state` and make
`engine.agent_core.databinding.apply_tool_result_to_state` call it.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest engine/tests/test_tool_runtime_v2.py::test_state_reducer_applies_result_profile engine/tests/test_tool_runtime_v2.py::test_state_reducer_clears_db_query_errors -q`

Expected: PASS.

---

### Task 5: Built-in Tool Registration and Legacy Deletion

**Files:**
- Modify: `engine/tools/dbfox_tools.py`
- Create built-in tool classes in `engine/tools/dbfox_tools.py`
- Delete: `engine/tools/builtin/*.yaml`
- Delete: `engine/agent_core/handler_registry.py`
- Delete: `engine/tools/tool_runtime_gateway.py`
- Test: `engine/tests/test_tool_runtime_v2.py`

- [x] **Step 1: Write failing built-in registry tests**

```python
def test_builtin_registry_loads_base_tools_without_yaml():
    from engine.tools.dbfox_tools import register_dbfox_tools

    registry = register_dbfox_tools()
    names = {tool.name for tool in registry.list_tools()}

    assert "db.query" in names
    assert "result.profile" in names
    assert "chart.suggest" in names
    assert "answer.synthesize" in names
    assert "analyze_data" not in names
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest engine/tests/test_tool_runtime_v2.py::test_builtin_registry_loads_base_tools_without_yaml -q`

Expected: FAIL because the existing registry loads YAML and `analyze_data`.

- [x] **Step 3: Implement built-in `BaseTool` classes**

Wrap existing tool functions behind typed `BaseTool` classes. Reuse existing
business logic; do not rewrite SQL safety or database behavior.

- [x] **Step 4: Delete legacy files and old tests**

Remove built-in YAML specs, handler registry, validation-only gateway, and tests
that assert legacy behavior.

- [x] **Step 5: Run test to verify it passes**

Run: `pytest engine/tests/test_tool_runtime_v2.py::test_builtin_registry_loads_base_tools_without_yaml -q`

Expected: PASS.

---

### Task 6: Agent Integration

**Files:**
- Modify: `engine/agent/nodes/tool_node.py`
- Modify: `engine/agent/tools/registry_bridge.py`
- Modify: `engine/agent/model/system_prompt.py`
- Modify: `engine/agent/progress/fast_path.py`
- Modify: `engine/agent/nodes/policy_node.py`
- Test: `engine/tests/test_analysis_flow.py`

- [x] **Step 1: Update tests for canonical names**

Replace `analyze_data` expectations with `result.profile` / `result_profile`.

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest engine/tests/test_analysis_flow.py -q`

Expected: FAIL before integration updates.

- [x] **Step 3: Integrate runtime registry into agent nodes**

`tool_node.py` invokes `ToolRuntime`. Model manifest export uses
`engine.tools.runtime.manifest.build_langchain_tools`.

- [x] **Step 4: Update prompt and progress guard**

Prompt instructs analytical flows to call `result.profile`. Progress guard
checks `result_profile`.

- [x] **Step 5: Run tests to verify they pass**

Run: `pytest engine/tests/test_analysis_flow.py -q`

Expected: PASS.

---

### Task 7: Verification

**Files:**
- All modified files.

- [x] **Step 1: Run targeted tool tests**

Run: `pytest engine/tests/test_tool_runtime_v2.py engine/tests/test_analysis_flow.py -q`

Expected: PASS.

- [x] **Step 2: Run broader engine tests**

Run: `pytest engine/ -q --ignore=engine/agent/tests/test_e2e_qwen.py`

Expected: PASS or report exact pre-existing failures with evidence.

- [x] **Step 3: Search for deleted legacy concepts**

Run: `rg "HandlerRegistry|handler_registry|base_tool|ToolRuntimeGateway|engine/tools/builtin/.*yaml" engine docs -g "*.py" -g "*.md" -g "*.yaml"`

Expected: no production references to removed runtime concepts. Design docs may mention removed concepts only as deletion notes.

Verification result:

- `pytest engine/tests/test_tool_runtime_v2.py engine/tests/test_analysis_flow.py engine/tests/test_tool_contract.py engine/agent/tests/test_policy_gate.py engine/tests/test_architecture.py -q` passed: 58 passed, 3 warnings.
- `pytest engine/ -q --ignore=engine/agent/tests/test_e2e_qwen.py` ran: 624 passed, 2 skipped, 3 failed. The remaining failures are startup/migration database setup issues where the `projects` table is missing, not tool-layer behavior.


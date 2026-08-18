# Capability DLC P0 baseline

> 文档类型：质量证据 / 架构基线
>
> 状态：当前
>
> 最后核验：2026-08-18
>
`DLC_IMPLEMENTATION_BASE_SHA`: `17c4c7d876bb6d499d863108ee51da0cfb82d5ef`
Authoritative roadmap: GitHub Issue #42.  This is P0 evidence, not a second
architecture proposal.

## Frozen current state

| Contract | Current observed behavior | Characterization coverage |
| --- | --- | --- |
| Agent session ownership | `AgentSession` and admission are datasource-rooted; admission rejects a different datasource. | `engine/agent/tests/test_session_repository.py` |
| Tool composition | P1 replaces the duplicate parent/worker registrar lists with `engine.runtime_composition.build_product_tool_registry()`. Both registries freeze and expose the same names; RemoteJob remains in-process-only. | `engine/tests/test_capability_dlc_p0_baseline.py`, `engine/tests/test_builtin_registry_contract.py`, `engine/tests/test_runtime_composition.py` |
| Execution resources | Database and Workspace are serializable `ResourceScopeRef`s; a worker attempt carries `ToolAttemptRequest`; `ToolRunContext` still has both `db_session` and `resources["database"]`. | `engine/tests/test_tool_attempt_contract.py`, `engine/tests/test_workspace_context_fragment.py` |
| Context | Production contributors return bounded `ContextFragment`s with provenance. | `engine/tests/test_workspace_context_fragment.py` |
| Memory | Memory v4 context is on by default; `DBFOX_MEMORY_V4_CONTEXT=0` selects the v3 context path. | `engine/agent/tests/test_context_memory_v4.py` |
| Agent loop | Result artifact checks and finalization tool allow-list remain in `RunLoop`. | `engine/agent/tests/test_run_loop.py` |
| Resource UI | `DataSourceTree` currently owns Project, Connection, Conversation, Database/Table and Workspace File presentation. | `desktop/src/features/datasource/__tests__/DataSourceTree.test.tsx` |
| Dock | Current tab compatibility includes capability-specific fields. Visibility is contribution-driven; unknown kinds fail soft. | `desktop/src/stores/__tests__/workspaceStore.test.ts`, `desktop/src/features/appShell/__tests__/WorkspaceDock.test.tsx`, `desktop/src/features/appShell/__tests__/dockViewRegistry.test.tsx` |

## P0 boundary

P0 adds no runtime abstraction and changes no product behavior. It intentionally
does **not** perform the following Issue #42 phases: shared backend composition
root, resource single-source cleanup, connector slot, project-scoped sessions,
tool prerequisites, Dock envelope migration, or selection.

The former parent/worker registration difference was deliberately replaced in
P1 by a single product composition contract: every RemoteJob tool remains
`in_process`, so worker registry visibility does not alter its execution
backend or model-visible tool materialization. `ToolRunContext` dual database
access remains a P2 fact and is not changed here.

## Verification map

Run the normal repository gates plus the characterization suites listed above.
P1 may change a frozen assertion only together with its composition-root design,
explicit ownership decision, replacement contract, and deletion of the
superseded registration path.

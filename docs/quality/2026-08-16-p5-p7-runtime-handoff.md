# P5B / P6 / P7 Runtime Handoff（2026-08-16）

> 文档类型：交接记录
>
> 状态：当前
>
> 最后核验：2026-08-17
>
> 基线：`main@72931e08`
>
> 用途：交给下一执行者继续完成第二能力族证明，不重复已完成的调查与实现。

## 1. 已经完成（请不要再改回）

### P5B：Database + Workspace resource seam
- `engine/tools/runtime/attempt.py`
  - `ResourceScopeRef(kind, id, version)`
  - `ToolInvocationContext(session_id/run_id/turn_id/invocation_id/idempotency_key/deadline_at/scope_refs)`
  - `ToolAttemptRequest(mode, tool_name, frozen_tool_version, invocation, authorized_input, attempt_timeout_ms)`
  - `CompositeResourceResolver`（按 scope kind 注册 resolver，freeze 后拒绝注册）
- `engine/tools/runtime/resource_context.py`
  - `build_tool_scope_context(db, request, tool)`
  - Database scope：`kind=database, id=datasource_id, version=generation`
  - Workspace scope：只在 tool capability 含 `filesystem_read` 时从 `DataSource.project_id -> Project.workspace_root` 解析 `WorkspaceReadService`
- `engine/tools/runtime/context.py` 增加 `scope_refs` 和 `resources`，Tool 通过 `context.require_resource("workspace")` 取授权资源。
- `engine/agent/tool_dispatcher.py` 已接入 `build_tool_scope_context`，现有 DB Tool 路径未改。

### P5A backend Workspace substrate
- `engine/workspace/read_service.py`
  - `WorkspaceReadService(root)`
  - `list_directory(relative_path, limit=600)`
  - `read_text_file(relative_path, max_bytes=1MiB)`
  - root canonicalize、relative path 拒绝绝对路径和 `..`、symlink escape 拒绝、binary/UTF-8 guard、sha256。

### P7 第一能力族 read-only vertical slice
- `engine/tools/builtin/workspace.py`
  - `file_read`：输入 `{path}`，输出 bounded content + path/size/sha256；产出 `dbfox.workspace.file_snapshot` ArtifactDraft。
  - `file_search`：输入 `{query, path_prefix, limit}`，输出 workspace-relative 文件名列表。
- `file_read` semantics：`produces=("dbfox.workspace.file_snapshot",)`。
- Artifact payload contract `dbfox.workspace.file_snapshot` 已注册到 `engine/agent/artifact.py` 的新 Registry。
- `engine/agent/context_fragment.py`
  - Kernel 定义 `ContextLane = working_state | resource | evidence`
  - `ContextFragment(source_id, source_version, lane, content, provenance)`
  - `ContextContributor` Protocol。
- `engine/agent/workspace_context.py`
  - `WorkspaceContextContributor` 查询该 Session 最近 succeeded Observation/Artifact，生成 bounded file-snapshot fragments。
  - ContextAssembler 将其放进 `session_memory["WORKSPACE_RESOURCES"]`，**没有**新增 `ContextSnapshot.file_context` 根字段。
- 前端：
  - `desktop/src/types/agentArtifact.ts` 开放 `AgentArtifactType = string`。
  - `desktop/src/features/workspace/artifacts/WorkspaceFileSnapshotArtifactView.tsx`
  - `artifactRendererRegistry` 注册 `dbfox.workspace.file_snapshot` renderer，点击打开 `workspaceFileStore.openFile` 到现有 File Dock View。
  - 之前的 `WorkspaceDockTabKind` 已开放 string，ShellStore 只负责 layout/identity。

### P6 真实 isolated worker transport
- `engine/tools/runtime/handler.py`
  - `ToolAttemptHandler` 校验 frozen tool version → resolve scopes → 调 ToolRuntime execute/reconcile。
  - 同一 handler 语义给 in-process / isolated 共用。
- `engine/tools/runtime/attempt_runner.py`
  - `InProcessAttemptRunner`：执行前检查 cancel，执行后若 late success 则转 TOOL_CANCELLED。
  - `IsolatedProcessAttemptRunner`：真实 `subprocess.Popen`，带 line-delimited JSON protocol、cancel/deadline、process-tree kill、stdout/stderr 上限、malformed result rejection 和 late result suppression。
- `engine/tools/runtime/worker_protocol.py`：`protocol_version=1`，单行 JSON frame。
- `engine/tools/worker.py`：`python -m engine.tools.worker`，decode request → ready/request handshake → build registry/resolver → `ToolAttemptHandler` → encode result。
- `engine/tools/runtime/resource_context.py`：workspace scope 现在携带 authorized `location`，worker 不需要重建应用容器。

## 2. 交接后下一步（按顺序）

### A. 完成 P6 真实 isolated worker transport
已实现：
- `IsolatedProcessAttemptRunner` 真实启动 worker，并保留 ToolExecutor 的 retry/deadline/cancel 所有权。
- worker 协议 handshake、serializable `ToolAttemptRequest`/`ToolResult`、parent→worker cancel、process-group/tree kill、输出上限、malformed result rejection、late result suppression、worker crash → `TOOL_OUTCOME_UNKNOWN`。
- 未声称 hostile-code sandbox；新增 `isolated-worker-platform-contract` CI job 在 `ubuntu-24.04`、`windows-2025`、`macos-14` 上运行 worker transport 与 patch contract 测试。

### B. P8 `file_write_patch`
已实现：
- `engine/workspace/patch_service.py`：canonical relative path、`expected_sha256` CAS、1 MiB 有界内容、temp sibling + fsync + atomic replace、conflict/no-silent-overwrite、纯文件系统状态的 reconcile。
- `engine/tools/builtin/workspace.py` 新增 `file_write_patch`：`isolated_process`、`filesystem_write`、`recovery="reconcile"`、`dbfox.workspace.code_patch` payload contract。
- 前端新增 `WorkspaceCodePatchArtifactView` 和 renderer contribution，`dbfox.workspace.code_patch` 不再走 unknown fallback。
- `filesystem_write` 未加入 `IN_PROCESS_CAPABILITIES`。

### C. 证明完整链（仍未作为真实场景验收）
代码路径已实现并通过 focused tests，但尚未用真实 Provider/桌面场景完成下列端到端验收：
跑一个真实 scenario：
1. Project 有 `workspace_root`；
2. Agent 调 `file_read`；
3. ToolDispatcher 生成 Observation + FileSnapshot Artifact；
4. WorkspaceContextContributor 生成 bounded ContextFragment；
5. 下一个 Run 的 Context 里出现 `WORKSPACE_RESOURCES`；
6. 前端 Artifact Dock 渲染 FileSnapshot renderer；
7. 点击在 File Dock 打开，且 File Dock 内核没有 `if viewType == file` 分支。

验收禁止：
- `RunLoop if tool == file_read`
- `ContextSnapshot.file_context`
- `Artifact Core if type == code_file`
- `Dock Kernel if viewType == file`

### D. 保持未完成的诚实状态
- `DBFOX_MEMORY_V4_CONTEXT` 仍默认关闭；P2 5.6 没有真实 Provider AgentBench 后测，不得打开。
- P9/P10 仍未实现。
- `file_write_patch` 已完成 backend 实现和 contract tests；但全链验收 C 未完成前，不把它当作产品级完成。

## 3. 本地验证命令（已执行过，交接后仍以这些为准）

```bash
# backend deterministic tests
.venv/Scripts/python.exe -m pytest engine/tests -q --tb=short   -m "not e2e and not integration and not real_llm and not migration and not engineering_contract and not platform_contract"

# agent tests
.venv/Scripts/python.exe -m pytest engine/agent/tests -q --tb=short   -m "not e2e and not integration and not real_llm"

# focused new tests
.venv/Scripts/python.exe -m pytest   engine/tests/test_tool_attempt_contract.py   engine/tests/test_tool_attempt_runner.py   engine/tests/test_workspace_read_service.py   engine/tests/test_workspace_file_tool.py   engine/tests/test_workspace_patch_tool.py   engine/tests/test_workspace_context_fragment.py

# frozen sidecar smoke（Windows 本机）
./.build_venv/Scripts/python.exe build_sidecar.py
cd desktop && npm run test:sidecar
```

## 4. 当前未监视的 CI 状态

- 当前工作树基线为 `72931e08`。
- 本阶段 P6/P8 变更尚未推送；推送前先跑完整本地门禁，再决定是否触发远端 CI。

## 5. 关键文件索引

| 事项 | 文件 |
|---|---|
| serializable attempt | `engine/tools/runtime/attempt.py` |
| shared handler | `engine/tools/runtime/handler.py` |
| isolated runner / transport | `engine/tools/runtime/attempt_runner.py` |
| worker protocol | `engine/tools/runtime/worker_protocol.py` |
| worker entry | `engine/tools/worker.py` |
| dispatcher scope integration | `engine/agent/tool_dispatcher.py` |
| workspace read substrate | `engine/workspace/read_service.py` |
| workspace patch service | `engine/workspace/patch_service.py` |
| file tools | `engine/tools/builtin/workspace.py` |
| context fragment seam | `engine/agent/context_fragment.py` |
| workspace context contributor | `engine/agent/workspace_context.py` |
| frontend file artifact renderer | `desktop/src/features/workspace/artifacts/WorkspaceFileSnapshotArtifactView.tsx` |
| frontend renderer registry | `desktop/src/features/workspace/artifacts/artifactRendererRegistry.tsx` |

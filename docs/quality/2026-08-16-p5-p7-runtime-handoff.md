# P5B / P6 / P7 Runtime Handoff（2026-08-16）

> 文档类型：交接记录
>
> 状态：当前工作树 `main@8266de4c`
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

### P6 已落地的 seam / 骨架
- `engine/tools/runtime/handler.py`
  - `ToolAttemptHandler` 校验 frozen tool version → resolve scopes → 调 ToolRuntime execute/reconcile。
  - 同一 handler 语义给 in-process / isolated 共用。
- `engine/tools/runtime/attempt_runner.py`
  - `InProcessAttemptRunner`：执行前检查 cancel，执行后若 late success 则转 TOOL_CANCELLED。
  - `IsolatedProcessAttemptRunner`：**目前只是 protocol_version=1 的 skeleton**，返回 `TOOL_EXECUTION_BACKEND_UNAVAILABLE`；没有真实 worker transport。

## 2. 交接后下一步（按顺序）

### A. 完成 P6 真实 isolated worker transport（不要从 UI/前端开始）
目标文件：
- `engine/tools/runtime/attempt_runner.py`：替换 skeleton 为真实 `subprocess.Popen`。
- 新增 worker entry（建议 `engine/tools/worker.py`），入口用 `python -m engine.tools.worker`。
- `engine/tools/runtime/handler.py`：已可复用。
- `engine/tools/runtime/executor.py`：把 `backend == "isolated_process"` 从“不可用”改为经 `ToolAttemptRunner` 执行；retry/deadline/cancel 仍只在 ToolExecutor。

必须覆盖：
- request/result 只传 serializable `ToolAttemptRequest` / `ToolResult`；
- worker 启动后 decode request → protocol/schema handshake → 校验 frozen tool version → resolve scopes → handler → encode result；
- parent→worker cancel；process group/tree kill；
- stdout/stderr、frame、output size 上限；
- malformed result rejection；
- late result suppression；
- worker crash 固定为 TOOL_OUTCOME_UNKNOWN（只在 reconcile 语义下可被 ToolExecutor 收口）；
- Windows/macOS/Linux 契约测试；
- 不得声称 hostile-code sandbox。

### B. P8 `file_write_patch`（真正需要 isolated backend 的写能力）
建议：
- `engine/workspace/patch_service.py`：
  - canonical relative path；
  - `expected_sha256` CAS；
  - bounded patch（例如单文件 diff/内容上限）；
  - temp sibling + flush/fsync + atomic replace；
  - conflict / no-silent-overwrite / crash reconcile。
- `engine/tools/builtin/workspace.py` 增加 `file_write_patch`：
  - `execution.backend="isolated_process"`
  - `capabilities=("filesystem_write",)`
  - `recovery="reconcile"` 而不是 `retry_safe`
  - Artifact type 建议 `dbfox.workspace.code_patch`，先注册 payload contract。
- **不要**把 `filesystem_write` 加进 `IN_PROCESS_CAPABILITIES`；当前 `IN_PROCESS_CAPABILITIES` 只允许新增的 `filesystem_read`。
- 写能力必须在 A 的 worker transport 完成后才接。

### C. 证明完整链（验收，不是再写框架）
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
- `file_write_patch` 未实现前，P8 不能标记完成。

## 3. 本地验证命令（已执行过，交接后仍以这些为准）

```bash
# backend deterministic tests
.venv/Scripts/python.exe -m pytest engine/tests -q --tb=short   -m "not e2e and not integration and not real_llm and not migration and not engineering_contract and not platform_contract"

# agent tests
.venv/Scripts/python.exe -m pytest engine/agent/tests -q --tb=short   -m "not e2e and not integration and not real_llm"

# focused new tests
.venv/Scripts/python.exe -m pytest   engine/tests/test_tool_attempt_contract.py   engine/tests/test_tool_attempt_runner.py   engine/tests/test_workspace_read_service.py   engine/tests/test_workspace_file_tool.py   engine/tests/test_workspace_context_fragment.py

# frozen sidecar smoke（Windows 本机）
./.build_venv/Scripts/python.exe build_sidecar.py
cd desktop && npm run test:sidecar
```

## 4. 当前未监视的 CI 状态

- 最后一次 push 是 `8266de4c`。
- GitHub Actions run 31959315130 当时仍在运行，后续执行者不要假设它已转绿；先看 run 状态，再决定修复点。
- 最近一次完全转绿的 push 是 `543661fa`。

## 5. 关键文件索引

| 事项 | 文件 |
|---|---|
| serializable attempt | `engine/tools/runtime/attempt.py` |
| shared handler | `engine/tools/runtime/handler.py` |
| runner seam | `engine/tools/runtime/attempt_runner.py` |
| dispatcher scope integration | `engine/agent/tool_dispatcher.py` |
| workspace read substrate | `engine/workspace/read_service.py` |
| file tools | `engine/tools/builtin/workspace.py` |
| context fragment seam | `engine/agent/context_fragment.py` |
| workspace context contributor | `engine/agent/workspace_context.py` |
| frontend file artifact renderer | `desktop/src/features/workspace/artifacts/WorkspaceFileSnapshotArtifactView.tsx` |
| frontend renderer registry | `desktop/src/features/workspace/artifacts/artifactRendererRegistry.tsx` |

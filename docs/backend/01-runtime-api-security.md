# 卷一：Runtime、API、安全与错误边界

> 文档类型：实现指南
>
> 状态：当前
>
> 最后核验：2026-08-21
>
> 适用范围：Sidecar 启动、FastAPI、鉴权、公开错误与关闭流程
>
> 权威合同：[系统总览](../architecture/system-overview.md)、[Runtime 基础能力 ADR](../architecture/runtime-foundation-decisions.md)、[错误边界合同](../architecture/error-boundary-contract.md)
>
> 核心入口：[`desktop/main/engine.ts`](../../desktop/main/engine.ts)、[`desktop/main/nodeEngineHost.ts`](../../desktop/main/nodeEngineHost.ts)、[`engine/main.py`](../../engine/main.py)、[`engine/db.py`](../../engine/db.py)、[`engine/engine_runtime/credentials.py`](../../engine/engine_runtime/credentials.py)

## 1. 本卷回答什么

本卷解释从桌面应用启动到 FastAPI 可接收业务请求的完整过程，并区分：

- Electron Main Host 拥有什么；
- Python Sidecar 拥有什么；
- Token 从哪里来、谁可以读取；
- 为什么 `/health` 也必须鉴权；
- API 输入、内部异常和公开错误如何分层；
- 关闭时哪些资源必须按顺序释放。

理解这条链后，才能正确排查“应用打开了但 API 不通”“旧 Token 还能用”“Sidecar Ready 后崩溃”“UI 只显示模型服务拒绝”等问题。

## 2. 进程与信任边界

正式桌面运行时包含三个逻辑容器：

```text
Windows 用户
  └─ Electron/TypeScript Host
       ├─ 创建本次 runtime generation
       ├─ 生成并持有本次 loopback Token
       ├─ 启动/观察/终止 Python Sidecar
       └─ 通过 sandboxed preload 把当前 endpoint 投影给 React Renderer
            └─ 通过 127.0.0.1 HTTP/SSE 调用 FastAPI
```

边界规则：

1. Renderer 不自行猜端口，不从固定文件读取生产 Token；
2. Sidecar 不管理桌面窗口，也不成为自身生命周期的最终权威；
3. 127.0.0.1 不是可信身份。任何本机进程都可能访问 loopback，因此仍需 Token；
4. Token 只证明调用者持有本次 Runtime 凭据，不替代数据源权限、工具策略或审批；
5. generation 用于识别“这是本次启动的配置”，避免旧端口和旧 Token 继续污染新运行时。

## 3. Python 启动入口

### 3.1 应用对象

[`engine/main.py`](../../engine/main.py) 创建 FastAPI 应用，装配：

- lifespan；
- 请求体限制中间件；
- 全局 Token 鉴权；
- Problem Details 错误处理；
- 数据源、查询、Agent、对话、凭据、备份、诊断等 Router。

不要在各 Router 复制启动、鉴权或错误转换。它们是全局边界能力。

### 3.2 `lifespan` 启动顺序

`engine.main.lifespan` 的启动阶段按以下因果顺序执行：

1. 初始化 metadata 数据库；
2. 运行并核验 Alembic 迁移；
3. 对未完成的 Credential Lease Saga 做 reconciliation；
4. 在受控写事务中执行安全审计保留策略；
5. 创建 `RunLoop`；
6. 创建并启动 `SessionCoordinator`；
7. 将服务标记为可接收工作。

这不是任意顺序：

- Agent Coordinator 依赖完整 schema；
- 凭据 lease reconciliation 必须早于新的凭据操作；
- 审计清理必须走与其他 Agent 写入一致的 SQLite 写事务规则；
- Ready 不应早于必需控制平面初始化。

### 3.3 关闭顺序

lifespan 退出阶段负责：

1. 停止 Coordinator 接收和调度新工作；
2. 关闭数据源资源生命周期管理器中的连接/隧道；
3. 关闭复用的 LLM HTTP 客户端；
4. 让 FastAPI/ASGI 完成剩余连接清理。

关闭顺序的目标是先停止产生新工作，再释放工作依赖。若反过来先关连接池，活跃 Agent 可能在关闭窗口中产生误导性工具错误。

## 4. Runtime Token 生命周期

### 4.1 `RuntimeCredentialPolicy`

实现位于 [`engine/engine_runtime/credentials.py`](../../engine/engine_runtime/credentials.py)。`resolve_token` 区分正式 frozen Sidecar 和源码开发模式。

正式 frozen 模式：

- Token 必须由 Host 通过受控环境传入；
- 缺失即启动失败；
- Python 不自行创建“开发 Token”作为生产 fallback；
- 这样才能保证 Host 是 runtime credential 的唯一权威。

源码开发模式：

- 显式环境 Token 仍优先；
- 没有环境 Token 时可读取开发 token file；
- 文件为空或不存在时生成高熵 Token 并用私有权限保存；
- 这是开发便利能力，不代表生产协议。

### 4.2 为什么不能硬编码或复用旧 Token

硬编码 Token 会把“持有本次 runtime capability”退化成任何知道源码的人都能调用。跨 generation 复用 Token 则会让旧 Renderer、旧日志或旧本机进程继续访问新 Sidecar。

正确判断应同时依赖：

- 当前 Electron `EngineSupervisor` 报告的 Ready 状态；
- 当前 generation；
- 当前 endpoint；
- 当前 Token。

这些字段是一个整体配置快照，不能只刷新端口而保留旧 Token。

## 5. 全局鉴权链

### 5.1 `verify_local_access_token`

实现位于 [`engine/main.py`](../../engine/main.py)。每个业务 HTTP/SSE 请求进入 Router 前经过统一校验：

1. `OPTIONS` 预检按协议放行；
2. frozen 环境执行 Origin/Referer 限制；
3. 源码开发模式可暴露开发文档；正式环境的 docs 路径返回 404；
4. 读取 `X-Local-Token`；
5. 使用常量时间比较检查当前 Token；
6. 失败时返回固定公开错误，不泄漏期望 Token 或内部配置。

`/health` 也经过鉴权。这一点很重要：Health 不只是“进程活着”，它会成为 Host/Renderer 判断当前 runtime 是否可用的协议端点。匿名 health 会给任意本机进程提供探测面，也会使测试绕开真实鉴权链。

### 5.2 鉴权不负责什么

全局 Token 鉴权不负责：

- 数据源账号权限；
- SQL 是否只读；
- Agent 工具是否可见；
- 某个工具是否需审批；
- 用户是否确认危险操作；
- 敏感字段是否脱敏。

这些属于后续不同边界。把它们混进 Token 中间件会形成难以测试的全能授权层。

## 6. 请求输入边界

### 6.1 请求体限制

[`engine/app/request_limits.py`](../../engine/app/request_limits.py) 中的 `AgentInputRequestBodyLimitMiddleware` 在大输入进入 JSON 解析、Pydantic 校验和持久化之前做上限控制。

目的包括：

- 防止意外粘贴大文件阻塞 Sidecar；
- 避免将超大用户输入直接写入对话和 Provider 上下文；
- 让失败发生在清晰的 HTTP 边界；
- 保证错误仍使用统一公开合同。

请求体上限不是 Context Budget。前者保护 HTTP/内存，后者控制 Agent Prompt。

### 6.2 Pydantic 请求合同

API 请求模型主要位于：

- [`engine/schemas/`](../../engine/schemas/)：通用业务 API；
- [`engine/api/conversation_contracts.py`](../../engine/api/conversation_contracts.py)：对话输入与投影；
- Agent/工具内部各自的严格 Pydantic Schema。

输入校验失败应由全局错误边界转换，Router 不应手写字符串拼接的错误 JSON。

## 7. API 模块划分

| 模块 | 主要职责 | 不应承担 |
| --- | --- | --- |
| [`api/datasources/`](../../engine/api/datasources/) | 数据源 CRUD、健康、metadata、schema | 自行保存明文凭据或新建连接池实现 |
| [`api/query.py`](../../engine/api/query.py) | 查询/结果相关 HTTP 入口 | 绕过 SQL Safety Service |
| [`api/conversations.py`](../../engine/api/conversations.py) | 组合对话 Router | 实现 RunLoop |
| [`api/conversation_commands.py`](../../engine/api/conversation_commands.py) | 提交输入、取消、审批等命令 | 直接在内存队列创建唯一事实 |
| [`api/conversation_queries.py`](../../engine/api/conversation_queries.py) | Session/Run/消息投影查询 | 修改运行状态 |
| [`api/conversation_stream.py`](../../engine/api/conversation_stream.py) | cursor replay + SSE live | 把断线当取消 |
| [`api/agent_results.py`](../../engine/api/agent_results.py) | Agent Result Artifact 读取 | 将完整结果注入模型 |
| [`api/credentials.py`](../../engine/api/credentials.py) | 凭据命令边界 | 返回 secret 正文 |
| [`api/diagnostics.py`](../../engine/api/diagnostics.py) | 诊断包/日志的受控导出 | 任意目录打包 |
| [`api/backup.py`](../../engine/api/backup.py) | metadata 备份恢复协议 | 无来源绑定的文件覆盖 |

API 层的理想职责是：认证后的协议解析、调用领域服务/Repository、提交事务、返回稳定投影。它不应复制领域规则。

## 8. 错误可信度模型

### 8.1 三类错误内容

| 内容 | 是否可直接展示 | 示例 |
| --- | --- | --- |
| 固定 catalog 公开消息 | 是 | “模型服务拒绝了当前请求” |
| 经明确类型标记的用户输入错误 | 是，但仍需控制长度/内容 | SQL 参数格式错误 |
| 任意异常或 `DBFoxError.message` | 否 | driver、Provider、文件系统原始异常 |

核心实现：

- [`engine/app/safe_errors.py`](../../engine/app/safe_errors.py)：错误代码到固定公开消息；
- [`engine/problem_details.py`](../../engine/problem_details.py)：RFC 9457 响应；
- [`engine/errors.py`](../../engine/errors.py)：内部异常类型；
- [`engine/policy/error_sanitizer.py`](../../engine/policy/error_sanitizer.py)：策略层错误净化；
- [`engine/policy/redactor.py`](../../engine/policy/redactor.py)：敏感内容脱敏。

### 8.2 为什么 `DBFoxError.message` 默认不可信

基类异常可能包装来自：

- 数据库 driver；
- Provider SDK；
- HTTP client；
- OS/keyring；
- SQL parser；
- 用户数据内容。

这些 message 可能包含 DSN、SQL 值、路径、Authorization header 或上游响应片段。因此仅仅“异常属于 DBFoxError”不能证明其 message 可展示。

公开边界的正确做法：

1. 识别固定错误代码；
2. 从 catalog 取稳定公开说明；
3. 未注册代码降级为通用错误；
4. 详细异常只进入受控日志，并先脱敏；
5. 只有明确的 `ToolInputError` 等受信类型可携带经过约束的用户可见说明。

### 8.3 RFC 9457 Problem Details

HTTP 错误使用统一结构，而不是每个 Router 返回不同形状。调用者通常依赖：

- `type`：稳定问题类型；
- `title`：简短公开标题；
- `status`：HTTP 状态；
- `detail`：安全公开说明；
- `instance` 或关联标识：用于定位，不暴露秘密；
- DBFox 扩展字段：稳定错误代码等。

前端应按稳定 code/type 决定交互，不按英文/中文 message 字符串分支。

## 9. 从内部错误到 UI 的链路

```text
Driver / Provider / Tool / Repository exception
  → 边界分类
  → 内部 code + 可观测诊断
  → safe error catalog / explicit public input error
  → HTTP Problem Details 或 Agent ToolResult
  → Agent Event / API response
  → React Transport 解析
  → UI 以稳定 code 显示用户操作建议
```

HTTP 与 Agent Tool 边界都必须遵循同一可信度原则，但载体不同：HTTP 使用 Problem Details，工具执行使用结构化 `ToolResult` 和事件。

## 10. 常见失败路径

### 10.1 启动时缺少正式 Token

- 触发：frozen Sidecar 未收到 Host 注入的 Token；
- 正确行为：启动失败，不生成 fallback；
- 排查：Electron launcher 的启动参数/环境、runtime manifest、Sidecar 日志；
- 不正确修复：在 Python 中生成固定开发 Token。

### 10.2 Renderer 持有旧 generation

- 触发：Sidecar 崩溃并由 Host 重启；
- 现象：旧端口连接失败或旧 Token 401；
- 正确恢复：Host 发布新 runtime config，Transport 丢弃旧 endpoint，幂等读取按策略重连；
- 非幂等请求：结果不明确时不得自动重放。

### 10.3 错误被过度净化

- 现象：UI 只有“请求失败”，无法定位；
- 正确做法：公开响应仍稳定、无秘密；受控日志保留 error code、correlation、组件、阶段和脱敏原因；
- 不正确修复：把原始 exception message 直接回传 UI。

### 10.4 开发文档在正式包可访问

- 风险：暴露 API 面和 Schema；
- 正确行为：frozen 模式 docs 路径 404；
- 验证：正式 Sidecar 合同测试，不只检查源码配置。

## 11. 关键测试

| 目标 | 测试 |
| --- | --- |
| Runtime Token 来源与 frozen 失败 | [`test_runtime_credentials.py`](../../engine/tests/test_runtime_credentials.py) |
| 启动生命周期 | [`test_startup.py`](../../engine/tests/test_startup.py)、[`test_db_init_lifecycle.py`](../../engine/tests/test_db_init_lifecycle.py) |
| API 鉴权合同 | [`test_api_security_contracts.py`](../../engine/tests/test_api_security_contracts.py) |
| 全局错误不泄漏 | [`test_global_error_boundary.py`](../../engine/tests/test_global_error_boundary.py) |
| Problem Details | [`test_problem_details.py`](../../engine/tests/test_problem_details.py) |
| 公开错误 catalog | [`test_public_errors.py`](../../engine/tests/test_public_errors.py) |
| 请求验证 | [`test_request_validation_contract.py`](../../engine/tests/test_request_validation_contract.py) |
| Agent 输入大小 | [`test_agent_input_request_limits.py`](../../engine/tests/test_agent_input_request_limits.py) |
| LLM endpoint 限制 | [`test_llm_endpoint_policy.py`](../../engine/tests/test_llm_endpoint_policy.py) |
| 诊断脱敏 | [`test_diagnostics.py`](../../engine/tests/test_diagnostics.py)、[`test_diagnostics_logs.py`](../../engine/tests/test_diagnostics_logs.py) |

## 12. 修改检查表

修改启动、API 或安全边界前后确认：

- [ ] 没有让 Python 与 Electron Main 同时成为 Sidecar 生命周期权威；
- [ ] 没有新增固定端口、固定 Token 或 production fallback；
- [ ] `/health`、SSE 和普通 HTTP 使用一致鉴权；
- [ ] frozen/source 行为差异有显式测试；
- [ ] Router 没有复制全局异常转换；
- [ ] 内部异常 message 未默认暴露；
- [ ] Problem Details code/type 保持稳定；
- [ ] 非幂等请求不会因 runtime 刷新自动重放；
- [ ] 关闭顺序先停工作再释放依赖；
- [ ] 日志和诊断包执行脱敏、白名单和大小限制。

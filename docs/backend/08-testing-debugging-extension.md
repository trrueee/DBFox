# 卷八：测试、调试、扩展与变更影响

> 文档类型：维护指南
>
> 状态：当前
>
> 最后核验：2026-08-21
>
> 适用范围：后端测试、调试、功能扩展和变更影响分析
>
> 配套文档：[工程门禁](../quality/engineering-gates.md)、[实现地图](../architecture/implementation-map.md)、[贡献指南](../../CONTRIBUTING.md)

## 1. 测试策略不是“pytest 全绿”

DBFox 的风险来自跨边界链路：Runtime、SQLite、Provider、工具、外部 datasource、SSE 和桌面 UI。测试需要分层证明：

| 层 | 证明什么 | 不能证明什么 |
| --- | --- | --- |
| 纯单元 | parser、policy、状态转换、序列化 | 真实事务/SDK/driver 行为 |
| Repository + SQLite | schema、事务、租约、幂等、恢复 | 真实 Provider/外部数据库 |
| API 合同 | 鉴权、请求/响应、Problem Details、SSE | 正式 frozen/安装行为 |
| Harness 场景 | 多 Turn、工具、取消、崩溃恢复 | 外部 Provider 事件兼容 |
| opt-in Provider | SDK/Responses/tool loop/stream | 所有模型和网络环境 |
| datasource 集成 | driver、SSL、readonly、类型 | 其他数据库版本 |
| frozen/安装测试 | PyInstaller/Electron/Token/sidecar | 未运行平台 |

测试报告必须说清环境和覆盖边界，不能从 Windows 推断 macOS/Linux，也不能从 fake Provider 推断真实 Provider。

## 2. 最小后端验证命令

常规完整回归：

```powershell
python -m pytest -q
```

静态与格式检查按项目配置执行，例如：

```powershell
python -m mypy engine
git diff --check
```

具体门禁以 [`docs/quality/engineering-gates.md`](../quality/engineering-gates.md) 和 CI 为准。不要为了本地通过而在 CI 加 `continue-on-error`。

## 3. 按变更范围选择测试

### 3.1 Runtime/鉴权/错误

```powershell
python -m pytest -q engine/tests/test_runtime_credentials.py engine/tests/test_api_security_contracts.py engine/tests/test_global_error_boundary.py engine/tests/test_problem_details.py
```

### 3.2 SQLite/迁移/事务

```powershell
python -m pytest -q engine/tests/test_db_init.py engine/tests/test_migrations.py engine/agent/tests/test_session_repository.py engine/agent/tests/test_terminal_transaction.py
```

### 3.3 数据源/SQL/结果

```powershell
python -m pytest -q engine/tests/test_connectivity_boundary.py engine/tests/test_sql_safety_service.py engine/tests/test_bound_parameters.py engine/tests/test_result_view_service.py
```

### 3.4 Agent/Provider/工具/记忆

```powershell
python -m pytest -q engine/agent/tests/test_run_loop.py engine/agent/tests/test_openai_model_adapter.py engine/agent/tests/test_policy_gate.py engine/agent/tests/test_context_assembler.py
```

### 3.5 确定性 Harness

```powershell
python -m pytest -q engine/agent/tests/harness/test_sqlite_scenarios.py
```

真实 Provider 合同是 opt-in，只有显式提供隔离测试凭据和配置时运行；不得把开发用户 credential 写入仓库、日志或默认 CI。

## 4. 确定性 SQLite Harness 应覆盖什么

[`engine/agent/tests/harness/test_sqlite_scenarios.py`](../../engine/agent/tests/harness/test_sqlite_scenarios.py) 应作为完整运行状态机的稳定场景集，优先覆盖：

- 无 phase 的正常最终文本；
- 显式 final_answer；
- 文本 + tool call 不提前完成；
- 工具成功后第二 Turn 完成；
- 工具失败后 repair；
- 重复无进展被停止；
- Provider incomplete/failed/cancelled；
- stream 部分文本不提交；
- approval wait/resume；
- clarification wait/resume；
- cancel during provider/tool/backoff；
- Session lease 丢失；
- Sidecar/worker 恢复 pending invocation；
- 非幂等未知结果不重放；
- Event commit/replay/snapshot；
- Memory 只写已完成事实；
- Recall search/read 完整闭环。

场景应固定时钟、id、Provider 脚本和数据库，避免 sleep 驱动的偶发测试。

## 5. Opt-in 真实 Provider 测试

[`engine/agent/tests/test_real_responses_contract.py`](../../engine/agent/tests/test_real_responses_contract.py) 的职责是验证外部边界：

- Responses 请求可被真实 Provider 接受；
- message `phase` 可能缺失；
- terminal/completed 事件正确；
- function call 与 function output 使用相同 call id；
- stream 在正常/异常/取消路径关闭；
- usage/错误分类可解析；
- 无工具纯文本能完成；
- 至少一个真实工具闭环。

测试必须：

- 默认 skip；
- 由环境显式启用；
- 使用专门低权限凭据；
- 有 token/cost/timeout 上限；
- 不访问真实用户 datasource；
- 记录 Provider/model/version 和 commit；
- 错误日志脱敏。

## 6. 故障定位的证据顺序

面对“Agent 失败”，按以下顺序，不要直接改 Prompt：

1. 当前 commit、配置模式和 runtime generation；
2. API admission 是否成功，Input/Run ids；
3. Session lease owner/token；
4. Run status/current turn/budget；
5. Turn context hash/tool materialization hash；
6. Provider terminal status/response items；
7. ToolInvocation input/policy/approval/status/result ref；
8. Observation 是否进入下一 Turn；
9. CompletionDecision；
10. assistant message/Run/Event 是否同事务完成；
11. SSE cursor/snapshot 是否正确投影；
12. UI 是否按稳定 code 呈现。

这条顺序能区分 Provider、Harness、工具、持久化和前端问题。

## 7. 常见症状排查表

| 症状 | 首查 | 常见根因 | 不要先做 |
| --- | --- | --- | --- |
| 模型拒绝请求 | Provider error classification、credential/config | key 缺失、模型参数、endpoint policy | 给用户看原始 SDK 响应 |
| 有文本无答案 | Turn termination、CompletionPolicy、assistant message | phase 被误当必要条件、stream incomplete | 提高 max turns |
| 工具不断重复 | call/output、Observation、ProgressGuard | call_id 丢失、output 未回送、失败不可行动 | 在 Prompt 写“不要重复” |
| schema_inspect 失败 | Invocation input、Catalog state | target 合同、Catalog stale、generation | 新增 Provider mapper |
| result_inspect 失败 | artifact id/ownership/source | 未持久化、过期、scope | 把完整 rows 放 ToolResult |
| 重启后任务丢失 | DB Run/lease/recovery | 内存队列成为事实、admit 未提交 | 再加一个内存队列 |
| UI 永久重连 | runtime generation、SSE code/cursor | 旧 Token、不可重试错误分类错误 | 无限 retry |
| 错误泄漏 | safe_errors、ToolRuntime | 信任 exception message | 仅在 UI 替换文本 |

## 8. 日志和诊断

可记录：

- correlation/session/run/turn/invocation id；
- 稳定 error code；
- 阶段和组件；
- duration、attempt、budget；
- provider/model 名称；
- datasource id/generation；
- SQL/参数的安全 fingerprint；
- artifact id；
- stack trace（仅受控本地日志且先脱敏）。

禁止记录：

- Runtime Token；
- Authorization/API key；
- datasource password/完整 DSN；
- SQL bound value（除非明确安全且必要）；
- 完整用户数据库行；
- Provider 原始请求/响应全文；
- keyring 内容；
- 任意环境变量转储。

诊断包采用文件白名单、大小/截断、脱敏和失败清理，不递归打包任意目录。

## 9. 修改功能的自顶向下方法

### 9.1 先定位事实源

问：变化属于 Runtime、metadata、datasource、Agent、Artifact 还是 UI 投影？只能有一个 canonical owner。

### 9.2 再定位真实边界

只有在以下位置通常需要 Adapter：

- Provider SDK；
- database driver/dialect；
- OS credential store；
- Electron Main/preload/Renderer IPC；
- HTTP public contract。

内部模块字段不一致应优先统一模型，而不是继续加 mapper。

### 9.3 写失败语义

在写成功路径前定义：

- 输入无效；
- 权限拒绝；
- 取消；
- timeout；
- dependency unavailable；
- 部分成功；
- crash/restart；
- duplicate/replay；
- stale generation/lease。

### 9.4 建立合同测试

优先测试可观察边界：API、Repository 事务、Provider fixture、Tool function loop、SSE cursor，而非只测私有辅助函数。

### 9.5 最小实现

复用现有 Service/Repository/Registry，不建立第二套 SQL、工具、事件或错误链。删除错误旧路径，而不是无限保留双轨。

## 10. 新增 API 的步骤

1. 确定 command 还是 query；
2. 复用当前 Router 分区；
3. 定义 Pydantic 请求/响应；
4. 使用全局鉴权和 Problem Details；
5. 调用已有 Service/Repository；
6. 明确 transaction owner；
7. 如有事件，与状态同事务；
8. 增加 OpenAPI/API 合同测试；
9. 更新实现地图/本手册索引。

## 11. 新增 metadata 表的步骤

1. 证明需要耐久事实，不是可重建临时状态；
2. 在 `models.py` 定义清晰约束；
3. 创建 Alembic 迁移；
4. 保持单 head；
5. 增加空库与升级测试；
6. Repository 接管读写；
7. 定义删除/保留/备份语义；
8. 不存 secret 或无界 payload；
9. 明确是否需要 Event/索引。

## 12. 新增工具的步骤

1. 确认现有 SQL/Catalog/Result 工具不能组合完成；
2. 定义 strict Schema、输出、幂等、recovery；
3. 注册唯一 Registry；
4. 加入 AgentDefinition tool group；
5. PolicyGate/approval；
6. ToolRuntime 安全错误；
7. 有界 Observation/Artifact；
8. Provider fixture 完整 call/output；
9. crash/retry/cancel 测试；
10. opt-in 真实 Provider（若协议边界变化）。

## 13. 新增 Provider 的步骤

1. 调研官方 SDK/协议和维护状态；
2. 只在 Provider Adapter 实现外部转换；
3. 映射 provider-neutral response items/termination/errors；
4. phase 等可选字段忠实保留；
5. function call/output 保持原生 id；
6. stream 所有路径关闭；
7. cancel/backoff 可中断；
8. 不按 Provider 名称修改 CompletionPolicy/ToolRuntime/UI；
9. fake fixture + opt-in 真实合同；
10. 记录不支持能力，不伪造。

## 14. 新增 datasource/dialect 的步骤

参见[卷三](./03-datasource-connectivity-catalog.md#13-扩展新-datasource-类型)，必须完整覆盖 Profile/Vault/Factory/Lifecycle/Catalog/Safety/Execution/Result，而非只加连接字符串。

## 15. 代码评审重点

- 是否在源头修复，而非加兼容层；
- 是否出现相同结构不同名称的 DTO；
- 是否出现第二份队列/状态/错误 catalog；
- 是否把安全规则写进 Prompt/UI；
- 是否持有数据库事务做网络调用；
- 是否将 secret/大结果进入日志、Event、Memory；
- 是否在 crash/replay 下重复非幂等操作；
- 是否把 fake 测试写成真实外部通过；
- 是否有 migration/rollback/恢复路径；
- 是否更新权威合同和索引。

## 16. 发布与环境结论

测试结论必须绑定：

- Git commit；
- 工作树状态；
- OS/架构；
- source/frozen；
- debug/release；
- 本地/CI Runner；
- 产物 hash；
- 执行命令与原始日志。

Windows 通过不能声称 macOS/Linux 通过；静态合同审查不能声称安装、签名、公证、动态依赖或 GUI 已验证。

## 17. 文档完成定义

一次后端变更的文档不是只写“新增了 X”。至少说明：

- 用户行为；
- canonical owner；
- 调用链；
- 数据模型/状态机；
- 事务和并发；
- 安全与错误；
- 取消/超时/恢复；
- 测试和证据；
- 已知限制；
- 源码索引。

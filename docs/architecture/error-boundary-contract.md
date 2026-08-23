# DBFox 错误边界合同

> 文档类型：规范参考
>
> 状态：当前
>
> 最后核验：2026-08-23
>
> 适用范围：HTTP、SSE、Agent、工具、持久化、日志和前端错误展示
>
> 代码事实源：`engine/app/safe_errors.py`

## 1. 目标

不可信的异常文本不得进入 HTTP/SSE 响应、浏览器状态、模型响应项、工具观察、持久化记录或日志。模型服务、数据库驱动、隧道、凭据库、用户输入和异常链中的文本都属于不可信内容。

## 2. 权威实现

`engine/app/safe_errors.py` 是公开错误的唯一目录。边界代码只接受 `FixedErrorCode`，并通过 `fixed_error_detail()` 或 `fixed_error_message()` 生成公开内容。未知错误统一降为 `INTERNAL_ERROR`；调用方传入的任意文本不能成为公开错误码或消息。

`DBFoxError.message` 本身仍是不可信内部诊断，不因异常类型属于 DBFox 就自动公开。
唯一例外是 `ToolInputError`：它只能携带 DBFox 自己编写的、有界的输入纠正消息，
不得包装驱动、Provider、Vault 或远端响应文本。Tool Runtime 对其他
`DBFoxError` 必须只按固定 code 查询目录；未注册 code 按 `INTERNAL_ERROR` 处理。

`log_unexpected_exception()` 只记录有限集合中的 `SafeLogOperation`、异常类型和不透明诊断指纹。它不记录 `str(exc)`、异常参数、异常原因、堆栈、凭据、SQL 结果或模型服务响应正文。

Runtime DLC 只能通过 Extension API 的 `log_extension_diagnostic()` / `log_extension_exception()`
写诊断。operation 必须是至少三段的 namespaced ID（例如 `dbfox.data.sql_guardrail_parse`）；无效
operation 统一降为 `extension.unexpected.operation`。这两个入口与 Core 日志使用同一个进程内
HMAC fingerprint，只允许 code、subject/exception type 与 fingerprint 进入日志。

## 3. 必须遵守的规则

- API 可以传递类型明确、文案固定的领域错误。兜底异常在创建响应前必须映射为 `FixedErrorCode`。
- 运行时事件、运行项、工具观察、结果制品元数据、数据源健康状态和持久化失败记录，只能包含目录中的错误码和有长度上限的公开摘要。
- 模型服务和数据库错误在进入持久化 Agent 记录前完成转换。恢复流程读取已经脱敏的记录，不从异常对象重新拼接消息。
- 前端只展示公开错误码和消息，传输细节与堆栈诊断不得进入 Zustand 状态。
- 不要在 `safe_errors.py` 外增加错误门面、别名表或兼容包装；调用方直接使用权威辅助函数。

## 4. 验证

每个新的信任边界都要增加包含哨兵秘密的回归测试，证明该秘密不会出现在日志、HTTP/SSE 响应、运行项、工具观察和数据库记录中。架构测试还要拒绝边界模块直接格式化异常或记录堆栈。

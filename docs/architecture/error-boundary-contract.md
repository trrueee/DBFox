# Error Boundary Contract

> 状态：当前事实
> 最后核验：2026-08-06
> 代码事实源：`engine/app/safe_errors.py`

## Goal

No untrusted exception text may cross into an HTTP/SSE response, browser
projection, Responses Item, Tool Observation, persistence record, or log. This
includes provider, driver, tunnel, vault, user-input, and chained exception
text.

## Authoritative implementation

`engine/app/safe_errors.py` is the single public-error catalog. Boundary code
accepts `FixedErrorCode` members and renders them through
`fixed_error_detail()` or `fixed_error_message()`. Unknown values fall back to
`INTERNAL_ERROR`; arbitrary caller text never becomes a public code or message.

`DBFoxError.message` 本身仍是不可信内部诊断，不因异常类型属于 DBFox 就自动公开。
唯一例外是 `ToolInputError`：它只能携带 DBFox 自己编写的、有界的输入纠正消息，
不得包装驱动、Provider、Vault 或远端响应文本。Tool Runtime 对其他
`DBFoxError` 必须只按固定 code 查询目录；未注册 code 按 `INTERNAL_ERROR` 处理。

`log_unexpected_exception()` records only a finite `SafeLogOperation`, the
exception type, and an opaque diagnostic fingerprint. It never logs
`str(exc)`, exception arguments, causes, tracebacks, credentials, SQL results,
or provider response bodies.

## Rules

- API handlers may propagate deliberately typed, static domain errors. Catch-all
  paths must map to a `FixedErrorCode` before creating a response.
- Runtime events, Run Items, Tool Observations, Artifact metadata, datasource
  health, and persisted failure records contain cataloged codes and bounded
  public summaries only.
- Provider and database failures are converted before they enter the durable
  Agent transcript. Recovery reads the already-sanitized persisted record; it
  does not reconstruct a message from an exception.
- Frontend projections render public codes/messages and keep transport or stack
  diagnostics out of Zustand state.
- Do not add an error facade, alias map, or compatibility wrapper around
  `safe_errors.py`; callers import the authoritative helpers directly.

## Verification

Every new trust boundary needs a sentinel regression proving the sentinel is
absent from logs, HTTP/SSE responses, Run Items, Tool Observations, and database
records. Architecture tests must also reject raw exception formatting and
traceback logging in boundary modules.

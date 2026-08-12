# 代码质量评审逐项关闭记录

> 文档类型：历史评审关闭记录
>
> 状态：历史
>
> 最后核验：2026-08-13
>
> 适用范围：`4cb9da13` 之后的代码质量评审整改；当前实现仍应以架构文档、源码和测试为准

本文关闭 2026-08-13 代码质量与架构评审中重复出现的 Top 10、架构问题、代码质量问题和技术债务 Top 20。原报告的多个章节描述了同一问题，因此本记录按 20 个唯一问题归并。

处理原则：先复现或证明调用路径，再修改唯一正式边界；没有正确性证据的文件体量、分层偏好和长期演进建议不作为缺陷修复。整改没有新增兼容层、第二套 SQL 链路、Provider 特例或万能基础设施抽象。

## 1. 评审基线与验证

- 仓库：DBFox
- 分支：`codex/llm-call-interface`
- 整改基线：`4cb9da132339a9675621ea99b79b5d4f5084bf80`
- Python：SQLAlchemy 2.0.41；SQLite 3.45.3
- 后端全量测试：`1042 passed, 4 skipped`
- 前端全量测试：309 项通过
- Rust 测试：23 项通过
- 静态检查：Python mypy、TypeScript、ESLint、Cargo Clippy、Cargo fmt、`git diff --check` 通过
- 生产构建：前端生产构建、Production Token 扫描和 bundle budget 通过

4 个跳过项仍是需要外部条件的 opt-in 场景。本记录不把单元故障注入写成真实远程 MySQL、macOS 或 Linux 运行证据。

## 2. 唯一问题关闭矩阵

| ID | 原问题 | 最终状态 | 处理结果与证据 |
| --- | --- | --- | --- |
| QR-01 | 流式导出或图表因 SQL 别名丢失敏感列血缘 | 已修复 | `StreamingQueryExecutor` 使用现有 SQLGlot 投影血缘生成 mask，并贯穿全部流式后端；血缘缺失或列数不一致时全列脱敏。真实 SQLite 别名和 fail-closed 测试覆盖。 |
| QR-02 | SQLite 写栅栏早退及 Event 写入口无栅栏 | 部分成立并已修复 | SQLAlchemy 逻辑事务与 SQLite 物理事务实验确认 DBAPI `in_transaction` 判断正确，因此不替换。直接并发调用 `EventRepository.append` 可复现 sequence 唯一约束冲突；公共写入口现复用既有 `begin_agent_write`。8 worker 场景连续运行 5 次通过。 |
| QR-03 | 审计记录只按 key 脱敏，漏掉 DSN 和复合密钥 | 已修复 | 补齐 key 规范化，并复用 `redact_sensitive_text` 对任意字符串值扫描；覆盖 authorization、DSN、database URL、connection string、client secret 等。 |
| QR-04 | 三套脱敏应合并成一个万能 Redactor | 架构建议被否决，具体缺口已修复 | 结构化结果行、SQL/PII 文本、HTTP 公开错误和诊断日志是不同信任边界，不能强行合并。本轮在实际边界补齐覆盖：`DataRedactor` 增加无引号凭据赋值和 URL 密码；审计复用诊断文本脱敏；流式结果复用投影血缘。 |
| QR-05 | 未知数据库异常被安全映射后完全不可诊断 | 已修复 | 在返回固定公开错误前使用既有安全日志记录异常类型和 HMAC 指纹；不记录原始 SQL 或异常消息。 |
| QR-06 | Run 状态存在后端枚举与前端手写词汇表 | 部分成立并已修复 | 后端 `RunProjection` 使用领域 `RunStatus`；前端 `AgentRunStatus` 直接派生自生成的 OpenAPI `RunProjection`。生产代码未发现裸字符串写 Run 状态。建立巨型中央状态机没有必要，未实施。 |
| QR-07 | 停滞或轮次上限绕过正常完成与引用校验 | 已修复 | `evaluate_bounded_partial` 复用正常 CompletionPolicy。只有完整回答或耐久成功的查询 Result Artifact 能成为有界部分结果；中断文本和普通 Artifact 不能提交。 |
| QR-08 | 同一轮为停滞判断重复构建完整上下文 | 已修复 | `_PreparedTurn` 携带已构建快照；没有新工具状态时复用快照，工具改变耐久状态后仍重新构建。没有新增第二个“廉价上下文”事实来源。 |
| QR-09 | dry-run 通过驱动错误文本子串分类 | 已修复 | PostgreSQL 使用 SQLSTATE、MySQL 使用错误号、DuckDB 使用异常类型。SQLite 缺少稳定细粒度错误码，只在 SQLite 边界保留本地消息分类；未知错误统一为 explain unavailable。 |
| QR-10 | 三套 SSE/重试实现及硬编码 demo SQL | 部分成立并已修复 | 硬编码 `ALTER TABLE` 和死回调已删除。生产会话流只有 `conversationRepository` 的协议读取与 `ConversationStreamRuntime` 的生命周期/退避所有权；生成客户端的 SSE helper 没有生产调用方，不是第二条运行链路，不能修改生成代码来追求形式统一。 |
| QR-11 | 超大 Decimal 序列化后不受单元格长度限制 | 已修复 | 先序列化所有类型，再统一执行字符串长度限制；增加超大 Decimal 回归测试。 |
| QR-12 | MySQL `MAX_EXECUTION_TIME` 复位失败污染池连接 | 已修复 | 复位失败时记录安全诊断并关闭物理 DBAPI 连接，使池不能再次复用。确定性故障测试通过；未声称已完成真实远程 MySQL 注入。 |
| QR-13 | 带尾部注释的单条 SQL 被误判为多语句 | 已修复 | 预检只拒绝多个分号；SQLGlot 继续负责语句数量，并过滤尾注释产生的非执行 `Semicolon` 节点。覆盖 `--`、`#` 和块注释。 |
| QR-14 | 数据库工具抛裸 RuntimeError，模型只得到通用失败 | 已修复 | 参数/Artifact 缺失使用现有 `ToolInputError`；策略拒绝使用固定公开码的 `GuardrailValidationError`；意外异常继续由 ToolRuntime 安全边界处理。 |
| QR-15 | 三套方言规范化返回 `postgres`/`postgresql` 不一致 | 误报，未修改 | `postgresql` 是 DBFox 领域/驱动规范名，`postgres` 是 SQLGlot 的外部 API 名。`DialectContext.sqlglot_dialect` 是真实边界上的单向转换；绑定参数也从 canonical dialect 显式投影到 SQLGlot 名称。没有证明错方言执行。 |
| QR-16 | DataSourceForm 使用 `as never` 绕过类型检查 | 已修复 | 使用 React Hook Form 官方 `FieldPath` 和 `FieldPathValue` 表达字符串与数字字段，移除类型逃逸。 |
| QR-17 | `record_no_progress` 名义写进度，实际只加锁刷新 | 已修复 | 删除无效方法和调用；现有 `record_progress` 继续持久化停滞指纹与计数。 |
| QR-18 | 未使用的派生 SQL 实现及 `count_mode=estimate` 被忽略 | 已修复 | 删除无调用方的派生 SQL 路径。基础表且无筛选时复用目录 `row_count_estimate`；筛选结果不伪造估算值。 |
| QR-19 | SQL 标签关闭后异步 finally 重建幽灵状态 | 已修复 | SQL console 状态写入归属现有 Zustand Store；patch/append 同时检查标签和状态仍存在。关闭后迟到结果不会重建状态。 |
| QR-20 | Registry 与 PolicyGate 的 capability 集合重复 | 设计权衡，未修改 | 两处校验处于不同边界：Registry 在注册时保证执行后端可承载能力；PolicyGate 在每次执行时限制 Agent Kernel 权限。它们共享同一 `ToolCapability` 词汇，但安全策略允许未来独立收紧，保留纵深校验。 |

## 3. 其他架构建议的最终判断

原报告还把以下内容列为架构问题或长期债务，但没有给出可复现正确性缺陷：

- **JSON 状态列：** `result_json` 的终态由 `ComposedResponse` 校验，工作态读取会检查对象类型；Session Memory 有版本、数据源 generation 隔离、条数上限和旧字段清除。拆列会引入迁移和双轨状态，当前不实施。
- **Repository 返回 ORM：** Agent Repository 与 SQLAlchemy Session 处于同一后端事务边界，当前没有跨进程领域端口需求。为每个 ORM 建镜像领域对象会增加映射和第二事实来源。
- **N+1：** 报告只按循环和 `session.get` 推断，没有查询计数、锁等待或延迟证据；多个循环已经一次批量取回记录。保留为性能观测方向，不作为缺陷。
- **Retention 常量：** 审计保留天数、事件回放窗口和内存条数属于不同产品语义，不应合并为一个 `RetentionPolicy`。
- **大文件或大模型：** `runtime_reset.py`、`AgentRun`、`TablePreviewPane` 的体量只能帮助定位评审区域，不能单独证明缺陷。没有行为变化时不做机械拆分。
- **Rust `Result<_, String>`：** IPC 命令目前返回固定、安全的用户消息；是否引入结构化 IPC 错误需要单独协议设计和迁移，不属于本轮确认缺陷。
- **100 处 `type: ignore`：** 主要来自 SQLAlchemy 声明式模型与历史类型边界；mypy 全量通过。应随模型迁移逐步收敛，不能批量删除或据数量判定运行错误。

## 4. 架构克制检查

| 检查项 | 结果 |
| --- | --- |
| 新增兼容层 | 否 |
| 新增 mapper 或 DTO 镜像 | 否 |
| 新旧协议双轨 | 否 |
| 第二套 SQL 执行链 | 否 |
| Provider 名称分支 | 否 |
| 万能 Redactor / SSE 核 / 巨型状态机 | 否 |
| 新增第三方依赖 | 否 |
| 删除无效实现 | `record_no_progress`、未使用派生 SQL、硬编码 demo SQL 与死回调 |

## 5. 最终结论

原报告指出的实际边界缺陷已经修复并通过回归；错误归因和没有运行证据的重构建议已明确降级或否决。不能继续沿用原报告的 P0/P1 标签来要求“统一一切”：当前需要保持的是具体边界的单一所有权、现有纵深防御和可复现测试，而不是新增通用中间层。

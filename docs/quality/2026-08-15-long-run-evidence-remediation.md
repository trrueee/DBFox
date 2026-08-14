# Agent 长任务收尾与证据呈现整改方案

> 文档类型：质量整改记录
>
> 状态：当前
>
> 最后核验：2026-08-15
>
> 基线：`main@1ee26ce67fc6baca7b2745e7d9442f7638db0032`
>
> 适用范围：Agent RunLoop、跨 Run Result Artifact、Task Plan、部分完成、Evidence 与对话前端

## 1. 目的

真实长任务暴露出四个相互关联但边界不同的问题：

1. 后续 Run 已通过 `result_inspect` 观察前序 Result Artifact，但更新 Task Plan 时仍被当作非法跨 Run 引用，控制工具异常最终令整个 Run 失败；
2. Run 只有硬轮次和硬工具上限，没有为整理计划、引用证据和形成回答预留收尾空间；
3. 没有模型回答的受限部分结果被自动附加“来源”，把“已经保存查询结果”错误表达成“这些结果已经支撑正文结论”；
4. 前端来源区域遍历全部结果工件，而不是只展示正文真实引用的 Evidence，造成大量无语义的“查询结果”按钮。

本轮修复保持现有 `Session → Run → Turn` 模型：用户的新消息创建新 Run；同一 Run 只在审批、补充信息、进程恢复等暂停场景中继续。不会按“继续”等关键词合并 Run，也不会新增 Work、Task 或第二套上下文状态。

## 2. 调查与复用决定

| 调查对象 | 可复用能力 | 本轮决定 |
| --- | --- | --- |
| `ArtifactRepository.available_result` | 校验同 Session、同数据源、同 generation、来自更早终态 Run 的 Result Artifact | 作为跨 Run 可用性的唯一判定，不复制规则 |
| `ArtifactRepository.referenced_results_for_run` | 只返回当前 Run 已通过 Observation 实际观察的前序结果 | Task Plan 只接受该集合，不接受任意历史结果 |
| `RunRepository.record_focus` | 在既有 `result_json.focus` 中保存当前缺失项 | 用于表达“进入收尾”，不增加状态表 |
| `ToolInputError` 与 Tool Invocation 结算 | 固定、安全、可恢复的参数错误 Observation | 控制工具复用相同错误语义；未知异常仍使 Run 失败 |
| `Evidence`、正文 `{{cite:...}}` 与 Terminalizer | 结论到 Result Artifact 的耐久关系 | 只有正文真实引用才创建 Evidence |
| Artifact Dock | 展示当前 Run 和保留的工件 | “全部已保存结果”继续由工件区负责，来源区不重复承担 |

参考 OpenAI Responses 的多轮与工具调用原则时，只采用“应用负责耐久状态、工具结果和终止策略”的边界；不使用 Provider conversation 代替 DBFox Session。参考 LangGraph 的 checkpoint/pending-write 思想时，只验证当前短事务和恢复模型，没有引入新运行时依赖。

未采用的方案：

- 不直接提高 24 Turn/48 Tool 的硬上限；这只会推迟失败并增加费用；
- 不依据“继续”“接着”等自然语言决定 Run 身份；
- 不让 Plan 接受同 Session 中任意 Artifact；未来 Run、未观察结果和其他 generation 必须继续拒绝；
- 不为不同 Provider 增加特例；
- 不自动从结果列表猜“主要证据”；
- 不让前端补造 Evidence 或最终回答。

## 3. 当前不变量

### 3.1 跨 Run Result Artifact

当前 Run 可以引用前序 Result Artifact，必须同时满足：

1. Artifact 属于同一个 Session；
2. 数据源和 datasource generation 与当前 Run 一致；
3. Artifact 来自当前 Run 之前的终态 Run；
4. 当前 Run 已通过结果工具成功观察该 Artifact；
5. Artifact 类型为 `result_view`。

SQL Artifact 和 Safety Artifact 仍然只在生成它们的 Run 内有效。跨 Run 复用结果不能绕过 SQL 验证、审批或执行权威。

### 3.2 收尾预算

硬预算用于保护成本和运行时间；收尾预算是硬预算内部预留的最后空间，不是额外额度。

进入收尾后：

- Run 保持 `RUNNING`，不创建新 Run 或新 Turn 类型；
- `focus.kind` 记录为 `synthesize`；
- Prompt 明确剩余 Turn/Tool 数量和必须完成的事项；
- 工具物化收紧到计划更新、已保存结果查看和完成回答所需的最小集合；
- 不再允许新的目录探索、SQL 验证、SQL 执行或图表生成；
- 若模型仍不能形成合法回答，才按原有硬预算或停滞规则结算受限部分结果。

收尾模式不得把没有正文引用的结果自动变成 Evidence，也不得把计划未完成步骤伪造为完成。

### 3.3 Evidence

Evidence 只表示“正文中的具体结论由哪个已观察 Result Artifact 支撑”。

- 完整回答中的 `{{cite:artifact_id}}` 经校验后生成 Evidence；
- 有回答但引用缺失时，按完成合同失败关闭，不由 Terminalizer 随机补最后一个结果；
- 没有模型回答、仅由系统生成的受限部分结果摘要不创建 Evidence；
- 系统摘要可以说明“已保存 N 个查询结果”，这些结果在工件区显示，但不是来源；
- 前端来源区只消费最终消息携带的 Evidence，不遍历全部 Artifact。

## 4. 实施批次

| 批次 | 修改范围 | 独立回滚边界 |
| --- | --- | --- |
| A | Plan 跨 Run Result 引用与控制工具输入错误结算 | Artifact/Plan contract |
| B | Run 收尾预算、focus 和工具收紧 | RunLoop finalization reserve |
| C | 受限部分结果与 Evidence 语义 | Terminalizer/Evidence contract |
| D | 前端来源与已保存结果呈现 | conversation reference UI |

每批独立测试、提交和回滚。批次之间不得共享临时兼容字段。

## 5. 验收标准

### 5.1 批次 A

- 当前 Run 的 Artifact 仍可用于 Plan；
- 前序终态 Run 的 Result Artifact 只有在当前 Run 已观察后才可用于 Plan；
- 未来 Run、未观察、跨 Session、跨 generation 和非 Result Artifact 仍被拒绝；
- `update_plan` 的此类参数错误结算为 `TOOL_INPUT_INVALID` Observation，模型可以继续；
- 数据库提交错误、lease/fencing 冲突和未知异常仍使 Run 失败。

### 5.2 批次 B

- 默认限制下，在硬上限前进入一次确定性的收尾阶段；
- 收尾阶段能查看已保存结果、更新计划并形成最终回答；
- 收尾阶段不能继续调用探索、查询执行和图表工具；
- 没有可交付回答时仍按原限制结算，不无限续期；
- 小任务、审批、取消、结构化输出和普通工具调用不退化。

### 5.3 批次 C

- 完整回答中的合法内联引用继续生成 Evidence；
- 没有回答的 `NO_PROGRESS`、`TOOL_BUDGET_REACHED` 等系统摘要不产生 Evidence 和“来源”；
- 部分文本、中断文本、未知 Artifact 引用不能成为完成回答；
- Run 保持真实的 `bounded_partial`，不伪造完整结论。

### 5.4 批次 D

- 来源区只显示最终回答真实引用的 Evidence；
- 同一 Artifact 的重复引用按 Evidence 语义去重展示；
- 已保存但未引用的 Result Artifact 只在工件区或“已保存结果”状态中出现；
- 点击来源仍能定位正确 Artifact；
- 历史消息、流式回答和刷新恢复表现一致。

## 6. 验证命令

每批至少运行对应定向测试。最终统一运行：

```powershell
python -m pytest -q
npm test -- --run
npm run build
npm run lint
npm run typecheck:test
cargo test --manifest-path desktop/src-tauri/Cargo.toml
cargo clippy --manifest-path desktop/src-tauri/Cargo.toml --all-targets -- -D warnings
cargo fmt --manifest-path desktop/src-tauri/Cargo.toml --all -- --check
git diff --check
```

真实 Provider 评测保持 opt-in，不能用 scripted Provider 的结果声称模型服务已通过。Windows 安装包必须记录文件名、大小和 SHA-256；本轮不声称 macOS/Linux 已验证。

## 7. 实施记录

| 批次 | Commit | 已验证结果 |
| --- | --- | --- |
| 方案基线 | `f00eaa7f` | 设计、不变量、验收标准和回滚边界已记录 |
| A | `eaf0091f` | Plan/Artifact/Tool 输入错误定向测试 11 项通过 |
| B | `18e88cd9` | RunLoop、收尾预算、进度保护与工具物化测试 46 项通过 |
| C | `d902db8c` | Completion、Terminalizer、Evidence 与 RunLoop 测试 46 项通过 |
| D | `3f8a9310` | Conversation 来源/保存结果组件测试 12 项通过；TypeScript 测试合同通过 |
| 工程合同 | `3160b8f3` | pytest 不再扫描 `.cache/.tmp` 中的依赖与历史产物；npm 锁恢复官方注册源；文档状态恢复统一枚举 |

最终回归结果：Python `1096 passed, 4 skipped`；前端 `80 files / 350 tests`；生产构建、ESLint、设计合同和测试 TypeScript 均通过；Rust `27 passed`，Clippy `-D warnings` 与 rustfmt 通过。npm 官方审计的 production 依赖为 `0` 个已知漏洞；真实 Provider 场景仍保持 opt-in，本轮未消耗模型额度。

上述 Commit 均可独立回滚；未新增 Provider 兼容层、第二套 Agent Runtime、第二套 Artifact 模型或自然语言 Run 分类器。Windows 安装包在本记录提交后由干净工作树构建，其文件名、大小和 SHA-256 作为本轮交付证据单独记录；macOS/Linux 未验证。

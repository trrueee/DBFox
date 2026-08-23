# Memory v4 测评设计

> 文档类型：质量设计
>
> 状态：历史
>
> 最后核验：2026-08-18
>
> 目标：在不把 Provider 波动、工具合同错误或运行时故障误判为 Memory 效果的前提下，决定是否将 `DBFOX_MEMORY_V4_CONTEXT` 从 shadow/candidate 切换为默认能力。

> 归档说明（2026-08-24）：生产 Runtime 已不再提供该 v3/v4 测试开关。旧 ABBA runner 会比较一个不存在的产品变化轴，因此已删除；当前连续性评测只测量唯一生产 Memory 路径。未来若重新引入候选实现，必须通过独立构建/版本比较，不得为测评向产品代码加入测试开关。

## 1. 决策范围

本设计评估的是跨 Run 的持久化工作状态，不评估通用模型能力，也不把一次模型输出的好坏当作 Memory 的结论。

Memory v4 的被测承诺是：在一个 Run 已经产出可验证 Catalog 事实、或在失败后保留可验证事实时，后续 Run 能在同一 datasource/catalog scope 内获得这些事实；用户纠正、scope 变化或无法验证的数据不能被错误复用。

本设计不引入第二套 Runtime、Memory store 或 Provider 包装层。测试始终通过现有的 `ContextAssembler`、`project_session_memory`、`RunLoop` 和 AgentBench harness。

## 2. 通过的定义

Memory v4 只有同时满足以下三类条件才可默认启用：

1. **正确性**：被记住的事实可追溯到 durable Observation/Artifact，过期或被纠正的事实不会进入下一 Run。
2. **连续性**：后续 Run 在需要前置事实的场景中达到与 v3 至少相同的结果正确率，并减少或不增加无必要的重新检索。
3. **运行质量**：不新增 projection 异常、基础设施失败或安全 veto；效率退化在预先声明的范围内。

单个 case、单次重复只能作为 smoke evidence，不能支持 cutover。

## 3. 三层测评

### A. 确定性 projection 合同（必须全绿）

不调用真实模型。测试使用 production Repository、terminalization、projector 与 `ContextAssembler`，直接证明状态转移：

```text
Run 1 durable Observation
  -> terminal boundary projection
  -> agent_session_memories.memory_v4_json
  -> Run 2 ContextSnapshot / prompt segment
```

建议新增/补齐以下场景：

| 场景 | 前置 | Run 2 必须证明 | 禁止行为 |
|---|---|---|---|
| 已验证 schema | `schema_search` + `schema_inspect` 成功 | 只注入同一 datasource/generation/catalog revision 的对象摘要 | 注入其他 datasource 对象 |
| 失败后继续 | Run 1 因 `AGENT_NO_PROGRESS` 失败，但已有成功 Catalog Observation | 投影仍保存可验证事实 | 因 Run 失败丢弃全部事实 |
| 用户纠正 | 后续用户消息更正已选表/过滤条件 | 新纠正优先于旧 projection | 使用被更正的旧条件 |
| scope 失效 | generation 或 catalog revision 改变 | 旧 projection 不注入 | 静默复用旧 schema |
| projector 失败 | 不支持的合同或损坏 payload | fail-soft、记录安全事件、Run 仍可继续 | 写入半合法状态 |
| 空状态 | 无可验证 Observation | 不创建虚假 Memory | 注入空壳摘要 |

断言必须检查 typed `SessionMemoryStateV4` 与最终 `ContextSnapshot`，不能只断言数据库 JSON “存在”。

### B. 脚本化连续任务（必须全绿）

使用现有 `RunLoop` 和可预测的测试 Provider；Provider 根据收到的实际 messages/tool outputs 选择下一步，不能直接调用 Memory API 或偷看数据库。

每个场景都由两个或三个 Run 组成：

```text
Run 1: 获得事实 / 用户纠正 / 可选失败
Run 2: 需要利用该事实完成任务
Run 3: 可选 scope 变化或反向纠正
```

最小场景集：

1. `schema-before-query`：Run 2 不重复 `schema_search`，直接生成正确 SQL。
2. `user-correction-wins`：Run 2 使用用户最新的字段/状态约束。
3. `failed-preview-then-query`：Run 1 失败后 Run 2 仍复用已验证 schema。
4. `missing-column-repair`：Run 2 不复用已被证伪的列。
5. `generation-change-invalidates`：generation 变化后 Run 2 必须重新发现。
6. `no-progress-does-not-poison`：真实 `AGENT_NO_PROGRESS` terminal Run 不应产生虚假 Catalog working state；失败/拒绝工具输出另有独立覆盖。

每个场景记录：Run 2 结果等价性、工具调用序列、重复 discovery 调用数、注入 fragment 的 provenance，以及是否发生 projection 错误。

### C. 真实 Provider 配对 A/B（发布证据）

真实测评只在 A/B 两层全绿后执行。先运行 `context_memory` 专项集，再决定是否跑完整 AgentBench。

#### 样本和排程

- 固定 8–12 个跨 Run memory cases；每个 case 至少 3 次重复。
- 一个 repetition 使用独立 metadata/runtime 目录与全新 provider-side state。
- 对同一 case 采用 ABBA 交错顺序：`v3, v4, v4, v3`；避免时间段、缓存与限流只偏向某一候选。
- 固定 commit、dataset、model、API base、prompt version、tool materialization 和 datasource snapshot。
- 真实 Provider 的文本与函数调用合同 smoke 必须先通过；基础设施失败单独标记为 unscored，不能计作模型或 Memory 失败。

每条报告只保存模型标识、端点、掩码 credential reference、commit 和环境哈希；绝不保存 API Key、Prompt、history、原始 secret 或 provider-side conversation ID。

#### 指标优先级

| 层级 | 指标 | 说明 |
|---|---|---|
| 硬门禁 | 安全 veto、projection 异常、新基础设施失败 | 任一新增即停止 cutover |
| 主指标 | Run 2 result equivalence、纠正遵从率、有效连续任务通过率 | Memory 的实际用户价值 |
| 诊断 | Run 2 重复 discovery 次数、重复工具比例、失败工具比例 | 定位是否真正复用事实 |
| 效率 | Turn、input tokens、p90 latency | 防止“正确但过度膨胀” |

成功率、结果等价和 safety 高于 tokens/latency。若 v4 正确但效率变差，结论是“候选有效但未达发布效率门槛”，而不是“Memory 无效”。

## 4. 门禁与阈值

### 必须通过

- A、B 两层 100% 通过。
- v4 无新增 projection fail-soft 事件、未评分基础设施失败或 safety veto。
- 对 v3 在全部重复中稳定通过的 memory case，v4 也必须全部通过。
- Run 2 的 Context evidence 能证明 Memory 注入来自相同 scope 的 durable Observation。

### 配对统计门槛

- memory 专项集的通过率不得低于 v3 3 个百分点。
- 用户纠正遵从率不得低于 v3。
- Run 2 重复 discovery 中位数不得高于 v3；若更高，必须有可解释的 scope 失效或安全重验依据。
- 中位 tokens 增幅不超过 15%，p90 latency 增幅不超过 20%。

只有每个 case 至少 3 次重复后才计算以上门槛。对小样本使用 case-level paired 表，而不是只看全局平均值。

## 5. 报告与诊断

现有 `summary.json` 与 `comparison.json` 保留为通用 AgentBench 门禁。Memory 专项报告需要额外输出每个 repetition 的：

```json
{
  "case_id": "memory-user-correction",
  "memory_variant": "v4",
  "run2_result_equivalent": true,
  "projection_written": true,
  "projection_consumed": true,
  "scope_match": true,
  "correction_obeyed": true,
  "run2_discovery_calls": 0,
  "projection_error_code": null,
  "classification": "scored"
}
```

分类规则：

- `runtime_defect`：projection 未写入/未消费、scope 串用、合同异常。
- `infrastructure`：认证、限流、网络、Provider 协议失败；unscored。
- `model_behavior`：Runtime 正常但 SQL、工具参数或答案不符合 golden。
- `efficiency_regression`：正确但超过预设 Turn/token/latency 阈值。

这能避免把真实 Provider 的随机工具参数错误错误归因于 Memory。

## 6. 实施顺序

1. 在现有 Memory projection/Context 测试中补齐 A 层表格中的缺口。
2. 在 Agent harness 添加 B 层的 six-case scripted provider suite，并让每个 case 产出上述断言字段。
3. 扩展 AgentBench reporting/comparison，增加 Memory 专项 case-level evidence；不要替换通用比较器。
4. 先使用 `python -m verification.bench.agentbench memory-paired --dataset verification/bench/agentbench/datasets/memory-v1.json --profile smoke --output <dir>` 跑一个三 case、十二 trial 的 v3/v4 ABBA smoke。该命令只启动现有 `real` 子进程：每个 trial 独立进程、runtime、metadata DB、datasource fixture 和 Session；child 在关闭 production DB 前写出 durable Memory evidence。
5. 专项集全绿后，运行 8–12 个 memory candidate cases、每个 3 个 ABBA block；通过后才提交默认 flag 切换。全量 60-case 回归属于最后的发布验证，不替代该专项集。

### Correction evidence 合同

需要验证“当前请求优先”的 case 必须在 versioned dataset 中显式声明
`"correction_evidence": true`。`correction_obeyed` 只由该声明和语义
checks（required/forbidden terms、numbers，以及存在时的 result equivalence）
推导；它不依赖 case id、tool trajectory、budget 或 overall gate。

若只发现 evaluator-derived evidence 字段漏算，可使用已有 `replay` 命令的
`--memory-paired` 模式重放 immutable TrialRecord artifact。该模式不调用
Provider、RunLoop、工具或 fixture，并记录 source workflow、source hash、
evaluator SHA 和 corrected evidence hash；重放不能改变 answer、trace、结果表、
Memory evidence、provider identity 或资源指标。

通过 candidate gate 后，Context 默认使用 v4：未设置
`DBFOX_MEMORY_V4_CONTEXT` 或设置为 `1` 都选择 v4；设置为 `0` 明确回退至
v3。v3 在默认启用后的稳定观察期内仍是 rollback 路径，不能与 default-on
change 一并删除。

## 7. 当前真实 Provider 结果的使用方式

`mimo-memory-v3-live` 与 `mimo-memory-v4-live` 是连通性 smoke，不是 cutover evidence。二者都完成且无基础设施错误；v4 得到结果等价，但单次运行 token/latency 较高且超过 Turn 限制。该结果应进入模型行为/效率诊断，不应用于修改 projection 逻辑或打开默认开关。


# P2 Memory v4 Cutover Gate 本地证据与限制

> 文档类型：质量证据 / cutover gate
>
> 状态：当前
>
> 最后核验：2026-08-16
>
> 适用范围：`catalog_revision`、Memory v4 projection、`DBFOX_MEMORY_V4_CONTEXT` read path 的 P2 5.6 验收

## 1. 结论

- P2 5.1–5.5 的代码合同已实现并由确定性测试覆盖。
- **P2 5.6 尚未完全通过**：缺少当前工作树下的真实 Provider AgentBench 后测与 v3→v4 对比。
- `DBFOX_MEMORY_V4_CONTEXT` 默认保持关闭，这是安全默认值；未完成 cutover 前不得默认开启。

## 2. 已完成的本地确定性门禁

以下测试在当前工作树运行通过：

- `engine/agent/tests/test_memory_v4_catalog_reducer.py`
- `engine/agent/tests/test_memory_projection.py`
- `engine/agent/tests/test_context_memory_v4.py`
- `engine/agent/tests/test_terminal_transaction.py`
- `engine/tests/test_catalog_revision.py`
- `engine/tests/test_migrations.py`
- `engine/tests/test_engineering_contracts.py`

覆盖证据：

- incremental / catch-up / full rebuild 共用同一 reducer，hash 一致；
- failed / cancelled Run 的 succeeded Observation 可进入 v4 projection；
- projection contract failure 不阻断 canonical terminalization，watermark 不前进；
- sequence gap 不跨越；
- resource-generation transition 会重置 Catalog working state，避免 projector 长期停留在旧 generation；
- prior search query 只提升其自身 footprint 的 candidate keys，不会把一次命中放大为所有历史对象命中；
- resource fence（datasource / generation / catalog revision）阻止 stale knowledge；
- prior digest 有界（8 objects / 12 columns / 16 KiB / 2,000 tokens 估算）；
- Memory 只保存 footprint/provenance，不保存 rows / 完整 schema / secret。

## 3. AgentBench 基线

已有历史 baseline（未提交的本地运行结果）：

- 路径：`.tmp/agentbench-continuity-efficiency-offline`
- 记录时间：2026-08-14T16:29Z
- 基线 commit：`88e0e4be2d526335b8325c2e85c95492a8e15149`
- Dataset：`dbfox-agent-continuity` v1.0.2
- Passed / scored：17 / 18

本次会话另执行：

- `python -m scripts.agentbench validate`：通过，dataset 60 cases；
- `python -m scripts.agentbench calibrate`：8/8 calibrated。

## 4. 未完成项与限制

- 没有真实 Provider 凭据/运行环境，未在当前工作树执行 `agentbench real`；
- 因此没有 v4 context flag 开启后的同数据集后测；
- 无法验证“无理由 exact Catalog duplicate 相对降低 >= 70%”这一目标；
- `10/50/100 Run` 的长期有界性仅由确定性 bounds 测试保证，尚未有真实长会话运行证据。

按 `docs/quality/technical-investigation-and-reuse.md` 最后一条，本文件如实记录该调查/运行限制，不声称“没有成熟方案”或“已通过 cutover”。

## 5. 继续 cutover 所需输入

1. 可用的测试 Provider 配置（凭据只进入 OS vault）；
2. 人工授权运行 `python -m scripts.agentbench real --dataset ... --repetitions 3`；
3. v3 baseline 与 v4 candidate 两组 summary；
4. `scripts.agentbench compare` 回归门禁通过。

在此之前，P2 5.6 保持未完成，`DBFOX_MEMORY_V4_CONTEXT` 保持默认 `0`。

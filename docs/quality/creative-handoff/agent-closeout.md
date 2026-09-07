# 子任务停止时的检查点与恢复入口

> 文档类型：工程交接
>
> 状态：当前
>
> 最后核验：2026-09-06
>
> 适用范围：本轮用户主动停止后保留的分支、在制品与审查结论

## Shader 独立验证

验证员已停止，未转入 Comic。源分支 `creative/shader` 最新补充为 `a293e46f`；根分支只合入此前 `5fce70bc` 的已完成证据。`cd8c94a7` 和 `a293e46f` 均需接手人先核对是否已被后续合入。

- 已完成：8a412cdb 的真实 GPU、固定历史 JSON/纹理、CAS、取消、Host 重启和恢复。详细见根 [独立报告](../shader-independent-verification.md)。
- 未完成：cd8c94a7 的窄/宽 Artifact 布局复验。新签名包已安装，但调用 driver 时 CDP 不可用，没有尺寸或截图，原因未确定。
- 当前安装包 digest：`7e6f64e5c84e6f190e0a12c59ffe414e65890024d518afff39b4b9239dde683c`。
- 最后自有 Electron PID 6264 与 19228 listener 已确认不存在；不要假设实例仍运行，也不要关闭别人的 Electron。
- 外部数据保留于 `D:/Project/DBFox-worktrees/creative-program/shader-browser-runtime`。不提交其中的 SQLite、密钥、包、日志或下载记录。
- 已准备但未执行的布局脚本：Shader 树 `verification/testkit/shader_independent/browser-artifact-layout.cjs`。

完整可移交的恢复说明已复制为 [Shader verifier handoff](shader-verifier-handoff.md)。该说明中的脚本路径均相对 Shader 工作树；文档副本不是已复制全部运行脚本或外部数据。

## Game 作者检查点

停止时工作树 `D:/Project/DBFox-worktrees/creative-game`，旧基线 `81345258`，现已保存 **WIP 检查点 `f54950ca3196ea6526d95a579b194f7b98469c43`**，仅 39 个精确自有文件，未合入根。Game 自有路径干净，用户 baseline 保留。不要从旧 HEAD 推断在制品不存在。

已知范围：`dlcs/dbfox.game/`、`verification/tests/system/test_game_dlc.py`、`docs/architecture/game-dlc.md`、`docs/quality/game-dlc-evidence.md`；完整 frontend 仍未完成。已有 32 项作者后端与真实运行时探针，不等于独立验收。保存检查点不会将其标 integrated。

详细的 13 项剩余工作、可能缺陷与恢复命令已复制为 [Game 作者交接](game-author-handoff.md)，另附[在制架构](game-architecture.md)和[作者证据](game-evidence.md)。**最新 Studio 虽已写入，但从未在浏览器成功挂载，不能声称可用。** runtime 的最后 event budget/排序改动也未复跑先前探针。下一位先实际挂载和排除明确风险，而不是立即宣布后端/前端全完成。named Chrome `game-engine` 已关闭，自有 Python server 不存在。本次保存没有重新测试。

## 四能力 Pattern / 工具预算独立审查

工作树 `D:/Project/DBFox-worktrees/creative-composition`，原生产失败检查点 `36224475`。此阶段没有实施工具发现功能，也没有改 Core 预算。

审查者已确认额外架构风险：控制函数在现有循环不计入 max_tool_invocations；Dispatcher 固定不贡献进展；ProgressGuard 跳过控制观察。因此普通 query→select→execute 可能先触发停滞/终止。必须明确预算、有限新信息/选择的进展和重复调用防护，不能用额外无限计数或反复翻页续命。

根[设计调查](../../architecture/bounded-tool-discovery.md)仍是草案。审查者已仅提交两份交接文档，源 **`d6419861509bfda242635f6fa432fc565c9d9968`**，根文档合入 **`6331d1a1`**：[Pattern 审计](../creative-platform-pattern-audit.md)、[工具发现独立审议](../../archive/bounded-tool-discovery-control-review.md)。已做 A/B/C/D 分类、源码路径核对和 Frozen 七问，**没有完成全面 Core 零泄漏证明，也没有正式批准候选实现**。目录/进展/预算/恢复/hash/guidance 仍需正反测试。用户停止后没有新增调查或测试，只有文档保存与 diff 检查；角色已结束。

## 当前工作的边界

本轮后续只生成交接文档和保存已经存在的在制品，不再运行新产品实现、GPU工作负载或完整新测试。不存在新建自动化或后台监控要求。其他 AI 何时执行哪个任务由用户决定。

# Creative Platform 模式审计交接

> 文档类型：架构审查
>
> 状态：草案
>
> 最后核验：2026-09-06
>
> 适用范围：Scene、Voxel、Pixel、Shader 的跨能力重复模式与通用工具发现；只读调查，未完成实施裁决或验收

## 结论与停止位置

当前证据支持把多能力同时加载 schema 的容量问题交给通用工具物化边界继续设计；不支持把四个 owner 的文档、版本、undo、几何、像素或 GPU 状态统一搬进 Core。默认保留 A/B 分类。工具发现的候选属于 D，必须经过 Frozen Kernel 审议和实际默认工厂验证。

用户因额度有限要求停止开发、转交其他 AI。本轮停止扩大调查和测试，只保存已读源码事实、候选约束和未完成项。没有编写产品或测试，没有运行新的联合验收；本报告不是四个 DLC 或整个 Creative Program 的完成证明。[工具发现审议交接](../archive/bounded-tool-discovery-control-review.md)保留实现前必须解决的细节。

角色为 Creative Platform Pattern Auditor / Architecture Auditor。审查者此前参与 Voxel 后端，随后承担其他 owner 的非作者验证与红队；因此本轮不将对 Voxel 的模式分析冒充其产品质量独立终审。本轮未参与工具发现候选实现，候选也尚未实现。

## 基线与证据来源

- 联合工作树：`D:/Project/DBFox-worktrees/creative-composition`，调查基线 `362244756eaf7f167aaf357e813338cf4c7ce24b`。
- 根工作树：`D:/Project/DBFox`。通过已有 CodeGraph 查询并读取当前磁盘源码；工作树未初始化 CodeGraph。Scene、Voxel、Pixel 已集成，Shader `8a412cdb` 在 Director 集成过程中被读取。不能把这个移动的根工作树当成单一已验收提交。
- 原始用户要求第 21、22 节：从代码检查 Core 侵蚀，重复模式分类 A/B/C/D，默认倾向 A/B，不立即重构。
- 已读根 `AGENTS.md`、`CONTRIBUTING.md`、`docs/architecture/core-kernel-constitution.md` 和根草案 `docs/architecture/bounded-tool-discovery.md`。
- 联合失败的既有实测记录见[组合验证报告副本](creative-handoff/composition-verification.md)；本轮独立读取实际测试工厂及相关生产源码，没有把 Director 实测计为本轮重跑。

联合树已有大量未提交基线，不属于本轮。三个领域 `contracts.py` 在 `git status` 中显示修改，但本轮 `git diff --stat` 没有内容差异，伴随 CRLF 提示；未修改、还原或纳入提交。此记录不替代后续集成前的字节核对。

## A/B/C/D 分类

| 重复模式 | 分类与建议 | 代码事实和差异 | 不能据此上移的内容 |
| --- | --- | --- | --- |
| canonical document 与私有对象身份 | A | Scene 的对象层级、Voxel 的 chunk/layer、Pixel 的 cel/frame、Shader 的 stage/pass/uniform 不是同一数据模型 | 通用 CreativeDocument、所有 owner 共用 Object 表、统一对象 selector |
| owner SQLite、head、revision、receipt | B，当前留 owner 内 | 四个 store 都有版本和收据；Voxel 以 `world_revisions` 加 `chunk_versions` 保存差量，Shader 另有 studio generation、texture 与 report，Scene/Pixel 的文档索引与正文约束不同 | 通用 Core 文档库、一个共享 head、跨 owner receipt 表、隐式跨库事务 |
| undo/no-op/diff | A，算法辅助可为 B | 共同要求 CAS 和历史不可变；实际差异包括 chunk 墓碑、对象列表顺序、frame/tag 成员顺序、GPU report 与文档写入的区分 | 将 undo 定义为删除历史、按重复 hash 唯一化版本、共享全量 replace 工具 |
| typed 人类操作与 Agent mutation 共用 store | B + 既有 C | 各 owner contributions 将 typed operation 与 Tool 连接到同一 store；人类操作仍有 mutation identity/CAS | 强迫每次拖动启动 Run，或新增绕开 ToolRuntime 的 Agent 写入接口 |
| 显式 ActionRun 产物与 Host 导航 | C，复用已存在接点 | artifact 身份、导航作用域、Representation 请求属于 Host；领域 payload、导出参数与 bytes 属于 owner | 第二条 export API、DLC 自造 Artifact envelope、导航即授予 Agent 权限 |
| Resource provider/resolver 与 Invocation 绑定 | C + 既有 D 执行 fence | 三个文档型 owner 注册 library/document 或 world，Shader 注册 studio；声明与发现交给 Host，私有对象仍由 owner 校验 | 为统一形状扩大 required_resources、把私有 selector 变成 ResourceRef |
| 有界 context、观察与分页 | B，复用既有 C/D 预算设施 | Scene 对象、Voxel chunk、Pixel 标签成员、Shader 原始 canonical bytes 分页具有不同稳定性证明 | 一个返回任意 JSON 的通用领域检视器，或只做字符串切片而隐去 truncation |
| Artifact 固定历史与源头完整性 | B + 既有 D provenance | 内容 hash、版本和导出字节属于 owner；producer Invocation、跨 Run availability 属于 Runtime | 用有效内容 hash 代替 producer 证明，或用 Artifact 私有 ID 补全 authority |
| 视口 render 生命周期、abort、作用域切换 | A/B + 既有 C 生命周期 | Scene/Voxel 共享 Three 的使用经验；Pixel Canvas 与 Shader compute executor 生命周期并不相同 | Core 自造渲染引擎、把 GPU context 或 DOM 节点作为耐久事实 |
| 工具 schema 按需加载 | D 候选，需审议 | 至少三个 owner 在同一真实工厂触发总预算不足，调度、Turn 冻结、恢复均由 Runtime 持有 | 各 owner 复制工具目录、provider 名称分支、另建执行器或权限目录 |

B 在这里表示可复用的 owner 内辅助模式或未来经过证明的库候选，不授权内部跨 DLC import。当前没有提出新公共包或新的共享可变状态。

代码定位：根 `dlcs/dbfox.scene/backend/store.py:167`、`dlcs/dbfox.voxel/backend/store.py:86`、`dlcs/dbfox.shader/backend/store.py:51`；Shader 表定义在 63–72 行，Voxel 表定义在 120–145 行。注册边界见各 owner 的 `backend/contributions.py`：Scene 452–470、Voxel 165–184、Pixel 252–272、Shader 167–178。这些定位用于继续核对实际实现，不代表每个路径均完成新一轮攻击。

## 已确认的通用容量缺口

联合测试 `verification/tests/system/test_creative_dlc_composition.py:122` 使用正式签名 fixture、真实资源授权和 `build_product_run_loop`；140 行只替换模型工厂。既有失败是在创建三种文档后的第 4 次 prepare，完整 schema 估计 31942，而默认整个 prompt 预算是 32768。旧手工构造 `RunLoop(max_prompt_tokens=128000)` 的成功不能证明默认路径可用。

根 `engine/agent/loop.py:797` 每轮读取资源目录，再物化可发现工具；`engine/tools/materialization.py:75` 的过滤是可见性、group、execution mode、resource kind，不是预算内按需选择。`engine/agent/prompt.py:61` 预留全部 schema 成本，随后才能裁剪历史。这里缺的是工具集合容量控制，不是领域文档优化。

Director 的只读成本调查为 60 个 schema / 31942，最大单工具约 3694；这是调查输入，不是本轮新增通过证据。完整 schema 复用官方 Pydantic 构造；命名类型实验仍约 30068，未解决系统内容空间不足。不得提高预算、删除用户要求工具、移除输入约束或改成任意 JSON 来交付。

## 草案必须补的控制循环问题

本轮独立源码发现：

1. `engine/agent/loop.py:610` 明确只把 `kind != "control"` 计入工具调用预算。不能说新 ControlCommand 自动受现有 `max_tool_invocations` 约束。
2. `engine/agent/tool_dispatcher.py:444` 成功结算 ControlCommand，但 453 行固定 `contributes_progress=False`。`engine/agent/progress_guard.py:111` 跳过这些观察。
3. 默认 `max_stalled_turns=2`、`max_turns=24`、`max_tool_invocations=48`，见 `engine/agent/run.py:39`。`loop.py:994` 保存并判断连续停滞，已有可用成果时可能进入 finalization。

因此在已有领域成果后，普通目录 query 一轮、select 一轮，两轮都可能保持原进展指纹，选择刚完成就提前 finalization；更多分页更明显。这是对现有分支的源码推导，尚未新增运行反例。不能以“控制成功”冒充领域进展，也不能简单放宽停滞门禁。

最小权衡应优先复用现有 Invocation/Observation 的耐久顺序、Run 调用预算与去重证据签名。无需先加新计数表或新 Run 状态事实。其他控制函数默认行为应保持。究竟采用已有语义字段支持有限发现进展，还是在进展投影处加入一个通用 Runtime 发现证据集合，仍须以正反测试比较；详见架构交接，当前没有冻结实现。

## Core 侵蚀审计的范围限制

本轮读取的主要链保持 `registry → materialization → frozen Turn → Dispatcher → policy/resource binding → ToolRuntime`。ControlCommand 可在其已有事务中完成目录操作，不需要向 DLC 注入 registry 或数据库服务定位器；`ControlCommandContext` 已有 db/lease/run/turn/invocation。

已读历史提交 `132a29fb` 的主题与范围，现行绑定源码在 `tool_dispatcher.py:289` 以后明确逐 Invocation 发现并绑定资源。因此工具目录绝不能恢复成整个 Project 的权限授予机制。

由于交接提前停止，未完成四个产品的全面 import/dependency 扫描、所有 lifecycle 路径复读、共享修改逐提交审计及候选新测试。不能据此声称“Core 零泄漏已独立证明”。已有领域质量报告的通过数也没有在本轮重复计数。

## 2026-11-08 实际使用补充

以上是本次文档调查时的 32768 基线，不能删除或改称当时已通过。后续实际 Scene / Animation 任务再次观察到全部原生工具历史被预算裁掉、计划重写被误判进展；按 [Core 内部正确性决策](../architecture/agent-context-continuity.md)修复后，产品默认输入预算明确调整为 65536，最新完整原生 Turn 不可静默丢失。此举是有成本的容量取舍，不是原草案的工具发现实现，也不证明默认 32K 路径已能完成这些任务。

产品默认工厂的三/四签名工作室组合现在同时覆盖原生 search 模型和不支持 search 的完整 schema 模型；64K 路径完成创建、局部修改、导出和跨 owner 拒绝验证。显式 32768 路径则确认在初始若干调用后，以 `AGENT_CONTEXT_BUDGET_EXCEEDED` 耐久失败，不自动放大预算、不切换 Provider、不丢掉最近工具链。该集合与 Story/Comic、Pixel/Game、Animation 红队共 19 项通过。

真实在线模型另外完成 35 对象场景与绑定动画，最后输入估计 55284；续作累计 936215 token，仍无自主渲染回执。完整失败/修复/局限见[第六阶段使用记录](./continuous-product-use-20261107.md)。通用发现容量、成本与草案控制循环的未决问题仍然保留，不能把本轮有限默认容量成功用作该草案已完成的证据。

## 接手顺序

1. 阅读架构交接，确认产品默认工厂失败仍可复现，保留原始失败和预算遥测。
2. 在 Frozen Kernel 七问下明确批准或拒绝工具发现；先关闭控制预算、进展、恢复、hash 与 guidance 五个未决边界。
3. 只实施已批准的 Runtime 接点，保持 SDK v2、领域输入 schema、执行权威和 ActionRun 的现有合同。
4. 通过真实默认工厂组合、Core 合同及独立攻击后，再将本文状态升级；本次只交付文档，不授权跳过任何门禁。

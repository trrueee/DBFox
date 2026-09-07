# Creative DLC Program — 其他 AI 接手总指南

> 文档类型：工程交接
>
> 状态：当前
>
> 最后核验：2026-09-06
>
> 适用范围：用户因额度有限主动停止本轮开发，转交其他 AI 继续完成 Creative DLC Program

用户已于 2026-09-07 明确恢复完整原始任务，并授权撤回自定义工具目录、重新设计与开发。下文暂停记录和交接时状态保留用于追溯；实时实施状态见[机器状态](../../dlcs/program-status.json)。原始 20 项能力与组合验收范围保持不变。

## 1. 先读这一页

用户最后要求：**本 Agent 停止扩展实现，输出详细文档和指导，剩余任务由用户交给其他 AI。** 不要把这次交接理解为整个计划已经完成，也不要自动恢复全部并行工作。接手 AI 应先服从用户指定的任务包；没有指定时，从本文的依赖顺序选择一个有界任务。

原始范围是第一波 8 个、第二波 12 个 Capability DLC，加上有必要的 Composition、独立审计和最终“蒸汽朋克狐狸世界”验证。此前向用户报告的整体 15%–20% 是按交付门禁的粗估，不是自动测量、工时预测或进度承诺。不要用累计测试数推算完工百分比。

推荐阅读顺序：

1. 本文：事实状态、未完成项、工作树与风险。
2. [执行与验收指南](creative-handoff/ai-execution-guide.md)：通用工程约束、角色隔离、命令与报告模板。
3. [分任务接手指令](creative-handoff/task-packets.md)：可复制给不同 AI 的具体任务。
4. 对应 `creative-handoff/lead-*.md`：第一波每个 DLC 原有完整 Lead 模板。
5. [原始完整任务](creative-handoff/original-program-brief.md)：全部 20 项、组合目录和最终成功标准。它定义范围；本文定义接手时的事实状态。
6. [工作树清单](creative-handoff/workspace-inventory.md)、[机器状态](../../dlcs/program-status.json)、对应质量报告。

## 2. 已完成到哪里

| 能力 | 实际状态 | 接手时仍需做什么 |
| --- | --- | --- |
| Scene | 产品、独立 Verification、另行红队、原生编辑/导出/生命周期证据已合入根分支 | 保持通过；参加通用预算修复后的组合回归和批次审计 |
| Voxel | 产品与独立验收已合入；64³/128³、历史 chunk、真实下载与生命周期有证据 | 保持通过；参加组合与批次审计 |
| Pixel | 实现、独立 Verification、49 项新增红队攻击及修复已合入 | 全局状态尚未标 integrated：默认三 DLC 联合预算门禁仍失败 |
| Shader | 8a412cdb 产品修复、独立红队 958f49fd、独立桌面验证 5fce70bc 已合入根分支 | CSS 补丁 cd8c94a7 仍在 Shader 分支；最后窄 Artifact 布局验证/证据和合入状态见补充交接。未通过前不宣称最终集成 |
| Game | 独立树内有后端、真实 Phaser runtime 和部分 Workbench 实现；32 项后端作者测试通过 | 保存/核查作者检查点；完成 Studio、领域 bench、实际 Agent/playtest 闭环，再安排非作者验证与红队 |
| Comic | 调查与完整 Lead 模板已准备，无完整产品 | 按预调查选排版/导出方案，再完整实现 |
| CAD | 有真实浏览器/CSP/包体积约束调查，无完整产品 | 先解决内核方案及发布边界，不能跳过阻塞直接写假 CAD |
| Animation | 有真实 Three.js Mixer/曲线行为调查，无完整产品 | 冻结 canonical 轨道/曲线语义，实现编辑、播放及公开 Scene 消费 |
| 第二波 12 项 | 原始范围和任务方向明确，未进入产品实施 | 先完成第一波稳定门禁；不得把空目录/架构稿计作产品 |

Music、Story、Visualization、Data、Workspace、GitHub 是参考能力，不能把它们原有功能计入本次新增 20 项的完成量。用户原有 Story/Workspace 改动也不是本 Agent 的交付。

## 3. 根分支与已验收代码

主工作区：`D:/Project/DBFox`，分支 `codex/creative-program`。交接文档写入前产品 HEAD 为 `e4732e46`。之后可能增加**交接文档提交**，请以 `git log` 和本文证据中的产品 SHA 区分。

| 项目 | 根分支可定位提交 / 证据 |
| --- | --- |
| Voxel 原集成 | `bb9a00a4`；[红队报告](voxel-adversarial-review.md) |
| Scene 后续生命周期修复/证据 | `fd3d8cfb`、`1ec34c12`；Scene 质量报告与原生 controls 证据 |
| Pixel 最终产品/红队合入 | `6b910f74`、`118be7fd`；源候选 `88e7c7d1`、独立红队 `13e2fcf9`；[红队报告](pixel-dlc-adversarial-review.md) |
| Shader 后端/前端 | `d975bdc7`、`4b117497`，对应源 `f6dde52a`、`4df3568d` |
| Shader 领域 bench | 根 `0522961c`，源 `079acb42`；catalog 冲突保留四种创作 suite 各一次 |
| Shader 关键修复 | 根 `e39e7c56`、`c7bf6691`、`a7e6b344`、`a47a91f8`、`cd52c32e`；最后对应源 `8a412cdb` |
| Shader 独立证据 | 根 `47bfc382`、`e4732e46`；源 `958f49fd`、`5fce70bc` |

共享修复已合入，接手时不要再次实现或重复 cherry-pick：

- `883e6bb7`：Sidecar ready 握手后继续排空 stdout，避免管道填满阻塞服务。[证据](engine-stdout-liveness.md)。
- `b3c9225d`：已选中的树叶在关闭标签页后可以再次激活。[证据](tree-resource-reactivation.md)。
- `2bd3fa75`：生产 RunLoop 工厂传入既有 frozen resource resolver，同一 snapshot 装配；来源同步提交 `73ad76f0`。[证据](product-run-loop-resource-composition.md)。
- `e24d2423`：选中/近期/上一轮 Artifact 上下文统一使用既有可用性验证。[证据](artifact-context-availability-verification.md)。
- `96403e71`：前端 Artifact 引用使用正式 artifactId，移除非法 object.kind。[证据](artifact-reference-admission.md)。

## 4. 最重要的未完成共性问题

### 4.1 默认工具 schema 预算 — 真正的生产失败

工作树 `D:/Project/DBFox-worktrees/creative-composition`，起始 HEAD `36224475`。

复现：

```powershell
Set-Location D:/Project/DBFox-worktrees/creative-composition
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_creative_dlc_composition.py -q --tb=short --show-capture=no
```

该测试使用实际 `build_product_run_loop`，仅控制外部模型。Scene、Voxel、Pixel 三次创建成功，**第 4 次 prepare** 暴露 60 个完整原生函数 schema，既有估算为 31942 token；默认总预算 32768 容不下系统说明和上下文。它是保留的失败门禁，不是应该删除的“坏测试”。

原联合测试使用手工 RunLoop 和 128000 预算，曾完成 15 请求、12 成功、3 个预期跨 owner 拒绝、12 Artifact 与停启隔离。该结果只能证明那种夹具配置，**不能证明默认产品可用**。

已调查并否决：19 个 Pydantic 命名类型别名试验只降至 30068，仍失败；实验全部撤回。不要增加预算、删用户要求的工具、削弱输入约束或改成自由 JSON。不要新建框架、私有工具执行器或第二 RunLoop。

候选草案：[按需工具发现](../architecture/bounded-tool-discovery.md)。方案仍未实现。独立审查另发现：ControlCommand 当前不计入普通工具调用预算，不贡献进展；ProgressGuard 忽略控制观察，默认停滞限制可能让“查询→选择→执行”在执行前提前终止。因此不能仅增加 discover 控制函数就宣布修复。需要明确有界成本、真正新发现的有限进展、重复调用防护和恢复语义。

独立审计已以源 `d6419861`、根文档提交 `6331d1a1` 保存：[Pattern 审计](creative-platform-pattern-audit.md)、[工具发现独立审议](../archive/bounded-tool-discovery-control-review.md)。它们明确未正式批准实现、未完成全面零泄漏证明；[补充交接](creative-handoff/agent-closeout.md)记录最终停止状态。没有审议闭合前不要改 Frozen Kernel。

### 4.2 Shader 最后 CSS 补丁

已验收产品源 `8a412cdb`；其独立 native 冷签包 digest：`8a14196f82c580313a08ee98d763a1d37f1cd3f9df00c8e279307201275fb361`。红队另行构建的包 digest 不同，因为签名/构建身份不同，不能只凭摘要不同推断产品源码不同。

最后原生截图发现 preview Artifact 完整 pixel hash 撑宽 grid，画布和按钮超出窄 Dock。源补丁 `cd8c94a7` 仅改 `studio.css` 与质量说明：单列 minmax(0,1fr)、直接子 min-width:0、长文本换行。根分支在本轮交接前**未合入**此补丁。

接手只需验证同一历史 preview/document/report 卡片的窄宽布局、内容可达、截图及尺寸，然后按结果合入。不必重跑全部 GPU、所有后端故障与完整压力测试来验证 CSS。原生实例是否关闭、保留 profile 和复现脚本见补充交接；不能假设旧端口仍活跃。

### 4.3 Game 在制品

工作树 `D:/Project/DBFox-worktrees/creative-game`，原基线 `81345258`；新作者检查点见补充交接。**不要从根分支新建空 Game 实现覆盖现有工作。**

已报告事实：32 项作者后端、17 个实际物化 schema 的完整 nullable 参数、正式生产工厂/ActionRun、公开 Pixel frame Representation 消费与 DERIVED_FROM。固定 Phaser 4.2.1 vendor 有许可证、provenance 和 hash 守卫的 VisibilityHandler 销毁修复。真实 runtime 在生产 CSP 下跑出 Canvas/HEADLESS 120 tick 报告一致、3600 tick 胜利条件、同 seed 的 spawn/lifetime/seek 一致，以及同 tick scene_change/finish 顺序和资源释放。

以上属于作者证据。完整 Studio、连续真实 Agent→playtest→observe→修改、规模、独立 Verification/红队均不可跳过。精确文件、命令和剩余操作由作者的 `docs/quality/game-dlc-handoff.md` 维护。

## 5. 最近验证证据，避免重复烧额度

| 验证 | 已完成结果 | 证明范围 |
| --- | --- | --- |
| 根 Shader 作者+红队+bench+大调用恢复+工程 | 164 passed / 153.19s | 根合入代码的确定性回归；不是实际 GPU |
| 根 Shader 独立 factory/fence/crash | 9 passed / 29.58s | 正式装配、真实 executor、提交前后恢复与不重放 |
| 根 Shader 四个前端文件 | 38 passed / 10.92s，typecheck:test 通过 | UI 合同、读页、生命周期、负驱动边界；jsdom 不证明布局或 GPU |
| Shader 独立红队 | 新 57 后端 + 16 前端分批通过 | [独立报告](shader-dlc-adversarial-review.md)，原失败与夹具修正保留 |
| Shader 独立真实桌面 | 9 native Tools / 8 Artifacts；实际错误→修复→预览 | [验证报告](shader-independent-verification.md)，模型是本地受控 SSE，不证明自由模型智能 |
| Shader 最后冷读 | 大文档 62 stages、128 active uniforms；30 请求 / 840ms | canonical 462264 bytes 与源 hash 保持；source 总 424809 bytes，二者不是同一计数 |
| Shader 最后冷 GPU | 一次 Render & publish，attempt 1，609ms，PNG 853 bytes | 65536 pixels 经独立 Pillow 全像素核对，公开 stream/hash 一致 |
| 根 Pixel 合入后 | 171 后端/bench/独立/工程通过；70 前端通过 | 不包含随后尚未修复的默认多 DLC 预算门禁 |
| 上次共享工厂修复后 | 823 System + 314 Agent Core 通过 | 不能把这批旧结果称为未来 Kernel 改动后的新回归 |

Shader native Choose PNG 被点击，但 Windows computer-use 服务管道两次不可用，没有完成原生文件选择/导入。已有 sampler、codec 与 domain 测试不能替代它。本环境也没有 packaged installer、Frozen Sidecar、保存对话框目标选择或长期 heap 上界的完整证明。明确保留这些边界，不伪造已测结果。

## 6. 后续建议顺序

1. 保存并阅读本轮全部检查点；核对根、Shader、Game、composition 的最新 HEAD 和 dirty baseline。
2. 用小任务结束 Shader CSS 的独立布局验收及精确合入。
3. 单独完成四能力 Pattern/Architecture Audit，冻结通用工具预算方案；另开实现 AI 修复并由非作者审查。
4. 让 Game AI 继续在制品，同时可启动独立 Comic AI；CAD 和 Animation 可以先做有界架构研究。
5. 第一波完整稳定后，实现有真实需求的 Pixel→Game、Scene→Animation、Scene→Game、Story→Comic 联合任务。普通 Agent 编排已经足够时，不额外建 Composition DLC。
6. 再进入第二波 12 能力，按依赖和用户预算逐项分发；最后执行原始世界级任务。

预算有限时建议每次只派一个明确交付：例如“完成 Shader CSS 验收”，或“Game 完成可编辑 Studio 并交作者验证”。收到可审查代码和证据后再派独立审查。不要让每个 AI 从头重读所有仓库、反复跑全量测试，或只重复写 roadmap。

## 7. 工作区与用户改动保护

根工作树有大量**用户先前未提交改动**。新建分支并不自动隔离这些文件；各创作 worktree 也携带了当时复制的 baseline。不要 `git add .`、reset/clean、覆盖锁文件或把所有 dirty 文件当成本 Agent 的输出。

特别是根当前未跟踪的 `docs/architecture/core-kernel-constitution.md`、API v2 surface fixture、Story consistency 与 Story 前端测试，都是既有 baseline 的一部分。即使你的测试依赖它们，也不代表获得将它们归入本任务提交的依据。

外部 baseline/patch 存于 `D:/Project/DBFox-worktrees/creative-program/`。本交接包不会将这些混合补丁、用户数据库、凭据或运行日志打包入仓库。换机器时，仅克隆根已提交分支可能无法复现本地基线；应由用户有意识地迁移必要的未提交源码与运行环境，审查敏感内容后再传输。

新 AI 先运行 `git status --short`、`git diff --stat`、`git worktree list --porcelain`，与交接清单比较。只暂存自己明确拥有的路径。修复/证据提交用 SHA 标识，不用“最新版本”作为可复现依据。

## 8. 如何结束每个接手任务

必须交付：准确分支/工作树/提交、实际改变的行为、命令与测试结果、独立证据来源、未验证范围、遗留 P1/P2、下一位 AI 的第一步。只有 Director/用户指定集成人在所有门禁完成后才更新 integrated。

交接本身不降低任何产品门禁。它的成功标准是：用户可以把某一份指令交给另一个 AI，后者不依赖本会话记忆，也不会误删现有工作、扩大 Core 领域职责或伪称全计划完成。

# Creative DLC Program — 其他 AI 接手总指南

> 文档类型：工程交接
>
> 状态：当前
>
> 最后核验：2026-09-07
>
> 适用范围：已恢复开发的 Creative DLC Program；原始任务、当前状态和历史交接索引

用户已于 2026-09-07 明确恢复完整原始任务，并授权撤回自定义工具目录、重新设计与开发。下文暂停记录和交接时状态保留用于追溯；实时实施状态见[机器状态](../../dlcs/program-status.json)。原始 20 项能力与组合验收范围保持不变。

## 1. 先读这一页

用户此前因额度有限要求暂停并输出详细交接；2026-09-07 又明确要求由当前 Director 删除不当实现、重新设计开发，并完成原始 DLC。当前按新指令持续实施，原暂停要求只作为历史记录。其他 AI 接手具体任务时仍应遵守其被分配的范围，避免重复启动已有作者或覆盖在途工作。

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
| Pixel | 实现、独立 Verification、49 项新增红队攻击及修复已合入；原组合预算问题已有原生 tool search 修复与确定性组合证明 | integrated；参加 Pixel→Game 真组合和最终批次验收，付费在线模型质量未测 |
| Shader | CSS 修复 `88fcb110` 和独立原生窄/宽 Artifact、不可变下载证据 `df6a91fe` 已合入 | integration_verification；保留质量报告中的文件选择器、安装包及最终批次范围限制 |
| Game | 作者候选已提交；独立树 `77d1deb5` 完成真实Pixel→Game组合、9项红队和原生编辑/撤销/重启/失败698/胜利3600/下载证据 | 两项真实UI问题正在修：通用Studio切换丢选择、Host窄窗43px；根产品尚未集成 |
| Comic | 作者完整候选 `196f949f` 已提交，24项测试/13类bench和原生UI有作者证据 | 独立Story→Comic组合与红队进行中；Story授权入口已修 `ffea18d5`，待独立复跑 |
| CAD | 真实 PlaneGCS 数值探针5项通过，发布包浏览器加载失败已复现，无完整产品 | 固定上游重新构建、几何内核及发布边界待解决；详见 CAD preflight 和复现脚本 |
| Animation | 完整工具/Representation/Workbench进入作者原生收尾；19后端/5Three/12类生产bench报告通过 | 最后尺标密度修复重签验证，随后独立Scene组合、红队与原生验收 |
| 第二波 12 项 | 原始范围和任务方向明确，未进入产品实施 | 先完成第一波稳定门禁；不得把空目录/架构稿计作产品 |

Music、Story、Visualization、Data、Workspace、GitHub 是参考能力，不能把它们原有功能计入本次新增 20 项的完成量。用户原有 Story/Workspace 改动也不是本 Agent 的交付。

## 3. 根分支与已验收代码

主工作区：`D:/Project/DBFox`，分支 `codex/creative-program`。最初交接时产品 HEAD 为 `e4732e46`；恢复后已新增真实产品修复 `88fcb110`、`e2a2c69f`，以及原生验证 `df6a91fe` 和 CAD 调查 `fc7e153e`。以下原始提交表保留追溯，不代表最新 HEAD；实时状态以 `git log`、机器状态和各项质量报告共同核对。

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

## 4. 当前共性问题与已关闭事项

### 4.1 工具预算：原生发现修复已合入

原生产四能力默认32768预算失败保留为回归。根 `e2a2c69f` 已在真实 Provider 边界接入原生 hosted `tool_search`/延迟函数 schema，保留完整 Responses 历史；删除此前未接受的自定义查询/选择控制面，原 Registry、Materialization、Dispatcher、授权与预算职责不变。独立四签名DLC组合峰值32711，默认预算内完成。

旧/未知模型仍走完整schema，原默认 `gpt-4o-mini` 容量问题没有被伪称消失；没有擅自替换用户模型。详见 [当前架构](../architecture/bounded-tool-discovery.md)、[独立审查](native-tool-search-review.md) 和 [组合验证](creative-dlc-composition-verification.md)。旧控制面讨论见 archive，仅作历史。

### 4.2 Shader CSS：修复和 scoped 原生复验已合入

根 `88fcb110` 与 `df6a91fe` 已完成Shader自己的grid约束、319/1440窄宽Artifact和1434bytes不可变下载复验。该补丁没有修通用Host布局。质量报告中原生文件选择、Frozen安装器、人工保存对话框、长期heap等边界仍保留。

### 4.3 正在修复的真正阻断

- **Host窄窗**：696px可用空间容不下420+320+8的分栏最小值，布局库自动折成44px而store仍认为打开。专门作者 `codex/game-host-fix` 在源头修分栏和显示一致性，不让各DLC各自加补丁。
- **Game作品定位**：初次通用Studio tab切到报告再返回丢游戏选择；数据保留。修复复用既有Host具体作品target/authority，原生和独立复核待完成。
- **Story授权**：独立真实Story→Comic组合发现自建WorldDescriptor缺SDK授权方法；根 `ffea18d5` 删除重复类型直接复用公开ProjectResourceDescriptor。原12项Story测试通过，组合独立复跑中。[修复说明](story-resource-admission-fix.md)。
- **CAD内核部署**：数值计算真实通过不等于发布可用，现成PlaneGCS包同时触及Host WASM和动态JS策略限制。需固定上游重新构建并实测；不得放宽生产CSP来冒充部署完成。

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

## 6. 当前执行顺序

1. 收束Game作品定位和Host布局修复，并做独立原生宽窄复核后再集成Game。
2. 完成Comic独立红队与真实Story组合；接收Animation作者候选后独立验证Scene组合。
3. 继续CAD固定上游构建、约束求解与几何内核实际部署，不将探针作为CAD产品。
4. 第一波稳定后扩展Scene→Game、Music→Visual/Game、Map→Story等原始组合；普通Agent编排足够时不新建Composition DLC。
5. 按依赖进入第二波12能力，最终执行蒸汽朋克狐狸世界任务和整体架构审计。

每项只重跑变更相关门禁，保留作者与独立证据区分；不重复从头调研已决事项，不用累计测试数推算完成率。

## 7. 工作区与用户改动保护

根工作树有大量**用户先前未提交改动**。新建分支并不自动隔离这些文件；各创作 worktree 也携带了当时复制的 baseline。不要 `git add .`、reset/clean、覆盖锁文件或把所有 dirty 文件当成本 Agent 的输出。

特别是根当前未跟踪的 `docs/architecture/core-kernel-constitution.md`、API v2 surface fixture、Story consistency 与 Story 前端测试，都是既有 baseline 的一部分。即使你的测试依赖它们，也不代表获得将它们归入本任务提交的依据。

外部 baseline/patch 存于 `D:/Project/DBFox-worktrees/creative-program/`。本交接包不会将这些混合补丁、用户数据库、凭据或运行日志打包入仓库。换机器时，仅克隆根已提交分支可能无法复现本地基线；应由用户有意识地迁移必要的未提交源码与运行环境，审查敏感内容后再传输。

新 AI 先运行 `git status --short`、`git diff --stat`、`git worktree list --porcelain`，与交接清单比较。只暂存自己明确拥有的路径。修复/证据提交用 SHA 标识，不用“最新版本”作为可复现依据。

## 8. 如何结束每个接手任务

必须交付：准确分支/工作树/提交、实际改变的行为、命令与测试结果、独立证据来源、未验证范围、遗留 P1/P2、下一位 AI 的第一步。只有 Director/用户指定集成人在所有门禁完成后才更新 integrated。

交接本身不降低任何产品门禁。它的成功标准是：用户可以把某一份指令交给另一个 AI，后者不依赖本会话记忆，也不会误删现有工作、扩大 Core 领域职责或伪称全计划完成。

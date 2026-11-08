# 可分发给其他 AI 的具体任务包

> 文档类型：任务指导
>
> 状态：当前
>
> 最后核验：2026-09-06
>
> 适用范围：用户按预算分别派发后续任务；不是自动启动指令

先阅读[总交接](../creative-program-handoff.md)。下列提示词可直接复制；路径对应当前 Windows 工作区，换机器时先核对工作树和基线。所有任务遵守[通用指南](ai-execution-guide.md)。

## A. Shader 最后布局与合入 — 最小收尾任务

```text
你负责 Shader 最后的窄 Artifact 布局验收与精确集成，不重做 Shader。
根 D:/Project/DBFox HEAD产品基线e4732e46已合入8a412cdb产品、958f49fd红队、5fce70bc验证。
Shader树 D:/Project/DBFox-worktrees/creative-shader 有cd8c94a7纯CSS补丁，根尚未合入。
先读本交接agent-closeout和verification/testkit/shader_independent/HANDOFF.md；核对后续证据提交。
旧截图final-cold-gpu.png暴露长pixel hash撑宽grid；补丁仅改minmax/min-width/换行。
恢复同profile签名包，实际打开原preview Artifact，在窄Dock和宽视图测client/scroll/bounds并截图。
再确认原document/report卡片标题、文字、源码入口、下载按钮可达。不新发布GPU成果，不重放旧写入。
若原生环境不可恢复，使用正式Host和签名DLC建立等价真实布局复验，明确证明范围。
通过后只cherry-pick尚未合入的CSS及补充证据，核对产品字节与源码，更新状态与质量报告。
不能把整个Program标完成，也不能绕过仍失败的多DLC默认预算门禁。
```

退出条件：原生布局事实明确；CSS 和其独立证据精确合入；没有遗留未解释的裁切。若仅环境阻断，交付可复现步骤与限制而不是假通过。

## B. 工具预算架构裁决 — 只读任务

```text
你是独立Architecture/Pattern Auditor。先读根bounded-tool-discovery.md和composition树的审计交接。
在Scene/Voxel/Pixel/Shader四能力中检查领域泄漏、重复状态和生命周期，按A偶然相似/B DLC库/
C稳定Host边界/D Core原语分类，默认A/B，不马上提炼公共创作框架。
复核实际build_product_run_loop三DLC第4prepare的31942/32768失败，不增加预算、不改产品。
调查现有materialize_tools、ToolMaterialization、ControlCommand、Turn/Observation、ProgressGuard。
特别核对控制函数不计工具预算且不贡献progress导致query-select提前finalize的风险。
给出最小可实施合同：目录、分页身份、加载选择、完整schema、旧Turn/hash、取消恢复、无authority扩张、
预算和有限进展成本；比较是否能只复用已有持久事实，避免新计数/表/SDK/ControlContext。
回答FrozenKernel七问，列出必须通过的独立反例；已有审计稿是待评估材料，不是强制结论。
只交架构裁决与证据，不实现代码。
```

## C. 默认工具预算修复 — 在 B 收敛后派发

```text
你是通用Runtime实现者。先获得任务B的明确审议结论，不把草案当冻结合同。
工作起点是creative-composition实际失败测试；先同步已接受共享修复/相关产品，保护baseline。
只实现经接受的provider-neutral、capability-neutral按需schema边界，保留原完整typed工具。
发现/加载不得授予资源权限，未加载调用仍由原Dispatcher拒绝，原policy/approval/执行/恢复路径不变。
控制选择须同Run耐久且有界，旧Run/版本/停用不继承；目录不能无限增长或通过重复翻页骗进展。
保持默认max_prompt_tokens，不删工具、不弱化约束、不加自由JSON通道或第二RunLoop。
更新真实模型fixture使其根据真实目录返回选择，再执行原15领域请求；保留12成功/3预期拒绝、
12Artifact及局部修改保持/停启隔离。发现控制调用另计，不能偷偷删原断言。
验证每轮schema/prompt峰值、额外轮次、暂停/恢复、sameTurn未加载拒绝、合同失效、预算边界。
完成相关Core/System/工程及DLC conformance，交非作者审查。精确报告新增公开/持久化合同与风险。
```

退出条件：默认生产三 DLC 联合任务通过；全部权限/恢复不变量保持；额外调用成本可观察；独立审查接受。一个“测试绿了”的手工 RunLoop 不算完成。

## D. Game 完成作者实现 — 接续已有代码

```text
你是dbfox.game Lead。不要新建空实现，先进入D:/Project/DBFox-worktrees/creative-game。
读取game-dlc-handoff.md、本包lead-game.md、当前game-dlc.md与program-status。
核对32作者后端、17实际nullable schemas、Phaser4.2.1 vendor与真实runtime证据。
先完成实际Studio：entity hierarchy、component inspector、preview、play/pause/reset、event log，
鼠标/键盘直接编辑与CAS、版本固定的playtest、Agent引用和Artifact历史视图。
实现狐狸躲史莱姆60秒获胜，并经历降速、dash+cooldown、生命、改90秒、人手删除敌人、Agent再平衡、
连续playtest和设计说明。保留唯一canonical model与确定性seed/tick/scene规则。
Pixel资产只经正式Representation和合法DERIVED_FROM，不import Pixel内部。
覆盖规模、停止/关闭/停用、迟到计算、提交前后恢复，完成12类bench及十类连续修改。
不要调整Core预算；共性工具发现由任务C负责。提交作者候选后，另派Verification和红队。
```

作者退出后，再分别使用通用独立验证/红队模板；不要让同一 AI 自称独立验收了自己实现。

## E. Comic 从调查进入产品

```text
你负责dbfox.comic，工作树D:/Project/DBFox-worktrees/creative-comic。
读lead-comic.md和comic-dlc-preflight.md；先用真实Chromium小探针选择文本排版/渲染/导出方案。
必须验证中文、英文长对白、换行、emoji、缩放、拖动、窄Dock、导出重开与字体/裁剪；不手写通用Unicode排版器。
Comic管理页/面板/镜头/角色位置/对白/字幕/视觉注释，Story继续管理人物与世界事实。
当前Story没有已核实的固定Artifact Representation，不能假设story.snapshot.v1或读Story数据库。
独立Comic不依赖Story安装；先完成全部指定工具、Page/Storyboard、Inspector/Dialogue真实编辑。
数百页按固定版本分页/虚拟化，不全量常驻DOM或Context；布局和分镜共用唯一canonical内容。
交完整作者实现、bench和例子，再由非作者验证和红队；确有正式输入依赖后才做Story→Comic。
```

## F. CAD 内核决策与完整产品

```text
你负责dbfox.cad，先读lead-cad.md与cad-dlc-preflight.md。
原实际Host CSP拒绝WASM compile各入口；无CSP的正确MIME探针成功不代表产品可用。
调查的Replicad/OpenCascade资源约22.4/22.98MiB，超过当时20MiB单asset限制。
不要直接放宽Host CSP/包限制，不要将假mesh布尔称为参数CAD；先比较成熟本地内核及真实执行边界。
如需通用Host seam，按FrozenKernel七问提供真实需求、最小范围和独立安全/生命周期审议。
canonical必须是可重算参数operation tree，含sketch/constraint/dimension/feature/body等。
目标78mm×10mm手机、65度倾角、充电槽支架，随后宽度82mm参数化重算，不能重新生成不可编辑STL。
验证几何正确性、深图、失败回滚、导出重新读取、直接编辑与Agent局部修改，再走完整独立门禁。
```

## G. Animation 与公开 Scene 消费

```text
你负责dbfox.animation，读lead-animation.md与animation-dlc-preflight.md。
既有Three0.185.1真实Mixer探针覆盖1001keys/10000seeks；LoopOnce完成后重播需明确解除paused。
Three clone/toJSON不会保存自定义Bezier控制点，不能用它作为canonical曲线存储。
自行冻结领域曲线/时间/轨道/关键帧模型，复用成熟Mixer作为运行投影，避免修改引擎或双份可写事实。
实现timeline、curve editor、playback、markers和全部增量工具、CAS/undo/固定历史Artifact。
Scene动画目标仅消费公开Representation；明确稳定对象定位、源版本变化、停用和过期规则。
数千关键帧的检视与UI必须有界，实际验证seek/replay/close/dispose和Scene→Animation联合任务。
```

## H. Composition — 用户任务优先于包数量

```text
你接手一个明确跨媒介任务。先说明普通Agent编排是否已经足够。
没有新的联合私有状态/资源需求就不创建Composition DLC，交正式编排测试即可。
需要Composition时明确dependency contract、自有state与操作；只经公开Artifact/Representation/Resource。
禁止跨owner私有import/store访问；来源证明不扩展Invocation权限。
测试A缺失、B缺失、均存在、stale、停用、冲突版本、取消、部分失败、重启、大成果。
优先Pixel→Game、Scene→Animation、Scene→Game、Story→Comic；后两者依赖真实可用公开合同。
保留原始提示词列出的后续组合与最终世界任务，不以一个联合测试声称整套Composition完成。
```

## I. 第二波 12 个能力 — 每次只选一个

统一要求：按原始 brief 第 5 节读取准确范围；使用完整 Lead 流程与独立门禁。下表是接手方向，不是已经冻结的模型/预算/依赖。

| DLC | canonical 方向 | 工作台与关键验收 |
| --- | --- | --- |
| map | regions/points/paths/layers/labels/terrain | 地图局部编辑、数千 feature 分页、Story 地理公开消费 |
| architecture | levels/rooms/walls/openings/furniture/constraints | 2D floorplan 与 3D 投影共用事实；尺寸和约束增量修改 |
| poster | 结构化版式、文字、图形、资源与图层 | 自由画布直接编辑，字体/排版/导出与历史保持 |
| typography | 字体/文字对象、组合、排版参数 | 文字作为创作对象，成熟排版与许可；不只保存字符串 |
| sound | clips/regions/effects/automation/mix | waveform/mixer/effect chain；与Music谱曲领域分开 |
| simulation | entities/rules/parameters/initial/observations | configure→run→inspect→modify，确定性/时限/取消和结果预算 |
| robot | robot/joints/kinematics/motion plan | 3D运动模拟，结构/计划可编辑；原任务不授权物理机器人控制 |
| electronics | components/nets/parameters/simulation | schematic与连接/仿真一致，成熟求解器调查及有界执行 |
| lego | bricks/connections/subassemblies/instructions | 搭建与连接约束，自动生成可检查步骤 |
| creature | anatomy/traits/proportions/materials/abilities/variants | 可视可编辑结构，不能只有文本character sheet |
| recipe | ingredients/quantities/procedures/timing/temperatures/flavor | 结构化修改、比例计算与流程一致，领域模型不进Core |
| fashion | garments/layers/materials/silhouette/palette/measurements/outfit | 服装组合与参数编辑，未来公开CAD/Scene/Creature消费 |

可复制启动句：

```text
你负责第二波dbfox.<目标>。先核对第一波依赖门禁与用户本次授权范围，读取original-program-brief第5节。
依ai-execution-guide的完整Lead流程调查、冻结25项合同、实现后端与真实工作台、bench/例子，
再交独立验证/红队。不要为了凑数复制别的DLC模型，不要先造公共创作框架，不引入未授权付费服务。
先给可审查的小型技术探针和明确模型决定，随后落实完整产品；进度只按证据报告。
```

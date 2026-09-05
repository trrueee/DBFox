# Voxel DLC 验证证据

> 文档类型：质量与验证
>
> 状态：草案
>
> 最后核验：2026-09-05
>
> 适用范围：`creative/voxel` 隔离 worktree；Windows x64。

Backend 与 Workbench 已有实现；以下门禁仍需完成独立 Verification 与 Red Team。实现者验证见本文后续记录和 `dlcs/dbfox.voxel/README.md`，不能据局部通过将整个 DLC 标为 integrated。

| 类别 | 必须验证的行为 |
| --- | --- |
| 模型 | create/inspect/fill/box/sphere/extrude/replace/copy/mirror/boolean/configure/delete；错误引用和 schema 输入；layer/palette/region 一致性 |
| 增量 | 局部修改不改变其他 chunk；不提供 whole-world replacement tool；no-op 不增加 version；批量操作候选数有上限 |
| 持久化 | reopen 同内容；事务中断完全回滚；损坏 chunk fail closed；未知 schema 拒绝；前后版本/undo 历史保留 |
| 并发 | stale input；frozen invocation 过时；两个 writer 只提交一个；frontend 与 Agent 先后修改可见 |
| Runtime | 取消/超时前和计算中不提交；提交后未知结果不重放；同 invocation 同 payload 恢复 receipt；不同 payload 同 identity 拒绝 |
| 资源 | project 归属校验；UI selection 不授权；只注册 owner namespace；resolver 的历史读取仅服务 frozen/reconcile 合同 |
| 生命周期 | 打包、签名 fixture、启用后 contributions、禁用后新 snapshot 清除、重新启用持久化保留；uninstall 默认保留数据 |
| 有界性 | 世界至少 128³ 填充；context 不含 voxel 数组；inspect 有分页；Tool output 和 Representation 明确上限 |
| Workbench | 实际 3D render、orbit、selection、palette、layer visibility、slice painting、bulk edit、undo；CAS conflict 刷新且不自动重试 |
| Artifact | immutable snapshot；分页 Representation；head 改变/删除后原 snapshot 不变；无外部 URL/路径 |
| Creative stress | 64³ 赛博朋克狐狸神社；十种修改走生产 Tool path；人编辑后 Agent 修改保持人改动 |
| Red team | 独立 reviewer 攻击上述边界，不依赖实现者声明；严重确认问题全部修复 |

Bench 使用现有 `verification/bench/framework` 的 manifest、TrialOutcome 和 reporting；catalog 注册交由 Program Director。单 DLC 固定数据和 scorer 仅放在 `verification/bench/capabilities/dbfox_voxel`。

目标用例为 simple creation、incremental modification、multi-stage creation、invalid instruction recovery、inspect-before-edit、stale version、no-op、ambiguous、large document、bounded context、user-then-Agent、negative no-modification 和 regeneration abuse。模糊/negative 场景不得通过自动猜测高风险几何修改取得通过。

## Creative stress 设计

目标作品固定世界尺寸 `64×64×64`，Y 轴向上。Palette 包含玄武岩、黑曜石、霓虹青、洋红、金、狐狸橙、奶油白，0 为透明空气。作品分 foundation、architecture、fox、neon 四层：基座与阶梯、双柱鸟居与横梁、中空神殿和门洞、多层屋顶、中央橙色狐狸头像与尖耳、青色双眼、悬浮灯笼和能量环。Named region 至少包括 shrine、fox、entrance。所有创作以高层 fill/box/sphere/extrude/copy/mirror/boolean 操作形成，禁止 per-voxel Tool 调用。

随后执行并保存每步结果版本、changed chunk、工具计数和确定性断言：

1. 添加一对新的霓虹灯笼。
2. 删除入口中的临时脚手架。
3. 仅替换狐狸眼睛 region 的材料，验证 region 外 chunk 不变。
4. 镜像/复制偏侧装饰完成入口大范围重排，验证 fox 层保持。
5. 修改洋红 palette 色值，保留所有 voxel index。
6. 模糊指令“调整一下”：明确缺少 selection/参数，不产生领域 mutation。
7. 从旧 inspect version 发出与当前状态冲突的修改：拒绝并保留 head。
8. typed Workbench operation 直接编辑阶梯；随后 Agent 修改远端灯笼：保留人改动。
9. 撤销一步修改再进行 correction；版本继续递增，旧 Artifact 保持。
10. refinement：局部 cyan 替换并导出 immutable snapshot；验证尺寸、named regions、layer、颜色分布和非空 chunk 数。

扩展规模用例建立至少 `128³` 实体填充（2,097,152 个 voxel），检查单次高层操作工具效率、context 字符数不随 voxel 数增加、mutation observation 只有摘要、分页 chunk 可完整重组但每页有界；再进行局部修改并验证只有命中 chunk 产生新 revision。

Domain Architect 首轮最终报告重复了一条已被Lead源代码核查否定的推断：不要求每次world修改后创建新Run。该推断不纳入本合同；以上“每个新ToolInvocation绑定current discovery版本”段落是权威决定。Backend Engineer实施任务已要求先重读实际绑定代码。

线程调度说明：当前工具的全局线程数限制包含已完成子线程，且无关闭线程工具。Domain Architect轮次已完成，随后同一专员线程切换为Backend Engineer；其后续实现不计作独立审查。最终Adversarial Reviewer必须由未参与Voxel实现的Agent承担。Workbench与Verification职责仍必须完成，不能以线程限制削减交付范围。

## 工具观察投影与 Context 边界修复

2026-09-05，`/root/voxel_observation_fix` 按 Director 指派担任 Backend 修复工程师；本节是实现者回归证据，不计为独立审查。

正式签名包和生产 RunLoop 先复现：`voxel_create` 已成功写入世界和 Artifact，但默认 `BaseTool.project_observation` 只投影通用计数字段，下一 Turn 的 `function_call_output.facts` 没有 `world_id`、`version`，无法依据真实观察发出增量修改。直接 Tool Runtime 测试读取 `result.output` 曾掩盖这一缺陷。

调查了公开 `ToolObservationProjection`、Music 已有领域投影、ToolSettlement 的耐久 facts / provider payload 路径，以及 Voxel `inspect` / `diff` 的完整条目分页。采用现有 SDK 扩展点：创建、十一种修改工具、inspect、diff 和 export 均以各自具体 Output 模型校验成功输出，再提供完整有界 facts 与 provider payload。失败、取消、结果未知时不投影成功世界信息；Artifact ID 继续由 Host 的 observation envelope 提供。没有新增依赖、Core 改动、兼容层或额外映射合同。

所有十五个 Tool 的 Runtime output 上限为 16,384 UTF-8 bytes；store 的 inspect 与 diff 通过缩减完整条目把每页控制在 12,000 bytes。成功投影完整保留版本、无修改标志、删除状态、计数、hash、对象和分页游标，低于 facts 32,768 / provider payload 65,536 bytes。Inspect 的 `next_object_offset` 固定同一 `version`；diff 的 `next_after` 固定原 `from_version` / `to_version`。没有截断 JSON 或对象字符串，页重组回归验证对象不丢失、不重复。

该边界测试还复现了合法控制字符名称在 JSON 中膨胀的问题：80 字符名称最多成为480个 JSON 字符，固定取4个 layers / 6个 palette / 3个 regions 会超过 ContextFragment 的4,000字符上限。经 Director 扩大修复范围，`VoxelContextContributor` 在包含指导文本的完整序列化内容上计数，必要时去掉完整对象并设置 `truncated=true`，保留完整 world/version/title 和 `voxel_inspect` 的 `object_offset=0` 入口。它不截取序列化字符串，也不缩写 ID 或名字。

当前验证命令与实际结果：

```powershell
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_voxel_dlc.py -q --tb=short --show-capture=no -k 'not signed_runloop or create-inspect'
```

43 passed，1 deselected，20.04秒。包含十五种工具的失败/取消/未知投影、全部具体成功 Output 合同、旧 receipt 的原版本投影、80字符四字节 Unicode 和 JSON 转义名称、128字符对象 ID、16 layers、完整 inspect 分页重组、128³世界两次写入后的512个变化 chunk 双哈希分页及错误版本游标拒绝。正式签名包的 `create → inspect` RunLoop 用例通过；动态世界 ID 与版本只来自实际 `function_call_output`，不从私有 store 给模型补齐。

`python -m mypy --no-warn-unused-configs --follow-imports=skip --no-incremental dlcs/dbfox.voxel/backend` 检查8个源码文件通过；`python -m pyflakes dlcs/dbfox.voxel/backend verification/tests/system/test_voxel_dlc.py` 通过。没有新增 `Any` 类型。

另执行完整增量回归：

```powershell
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_voxel_dlc.py -q --tb=short --show-capture=no -k signed_runloop
```

1 passed，1 failed，4.70秒。唯一失败为 `test_signed_runloop_observations_drive_incremental_voxel_edits[incremental]`：首次 `voxel_fill` 的 snapshot Artifact 被 Host `ArtifactRepository._prepare_drafts` 拒绝，观察返回 `TOOL_OUTPUT_CONTRACT_FAILED`。原因是该路径仍按 Run 初始 SessionInput 的 library 引用检查，而调用已经合法绑定新建 world 的 ToolInvocation 引用。领域写入先已提交，因此不得把此问题表述为“没有修改”，不得重放写入、改为新建 Run、删除 Artifact 或绕过 authority 使测试通过。Director 已接收 Scene 和 Voxel 的双能力证据，正单独处理通用 Host 合同修复。本回归保持失败，不加 skip / xfail；上述局部通过命令的排除条件必须连同这一限制报告。完整增量场景包含 stale 拒绝、重新检查、no-op、rename、undo、diff 和历史 export，但本轮不能声称这些步骤已在正式 RunLoop 全部执行。

这轮改动不修改 SQLite canonical 数据、版本/receipt 协议、前端或依赖锁；独立 capability benchmark、创作压力测试、UI/Host 整链验证和最终独立对抗审查仍由 Director 后续安排。

## Workbench 导航与作用域回归

Director 随后在正式前端 Host 可选 `workbench.openArtifact` 合同上接入 `worlds.snapshot`
结果。调用前捕获 Host 实例、workbenchScopeId 和 AbortController；操作及导航使用同一
signal。组件卸载或作用域改变后取消；晚到成功结果不导航、不重放快照动作。旧 Host 缺少
该方法时明确报错，快照写入不开始。fixture 显式移除方法模拟旧 Host，避免继承新 Host
的方法导致错误的兼容测试。

`npx vitest run src/features/dlc/__tests__/dbfoxVoxelFixture.test.ts --maxWorkers=1`：
16 passed，3.69秒；`npm run typecheck:test` 通过。新增卸载、切走再切回的等待中快照用例，
断言原 signal 已取消、晚到结果不导航且 action 只调用一次。测试使用正式 UI、Host primitives
与受控 typed operation 边界；不能替代真实后端/Electron 整链验证。

此前真实 GPU 探针使用内存 typed operation fixture：神社渲染1556个表面实例，隐藏屋顶后624，
隐藏操作不改变持久文档；绘制使占用2424→2425、版本递增到2；560px视口为单列。该探针只证明
Three.js 和工作台交互，不证明生产 Action Run、导出导航或重启恢复。共享 Loader 迟到注册修复
已合入此 worktree（`6f70ab8c`）；Voxel 的独立生产浏览器、12类 bench 与10类压力任务仍待完成。

## 共享 Artifact 权限修复后的完整回归

2026-09-05，Director 将通用修复 `8ba14f69` 合入 Voxel worktree 为 `76091eef`。Artifact 来源由真实、已持久化的 producer Invocation 与显式同 Run DERIVED_FROM 关系证明，不再用过时的初始 SessionInput 引用否定合法增量修改。领域工具、测试断言与 SQL 安全链没有为通过此回归而放宽。

从 worktree 根运行：

```powershell
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_voxel_dlc.py -q --tb=short --show-capture=no
```

结果 **44 passed，20.84秒**，无排除、skip 或 xfail。此前失败的签名生产 RunLoop 增量用例现已完整通过，动态世界 ID 和版本仍仅来自真实 `function_call_output`；stale 拒绝、重新检查、no-op、rename、undo、diff 与历史 export 均已执行。上节43通过/1失败记录保留为修复前证据，不代表当前阻塞。

共享修复在主工作区另通过 Core/System 确定性集合822项（137项按现有marker排除）和工程合同45项。以上不代替 Voxel 独立 capability benchmark、真实生产 Workbench 整链及最终对抗审查，DLC 尚未标记 integrated。

## 严格 schema 修复与 Director 编写的 capability suite

Director 建立了 suite-owned `verification/bench/capabilities/dbfox_voxel` 并注册统一 catalog。复用现有 framework、签名安装和生产 RunLoop；没有新增 Core 或通用执行抽象。模型只从正式 Observation 得到动态世界 ID/version，独立的 scorer 状态不会反馈给模型。

首轮14案例中13通过，整世界替换拒绝案例因 scorer 错把所有 Invocation 的 attempt_count 都要求为1而失败。持久证据显示非法 union tag 在 admission 阶段被正确拒绝，attempt_count=0、无事实、无Artifact且head不变。修正 scorer 区分 rejected=0 与已执行=1，并增加精确拒绝原因检查；未修改产品行为。统一 CLI 随后14/14通过。覆盖12类基础任务、额外再生成滥用拒绝和十类持续创作压力。

首轮压力作品用44次正式工具调用、46 Turns生成并修改64³神社，最终v38、23,386个layer voxel、60chunks、4layers、8palette slots、3regions。十类修改包括新增灯笼、删除脚手架、局部眼睛替色、入口重排、palette参数、歧义不改、stale拒绝、人改阶梯后Agent远端修改、undo/correction、局部refinement。完整suite最大context 1,573字符、最大Observation 1,942 bytes；大型世界2,097,152 cells仍通过有界高层操作。详见 suite README 与报告，不能据脚本模型声称真实LLM创意能力。

另外复现 canonical schema 的类型漏洞：`Literal[1]` 接受布尔true和浮点1.0。将SQLite document_json的schema_version改为这些值、保留原hash后，snapshot仍成功读取，原因是解析归一回整数1。三参数回归修前2失败/1通过；改用已存在的Pydantic `Field(strict=True,ge=1,le=1)` 在唯一文档模型处严格拒绝。没有迁移、兼容层或数据修复，损坏文档必须明确失败并保留原记录。字符串"1"也保留拒绝断言。

本节为Director实现者验证，后续独立验证员仍须审查scorer、真实Host/Electron和故障边界，最后由未实现Voxel的reviewer作对抗审查。

最终联合命令为 `python -m pytest verification/tests/system/test_voxel_dlc.py verification/tests/bench/test_voxel_bench.py -q --tb=short --show-capture=no`：**61 passed，39.45秒**，包含47项后端和14项bench，无排除或xfail。pyflakes通过；mypy检查8个后端源码通过。

严格schema修复后的统一CLI再跑14/14，精确签名包digest与全部持久Invocation证据保存于 [suite报告](../../verification/bench/capabilities/dbfox_voxel/evidence/report.md)。导出的固定v38世界占501,633 bytes，4页，SHA-256 `66f1cb4bf40b9ac5c71f437751d27a8dba58ca6928cc70f4c49393c17f8d887d`。报告JSON和公开snapshot放在suite-owned evidence目录，docs只保留说明；临时SQLite/签名安装目录留在仓库外。

工程合同初跑44通过/1失败：Voxel架构草案缺少规定的文档类型和最后核验页眉。补齐当前页眉后同一集合 **45 passed，3.71秒**，未改合同断言。此前用官方 `npm.cmd run build:visualization-vendor` 消除已知Windows CRLF生成资产偏差；这些非Voxel生成文件不纳入提交。

候选提交前增加 owner `.gitattributes`，仅保护固定frontend/vendor原始字节不受Windows自动CRLF转换；工作树、Git index与checkout filter输出逐字节相同，749,590 bytes及SHA与provenance吻合。自有文件的staged diff check通过；完整diff check发现的21处空白均在固定Three.js生成bundle的GLSL字符串中，保持上游字节，不为格式检查改写已校验vendor。
## 独立验证发现后的回执与导航修正

2026-09-05，独立 Verification 工作者复现了两项缺陷：Host 缺少可选导航方法时仍先创建持久化快照；合法 JSON 的损坏回执可伪造世界、项目、版本、hash 或方块数。Director 复现后者为 **5 failed / 1 passed**。

修复复用 owner 内已有 `_snapshot`/`summary`，在唯一 `_receipt` 读取边界严格验证结果并核对请求身份、base/result 列、固定历史 revision 完整摘要、changed/parent 关系与耐久 chunk delta 数。不会使用后来 head 替代原操作结果，也不会重放几何。导航检查移到 ActionRun 之前。没有新依赖、表、兼容层或 Core 变更；现有 Pixel 的固定 revision 摘要检查提供了项目内参考，未导入其私有实现。

Director 从本树执行 `python -m pytest verification/tests/system/test_voxel_independent.py verification/tests/system/test_voxel_dlc.py -q --tb=short`：**65 passed / 37.22秒**；完整 Voxel 前端 fixture **16 passed / 5.30秒**；8个后端模块 Mypy 通过。这些是修复者验证，独立复验继续进行。

继续增加攻击后，合法正数 `changed_voxel_count=99` 仍可蒙混过关。现在从原 base/result 的实际 delta chunk 字节差核对该数值，复用 `_raw` 的完整性检查，不重新执行几何。35项独立故障测试由 Director 复跑 **35 passed / 12.58秒**，8模块 Mypy 通过。新增真实 executor 的两个 before-commit 测试初稿误将内部 `not_applied` 当成公开结果；独立验证员依据 Runtime 将其映射为 `failed / TOOL_RECONCILIATION_NOT_APPLIED` 的合同修正断言，原版本未变化、未重放断言保留。

## 历史快照与三维选择补齐

独立真实 Electron 首轮发现快照面板只有摘要，3D 无点击选择。补齐后，三维点击通过已固定 vendor 的 Three Raycaster/instanceId 选择一格，拖动保持 Orbit；选区不授予权限。该实现直接复用官方 [Raycaster](https://threejs.org/docs/pages/Raycaster.html)，没有另一套碰撞引擎。

完整成果面板只从 Host `context.representations` 读取固定 `manifest/chunks`，检验表示类型、操作、版本和 fingerprint，分页完成后才显示。当前世界与历史快照共用 DLC 内只读 chunk 投影，历史读取不调用当前世界 operation。新增导出文件用标准 Blob/下载链接，卸载、停用时按 [URL.revokeObjectURL](https://developer.mozilla.org/en-US/docs/Web/API/URL/revokeObjectURL_static) 释放 URL；无共享 SDK、后端 operation、锁文件或 Core 变化。

独立验证员报告同一 Runtime 当前 v9 与历史 v8 同时存在；历史3D显示1135表面块，隐藏Base后显示0但JSON下载仍包含全部图层。实际 Electron DownloadItem 完成34,256 bytes（验证层指定保存路径），磁盘逐chunk核对与剩余生命周期验证继续进行。新增8项固定表示/错误页/取消/全层导出测试使前端达到24项通过，typecheck通过。上述阶段结果不替代完整独立终审。


## 独立验收后的样式与监听器修复

独立检查发现studio.css未满足Host设计合同，以及OrbitControls注册/释放键盘事件时DOM root不同。Director将选择器限制在真实dbfox-voxel根内，字体/标签颜色采用既有令牌，调色板颜色作为领域数据直接传给style；移除两处!important。未修改设计合同。

Viewport先挂载canvas再连接OrbitControls，React layout cleanup在DOM移除前断开。独立普通卸载测试由失败转为通过，但按住Control卸载仍有keyup残留。固定r185与当前上游dev的[OrbitControls源码](https://github.com/mrdoob/three.js/blob/r185/examples/jsm/controls/OrbitControls.js)均未在disconnect移除动态Control keyup；没有对应的公开清理API。

采用固定Three 0.185.1 tarball的最小构建期源码补丁，仅在disconnect移除keyup并重置Control状态。没有运行时私有字段wrapper、伪造用户keyup或新事件代理。复现命令为desktop目录下 `node scripts/build-voxel-vendor.mjs`；脚本先验证原始sha512，再断言补丁唯一位置，使用固定esbuild0.28.2构建。原始/补丁源码hash、产物hash和补丁负责人/退出条件维护在vendor/provenance.json。升级到修复上游后，删除补丁并要求两个独立原生监听器用例通过。MIT许可证原样保留，未修改共享锁文件。

新产物749587bytes，SHA256为4019cf00891df54884c4d14981c787f36e47b125590241402a5c9b1759351929。原两个独立断言未改：26项frontend通过3.60秒，完整lint为0errors/5条既有warnings。真实Electron重签与Control-held清理复验仍由独立Verifier完成后记录；本节不代替其结论。

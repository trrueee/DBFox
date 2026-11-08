# Game DLC：规范文档、物理步进与创作工作台

> 文档类型：架构说明
>
> 状态：已接受
>
> 最后核验：2026-09-06
>
> 适用范围：`dbfox.game` schema 1；Game Lead 的实施合同。五项角色按阶段履行，当前为作者架构阶段，不是独立 Verification 或 Adversarial Review。

Game 拥有可编辑的二维小型游戏。第一份完整示例是狐狸通过键盘躲避史莱姆，在游戏时间 60 秒后获胜；Agent 可以创建、试玩、读日志、局部调整后再试玩。正式试玩必须经过原 Tool，不能用静态截图或另一套 Python 模拟器代替。本页取代 实现前调查 (source file: `D:/Project/DBFox-worktrees/creative-game/docs/architecture/game-dlc-preflight.md`) 中尚未冻结的选择，后者保留调查出处。实现与实际验证在 [质量页](game-evidence.md) 持续更新。

Copy from creative/game checkpoint f54950ca; unmerged WIP, not independent acceptance. Code and remaining risks: [author handoff](game-author-handoff.md).

## 1. 成熟引擎与最小适配

固定 **Phaser 4.2.1 / Arcade Physics / Canvas renderer**。官方 npm registry 的精确包为 MIT，依赖 eventemitter3；不使用本机浮动镜像的 4.0.0 或标为 4.1.0 的在线 API 来推断行为。调查比较了固定 3.90.0 与 4.2.1 World 源码；最终 4.2.1 的真实浏览器探针已验证 Canvas、HEADLESS 和 reset 使用相同 physics 结果。它的公开 `World.singleStep()` 调 `update(0, frameTimeMS)` 再 `postUpdate()`，包含 Body.preUpdate、速度/碰撞和 GameObject 回写，不能用单独 `World.step()` 替换。

使用上游 ESM source entry 构建 DLC 离线产物，按上游 webpack 的 `typeof CANVAS_RENDERER/WEBGL_RENDERER/WEBGL_DEBUG/FEATURE_SOUND` 常量选择 Canvas。Physics export 只保留上游 Arcade 模块，排除未使用的 Matter；无手写物理、三角剖分、渲染器或脚本解释器。DLC 自有 build/lock/vendor provenance 保留精确源、许可证、hash 与修改，不能修改共享 node_modules junction 或锁。

4.2.1 原 `Core/VisibilityHandler.js` 的实际缺陷：每创建一个 Game，永久增加一个 document visibilitychange listener，并覆盖 window.onblur/onfocus；销毁不会清理。原包四次创建/销毁后监听净增 4，Canvas 虽已移除仍泄漏闭包。采用 hash 固定的 build-time 最小源修复：用独立 addEventListener 注册 blur/focus，并在 Game DESTROY 时对称解绑三个 listener；不改物理语义，不在产品中拦截全局 EventTarget。固定源 SHA-256 为 `5a520230ec2af86e779655102ea3b7217a989a5cd5cdd06bc3a644fa9b7d1d93`，源变化必须停止构建并重新审阅。原与修复后的真实探针均保留。后续上游正式修复时重新评估并删除补丁。

Phaser mouse 的 wheel 清理缺陷另有 [上游 issue 7340](https://github.com/phaserjs/phaser/issues/7340)。游戏使用公开 `input:{keyboard:false,mouse:false,touch:false,gamepad:false}`，Workbench 自己将明确的键盘/指针输入转为领域 action，监听随视图和 activation 对称清理。输入选择、暂停、focus 与 DOM detach 不写回游戏文档。autoFocus=false，不争抢用户窗口焦点。

依据：[官方 4.2.1 发布](https://phaser.io/download/release/v4.2.1)、[固定 World](https://github.com/phaserjs/phaser/blob/v4.2.1/src/physics/arcade/World.js)、[Game 生命周期](https://github.com/phaserjs/phaser/blob/v4.2.1/src/core/Game.js)、[VisibilityHandler](https://github.com/phaserjs/phaser/blob/v4.2.1/src/core/VisibilityHandler.js)、[上游 MIT](https://github.com/phaserjs/phaser/blob/v4.2.1/LICENSE.md)。选择成本是 fixed source build 和小型数据→Phaser 实例适配；没有新 Host seam、运行时 npm、网络资源或原生模块。

## 2. 规范模型

`GameProject` 只保存数据：`id/schema_version=1/title/engine='phaser-arcade-4.2.1'/tick_hz=60/initial_scene_id/scenes/entities/behaviors/rules/variables/assets`。版本、Project 归属、删除状态、parent revision 与 hash 在 revision envelope，不在 Phaser 对象中。所有 id 是由 owner 创建的稳定 UUID；同文档所有对象身份唯一，删除后不能借用旧 id 创造另一种对象。

- Scene：`id/name/width/height/background/gravity_x/gravity_y`。Game 有序 scenes；实体显式 scene_id。层级是 scene → entity → components；不引入无定义的多重 parent transform。
- Entity：`id/scene_id/name/enabled/tags/components`。Transform 是必需的唯一组件，其余 kind 每实体最多一个。禁用实体可作为 spawn 模板，不参与初始运行。
- Components：稳定 `id` 与判别 `kind`。`transform` 包含中心 x/y、width/height、angle；`visual` 包含 builtin shape 或 asset_id、color、opacity、depth；`body` 包含 dynamic/static、rectangle/circle、初始 vx/vy、drag、bounce、world bounds、solid；`health` 包含 initial/max。Arcade body 是轴对齐矩形或圆；angle 仅作用于视觉，不假装支持旋转多边形碰撞。
- Behavior：稳定 id、entity_id、enabled 与严格判别参数。支持 player_control（规范 up/down/left/right action 和 speed）、seek（显式目标 entity 与 speed）、patrol（有界 waypoints/speed/loop）、wander（speed/turn_interval_ticks）、spawn（同 scene 的模板 entity、interval_ticks/count/max_alive/region）、lifetime（ticks）。控制速度只通过 Arcade body API；不复制物理积分。
- Variable：稳定 id、唯一 name、type=int/float/bool、initial。初值是作品事实；运行值是派生内存。数值严格有限，不接受 bool 冒充整数或显式 null。
- Rule：稳定 id、scene_id、name、enabled、trigger 与有序 actions。触发器为 elapsed_tick、overlap（left/right tag，enter/stay）、variable_compare、health_compare；action 支持 finish(win/lose)、variable_set/add、damage、despawn、spawn、scene_change。明确 entity id 或 overlap 的 left/right 作为目标，不接受任意表达式、递归条件树、JS/Lua、路径或 URL。
- Asset：稳定 id/name/width/height/format=rgba8/content_hash，可选经过真实公开 Representation 读取产生的 immutable source provenance。RGBA 为 top-left；BLOB 去重后只由 owner 保存。内置 rect/ellipse/fox/slime 是 renderer 的固定图形词汇；任意素材使用 RGBA asset，不能把代码伪装成 asset。

编辑只接受 typed 局部 operation。批次中 create 可以声明短 local ref；后续操作用 `{ref}`，其他定位用 `{id}`，不可引用未来创建。component_modify/behavior_modify/rule_modify 只更新指定稳定对象，不能提供 whole GameProject replacement。删除有关联的对象须在同批次显式解除/改指向，最终图不闭合则整个批次失败。删除 entity 可显式 cascade 自己的组件/行为；其他实体或规则的外部引用不会悄悄改变。

## 3. 二十五项权威边界

| 问题 | 冻结决定 |
| --- | --- |
| 1 Resource | 每 Project 一个 `dbfox.game.library` bootstrap Resource；每 GameProject 一个 `dbfox.game.project` Resource，id=game id/version=game revision。library 版本反映 inventory 变化，不能来自 UI tab。 |
| 2 Object | scene/entity/component/behavior/rule/variable/asset 都是同一游戏中的稳定 Object；scene 不等于其他 DLC 的 SceneDocument。 |
| 3 Selection | entity/component、多个 entity 或 scene 的选择是 Object/locator；不产生或扩大 Resource authority。 |
| 4 canonical document | 第 2 节 GameProject；人/Agent 操作同一份内容，没有另一份 Agent JSON 或可写 Phaser 镜像。 |
| 5 SQLite durable facts | library inventory/generation、game ownership/head/tombstone、append-only revisions、typed mutation receipts、不可变资产 BLOB 和 playtest reports。写入 BEGIN IMMEDIATE/CAS 同事务完成。 |
| 6 view state | 选区、zoom、pan、inspect panel、草稿、键盘、play/pause、临时实体/变量、Phaser/GPU/RAF handles。reset 重建运行实例，不产生 revision。 |
| 7 Agent context | Resource 版本、scene/entity 数量、入口、简要规则和最近报告摘要；显式 inspect 分页读对象和日志。 |
| 8 不进 context | 全量游戏、RGBA/base64、每帧轨迹、全部输入日志、lease/claim、内部路径与秘密。 |
| 9 version | 有效编辑/删除/undo 追加新 revision；noop/stale/invalid/playtest/export 不推进 game head。library inventory 单独同事务变化。 |
| 10 stale ToolInvocation | 真实冻结 Invocation resource version 与 expected_version 双检查；正常执行前及提交时核对 live head。历史 resolver 仅供原调用恢复，不授权新写。 |
| 11 Human/Agent 冲突 | 公共同一个 typed apply。UI 保留草稿/拖动预览并提示重读；不凭旧 expected_version 覆盖，不自动 replay。 |
| 12 operation log | receipts 按 project/game/actor human 或 agent/request identity 分域，保存规范输入 hash、base/result、changed 与精确产物。noop 只能领取自身 receipt，不能冒领别人的 revision。 |
| 13 undo | 指定历史内容及删除状态复制为新 revision；hash 不唯一，可恢复 tombstone 和 undo-of-undo。 |
| 14 diff | 固定两个 revision，按稳定对象 identity 比较字段/增删并分页，完整游戏不塞 Tool Observation。 |
| 15 crash | 未提交回滚；已提交查 exact receipt 重建同一 Artifact drafts。reconcile 只读，不重写、不重跑游戏；缺证据返回 unknown。损坏 schema/hash/identity/accounting fail-closed。 |
| 16 deactivate | 中止 claim/轮询/RAF/输入/observer，销毁所有 Phaser 实例和派生纹理；旧 epoch 的晚回调不能动新 activation。耐久作品和报告保留。 |
| 17 Project 删除 | 当前 Host 无公开 project-delete callback；不私查 Core metadata，不承诺自动清理。显式 game delete 写 tombstone；历史表示保留。 |
| 18 大作品 | 第 5 节分别约束 canonical、运行实体、collision/action 工作量、tick、报告与 owner 历史；列表分页、viewport 只派生显示，不能悄悄丢实体。 |
| 19 bounded results | Tool 明确 ObservationProjection：常规 facts ≤8KiB、显式页 ≤16KiB。playtest 摘要含精确版本/seed/ticks/终态/关键事件和 truncation，详细报告分页。 |
| 20 approval | 本地可逆操作沿用 Runtime 政策；asset 只经正式文件选择或授权公开 Representation。没有外部发布、执行脚本或新增审批状态机。 |
| 21 retry | 只读 inspect 可重读；写入/试玩未知结果不自动重试。相同身份同输入只返回原 receipt，不重新生成随机结果。 |
| 22 非幂等 | 不同 request/invocation 的 create/apply/undo/delete 是新动作；playtest 原输入/seed/source/proof 唯一绑定一个报告，不接受旧 id 搭配新输入。 |
| 23 Artifact | `dbfox.game.project-revision`、`dbfox.game.playtest-report` 由正式 Tool/ActionRun 返回。refs 是真实冻结 producer scope；创建结果的新 game id/version 在结果 facts，不能伪造新 Resource refs。 |
| 24 Representation | 不可变文档/对象/资产字节/报告事件与终态分页 JSON；导出同一固定 revision。Artifact locator 决定 project/game/version/hash，参数不可覆盖。 |
| 25 Composition | 其他 DLC 从已授权的 Artifact Representation 读取。不导入 Game store；普通 Pixel→Game Agent 编排已足够时不创建 Composition。只有新联合事实需求另行审议。 |

## 4. 唯一执行步骤与派生请求

每个运行固定 document revision、source hash、engine version、seed、最大 ticks 和按 tick 的 action 输入。创建 Phaser Game 后等待 Scene.ready，再停止其自动 loop；场景以 `customUpdate=true/fixedStep=true/fps=60/timeScale=1` 创建。一次 `advance(input)` 的顺序固定为：

1. 应用当前 tick 的 action 更新，保持未变 action；处理启用的 controller/seek/patrol/wander 行为，使用 Phaser Vector2/RandomDataGenerator。
2. 调用 **一次 `World.singleStep()`**，由 Arcade 完成 pre/update/collision/post。collision callback 只记录有界候选，不在碰撞遍历中增删实体。
3. 逻辑 tick 加一，按 canonical rule 顺序处理触发器；overlap 对稳定 runtime identity 排序。enter 与上一 tick pair 集比较，stay 每 tick 一次。所有触发条件使用本 tick 派生状态。
4. 顺序执行有界 actions，deferred spawn/despawn/scene change 在遍历后生效。首个 finish 决定终态，后续规则不覆盖它；计时规则用 tick/60，3600 tick=60 秒。
5. 输出有界事件并在需要时由同一 Phaser Canvas renderer 绘制。Workbench `Game.step` 与 playtest `Game.headlessStep` 进入同一个 scene update/advance；区别只有是否渲染。

所有 Phaser Clock/Tween 不承担游戏规则时间，墙钟只调度真实用户播放速度与超时。pause 不推进 tick，reset 使用原 seed/initial state 重建。playtest 加速执行固定步数，分批让出浏览器事件循环并检查 abort/deadline；不得以“已等待 60 秒”作为获胜。跨平台逐位确定性不作承诺，报告记录固定引擎与实际终态，同平台同 source/input/seed 应重现。

运行 identity 和规则优先级也是合同：原始实体使用 canonical UUID；spawned entity 使用 `template_uuid:spawn_ordinal`，ordinal 从 1 开始，按实际 spawn action 执行顺序全 run 单调增加。reset 归零，scene change 不归零；模板 UUID 单独保留。canonical 不接受这种 runtime id。相同 revision/seed/input 的 reset 会生成相同 runtime identities。一个实体最多一个 enabled player_control/seek/patrol/wander；其他组合在提交前拒绝。

elapsed_tick 使用 scene-local tick 精确相等，只在指定 tick 触发一次。variable_compare 和 health_compare 使用 false→true 边沿，场景进入时前态为 false，因此进入后首次条件为真会在第 1 tick 触发；条件持续为真不重复触发。所有规则条件在本 tick actions 之前统一取样，前一条 action 导致的变量/健康变化从下一 tick 触发条件。按 canonical rule 顺序和每条 actions 顺序执行：首个 finish 立即确定终态并停止后续 actions，取消本 tick 待执行 scene change；没有 finish 时，只执行首个 scene_change，其余记录 ignored。切场景重建目标 scene 的 canonical initial entities，重置 scene-local tick 和触发器前态，保留 run-global tick、变量和 spawn ordinal。

正式 `playtest` Tool 创建一个 owner-local 瞬时请求，activation executor 通过既有 machine typed operations attach/next/complete/detach 领取。绑定 owner/package digest、registration counter、epoch/lease、invocation、game/revision/hash、request hash、claim 与 deadline。没有 durable job、通用队列或每次 edit 新 Run。complete accepted 仅是交接；原 Tool 仍需核对取消、deadline、epoch、live head，再同事务保存报告/receipt。另一个游戏修改不作废已领取 source。整个 Renderer hidden/离线时明确 unavailable/timeout，恢复只接未来显式请求。

以公开 `game.destroy(true,false)` 请求销毁，停止自动 loop 后用公开 `game.headlessStep(0,0)` 完成 pending destroy；不调用私有 runDestroy。生成的 Canvas/纹理、所有自身 DOM 事件和临时状态全部释放；不会以全局 noReturn=true 破坏未来实例。

## 5. 有界合同与接口形状

首版上限：每 Project 64 active games、128 retained game identities（含 tombstone）；每 game 16 scenes、2048 canonical entities、每 scene 512 entities（含禁用模板）、每 entity 4 个组件；behaviors 2048、rules 256、variables 128、assets 64。单 asset RGBA ≤1MiB/512×512，unique asset raw 总计≤4MiB；canonical JSON≤2MiB。scene 维度64–4096；transform 坐标±8192、尺寸1–1024、angle±360。速度/重力/drag 有限并限制量级，运行数值溢出拒绝，不假装支持连续碰撞检测。

tombstone 仍以明确 deleted 名称进入有界 discovery，允许 inspect/undo 原身份；其他编辑拒绝。library inventory 包含每个 game 的 head version，任何 canonical head 变化均在同事务推进 library version，历史 library snapshot 由 revision 的 library_version 精确重建。普通 game edit 只 fence 该 game，不因其他 game 修改失败。创建操作才 fence library version。

一个 apply 最多64 typed operations、批量 entity create/transform/delete 最多128对象，一次 action 最多64个唯一 creation refs（只引用本 action 中较早创建对象），普通 input≤256KiB；native asset upload 单独 typed operation≤1.5MiB。每条字符串有明确长度，未知字段拒绝、bool 不作 int。Host 的 native strict function schema 将可选 nullable 字段也列入 required，因此仅有明确 `default=None` 的字段接受 null 并归一为省略（例如 visual.asset_id、creation ref、局部修改的可选参数）；必填字段、数值、boolean 及未知字段的 null 仍拒绝。Canonical 编码不写 null；读取时逐字节核验规范编码与 hash，不能用此归一掩盖存储损坏。模型不能指定 owner/project 文件路径。每页≤50对象/32KiB；Tool 检视使用≤16KiB的更小投影；asset_bytes offset 是原 byte、limit≤16384，并固定 revision 与该 revision 内 asset_id。

单次 playtest≤7200 ticks，输入事件≤1024（tick 从0开始、同 tick/entity 不重复，action 为 up/down/left/right）；seed 严格 int 0..2^31−1。运行 active entities≤512（包含 spawned），每 tick collision candidates≤4096、actions≤4096，总 actions≤1,000,000。超过预算显式失败，不偷偷截断模拟。日志最多1024事件、末态最多512实体、整体报告≤1MiB；日志截断须明确计数且不丢终态/失败原因。请求 snapshot JSON≤8MiB，owner 历史/资产/receipts/report payload 总计≤256MiB，SQLite页/WAL有额外开销；满额拒绝新 payload，保留既有读取，不自动清历史。

公开 project operations 族：games.list/create/get/head/apply/undo/delete/revisions/diff/export/playtest、assets.upload；machine 操作限定 playtest executor lease。写 input 必须 request_id + observed expected_version（create 用 expected_library_version），mutation 输出 game summary、新 library version、changed、changed_ids、created_refs。playtest/export 是 ActionRun，返回 session_id/run_id/artifact_ids/outcome；普通编辑直接到同一 store。实际模型生成 schema 后取代人工字段列举，Workbench 只能按同一个注册 schema 调用。

Tools 至少含 game_create、game_inspect、game_modify、scene_create、entity_create/delete、component_add/modify、behavior_create、rule_create、variable_create、playtest，补 game_delete/undo/diff/export 与 asset_import。Tool 不接受 Project id；Resource selector 只选择 Host 当前冻结且属于 owner 的 game/library。inspect 提供 generation/version 和稳定 id，Agent 下一次调用必须使用所见版本。

## 6. 完整工作台与门禁

工作台包含场景/实体/组件树、实际 Phaser viewport、选择/多选/drag、component inspector、行为/规则/变量/素材编辑、play/pause/reset/step、时间与 event log、历史/undo、正式 Agent handoff。创建后的狐狸游戏可以完全由 Human 继续改。viewport 拖动在指针松开时一次有界 transform 操作，busy 防重入；版本变化保留本地提案并显式重读，不按每帧发送写入。树叶重开、Control-held、窗口隐藏/失焦、DOM detach 与卸载均需真实检查。

必须保留 domain/persistence/CAS/runtime/lifecycle/authority/frontend 测试、正式 RunLoop 的12类 capability benchmark、至少10类连续创作修改和真实示例。author browser probe、memory transport 或伪 report 不代替已安装签名包/生产 Electron 验证。五个角色当前按 Director 调度顺序履行，任何作者测试不算独立红队；未参与实现者的 Verification/Adversarial 与 confirmed high severity 修复完成前，DLC completion=false。

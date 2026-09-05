# Game DLC 实现前合同调查

> 文档类型：架构提案
>
> 状态：草案
>
> 最后核验：2026-09-05
>
> 适用范围：dbfox.game 的独立 Lead / Domain Architect 启动材料；Director 调查，不替代独立架构阶段或实现门禁。

目标保持为真正可编辑的小型游戏工作台：用户与 Agent 创建狐狸躲避史莱姆、存活 60 秒获胜的游戏，执行 playtest、观察结果、修改规则后再验证。数百实体、十类增量修改和实际运行不能被静态预览替代。

## 复用调查与尚未冻结的选择

项目已有 SQLite 事务、typed operations、Resource resolver、Tool Runtime、Artifact / JSON Representation、Host Tree 与 Dock。Scene 提供可编辑层级和固定导出；Pixel 提供版本化精灵及分页 RGBA 表示；Shader 已有独立于 Dock 的 activation 计算请求方案，但尚未完成独立生产验收。研究这些边界，不能导入其私有 store、renderer 或 compute 模块。

Phaser Arcade 提供成熟的物理更新、碰撞、空间索引和固定时间步，优先调查其作为唯一游戏执行内核；canonical 文档只包含类型明确的数据组件和行为，不存 Phaser 对象或任意 JavaScript。已读固定 [3.90.0 World 源码](https://github.com/phaserjs/phaser/blob/v3.90.0/src/physics/arcade/World.js)：`update` 包含 body preUpdate，`step` 直接推进 body 并处理碰撞，两者不是可以任意混用的同义接口。应按采用版本核验完整 pre/update/post 顺序，Workbench 与 playtest 必须调用同一条步骤函数。

2026-09-05 显式查询官方 npm registry 的 latest 为 **4.2.1**，而本机默认镜像返回 **4.0.0**，在线 API 页标为 **4.1.0**。不能用镜像或浮动文档推断固定版本能力。官方元数据：4.2.1 解包 112,530,289 bytes，依赖 eventemitter3；3.90.0 解包 146,876,558 bytes。解包总量不等于最终 vendor 大小，后续必须在 DLC 本地锁定依赖、只打包所需运行产物和许可证，验证单文件20MiB、归档50MiB和文件数合同；不能整包复制 npm 源码。[4.2.1 固定 World 源码](https://github.com/phaserjs/phaser/blob/v4.2.1/src/physics/arcade/World.js)、[固定 MIT 许可证](https://github.com/phaserjs/phaser/blob/v4.2.1/LICENSE.md)。

尚未决定采用 3.x 或 4.x，也未安装新依赖。需核验最终固定版本的安全公告、稳定 API、包体、严格 CSP、Canvas/WebGL 以及销毁行为。标准 Canvas 只提供绘制，不提供游戏物理；手写第二套 Python 碰撞/计时器来评分会制造两套游戏语义。原生 pygame/pymunk 和运行时 Node 子进程不符合当前纯 Python DLC 分发边界，不作为默认方案。

## 供独立 Architect 冻结的 25 项回答

| 边界 | 提案与待核验点 |
| --- | --- |
| Resource | Project 内的 Game Library 用于发现/创建；每个独立 GameProject 为带版本的 Resource。不要从当前 UI tab 推导授权。 |
| Object | scene、entity、component、behavior、rule、variable、asset 为 GameProject 内稳定对象。Game scene 与 dbfox.scene 的三维文档不是同一个实体。 |
| Selection | 选中 entity/component 与位置范围属于对象引用/locator，不扩展 Resource 权限。 |
| canonical | GameProject schema1：有序 scenes、entities、严格组件、声明式行为/规则、初始变量、资产内容及固定来源。每个字段只有一处可写事实。 |
| durable facts | 项目归属、head、不可变 revisions、parent、规范输入绑定的 receipt、固定 playtest 报告与导入素材。写入使用 owner SQLite 单事务。 |
| view state | camera、选中对象、未保存草稿、正在播放的临时实体、键盘状态、GPU/Phaser handles。暂停/重置临时运行不偷偷修改原作品。 |
| Agent context | 精简场景/实体数量、规则概况、版本、最近 playtest 的终态与失败摘要；显式分页读取组件和日志。 |
| 不进入 context | 全量实体数组、每帧轨迹、纹理/音频字节、运行请求 claim、用户凭据或内部文件路径。 |
| version | 局部编辑原子递增；no-op 不增；保存与 playtest 各自区分文档变更和派生结果。不得回退 head。 |
| stale invocation | 已冻结 Resource version 与 expected_version 一致，事务内再次核验。读取结果不能暗中替换调用者版本。 |
| Human/Agent 冲突 | UI 与 Agent 调同一个 operation；冲突保留草稿，显式重读后再提交新的请求，不自动重发。 |
| operation log | 请求按 human/Tool 身份分域，规范输入 hash、base/result、影响对象与唯一结果关联同事务保存。参考 Voxel 新红队：no-op 不可冒领别的 producer revision。 |
| undo | 恢复指定历史内容形成新的 revision，不回拨版本号；清理被删除对象的引用或拒绝不完整修改。 |
| diff | 按稳定 scene/entity/component/behavior/rule/variable id 比较两个固定版本，结果分页。 |
| crash | 提交前检查取消并回滚；提交后只查精确 receipt，未知结果不自动重放 playtest 或写入。历史数据损坏拒绝，不能自动建空游戏。 |
| deactivate | 中止临时计算、撤销 renderer epoch、释放输入/RAF/Phaser实例/纹理/observer；保留文档与已提交报告。Control-held 与 DOM-detachment 必须实测。 |
| Project 删除 | 当前无公开 project-delete callback；不能声称自动清除私有数据。显式删除作品采用 tombstone，历史 Artifact 可读。 |
| 大作品 | 至少数百实体。预算需同时约束文档字节、实体/组件数、动态 spawn、ticks、输入序列、碰撞工作量、事件与导出；准确上限由实测后冻结，不以UI截断冒充支持。 |
| bounded results | Tool 显式 observation projection；playtest 返回完成/失败/取消、已执行ticks、seed、固定版本与有界关键事件；完整报告可分页读。 |
| approval | 本地可逆创作和有界游戏预览沿用 Runtime 政策。资产只消费授权公开表示或正式文件选择；不接受脚本、网络URL或任意文件路径。 |
| retry | 只读 inspect 可重读。写入/playtest 不自动重试；新运行需新 invocation，取消或generation变化后旧结果不能提交。 |
| 非幂等 | 同一身份同一输入只返回原 receipt；不同输入重用身份拒绝。playtest 重复绑定原报告，不能随机重跑后覆盖。 |
| Artifact | 固定 GameProject revision、playtest 报告与导出；正式 Tool/ActionRun 产出，显式 producer/source lineage。Canvas预览不是耐久证据。 |
| Representation | Game 文档/报告为分页 JSON；导入 Pixel 时只读受授权的固定 sprite 表示。保存导入内容与来源指纹，后续编辑是 Game 自有资产，不双写 Pixel。 |
| Composition | 普通 Agent 编排 Pixel→Game 足够时不新增 Composition DLC；只有真实联合状态和协议需求出现后另行提案。 |

## 先证明的执行边界

Playtest 与可玩预览必须使用同一固定内核、seed、tick 顺序和规则语义。记录逻辑ticks，不能用壁钟延迟计算“已存活60秒”；同时真实用户播放的速度由实际时间驱动。游戏变量的初值属于文档，模拟中的值属于临时运行。输入可来自键盘或有界的按tick序列，不能向模型开放代码执行器。

公开 SDK 的 Tool context 已有 `is_cancelled`、冻结资源与 JSON representation 读取；operation scope 支持 owner-bound machine 调用。可调查 activation 时启动的只读派生执行器，关闭 Dock 后仍可处理正式 Tool 创建的一次请求；不得据 Phaser 的 HEADLESS 名称假设 Python Sidecar 能运行浏览器库。整个 renderer 不可用时必须有明确超时/取消结果，不新增耐久job队列、通用调度器或自动重试。

这条路径必须首先通过最终签名包和生产 Electron：Dock 关闭运行、暂停/重置与相同输入重现、过期结果拒绝、卸载清理和数百实体。未完成这些证据前，Backend 存了 GameProject 与 browser fixture 通过均不能作为完整 Game DLC 交付。

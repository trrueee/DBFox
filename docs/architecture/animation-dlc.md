# Animation DLC

> 文档类型：架构设计
>
> 状态：当前
>
> 最后核验：2026-09-07
>
> 适用范围：`dbfox.animation` 作者候选；独立验收由 Director 调度。

AnimationDocument 是唯一可写事实，包含 Targets、Tracks、Keyframes、Curves、Clips、Markers、Timing。工具和 Workbench 共用 owner SQLite 事务；Three 对象、插值器、Mixer、播放位置、选择和画布均是可丢弃的投影。Core/SDK 未修改。

## 调查与复用决定

复用了 Host Tool Runtime、冻结 Resource、Artifact/Representation、ActionRun、Workbench 导航和标准库 SQLite。调查了现有 Scene 的公开表示与包构建模式，没有导入 Scene 私有代码。模型及时间约束来自本领域；曲线求值使用固定 Three 0.185.1 的 `LinearInterpolant`、`DiscreteInterpolant`、`BezierInterpolant`，播放使用 `AnimationMixer`。官方依据：[AnimationMixer](https://threejs.org/docs/pages/AnimationMixer.html)、[KeyframeTrack](https://threejs.org/docs/pages/KeyframeTrack.html)、[BezierInterpolant](https://threejs.org/docs/pages/BezierInterpolant.html)。

Three 默认 Float32 时间会削弱长时间线精度，派生 track 显式使用 Float64 时间和值。每个 track 的派生 interpolant 工厂只负责二分选择当前区间，并委托 Three 的三种原生插值器；没有自写曲线数学、第二文档或双向同步。该单向边界用于每个关键帧区间不同 easing 的真实变化轴。删除 Animation 前端即可删除它，不被其他 owner 依赖。

Three clone/toJSON 丢失 Bézier 控制点，不能作耐久保存。规范 JSON 导出完整保存曲线；reload 重建投影。原生 LoopOnce 到末尾会暂停 action；每次显式 seek 前恢复 action.paused=false，mixer.timeScale=1。UI 暂停停止调度，不设置 Mixer timeScale=0。预研细节见 [preflight](animation-dlc-preflight.md)。

依赖仅新增本 DLC 的 `three@0.185.1`（MIT）和构建时 `esbuild@0.28.2`；package-lock 由 npm 生成。浏览器仅加载自带 bundle，无 CDN、远程字体、模型服务或运行时 npm。`licenses/provenance.json` 保存锁内 integrity、bundle SHA256/字节数、来源与构建命令。供应链风险是维护固定第三方版本；升级必须重跑数值/seek/clip/混合 easing 与浏览器测试。bundle 上限 512 KiB。

## 时间与曲线合同

时间是严格整数毫秒，闭区间 `[0,duration]`，时长 1..3,600,000 ms。帧率为 24/25/30/48/50/60/120，帧键盘步进按帧索引换算整数毫秒，避免连续累加四舍五入误差。播放速率 0.1..4，正向播放；反向仅显式 seek，不承诺反向事件播放。

Track 绑定一个稳定 target ID 及白名单 `position|rotation|scale` 的 x/y/z 标量。旋转为局部 Euler XYZ 弧度；不能传任意 Three PropertyBinding 字符串。一个 target 的同一属性最多一个 track。值有限且在 ±1,000,000。Track 可以改名、重绑属性或启停，完整文档验证拒绝重复绑定和悬空引用。

Keyframe ID 稳定；同轨同 tick 不允许两帧，批量移动同时验证，因此可以原子交换两个时间。缺少 curve_id 表示 linear。每个 key 的 curve_id 作用于它到下一帧的区间。Curve 为 linear/hold/bezier，控制点以该区间起终点归一化，0≤x1≤x2≤1，-4≤y1,y2≤4。允许过冲；端点同值时归一化 easing 保持常值。共享 Curve 修改影响所有引用；不会复制成第二份事实。最后一帧后的值夹持最后值。

Clip 是 track_ids 与 `[start,end]` 的非破坏播放窗口，start<end；trim 保留所有 key 和曲线，不补造端点。选择 Clip 时仍以完整原轨在绝对 tick 求值，因此裁剪前后同 tick 数值一致。Marker 在播放跨越 `(previous,next]` 时提示，seek 不提示；loop 返回起点时允许起点和终点各一次，单次调度最多列出每个 marker 一次并报告 loops 数。后台不可见/停用/卸载停止播放，渲染帧延迟上限 250 ms，不补放后台事件。

## 25 项权威问题

| 问题 | 当前合同 |
| --- | --- |
| Resource | Project Animation Library 与独立 Animation document resource，分别 `dbfox.animation.library`、`dbfox.animation.document` |
| Object | target/track/key/curve/clip/marker 都是 document 内稳定对象，不自行获得授权 |
| Selection | 前端选择，仅用于 WorkbenchReference 的 object/locator；authority 始终是文档 |
| Canonical | 严格 Pydantic Document；collection 按 ID 排序；JSON 有限值、排序字段、无多余字段 |
| Durable | owner data_path/animation.sqlite3 的 documents/revisions/entity_ids/receipts；SQLite FULL、事务 CAS |
| View | 播放位置、片段选择、窗口、轨道页、当前对象、表单和拖拽草稿；不进文档或模型上下文 |
| Context included | 文档 ID、版本、标题、有界计数与 inspect 指引，总内容≤4000字符 |
| Context excluded | 全量 key/曲线数组、Three cache、Canvas、DOM、完整导出 |
| Version | 单文档单调整数版本；固定 canonical SHA256，修改/no-op 结果明确 |
| Stale | expected_version 必须等于 live head；Agent 同时匹配 frozen scope.version；不自动重放 |
| Human conflict | UI/Agent 同事务入口，先提交者胜；失败显示错误并保留草稿，重新读取后重新判断 |
| Op log | 每个 immutable revision 保存规范操作输入；receipt 绑定 project/action/input 的 SHA256 |
| Undo | 复制既有版本的文档内容为新 revision，保留全部历史，恢复原稳定 ID |
| Diff | 按对象 ID 列 added/removed/modified 与字段名，分页≤100 |
| Crash | commit 前异常/cancel 回滚；commit 后丢响应由原 invocation receipt reconcile，不产生第二次写 |
| Deactivate | Host 移除所有 contribution；前端 abort 请求、取消 RAF、释放 Mixer/root/URL/样式；owner 数据保留 |
| Project delete | 本域 `delete_project` 原子删除文档/历史/receipt/tombstone，已单测；当前 public BackendExtensionHost 无项目删除回调，未伪造自动清理或访问 Core DB。此 Host 接入缺口需 Director 处理，不能宣称项目删除全链完成 |
| Large | 500 tracks、20,000 keys/curves、1000 targets/clips/markers、每 Clip≤128 tracks、16MiB文档；单增量 key/ID批≤256 |
| Context bounds | inspect≤100实体且约120KB owner页；provider projection≤24KB并返回精确 next_offset/has_more；场景绑定每页100且最多10,000对象 |
| Approval | 原 Host policy/Runtime；本地 owner edits warning、requires_approval=false；不访问外部写服务 |
| Retry | 读 retry_safe；写 retryable=false/reconcile；取消/断线未知结果不自动生成新 invocation |
| Non-idempotent | 创建、编辑、undo/delete 都用 durable receipt；同 invocation 不同请求明确拒绝 |
| Artifact | `dbfox.animation.revision` 固定 animation_id/project/version/hash/title，原 Tool Runtime 生产 |
| Representation | `dbfox.animation.document.v1`：summary、六类实体页、stream export_json，读取固定版本并校验hash |
| Composition | `scene_bind` 经当前 Run 的 `artifact()` 与公开 `read_artifact_representation` 读取 Scene summary/objects_page；持久 source保存artifact/id/version/hash/object_id与固定TRS快照；不跨ownerstore/import，不按名称绑定，不宣称三维Scene renderer或联合可写文档 |

## 工具与交互

20 个工具：animation_create/inspect/diff/undo/delete/export/rename，target_create，track_create/modify，keyframe_add/move，easing_set，clip_create/trim/modify，timing_modify，marker_set，entity_delete，scene_bind。除 library create 外都要求精确 Animation resource。UI 原生增量操作走 animations.create/get/list/apply/undo/delete/diff/artifact；导出借助 ActionRun 产生 Artifact 并用 scope-fenced Host 导航打开。

Workbench 时间线 Canvas 每次只绘制 12 条轨道和当前时间窗内 keys；关键帧表每页50，clip面板每页10、marker面板每页20。时间线拖拽只在 pointerup 提交一次；方向键/Shift方向键按1/10帧移动；Delete 删除 key；Ctrl+Z 还原上一 revision。曲线手柄与数值控制点共用 easing_set。DOM 不是 key 数量的线性镜像。完整读取最高20,000 keys需分页，首载仍有成本；不是无限数据承诺。

本版预览是 Three 求值后的局部 XY 示意，显式标注；不冒充 Scene 三维场景消费。Scene 实际消费边界已通过源 owner 的真实公开 Representation 对象测试，完整跨签名多DLC RunLoop 组合和独立质量验证仍需独立验证员。

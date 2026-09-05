# Voxel World Studio DLC

> 文档类型：架构说明
>
> 状态：草案
>
> 最后核验：2026-09-05
>
> 适用范围：`dbfox.voxel`；不修改 Core、SDK 或其他 DLC 私有状态。

## 调查与决策

已研究 Music 的资源 provider、typed operations 和可恢复创作 Tool；Story 的 project-scoped direct edit；Visualization 的 Artifact Representation；Workbench SDK 的 connector、Dock、Artifact 和 `onAsk` 合同。Music 的整文档 revision 和历史内容 hash 唯一索引不适用于分块世界：重复历史内容必须能作为 undo 的新 revision。

持久化复用 Python `sqlite3`、`array`、`zlib` 和 SQLite 事务，不增加数据库抽象或依赖。[SQLite 官方事务说明](https://www.sqlite.org/lang_transaction.html)确认 `BEGIN IMMEDIATE` 先取得写事务，配合 version 比较防止丢失更新；事务把 metadata、chunk delta 与版本一起提交。领域几何为整数格点上的集合运算，不能从 Data/Story/Music 复用，不引入 native voxel engine。

渲染优先使用 DLC-local 固定版本 Three.js 的 [InstancedMesh](https://threejs.org/docs/pages/InstancedMesh.html)、[OrbitControls](https://threejs.org/docs/pages/OrbitControls.html) 和官方 [voxel geometry](https://threejs.org/manual/en/voxel-geometry) 边界面生成方法。Three.js 为 MIT，需记录版本、包完整性、vendor hash 和许可，按 package asset 提供；不使用 CDN、不修改 Host npm 锁文件、不引入全局共享 renderer。

## Canonical proposal

Resource：Project 中的 Voxel Library 是创建入口；每个独立 VoxelWorld 是 version-fenced Resource。Chunk、layer、palette entry、named region 是该 world 内 object，不各自扩展 authority。

Canonical durable state：world 标识、project 归属、整数 size、version、title、palette、ordered layers、named regions、metadata 和每层稀疏 16³ chunk 的 palette index。Palette index 0 始终为空，非零 index 必须引用有效颜色。世界尺寸每轴至多 256，每个操作至多 2,097,152 个候选格点，超限明确拒绝；大世界分区域调用高层工具。

View state：相机、hover、当前笔刷、当前 layer、层可见性、slice axis/index、临时 selection 与展开状态留在组件；selection 可作为 object reference/请求输入，不能给予资源权限。Derived state：mesh、surface cache、统计和 viewport 均可从已提交 chunk 重建。

Operation：严格类型的 fill、box、sphere、extrude、replace、copy、mirror、boolean 与 metadata/configure。所有修改、delete 和 undo 必须提供 `expected_version`。UI 与 Agent 调用相同 store 方法；未知结果不自动重试。Operation log 记录被修改 chunk 的前后值和 metadata 前后值；不保存第二套可写作品。

Artifact：显式 export 返回固定 world version 的不可变 snapshot 证据。Representation：`dbfox.voxel.world.v1` 输出 manifest 与分页 chunk 数据，跨 DLC 消费它而非读取 private SQLite。历史 snapshot 的读取必须不依赖 current world head；删除 world 后保留合法 Artifact 的历史数据，uninstall 默认保留 owner data。

## 待独立 Architect 冻结

- 层叠合成规则、锁定 layer 的编辑和 copy/boolean 来源语义。
- chunk 编码、版本/operation identity、重复 invocation 和 cancel 在提交边界的规则。
- undo cursor 与 undo-of-undo，no-op 的历史语义。
- 删除和 Project lifecycle：Host 当前无 project-delete hook；owner tombstone/retention 政策必须明确。
- Agent inspect/context、frontend chunk paging、immutable Representation 的独立有界预算。

## 验证门禁

确定性 domain/持久化/CAS/lifecycle/工具 authority/context/前端交互测试；生产 Tool 路径构建 64³ 赛博朋克狐狸神社并至少十种增量修改；二百万以上 voxel 的大规模边界验证；独立 adversarial review；所有严重已确认问题修复后再申请 integration candidate。

## 前端依赖边界

已从官方 npm registry 核验 `three@0.185.1`，MIT，无运行时依赖；tarball 为 `https://registry.npmjs.org/three/-/three-0.185.1.tgz`，完整性为 `sha512-5aojFCXKwnjBRZvUnt3WFfEcvUJgkN5LlijRFN95hMy8WVkG4I0QNcJE+OuWvuJ0bOdStrbfXn0pkd6/QyiAlg==`。当前 Host 构建环境已有 `esbuild@0.28.2`。后续只生成 DLC 自身 vendor bundle 和许可，不修改根或 desktop 依赖锁，不运行 runtime 包管理器。

选择 Three 是因为相机控制、GPU 资源管理、raycast 与 instancing 已成熟，DLC 仅负责格点数据到 Three geometry 的真实渲染边界。世界 canonical 数据不含 Three class、不保存第二套 SceneDocument、不调用其他 DLC 私有 renderer。运行时不加载外部纹理、网络模型或用户 shader。供应链安全审查需记录实际 vendor hash 与使用版本，不能以 MIT 许可证代替安全验证。

## 已冻结的持久化与并发决定

2026-09-05 的独立 Domain Architect 首轮接受：唯一 append-only `chunk_versions` + `world_revisions`，`worlds.head_version` 仅指向当前已提交 revision。Chunk 固定 16³ 个 uint8 palette index，raw 长度恰好 4096；0 为空气，其余最多255个不透明 `#RRGGBB` 条目。压缩只使用 stdlib zlib，解码在4097字节截断并核对实际长度、eof、unused_data 与 unconsumed_tail；损坏时拒绝，不将损坏视作空气。

限制为每轴1..256、每world最多16层、128个region、64KiB规范metadata、8192个当前非空chunk slot（跨层计数）、每Project最多128个active world，单操作候选格点≤2,097,152。历史使用独立owner存储quota，达到上限停止新写入；不能静默GC已被Artifact引用的历史。

所有几何源从开始时的immutable revision读入；copy重叠不就地传播，boolean必须选择source layer，不读取UI可见合成。Undo输入为 `expected_version` + `target_version`，把目标快照恢复为新revision；不存在隐式可写undo cursor，undo-of-undo通过恢复撤销前版本完成。No-op不增version，但可写精确invocation receipt。Content hash不设唯一。

同一事务提交revision、head CAS和receipt；receipt绑定invocation identity、canonical输入hash与精确结果。resolver允许读取immutable历史revision（含soft-deleted world）以支持Host先resolve再reconcile；正常Tool执行重新验证active、frozen version、input expected_version、当前head，reconcile只查receipt，不重新执行。

Host每个新ToolInvocation会重新从当前Project discovery取得canonical资源版本；`AgentSessionInput`仅是initial intent。因此同Run可create→inspect→edit→edit，DLC不私自刷新scope。证据在 `engine/tools/runtime/resource_authority.py` 的selected ID绑定与 `engine/agent/tool_dispatcher.py` 的每次discovery+binding。Tool输入陈旧版本仍会被domain CAS拒绝。

Read paging固定目标revision，keyset游标按layer/chunk坐标排序，每页≤16 chunks；`since_version`只过滤同一目标revision的变化。World fingerprint来自规范metadata与排序chunk key/hash，不序列化全voxel。Context只含world summary、有限region/layer对象引用与分页提示，不包含raw chunk数组。

## 工作台实现与本轮验证

状态：当前实现，待程序级独立验证。2026-09-05，原 Scene Domain Architect / Backend Engineer 按 Director 调度转任 Voxel Workbench Engineer（线程 `/root/scene_lead/domain_architect`，逻辑归属 Voxel Lead）；本节是实现者证据，不计为独立 Verification 或 Red Team。

`frontend/index.js` 注册正式 `dbfox.voxel` connector、`dbfox.voxel.studio` Dock 和 `dbfox.voxel.snapshot` Artifact card。使用 Host React、Tree、operation/projectId、onAsk、scope 和主题令牌；不增加共享前端依赖、不调用私有 HTTP、不保存第二份可写 world。调查过 Music/Story 的 frontend fixture 与 Host SDK，采用同一注册边界；Three 的相机、OrbitControls、BoxGeometry、InstancedMesh 和 GPU 生命周期直接复用离线 vendor，DLC 只计算格点可见性与实例位置。`world-data.js` 是只读 chunk 解码/合成，`viewport.js` 只拥有派生显示资源，`studio.css` 使用既有浅色/深色主题令牌。

直接编辑包括世界创建、方块调色板/新颜色、图层选择/本地显隐/持久锁定/新图层、X/Y/Z 切片、矩形填充/矩形擦除/矩形选择、整数边界输入、fill/box/sphere/replace/copy/mirror/extrude/boolean、命名区域、恢复父版本或最近历史版本。矩形工具每次 pointer-up 只发一个有界 operation；取消笔触不写入。方向键移动光标，空格执行单次绘制/选择，Delete 擦除；锁定层可选择但不能写入，按键自动重复不发连续写请求。所有写入使用当前 `expected_version` 与新 `mutation_id`，同步 busy ref 防重入。未知结果和 stale rejection 只刷新，不自动重放。

每个世界先 get 当前 metadata，再按该固定 version 读取至多16 chunks/页；已有投影使用 since_version 增量并处理空墓碑和 layer 删除，全部页成功后才发布。混合版本、错误坐标/索引、重复游标和取消都拒绝。外部 Agent 修改通过窗口 focus、同 DLC 变更通知和可见页面3秒只读轮询同步；绘制中和写入中暂停自动读取。失败保留上次显示、禁用修改并允许手动刷新。选区引用只包含 world authority、layer object/version 和 bounds locator，不扩大资源权限。

3D 按可见图层从底到顶合成，使用最多60,000个表面方块的 InstancedMesh；超过预算明确显示“预览已截断”，提供“仅预览选区”和完整切片编辑路径。此预算只影响显示，不能据预览反写 canonical。大世界合成使用最多16MiB uint8 稠密派生投影，chunk 仍保持稀疏；合成/实例构建分批让出主线程且支持取消。切片底图按 revision/layer/axis 缓存，光标移动仅重画叠加层。极窄或高世界的离屏画布两轴均不超过768像素。渲染按 controls/resize/data change 请求 RAF，没有常驻空转循环。卸载/停用会中止请求与构建、清除轮询/focus通知、断开 ResizeObserver、释放 controls、instance/geometry/material/helper/renderer 和 DOM canvas。WebGL 不可用时明确提示且切片仍可编辑。

“保存快照”只调用正式 `worlds.snapshot` ActionRun。动作前先检查 `host.workbench.openArtifact`，缺少此可选能力时直接提示未创建快照；通过后捕获当前 context 的 workbenchScopeId，返回后调用通用 `openArtifact({projectId,sessionId,runId,artifactId},{workbenchScopeId,signal})`，使用服务返回的第一个 Artifact id 和同一取消信号。独立生产 Electron 已验证真实 ActionRun→Artifact Dock，以及固定历史版本的 Representation 三维查看和实际 DownloadItem 文件下载；完整独立门禁继续执行。内联卡片打开固定成果；成果面板的“打开当前世界”明确转到可编辑 head。

本轮确定性 fixture 共14项通过（3.28秒），使用真实 Host contribution staging 和真实 Three 几何/矩阵/OrbitControls，仅替换 WebGL device；覆盖 chunk 轴顺序、图层合成、固定版本增量/墓碑、分页/取消拒绝、表面剔除与预算、创建、单笔写入、onAsk、锁定、busy/stale、读失败恢复、WebGL 不可用、放弃笔触、Artifact navigation seam、外部修改、undo 与停用释放。测试代码通过 `typecheck:test`，本 fixture ESLint 和三个 DLC JS 的 no-undef/no-unused-vars 检查通过。可复现命令（worktree 根）：

```powershell
npm --prefix desktop test -- --maxWorkers=1 src/features/dlc/__tests__/dbfoxVoxelFixture.test.ts
npm --prefix desktop run typecheck:test
node desktop/node_modules/eslint/bin/eslint.js --config desktop/eslint.config.js desktop/src/features/dlc/__tests__/dbfoxVoxelFixture.test.ts
node --check dlcs/dbfox.voxel/frontend/index.js
node --check dlcs/dbfox.voxel/frontend/world-data.js
node --check dlcs/dbfox.voxel/frontend/viewport.js
```

另用本机 Edge 的真实 WebGL 做隔离浏览器检查：Host operation 为内存 fixture，未连接用户项目；32³神社显示1,556个表面方块，隐藏屋顶后624且version保持1，键盘绘制后voxel计数2,424→2,425、version1→2，选择与onAsk保持version2并携带正确layer/version/bounds。已检查真实截图；普通全页截图超时后使用有界内容截图。浏览器窄布局观察到560 CSS px下单列528px、无页面横向溢出，临时viewport已恢复。以上不代替真实Host导航、实际大规模GPU性能、完整Agent创作bench或最终独立对抗审查。


## 固定渲染依赖的生命周期修正

相机控制必须在canvas挂载后连接，并在React layout cleanup、DOM删除前释放，保持同一事件root。Three0.185.1另有Control保持按下时disconnect遗留keyup的问题；DLC固定构建仅补足该移除与状态重置，原始/补丁/产物hash与升级删除条件记录在vendor/provenance.json。此补丁由Voxel owner维护，不成为Core或通用事件层；已有两个不替换控件的独立原生EventTarget回归。详情见[验收证据](../quality/voxel-dlc-evidence.md)。

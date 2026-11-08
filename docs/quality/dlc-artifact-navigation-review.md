# DLC 工件导航的独立架构审议

> 文档类型：架构审议与实施门禁
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：前端 Host / Public SDK API v2；不修改 Kernel、后端端点或领域实现。

## 决定

**有条件接受新增可选的 `host.workbench.openArtifact`。** 两个独立工作台已遇到同一真实缺口，现有公开入口不能完成“Action Run 已生成成果 → 在当前工作台查看该成果”。接受的是下述受约束的导航合同，不是对尚未实现的代码或测试作通过结论。

本轮审议者未参与 Host 候选设计或实现；此前参与 Voxel 后端，因此不对 Voxel 自有实现作独立质量背书。本轮只读取源码、SDK、宪章、贡献指南和 Git 历史，并修改本记录与提案。工作区不存在 `.codegraph/`，按仓库规则跳过 CodeGraph。

## 源码与历史证据

| 已核实事实 | 源码位置 |
| --- | --- |
| Owner 只能打开自身已注册的 Dock viewType。 | `desktop/src/features/dlc/extensionHost.tsx:325`；`sdk/frontend/index.d.ts:320` |
| Dock 已有 `workbenchScopeId`，Host 已有 `currentScopeId()`。 | `sdk/frontend/index.d.ts:148`、`:324`；`desktop/src/stores/workspaceStore.ts:296` |
| 只有 Artifact View context 有既有工件导航/Representation 入口。 | `sdk/frontend/index.d.ts:236`、`:238` |
| 既有 Artifact View 回调按 ID 从 canonical store 重新取值，不信任调用方 envelope。 | `desktop/src/features/dock/dockViewContent.tsx:172`、`:176` |
| `loadRunArtifacts` 两次仅凭全局 artifact ID 缓存提前返回，随后直接 upsert；它不是公开身份验证边界。 | `desktop/src/stores/conversationStore.ts:198`、`:201`、`:206`、`:210` |
| 正式 Session 读取返回项目归属；缺失/已删除 Session 不可读取。 | `desktop/src/features/conversation/conversationRepository.ts:87`；`engine/agent/projection.py:33`、`:63` |
| 正式 Run 工件端点检查 Run 的 `session_id`，再读取该 Run 的持久工件。 | `engine/api/conversation_queries.py:103`、`:112`、`:117` |
| Session snapshot 的 Run 列表分页，默认只有 20 条。 | `engine/api/conversation_queries.py:58`；`engine/agent/projection.py:37` |
| canonical 工件包含 `id/session_id/run_id`；Core Dock 只保存工件身份引用。 | `desktop/src/types/conversation.ts:184`；`desktop/src/stores/artifactDockStore.ts:22` |
| Loader 已有投影 epoch、暂存注册和失效/退休流程。 | `desktop/src/features/dlc/extensionLoader.ts:44`、`:72`、`:137`、`:221`、`:247` |
| HTTP 客户端可能因 Engine 更新重取配置并重发安全 GET；HTTP 成功不证明原导航仍有效。 | `desktop/src/lib/api/client.ts:71`、`:347` |

历史提交 `117361f812760216feec039a43aae399f40b4597`（2026-08-30，`feat(dlc): project resource inventory contract across core and dlcs`）在 `sdk/frontend/index.d.ts` 增加 Artifact View 内的可选 `resolveArtifact/openArtifact`，没有提供从工作台按耐久身份导航的入口。`e64cd16f874b546514e5cf0abccbb0b9976ad34a`（2026-07-31，`重构：实现 Responses Agent Timeline 前端`）引入现有 `loadRunArtifacts` 与 ID 缓存快捷路径。可以复用其投影路径，不能把缓存行为当作新公共边界的归属证明。核验基线 HEAD 为 `2dc62653`，另有用户未提交基线；本审议不改动或提交该基线。

## 最小公开合同

建议冻结以下签名；新增类型属于 `sdk/frontend`，`workbench` 保持既有必选成员：

```ts
export interface ArtifactNavigationTarget {
  readonly projectId: string;
  readonly sessionId: string;
  readonly runId: string;
  readonly artifactId: string;
}

export interface ArtifactNavigationOptions {
  readonly workbenchScopeId: string;
  readonly signal?: AbortSignal;
}

// FrontendExtensionHost.workbench 中新增：
openArtifact?(
  target: ArtifactNavigationTarget,
  options: ArtifactNavigationOptions,
): Promise<void>;
```

`sessionId` 即 Action Run 返回的 Session，也是现有 conversation API 的 `conversation_id`。四个 ID 均须为非空字符串；运行时只提取和校验声明字段，不接受调用方 envelope、标题、payload、URL、viewType、renderer/store 对象或权限声明。成功只表示验证后已打开 Core Dock；错误/过期/中止均拒绝，错误信息有界。未知结果不创建占位工件，不轮询或重新执行导出。

放在 `workbench`，因为它属于当前工作台导航，且已有 scope API。`artifactViews` 是视图注册边界；`DockRenderContext` 专属 Dock，不适合通用 Host 命令。无需新增独立 `artifacts` 命名空间或给 Dock 暴露完整 Representation API。暂不增加 activate、selectedViewId、批量导航、返回 payload 或任意 tab 配置；Core Artifact View 继续负责匹配视图和下载。

`workbenchScopeId` 必须取自动作发起时的 `context.workbenchScopeId` 或 `host.workbench.currentScopeId()`，在等待导出之前保存。只在导航方法调用时捕获当前 scope，无法识别导出期间已经切换工作台的旧回调。DLC 应在卸载或工作台变化时中止其动作生命周期 signal；Host 只中止读取和导航，不重放或撤销已经提交的 Action Run。scope 是生命周期关联，不是资源 authority。

## 身份与唯一投影路径

1. 检查 Host 绑定的 owner 仍为已接受的激活实例，signal 未中止，当前 Project 与请求 Project 相同，当前 scope 与发起 scope 相同，再开始读取。
2. 通过现有 `getConversation(sessionId)` **新读取** Session，验证返回 ID 和 `project_id`。缺失、已删除、无项目或其他项目拒绝。不能只信任 `detailById`，也不能调用带 follow 行为的 `openConversation` 做读取。
3. 通过既有 repository 和 `loadRunArtifacts` 的同一加载路径，**新读取** `getConversationRunArtifacts(sessionId, runId)`。后端已验证 Run → Session；不能要求 Run 出现在分页 Session snapshot 中。不得因目标 ID 已缓存而跳过验证。
4. 在 upsert 之前验证响应工件 `session_id/run_id`，目标 `artifactId` 确实出现在本次响应且身份无歧义。已有不同归属的同 ID 缓存不能满足请求或被无声覆盖。格式解析沿用 `parseConversationArtifact`，不另建 envelope 模型。
5. 生命周期仍有效时，把服务端工件写入唯一 `conversationStore.artifactsById`，从此投影取得 canonical 工件，调用既有 `openArtifactDock`。打开前再核验身份与生命周期，中间不留下新的异步间隙。

现有 `loadRunArtifacts` 需要最小内部增强，支持必须读取、可中止且提交前验证的入口；不能在 Host 复制另一套 fetch + upsert 存储链。旧 timeline 调用合同保持。内部签名由实现者以最小方式完成，不要求额外通用策略层。不能先把未经校验或已失效响应写入全局缓存，再只抑制打开 Dock。

`artifactLoadRequests` 目前按 Session/Run 去重。新请求不能加入过期 generation 的 promise；不能用一个调用方的 AbortSignal 杀死其他仍有效的 timeline/导航订阅。可让有取消要求的导航使用独立请求，并共用唯一加载和投影代码，无需通用请求管理器。若共享传输，须证明消费者生命周期隔离以及最后一个消费者离开后才取消传输。

目标 Session 不必等于当前聊天 Session：Action Run 可能创建独立 Session，这正是实际需求。导航不切换会话、不开启 followRun、不修改耐久 selected artifact、不加入 onAsk 引用、不改变冻结资源或重建导出。不按领域字符串限制工件类型；owner-bound 指调用能力绑定到实际激活 owner，工件归属以 Project → Session → Run 校验，同项目组合成果仍可查看。

## 生命周期约束

| 变化 | 必须拒绝/停止的情形 |
| --- | --- |
| Owner activation | 注册还在 staging、注册失败、停用、升级、退休，或同 owner 同 package digest 重新激活后的旧 Host 引用。仅检查 `dlcId + digest + loaded` 不能识别后一种情况。复用 Loader 的确切激活实例/epoch，不新增平行状态机。 |
| Engine | 请求开始至投影提交/导航前 generation 改变，或现有失效流程已撤销 owner。GET 客户端恢复成功不能使旧导航复活。使用 `getRuntimeSession().generation`，不复制 token/session 状态。 |
| Project/workbench | 调用时已不匹配发起 scope；请求期间离开该 Project/scope；即使随后切回同一 scope，已取消请求也不能复活。复用 store 订阅和一次性失效标记/取消，无需持久化导航状态。 |
| Abort/unmount | 预中止不发请求；每个 await 之后、解析后、upsert 前和打开前均检查。视图卸载由调用方 signal 传达，Host 不猜测 React 挂载状态。 |

发起动作至导航方法调用之前的卸载或“切走又切回”，需要调用方贯穿导出等待期的 signal 表达。方法尚未调用时，Host 无法从稳定 scope ID 还原中间 UI 行为。因此实际 Workbench 必须保留作用域和取消生命周期，不能把可选 signal 理解为无需处理晚到回调。请求开始后 Host 对 scope 变化的取消必须单向失效，不能只在最后比较相等值。

异步完成后先更新缓存再检查 owner/scope 不合格。Loader 失效可以撤销所有旧 Host 的此项能力；本次不为无关旧方法重做权限系统。

### 最小 activation lease 方案

无需让公开 Host 接收 digest，也无需创建生命周期框架。可在每次 `createStagedExtensionHost` 内创建一个仅用于新导航能力的闭包：`active = false`、`revoked = false` 和一个 `AbortController`。在内部 `StagedExtensionHostResult`（`extensionHost.tsx:45`）增加 `activateNavigation(): void` 与 `revokeNavigation(): void`；**这两个控制方法不放入交给 DLC 的 `host`**。activate 只允许尚未 revoked 的 staging 实例变为 active；revoke 同步置为永久失效并 abort，重复调用无害。导航检查 active 且未 revoked，并接入该 signal。单个新 Host 闭包本身就是唯一 lease，无需字符串 ID 或额外 registry。

Loader 按现有阶段调用控制方法：

1. 创建 staged Host 后保持 inactive；导入/注册/去重失败时 revoke。stale epoch 分支 revoke 本批全部 staged Host，即使 `module` 对象与当前实例相同，也不能跳过 lease 撤销。
2. 只有 `epoch === projectionEpoch` 且该 owner 的贡献通过全部检查，在接受本批投影的同步提交段才 activate。扩展现有 `ActiveFrontendModule` 记录，保存对应 `revokeNavigation` 即可；不另建一份 owner/digest 状态表。
3. `reserveProjectionEpoch`/显式失效开始时，同步 revoke 现有 active records 的导航 lease；不等 `lifecycleBarrier` 或异步 `module.deactivate()`。这使新一轮投影调查期间旧入口默认拒绝，避免延迟停用回调放行导航。
4. 替换 active map 时所有退休 Host 的 lease 都 revoke，**不使用 `module` 对象或 digest 相等来跳过**。`extensionLoader.ts:249` 的 module 相等分支只决定是否执行 module 的生命周期回调，不能决定旧 Host 是否有导航权限。新一次注册得到新闭包，旧闭包永远不能再次 activate。

这只为已存在的 Loader staging/accepted/retired 边界增加两个内部同步钩子和取消句柄；不改变公开 API、module.deactivate 的去重逻辑或旧贡献注册行为。也可用等价的 Loader-owned 唯一对象身份加只读 predicate/signal 注入 Host，但不得退化为 `useDlcStore.records` 的 digest/status 判断。必须测试“同一个 ESM module 对象、相同 digest、再次 register 得到新 Host”的旧引用失效。

## 宪章第 6 节逐项结论

| 问题 | 审议结论 |
| --- | --- |
| 1. 正确性或两项真实需求？ | Scene `scenes.artifact` 与 Voxel `worlds.snapshot` 的独立 Workbench 核验成立；源码确认缺公开结果入口，不是预设未来能力。 |
| 2. 既有贡献面为何不足？ | Tool/operation 已完成持久导出；Context/Guidance/Completion 不负责 UI 导航；Artifact/Representation 的读面只注入 Artifact View；onAsk 不是结果导航。 |
| 3. 为何 owner 无法解决？ | Owner 不能访问 Core store、Core viewType 或私有 API；另写导出/下载链会复制已有事实和格式。 |
| 4. 中立、owner-bound、fail-closed？ | 只用通用持久身份和 Host scope，绑定确切 activation；缺能力、归属错误或过期默认拒绝，不添加领域/provider 分支。 |
| 5. 新增中间层或双写？ | 无新事实源、endpoint、格式 mapper 或重试链。新增入口位于真实 SDK 边界，复用 repository/store/Dock；若复制投影或导出则退回。 |
| 6. API v2 与持久化兼容？ | 方法可选，原签名不变。旧 Host 可以没有方法；新 DLC 显式检测并报告不可用，不以私有 HTTP 降级。Python API、manifest 版本、Frozen Run、SQLite、后端合同不变。 |
| 7. 什么验证足够？ | 下列身份、缓存、竞态、旧 DLC 和真实工作台门禁，加宪章要求的基础回归。文档审议不能替代测试。 |

复用决策：项目已有读取、投影、Dock、Loader epoch 和取消基础，直接复用并做最小边界增强；无需第三方依赖、自研下载器或通用状态机。主要风险是缓存与生命周期。无迁移/兼容链清理债务；一次性监听器必须在成功、失败、中止路径释放。

## 实施与验证门禁

须用生产 Host/Loader/store 边界覆盖有区分度的场景，不能只验证自制 mock 对象有某个属性：

- 同项目 Action Run Session 与当前聊天不同仍可打开；旧 Run 不在 Session 第一页仍可打开；Core Dock 使用服务端标题/payload，下载走既有 Artifact View。
- 错 Project/Session/Run、未知/空身份、缺失目标、响应归属错误拒绝；缓存已有目标但请求错 Run/Session 仍读取并拒绝；正确缓存不代替新的项目核验；失败不制造投影/页签。
- 失败注册/已停用 Host、同 digest 再激活后旧引用、请求中升级/Engine generation 改变、预中止/解析后中止、请求中切工作台和切走再切回，均不导航或提交失效投影。
- Workbench 按导出前 scope 导航；导出等待中卸载/换 Project/换工作台不让旧回调打开新工作台；保留正式返回的 Artifact IDs，不重新导出。
- 同 Session/Run 并发读取与取消不错误影响其他消费者；新请求不加入旧 generation 的共享请求；各终止路径释放监听器。
- 旧 API v2 Host/DLC 无新方法仍可注册；新 DLC 缺方法时报告不可用；不能通过 `dockViews.open` 打开 Core viewType；没有新增 Kernel/backend/领域字符串或私有导入。

当前 `verification/tests/system/test_engineering_contracts.py:167` 的表面快照只比较 Python `dbfox_dlc_api.__all__`，不能证明前端新增兼容。**纯前端新增不应修改 Python surface 清单。** 须补真实 `sdk/frontend/index.d.ts` 的类型/表面兼容门禁：旧 Host 不提供可选成员仍可赋值，新签名要求完整身份/scope，不能传 envelope。并覆盖 `extensionHost`、`extensionLoader`、`conversationStore`、`artifactDockStore` 的生产路径。`dlcFeasibilityContract.test.ts` 中自造公共对象的示例检查不能单独算 conformance。

实施后报告实际命令和数量：仓库根 `python -m pytest verification/tests/system/test_engineering_contracts.py -q`、宪章指定 Agent Core 回归；`desktop/` 中对应 Vitest 文件（`--maxWorkers=1`）、`npm run typecheck:test`、`npm run lint`、`npm run build`。独立记录无关基线失败，不改写用户基线使其表面通过。Scene/Voxel 正式按钮接入与可查看/下载结果须有真实 fixture 或浏览器证据。本轮未运行实现测试，未作发布通过结论。

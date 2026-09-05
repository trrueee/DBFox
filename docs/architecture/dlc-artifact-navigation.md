# DLC 工作台的工件导航

> 文档类型：公共接口合同
>
> 状态：当前
>
> 最后核验：2026-09-05

## 问题与调查

Scene Workbench 的显式导出调用 `scenes.artifact`，通过现有 Action Run 生成耐久 Artifact，
返回 Artifact、Run 和 Session ID。其 Artifact View 已有正式 Representation stream 下载面，
但工作台无法把刚生成的结果交给该视图。`host.dockViews.open` 只允许本 DLC 注册的 viewType；
`DockRenderContext` 只有 onAsk，只有已经渲染的 `ArtifactViewContext` 才有 openArtifact 和
representations。让用户手动寻找一次未打开的 Action Run 不是完成的导出交互。

Voxel Workbench 专员 `/root/scene_lead/domain_architect` 独立确认第二个真实需求：
`worlds.snapshot` 同样返回 Artifact IDs、Run 和 Session，用户需要直接查看不可变快照及下载
Representation JSON/chunks，但 Dock 没有成果访问面。两个工作台都拒绝用私有 HTTP 或另一条
导出链绕过限制。独立架构审议见 [质量记录](../quality/dlc-artifact-navigation-review.md)：
有条件接受通用导航边界，实施仍须满足身份、生命周期与兼容门禁。

已检查公开前端声明、extensionHost、extensionLoader、ArtifactViewHost、artifactDockStore、
dockViewContent、conversationStore 与 conversationRepository。`getConversationRunArtifacts`
已有带 Session/Run 归属的正式读取端点；`loadRunArtifacts` 复用唯一 conversationStore 投影，
`openArtifactDock` 只创建身份引用页签，不复制 payload。Git 历史 `117361f8` 已提供 Artifact
视图内导航，但没有工作台的入口。本次不引入第三方库。

## 公开合同

前端 Host 的 `workbench` 提供以下可选、默认拒绝的 Stable API v2 方法：

```ts
interface ArtifactNavigationTarget {
  readonly projectId: string;
  readonly sessionId: string;
  readonly runId: string;
  readonly artifactId: string;
}

interface ArtifactNavigationOptions {
  readonly workbenchScopeId: string;
  readonly signal?: AbortSignal;
}

openArtifact?(
  target: ArtifactNavigationTarget,
  options: ArtifactNavigationOptions,
): Promise<void>;
```

scope 必须在导出等待前保存；组件卸载或
工作台变化时取消贯穿该动作的 signal。不让 DLC 传入 envelope、payload、任意 viewType、
URL 或 Renderer Store；完整类型及语义见独立审议。

Host 从正式持久读取路径核实 Project、Session、Run、Artifact 的归属，将结果载入既有
conversationStore，再打开现有 Core Artifact Dock。未知或错配身份拒绝，不伪造空 Artifact；
engine generation、DLC activation、workbench scope 或 Project 改变后，不把晚到结果导航到新
工作区。Session 项目归属及 Run 工件都必须通过正式读取新验证，不能以 `loadRunArtifacts`
的 ID 缓存命中跳过；Session 的 Run 列表分页，不要求目标 Run 出现在当前页。绑定确切
activation 实例，包含同 package digest 再激活后旧 Host 引用失效。校验在投影提交前完成；
读操作可中止，创建导出的写操作仍由原 Action Run 执行一次，导航不重放它。

通过归属验证后，Host 在现有 Dock tab 的 projectId 字段保存该已验证项目。单个工件视图
对这一显式导航入口按当前 Project 显示；其 tab 仍只存在于原 workbench scope，支持草稿
工作台和当前聊天之外的 Action Run。没有此字段的 timeline 入口保留原会话显示语义；
工件集合仍绑定当前聊天。该字段是显示元数据，不授予 Resource/Artifact 后端读取权限，
不会切换聊天、复制会话状态或建立另一份工件投影。

导航方法只负责查看已存在结果，不改变 Resource authority，不创建 Run，不执行领域导出，
也不提供私有 API client。Artifact 自己注册的 Representation 决定内容和下载格式。

## 读取、提交与生命周期

`extensionHost.tsx` 先读取 Session 并核实项目，再调用既有 `loadRunArtifacts`。该 store 方法
保留 timeline 的缓存/共享读取合同；提供内部导航 options 时，使用独立的新读取，不加入
timeline 的共享 promise。相同加载函数负责正式 API 读取、既有 schema 解析和唯一
`upsertArtifacts` 投影，不建立新的 Artifact 模型或 store。API 读取均传递 AbortSignal。

投影前校验完整响应的 Session/Run、重复 ID、目标是否存在，以及已有同 ID 缓存是否属于
其他 Session/Run。不同归属的缓存产生冲突错误，不静默覆盖。Host 的 `beforeCommit` 检查
generation、激活 lease、scope 和 Project；`afterCommit` 在同一同步调用中再次检查，从
canonical store 取回并核对目标后调用 `openArtifactDock`。同步 store 订阅者也可能切换
项目，因此投影后仍须检查。导航不调用 `openConversation`、follow、选择工件写入或 onAsk。

每次 staged Host 只有一个内部 lease，初始 inactive。Loader 接受贡献后激活；新一轮
projection、失效、失败注册和退休均永久撤销并中止旧 lease。即使同一 ESM module 对象和
digest 重新 register，旧 Host 也不会复活。activate/revoke 只交给 Loader，不暴露给 DLC。
工作区订阅发现 Project/scope 变化后单向取消；切走再切回不恢复请求。订阅在成功或失败后
释放。Host 不缓存 token，也不重新实现 Engine generation。

模块导入可以并行；register、失效后的清理和贡献提交复用 Loader 既有 lifecycle barrier
串行执行。开始注册前及每个 DLC 之间检查 epoch，过期导入不再调用 register。原因是同一
ESM 可能在模块变量中保存 Host：仅在最终投影处拒绝过期结果，仍会让迟到的 register
覆盖当前 Host。正在执行的异步 register 完成并清理后才可进行下一次注册；同一 ESM 的
有效重注册保留既有复用语义，不通过停用仍挂载的组件来掩盖竞争。

正式 `creating/failed/stale` 工件仍可由已有视图呈现其状态；它们与 HTTP 失败、缺失工件
不同。缺失或归属错误不投影、不创建页签。Host 返回有界错误信息，取消保留 `AbortError`。
导航失败不撤销已经完成的导出，也不重放写操作；调用方应保留正式结果身份。

实现复用项目已有 repository、Zustand store、Dock 与 Loader 阶段。取消使用平台
[AbortSignal](https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal)，工作区失效复用
[Zustand 的 subscribe](https://zustand.docs.pmnd.rs/reference/apis/create-store.html)。
不新增依赖、缓存框架、下载器、后端端点或兼容路径。

## 宪章第 6 节的逐项说明

1. 这是 Host 自有工作台与耐久 Artifact 之间的导航边界。Scene 与 Voxel 的实际工作台实现已
   分别确认相同阻塞；证据来自两个 Workbench 专员核验的公开 SDK 和 owner Action Run 返回值。
2. typed operation 能完成写入和产生 Artifact；现有 Dock 无法读取/打开其结果。onAsk 是加入
   对话引用，不能替代查看或下载；放宽 owner dockViews.open 也无法保证真实 envelope 已载入。
3. DLC owner 无法合法访问 Core Artifact 投影、Core Dock 或私有 API。各 DLC 自建下载 endpoint
   会重复已有 Representation 边界，绕过统一成果读取。
4. 所有参数都是 Host 已有通用身份。Host 核实持久归属并控制导航；错误、取消和过期结果拒绝。
   不在 Kernel/Runtime/SDK 中增加任何领域 ID、格式或分支。
5. 复用既有读取、投影与 Dock；不建立第二份可写 Artifact 模型、字段映射表、重试或兼容链。
   新导航与 timeline 共用原加载及投影函数。
6. 作为 Stable API v2 可选新增，旧 DLC 不需改动。缺少新能力时新 DLC 明确报告不可用，不以
   私有访问降级。冻结 Run 和 SQLite 表不变，无迁移。公开声明、文档和前端类型/表面
   conformance 同步更新；现有 Python `__all__` 快照不能代替前端门禁，也无需因此修改。
7. 必须验证真实结果导航、错配/缺失/跨 Project、失败/取消/停用/工作区切换、无写入重放、旧
   DLC conformance，以及 Scene/Voxel 导出路径。执行工程合同、Agent Core 回归、前端测试、
   类型检查和构建；实际结果写入独立质量记录。

## 交付边界

工作区为 `creative/host-artifacts`，与各领域 change set 分离。只提交明确新增的通用 Host
文件；不得把 Director 提供的用户未提交基线带入该提交。完成的提交必须带上两个实际 DLC
需求、独立架构结论和[Host 验证证据](../quality/dlc-artifact-navigation-validation.md)。
Host 验证不替代各领域按钮的真实接入、下载验收或后续独立红队检查。

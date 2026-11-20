# 电脑操作与受控浏览器

> 文档类型：架构与交互设计
>
> 状态：当前
>
> 最后核验：2026-11-18
>
> 适用范围：Windows 11 x64、Sidecar Host 能力、Agent、Electron 与工作台

## 目标与边界

在已有唯一 RunLoop 中支持选择电脑目标、观察界面、逐次审批操作、确认操作后状态、人工接管
和交付可检查证据。浏览器与桌面均使用正式 Tool Runtime、冻结 ResourceRef、Artifact 和
Representation；不建立第二套 Agent、审批、任务调度或成果存储。

沿用本轮之前明确的本机授权执行范围，不把工作目录、独立浏览器配置或 Job Object 描述成
OS 安全沙箱。桌面只支持当前登录用户可访问的普通窗口，不提权、不操作安全桌面。网页和
应用中的指令作为不可信内容处理，不能授予操作权限。

## 调查与复用决策

| 已调查方案 | 采用方式与取舍 |
| --- | --- |
| 现有 Workspace、Local Execution、资源发现、审批与 Artifact | 直接复用生命周期和权威状态；电脑目标是独立 Host 资源，不塞入 Data，也不让 Renderer 驱动 Agent |
| Windows UI Automation / pywinauto | 复用成熟 UIA 控件访问与输入库；Host 适配仅负责目标身份、观察一致性和取消围栏。不复制 UIA 实现，不使用 uiAccess 或管理员提升 |
| Playwright Python | 复用页面、框架、DOM、截图和输入协议；使用本机明确选定的 Edge，独立用户数据目录，不连接个人浏览器配置 |
| Electron debugger / WebContentsView | 有现成页面控制能力，但需要新增 Sidecar 到 Main 的操作传输及双向生命周期；本轮浏览器使用与 Sidecar 同一监督边界，Electron 保留展示和停止入口 |
| 现有 WindowsProcess | 复用 Job Object 管理受控浏览器及子进程，不再增加 taskkill 或 PID 推断链 |
| 当前模型观察合同 | 只有有界文本；新增通用、可选的图片引用，通过现有 Artifact 表示读取，避免把截图字节塞进业务状态 |
| 现有 React / Radix / TanStack Query 与设计令牌 | 直接复用组件、请求取消和主题；不添加另一套组件库或前端任务状态机 |

pywinauto 为 BSD-3-Clause，Playwright 为 Apache-2.0，Pillow 为其上游许可。新增依赖经原有
uv 哈希锁工作流生成、安装与 Frozen 验证。主要成本是 Playwright 驱动体积、COM 线程规则、
浏览器版本兼容和截图保留空间；驱动放在清晰的系统边界，未来可替换，数据合同不绑定厂商。

官方依据：[Windows UI Automation](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-uiautomationoverview)、
[UIA 安全边界](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-securityoverview)、
[pywinauto](https://github.com/pywinauto/pywinauto)、
[Playwright 浏览器支持](https://playwright.dev/python/docs/browsers)、
[Playwright 与 PyInstaller](https://playwright.dev/python/docs/library#pyinstaller)。

## 所有权与数据

| 对象 | 权威所有者 |
| --- | --- |
| Session、Run、Invocation、Approval、Observation | 既有 Kernel 和持久层 |
| 目标授权、权限、代次、到期和撤销 | Host 电脑能力的 SQLite 资源存储 |
| UIA、浏览器连接、输入互斥、OS 句柄 | Sidecar 电脑运行时 |
| 浏览器进程树 | 既有 WindowsProcess Job |
| 截图与操作证据 | 既有 Artifact；截图文件位于私有结果后端 |
| 图片的模型输入形式 | 通用媒体合同与现有 Provider 边界 |
| 预览、选项卡、加载和选择状态 | 既有 Dock / UI 投影 |

授权选择明确的项目、窗口或受控浏览器，区分观察和控制。控制授权不能替代每次 Tool 操作审批。
撤销、到期、进程身份改变或 Sidecar 重启使旧代次失效；不会自动重开浏览器或重放点击、输入。
暂停/停止是用户操作入口，须立即使后续副作用失去授权；对已发出的不确定操作要求重新观察。

观察是不可变工件，包含来源身份、时间、界面范围、可用元素和图片引用。操作引用明确的观察；
检查目标仍存在、进程身份与范围仍一致、元素仍属于该观察，再在实际副作用前检查授权和取消。
操作后返回新的实际观察。程序接收输入不等于用户任务完成，界面分别显示操作事实和任务结束。

## 前端交互

1. 对话提供“电脑”入口，打开工作台中的电脑面板；没有授权时展示浏览器和共享窗口两种选择。
2. 共享窗口先选择具体应用和窗口，再明确选择观察/控制与期限；展示访问范围与停止方式。
3. 受控浏览器使用独立配置，显示当前地址、状态和可检查的页面预览；不复用个人 Cookie。
4. 活动状态显示目标、权限和有效期；审批卡展示确切动作及内容，用户可以拒绝。
5. 预览显示观察时间与来源，明确区分加载、过期、目标失效、被接管和失败；不把旧图冒充当前图。
6. 固定提供停止/接管入口和可用的全局停止快捷键。切换对话、关闭标签和刷新仅改变投影。
7. 操作和交付复用时间线及成果卡；打开截图/操作证据时校验来源和保留范围。

视觉沿用既有系统字体、Phosphor 图标、语义色、圆角和留白：浅色柔和底面、深色独立校验、
紧凑工具栏、分段选择和清晰主次按钮。透明度仅用于次级工具栏，避免低对比的新拟态；
不采用技能检索中的营销单栏、衬线字体或金色配色建议。保持键盘操作、可见焦点、减弱动态、
窄 Dock 和大字号可用，操作反馈以事实文字配合图标表达。

## 通用媒体合同变更说明

这是桌面与浏览器两个独立能力共同需要的模型输入变化，不增加电脑业务规则到 Kernel。
现有文本 Observation 与 JSON model_read 不能表达图片；只在界面展示截图无法让模型观察。
能力 owner 发布不可变图片 Artifact，通用层根据明确的媒体引用与表示合同读取有界图片，
Provider 在实际请求边界使用原生图像内容项。截图二进制不写入 Run、Context 或 Observation 表。

新增字段可选、默认空；旧 Tool、API v2 DLC 和已有冻结运行保持文本语义。保留图片字节、
单次模型图片数量/尺寸与模型输入预算分别限制，过期或无权访问时明确失败，不默默替换来源。
更新公开表面快照与 conformance，检查旧 DLC、Core 上下文预算和真实 Responses 图片输入。
没有临时双协议、场景映射或新的 Provider 名称分支。

### Kernel / Stable 合同变更的七项依据

1. Windows UIA 窗口观察和 Playwright 页面观察是可独立运行、分别验证的系统能力；二者均需将
   实际图片交给模型。仅有文本是共同的表达缺口，不能由控件树或 DOM 摘要替代。
2. 原有 `provider_payload` 只允许 JSON，`model_read` 只返回 JSON；把图片放入 UI 或另建聊天
   调用都不能补齐生产 RunLoop。采用可选 `ToolMediaReference` 与 `model_media` stream purpose。
3. owner 仍负责捕获、密码元素处理、文件保留和 SHA-256 校验。只有 Provider 请求组装属于
   通用 Runtime，因此在通用层解析媒体引用，不在 Kernel 解析电脑 payload。
4. 引用必须属于本次结算发布的 Artifact；读取复用原有 Run/Session 来源证明、冻结 snapshot
   和 Representation dispatcher，仅接受声明为图片的操作。第三方 DLC 默认不能声明原生电脑
   执行权限；Host 装配明确授予，PolicyGate 继续逐次审批控制操作。
5. 无新 mapper、fallback、双写、第二套审批或 Agent。`requires_current_resources=False` 是
   Host 内部的不可变证据读取语义：保留同对话证明和保留预算，结束实时共享后仍能检查过去
   已捕获的证据；它不恢复新观察或控制。默认仍要求当前资源，不改变旧扩展行为。
6. API v2 新字段默认空，旧调用保持文本；原有 Frozen Run 不补造图片。Prompt 版本为 4.2，
   durable Context/Observation 只存引用。SDK 声明和公共表面快照同步更新，未增加旧协议兼容层。
7. 验证覆盖媒体预算、旧文本工具、图片过期、不可变 DB 引用、真实 Edge/Win32、正式 HTTP、
   生产 RunLoop 三次审批与 SHA-256 对照。真实本地视觉模型使用独立的 `real_llm` 用例，
   其决策结果不与脚本化模型边界的链路测试混称。

## 当前实现合同

- 资源 owner 为 `dbfox.computer`，种类为 `dbfox.computer.target`；用户选择窗口或独立 Edge。
  授权限于一个对话，分观察/控制，期限 5、15 或 30 分钟。同类目标替换需要明确选择。
- 正式工具为 `computer_observe`、`computer_act`、`browser_navigate`。动作支持点击、双击、
  文字、按键、滚动、聚焦和浏览器返回/前进/刷新、新建/选择/关闭页面。每个控制动作单独审批。
  浏览器至多观察 8 个页面和 8 个 frame；元素至多 64 个，页面正文摘要至多 4000 字符。
- Windows 输入只进入所选普通窗口与同进程所属对话框；先明确批准聚焦，再操作前台目标。
  观察检查 HWND、PID、进程创建时间、可执行路径、几何和元素身份；文字使用完整内容摘要
  检查并发变化，不以截断的前 160 字符判断内容未变。
- 操作使用 120 秒内的最新观察；实际输入前再次检查授权、代次、期限、取消、焦点与敏感输入。
  停止先置取消围栏，再修改持久授权，独立浏览器立即关闭其 Job。队列中的延迟查找不能在
  停止后继续发送输入。重启把共享标为 interrupted，不接回旧控制或重放动作。
- 单图最多 1280×900、2 MiB；最多向模型送入一张最新图片，另保守预留 4096 输入 token。
  截图最长保留 24 小时、至多 512 张/256 MiB，按先到的条件清理。文件失效时明确报错。
- 前端预览是当前读取的 UI 投影，不是正式工具执行证据。观察和动作经原有 Settlement
  产生不可变 Artifact，Dock 使用同一 Representation 读取；动作记录只证明输入已发送。
- Main 注册 `Ctrl+Alt+Shift+Esc`，通过当前代次的认证 HTTP 固定停止入口执行；注册结果
  通过现有窄化状态 IPC 告知 Renderer，失败时界面明确显示不可用。面板另有固定全部停止入口。

第一期不提供系统提权、安全桌面、终端 UI、密码填写、个人浏览器配置接管、文件上传/下载
搬运或跨应用拖放。终端和项目文件继续使用已有正式命令/Workspace 工具。当前用户权限、
Job 和浏览器配置隔离不是 OS sandbox，也不能保证任意应用或任意任务都能可靠完成。

## 实施与验证

按资源和授权 → 原生适配 → 工具/媒体/证据 → API → 前端 → 故障与真实任务验收推进。
覆盖授权撤销与同目标重绑、陈旧观察、焦点变化、取消/超时、不确定结果、不重放、进程清理、
模型实际收到图片、截图过期，以及浅/深色和窄 Dock。实际 UI 验收只操作专用夹具和明确授权
的目标，不用其他用户应用充当测试数据。每项实现与验证结果另记，本文不把设计当作已通过。

本轮源码、Frozen、真实本地模型和桌面交互的分层结果见
[电脑工作台验收记录](../quality/computer-workbench-verification.md)。

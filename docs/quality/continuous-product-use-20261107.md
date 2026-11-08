# 连续产品使用与共享链路修复

> 文档类型：质量记录
>
> 状态：当前
>
> 最后核验：2026-11-08

## 范围与方法

基线为 `7670e346` 的未提交工作区，保留此前源码审查和培养方案验收的改动。本轮沿用户流程继续使用可见 Electron 开发客户端；真实模型为已配置的 `deepseek-v4-flash`，没有替换工具输出或模拟产品 API。运行数据隔离在 `desktop/output/user-journey-20261107/runtime`，未重装或修改已安装客户端的数据。

工作区业务输入为本地建立的发布需求、错误计价函数、短篇创作、像素招牌和故事分镜需求。截图、DOM 快照、命令日志和业务文件留在被忽略的 `desktop/output/user-journey-20261107`，不提交数据库、凭据或日志。默认开发 Bundle 只有 Data、Workspace、Music、Visualization、Story 五项；后续用既有签名安装服务，在隔离 QA 目录安装了本地源码构建的 Pixel、Comic，未改默认发行配置。安装准备经过签名验证与精确包指纹复核，只在该 QA 目录登记开发发布者，不能计作界面安装流程验收。本记录不代表 13 个 DLC 或 271 项操作全部通过。

## 已定位并实施的修复

| 问题 | 真实触发与根因 | 修复落点 |
|---|---|---|
| 并行写入审批提前恢复 | `run_ea8c4cfdd2ba4d298baaefd023458b0b` 同轮申请两次写入；只批准一项就恢复模型，另一项没有 native function output，最终 Provider 400，计价文件没有写入而清单已宣称完成 | Run Repository 根据未结算的 Approval/Question 计算等待状态；审批批准、拒绝和过期都经过此边界，不增加第二份等待状态 |
| 待批操作显示“已拒绝” | 时间线把尚未决定的审批归为拒绝；底部只取最后一项，文件目标和正文难以核对 | 显式 pending 展示、按当前 Run 顺序逐项处理、待批数量、文件路径与可展开的实际参数 |
| 取消后排队任务像卡住 | 前一个 Run 取消后，后端已推进下一项；前端停止会话流后，只检查刚取消的 Run，漏接后继 | 取消后复用 `openConversation` 恢复当前任务；传输层依据权威快照续接同会话的后继 Run，继续使用原 cursor 和取消 fence |
| 合法隔离命令被一律拒绝 | Workspace manifest、编译器和 Registry 都支持隔离 `subprocess`，PolicyGate 却无条件禁止 | PolicyGate 仅对 `isolated_process` 允许该能力；同进程注册仍拒绝，审批与 signed manifest 权限保持有效 |
| 虚假的远程排队任务 | 之前真实工作簿任务转入 `remote_job_submit` 后永远 queued；源码只创建 Artifact，没有执行端 | 移除生产装配、默认快照身份、注册入口和空壳实现；有真实执行端之前不再向模型提供这些工具 |
| 资源版本改变使整个 Run 崩溃 | 故事 `run_f9d4d3b687de46539701ff485ab7dd5d` 首次创建人物成功后，后四次 Invocation 的冻结版本过期，scope 校验抛出的预期 ToolInputError 逃逸 | Dispatcher 把进入 leaf 前的预期拒绝纳入正常 Observation 结算；保留原 Invocation refs，不自动升级版本或重放写入 |
| 新项目读取故事世界返回 500 | `worlds.get` 在世界不存在时返回 None，声明的 WorldOutput 却不允许空值；UI 把错误掩盖为空状态 | Story owner 的读取操作返回明确的 `{world: WorldOutput \| null}`，对应前端同步消费该合同 |
| 文件成果只能看到元信息 | 点击发布清单只显示 Code Patch、路径和 hash，无法阅读实际文件 | Workspace owner 用现有 Representation 注册点提供有界文件读取；复用现有 FileContent 展示 Markdown、源码和分栏 |
| 成果图标丢失文件语义 | Markdown 被归为代码、文件快照被归为通用成果、Visualization document 被归为包裹 | 统一展示入口识别文件成果的文件名，并在正文、成果列表和 Dock 使用已有的 Markdown/语言图标；无新图标依赖 |
| 故事补检指令不够可执行 | `run_18196b1301c947888c94d87c975f5e59` 保存章节后，读章节、列修订并重复最终回答，没有真正执行写后的 graph check，最终 NoProgress | 复用现有 CapabilityGuidanceSpec，Story owner 明确读设定→逐项写入→写后查设定；完成拒绝理由明确指出所需调用，保持检查条件 |
| 简单持续低音无法表达 | 8 小节真实音乐任务要求每小节一个左手音，现有四种模板最少产生两个音；模型另有拍位从 1 开始的错误 | 在原有展开器增加 `sustain_bass`，拍位与时长直接在规范 Pydantic 字段说明；Compose 工具版本升至 3，指导版本升至 2 |
| 同轮多次提问或提问与审批混用崩溃 | Question 请求只允许 running，第二次请求从 waiting_input / waiting_approval 抛 QuestionConflict；查重按整个 Turn，会混淆 Invocation | 请求允许运行中的等待态，按唯一 ToolInvocation 关联问题，复用既有等待状态刷新；无新表、等待队列或协议 |
| 文件搜索发现能力不匹配 | 名称查找只列当前目录，空 query 又被拒绝；模型反复绕到 grep/命令 | 非空 query 做有界递归的文件名/路径字面搜索，空 query 列直接子项；搜索与 grep 共享全局扫描预算，目录和忽略项也消耗预算，跳过链接目录循环 |
| 合法大文件最后一页不可读 | 服务接受 1 MiB 文本，但 offset 最大只有 1,000,000，最后不足一页无法读取 | 读合同上限与文件字节上限对齐到 1,048,576；读取工具版本升至 2，保留有界分页 |
| 故事工作台缓存与窄 Dock 布局 | Agent 保存后已有视图仍持有旧目录；窄面板两栏挤压，章节标题竖排、正文溢出，章节模式还显示人物表单与假“载入中” | 激活、切换和显式刷新读取 owner 数据；复用 Host 已有 CSS container，窄栏上下布局、正文独立滚动，按模式呈现对应表单，时间本地化 |
| 正规风险值显示未知 | command_run 的权威风险为 danger，前端只识别 high/critical，实际审批显示“风险待确认” | 既有 riskLevelLabel 接受规范 danger；真实审批已显示高风险。工具摘要的通用等待文案改为“等待处理”，避免把业务提问说成授权 |
| 并发启动的目录探针互相占用 | 扩大回归真实出现 WinError 32：两个进程同时打开、删除固定 `.write_test` | 根目录与子目录使用标准库 TemporaryFile 的独立文件和自动清理；无重试、进程锁或权限放宽 |
| Pixel 后台检查解锁其他读取 | poll 即使没有发起刷新也清除 loading，使进行中的手动读取提前解锁；固定反例在修改前失败 | 复用现有 read Controller 识别读取归属，只有持有者结束/取消时释放状态；后台 head 返回后重新检查读取状态 |
| 创建操作先打开额外查看页 | 实际点击“创建像素作品”出现两个同名标签；Host 对创建先调用 open，再调用 onAdd，项目设置页也如此 | 创建直接调用 owner 的 onAdd，查看调用 onOpen；Pixel 声明已有的 onOpen 合同。Story onAdd 返回真正的异步任务，让 Host 可接住错误 |
| 报告混淆开发完成与验收通过 | 真实周报首次将文档“已完成”写成“通过（待回归）”，已拒绝该写入并要求改正 | Workspace 通过已有 CapabilityGuidanceSpec 约束静态判断、写入和执行证据的区别，以及有界搜索的结论范围；这是模型指导，不是模型准确性证明 |
| Pixel 数组绘制拒绝后反复检查 | 两次真实接力为 16×16 的 stamp 传入 258 个像素；旧校验只有泛化 value_error，模型改为检查而未修正数组 | 复用 PydanticCustomError，返回 `pixel_stamp_pixel_count_must_equal_rectangle_area`；字段说明写明行序和精确数量，写工具版本升至 2，owner 指导优先使用简单图元。保持原子拒绝，不截断、补齐或部分写入 |
| Pixel 标签无法恢复具体作品 | 编辑器把文档选择放在组件局部状态，Host 持久化的仍是作品目录视图 | 作品摘要提供唯一文档 target；通过已有 openWorkbench 打开具名标签，恢复时按该 target 读取 owner 数据，返回目录复用目录标签。Artifact 的固定版本引用保持独立语义 |
| Pixel 首次手势有时被清理 | 手势注册与停止清理处于被动 effect，首帧输入可能先于 effect；清理又可能影响新手势 | 仅将必须在绘制前完成的手势注册放到 useLayoutEffect，并校验当前 active 状态；复用原有手势上限、取消和读取归属。未增加全局监听层或重试绘制 |
| Pixel 工作台图标不一致 | 作品入口使用单独手绘的网格图标，与 Host 文件和图片展示不一致 | 采用 Host 已有 ResourceIcon 的 image 类型，无新增图标库 |
| 创建分镜后输入预算拒绝变成运行时崩溃 | 七个扩展激活时，创建 Comic 资源后新增可发现工具，下一次 prepare 抛 ContextBudgetExceeded，Coordinator 只结算为 AGENT_RUNTIME_ERROR | RunLoop 捕获既有类型，经 Terminalizer 结算为固定安全错误 AGENT_CONTEXT_BUDGET_EXCEEDED；提示减少引用或停用无关扩展并重启，不扩大预算、裁剪必要工具或重放写入 |
| 固定成果冷启动显示不可用 | 从工作台导出的 Action Run 属于独立 Session；标签保留了 Artifact ID，内容却只从当前聊天的内存投影查找 | 增加 Project 范围的单成果信封读取，直接查询既有 Artifact→Run→Session→Project 归属，恢复到原 artifactsById。Dock 仍只保存身份，无新增 SDK 字段、信封副本或自动重新导出 |
| Comic 查看入口多一层空壳 | 项目菜单先打开 Host 中转标签，再点一次“打开 Comic Studio”才进入实际作品库，图标为字符符号 | Comic 声明现有 onOpen 和 objectKinds，直接打开作品库及具名作品；入口与标签复用 Host 标准文档图标 |
| 余额不足误报为参数配置错误 | 真实连接探针返回 SDK APIStatusError、HTTP 402；Agent 归为 request rejected，连接测试另用通用失败文案 | SDK 公共边界统一 HTTP 状态分类，402 使用既有额度错误且不可重试；Agent、连接测试和模型列表共用。设置页通过已有 ApiError 保留安全原因 |
| 深色分镜上的角色名难以辨认 | 实际打开工作台与独立 HTML，深色文字落在深色面板上 | 共用 SVG 渲染器为角色名增加白色描边；不修改规范作品数据或新建渲染链 |
| 文件写入保护在两条入口不一致 | 工具入口检查已有文件的 hash，共用 Service 和 public operation 却允许无 hash 覆盖；工具检查还在写锁之外 | 新建与覆盖的前置条件统一放在 WorkspaceService，未提供 hash 只能创建新文件；工具与 operation 消费同一种固定冲突，后者返回 WORKSPACE_CONFLICT / 409 |
| 暂存期间的外部修改仍可被覆盖 | 实际文件系统故障注入在暂存时新增目标或保存新内容，旧代码继续 replace；移动也会覆盖预检后新建的目标 | 覆盖的 hash 检查移到暂存完成后，新建采用不覆盖发布；Windows 移动使用拒绝覆盖的 rename。沿用 owner SQLite 写锁，不新建锁服务 |
| 写入成果可能记录后来的人类内容 | 写入后重新读取目标，外部编辑器此时保存会让返回值和 Artifact hash 指向他人的后续内容 | 从实际提交的字节构造原有 WorkspaceFile；后续外部变化由既有 Representation 检查拒绝，不作为本次写入结果 |
| 文件变更无法正常刷新 | 真实 UI 中外部新增文件不进入树，重复选择已打开文件仍显示旧内容；分页失败只让用户关闭重开 | 增加显式刷新，同时读取目录与当前文件；保留查看模式和冲突前缀，用 AbortController 取消旧读取，迟到分页不能拼入新版本 |
| 文件目标另存一份缓存 | FilePreview 用 fileState 重复保存 Dock 已有的路径与绑定，缺少 stateKey 的目标会共享空键 | 删除该缓存，直接读取规范 target；不新增身份映射、文件 DTO 或持久化内容 |
| 排队任务误报模型等待 | 等待审批期间的后继 Run 在 SQLite 为 queued、零 Turn，真实界面却显示“正在等待模型响应”，既有测试也断言了此错误文案 | UI 先按权威 Run.status 区分“已排队”和“正在准备任务”，运行后再使用 phase；排队使用标准时钟图标 |
| 审批主界面暴露内部工具编号 | 真实审批卡片显示带 owner hash 的 wire name 和英文默认理由 | 默认理由复用已有 ToolPresentation.title；风险、目标与决策继续可见，内部编号与完整参数放入可展开详情；审批规则与耐久身份不变 |

## 复用与边界决策

1. 审批、提问、取消、scope 拒绝都修在既有权威边界，未创建新的状态机、调度器或兼容执行链。等待事实仍来自 SQLite；SSE 和 Zustand 只做投影。已开始执行的 Invocation 若无法核对结果，仍结算为 TOOL_OUTCOME_UNKNOWN，不能当作明确失败后重放；尚未执行的旧版本请求才正常拒绝。
2. 文件预览直接采用现有 Artifact Representation 和 `host.ui.FileContent`，复用 WorkspaceService 的路径约束、1 MiB 文件上限及 FileReadInput/Output 的 12,000 字符分页。请求不能改写文件路径；来源 refs、当前绑定版本和内容 hash 必须匹配。文件变化返回 SOURCE_CHANGED，绑定撤销或路径不可用返回 SOURCE_UNAVAILABLE，不以最新内容替换历史成果。
3. 已调查项目的注册、隔离执行、DLC Operation、Representation、音乐规范模型和伴奏展开器；查阅了 [Pydantic 官方 JSON Schema 文档](https://pydantic.dev/docs/validation/latest/concepts/json_schema/)。使用已有模型的 Field 描述表达拍位，未引入 schema 映射表或自制 JSON 解析器。
4. 无新增依赖、迁移、API v2 符号或通用中间层。Story 的空值读取 envelope 是该真实 Operation 边界的返回合同，不复制 World 字段，也不同时支持两套内部形态；同一签名 DLC 包同时交付前后端。
5. 远程任务属于缺少真实执行端的领域空壳，不是 Kernel 必须保留的职责。内置工具集合与物化 hash 有意更新；冻结 Run 不能静默换实现，旧 Artifact 仍由既有未知历史类型 envelope 读取机制处理。未来需要远程执行时应由具备实际回执、状态和取消闭环的 owner DLC 提供，不在 Core 保留假队列。
6. 文件发现复用 os.scandir、heapq 和原来的 Workspace 数据模型，不创建文件索引；可写性探针复用 [Python TemporaryFile](https://docs.python.org/3.12/library/tempfile.html#tempfile.TemporaryFile) 的原子独立创建与清理，替代固定名的竞态探针。Dock 布局使用 Host 已有的 container sizing，不引入 ResizeObserver 镜像布局状态。
7. Pixel 的输入拒绝采用 [Pydantic 官方自定义验证错误](https://pydantic.dev/docs/validation/latest/concepts/validators/#raising-validation-errors)，而非解析异常文本或另建输入修补器；绘制前的生命周期注册采用 [React useLayoutEffect](https://react.dev/reference/react/useLayoutEffect)，网络读取仍沿用现有异步生命周期。没有引入依赖、兼容层或双份文档身份。该 effect 会阻塞绘制，范围仅限必要的手势注册与清理。
8. 调查了 PromptAssembler、Evidence Ledger、ProgressGuard 和[当前工具发现决策](../architecture/bounded-tool-discovery.md)。此 QA 组合向模型提供 46 个完整工具，schema 估算 22,943 tokens，默认上下文预算为 32,768；旧轮次可被整批移出窗口，错误仍进入有界证据账本。未知 Provider 当前使用完整 schema 是已接受边界，本轮未增加自制 tool search、领域筛选器或预算 fallback，也未把模型反复改画推定为 Core 丢失全部错误。
9. 成果恢复先调查了现有 Run-artifacts 读取、Host openArtifact、Dock identity 和 Repository。旧读取要求 Session/Run ID，标签有意只保存 Artifact ID；因此在真实 HTTP 边界新增 `GET /projects/{project_id}/artifacts/{artifact_id}`，返回原有 Artifact 模型，使用既有生成客户端与解析器。未向标签复制信封或追加一套身份映射。读取是 Core 通用职责，DLC 不能自行从 Host 冷启动内存推断 Session/Run；这项修复不新增 Kernel 状态、SDK 符号、迁移或领域规则。旧成果内容仍经原 Representation 校验。失败、取消和 generation 变化不提交迟到结果；显式重试重新读取，不重新执行导出。
10. 核对项目 SDK 工厂、Agent 分类器及诊断 API，并查阅 [DeepSeek 官方 HTTP 状态](https://api-docs.deepseek.com/quick_start/error_codes/)与 [OpenAI 官方错误合同](https://developers.openai.com/api/docs/guides/error-codes#api-errors)。将原有 ProviderFailure、状态分类及 Retry-After 解析移动到既有 `engine/llm/providers/openai.py`，两种调用共用一个实现。402 是明确的额度失败；429 继续区分结构化账单错误与暂时限流。未解析上游原始报错文本、增加 provider-name 分支、兼容协议、依赖或第二套错误模型；未知异常仍使用原安全诊断。原始上游正文不进入 UI 或业务日志。
11. 文件提交调查了既有 Service、工具/public operation、历史提交、标准库 [os.rename / os.replace](https://docs.python.org/3.12/library/os.html#os.rename)及 [os.link](https://docs.python.org/3.12/library/os.html#os.link)，并比较了已归档的 [atomicwrites 实现](https://github.com/untitaker/python-atomicwrites/blob/master/atomicwrites/__init__.py)。保留现有 NamedTemporaryFile、fsync 与 SQLite writer reservation，仅在真实文件系统边界区分新建和覆盖：Windows 用不覆盖的 rename 发布新文件，POSIX 用 link 发布；覆盖经提交前 hash 检查再 replace。未引入已归档依赖、通用文件包装器、重试链或第二份文件模型。当前真实验证平台仍为 Windows；提交前检查与 replace 之间不构成外部编辑器参与的原子 CAS，不宣称消除了任意时刻的外部竞态，非 Windows 移动也未通过真实 Runner 验证。
12. 文件刷新沿用 Host operations 的 AbortSignal、现有目录模型与 FileContent；没有增加文件索引、磁盘监听或自动轮询。FilePreview 以 Dock target 为身份事实源，刷新读取最新内容；固定 Artifact 仍执行原来的来源 hash 校验。审批优化只修改默认展示理由与详情布局，不改变 Kernel 的批准条件、决策顺序、ID、Schema 或 SDK；DLC 无法修改 Core 共用审批卡片，因此在现有 Policy/React 展示边界修复，无新增 Kernel 状态。

## 真实业务证据

- 发布需求→读取 TypeScript→批准修改→更新清单：`run_c3e7ab3e9fd34ed1b1651c7c651a687c` 实际保存两个文件并完成。模型先前错误拒绝 100% 折扣的写入被人工拒绝；修正后的代码独立执行 6 组正常金额（含 100% 折扣与半分舍入）、7 组非法输入，均通过。这个有限样本不能证明任意金额精度都正确。
- 两项同轮写入：`run_807ec50a7b2d467da92916121bf1b380` 批准第一项后仍为 waiting_approval，另一项仍 pending，两文件都尚未落盘；全部批准后两项执行并完成，没有再发生缺少 function output 的 400。之后第三个文件是下一轮独立审批，不属于同一个并行批次。
- 文件展示：`markdown-dock-after.md/.png` 记录真实 Dock 的标题、表格、任务列表、源码/预览/分栏与对应文件图标；`checklist-dock-before.md` 记录改前仅有元信息。
- 取消与排队：`run_03b5998279d746ec9eb1222a1612247a` 停止后，同会话 `run_7f6b9f94bb444778888a715495a60d60` 无需重载即可显示完成结果 323；证据为 `queue-cancel-restored.md`。
- 命令：`run_9feefa89780e425caaccb9f9d23f7c62` 在客户端经三次具体命令审批，实际调用本机 Node，输出 398、358.2、0；数量 0 抛 RangeError，exit 0。`node-execution-approval.md` 留有规范高风险标记。
- 故事：5 个实体、6 条关系已在 UI 接受并提交为首个不可变修订。新增指导后 `run_05eaf6b827b749d88c383198a78cd548` 完成第二章《返件》，读回发现引号缺失后用版本校验修改同一章，没有新建重复章节，并执行写后 graph check。`story-second-chapter-visible.md` 确认章节内容与 v1/v2 历史；`story-dock-responsive.png` 确认窄 Dock 可阅读。此前仍有一次 Provider 流失败与一次 NoProgress，均保留历史事实。
- 音乐：`music-studio.md` 与 `music-playing.md` 记录真实乐谱打开、播放切换和停止。新模板真实复验 `run_1a56eb02ab2044d2a7671460821fa213` 完成；独立只读检查新 score `score_0485a8cbe1c249c0aba96a5d473379ec` 的 8 个小节均恰有一个左手音，beat 0、duration 4。旧 score 保持原来的两个左手音，没有改写历史。未通过音频采集确认听觉质量。
- 提问→报告：`run_09bd7da63cdd4f89903968394ae4bd60` 真实模型同轮提出两个独立问题；先回答第二个后，SQLite 仍 waiting_input、1 answered / 1 pending，未开始写入。两项回答后进入文件审批。首版验收语义不准确，拒绝后新指令 `run_537f5ea1dd72492788b3465b98a4a35d` 修正、获批、保存并回读。`weekly-markdown-dock.png` 留有渲染证据；其业务结论仍需审阅，不能把报告成功保存等同于内容正确。
- Pixel 人工编辑：实际创建 16×16 透明作品、拖动绘制保存为 r2、框选旋转保存为 r3、复制第二帧保存为 r4；手动刷新后两帧与内容仍在，播放切换为暂停后正常停止。`pixel-stroke-saved.md`、`pixel-frame-duplicated.md`、`pixel-animation-playing.md` 记录这些交互。
- Pixel 模型接力：第一次 `run_bb045f179b2d4dd481ecd4fbdb037ec9` 的错误 stamp 被原子拒绝，之后只成功修改调色板到 r5；反复检查后人工停止。加入明确错误合同后，第二次 `run_bd75811b08794e4baeeb13877036f8b1` 仍传入同样错误数量，最终 AGENT_NO_PROGRESS，不能记为修复后的模型任务通过。新会话重新引用作品并要求使用矩形与线条，`run_7640304849d9412fa2c91b7dfe555e1d` 成功画出钟面，但继续改到 r11；在界面通过“补充当前任务”要求按当前版本交付后，同一个 Run 消费该指令并 completed，没有新建替代任务。其自主收尾仍未通过。
- Pixel 数据与交付：独立只读核对 r4 与 r11，图层及第二帧完全一致，第一帧已改变；第二帧规范 JSON 的 SHA-256 为 `150f30b22a4392a99a50dc759bded102323fdeffd6fb781d2d0d0cabda30ae46`。冷启动后具名作品标签恢复到 r11（`pixel-cold-restored.md`、`pixel-final-cold-client.png`）。通过实际下载按钮和 Windows 保存对话框导出 16×16 当前帧 PNG、32×16 两帧 Sprite Sheet，两者均为 RGBA，包含透明像素；逐像素核对导出两帧与规范文档均相同，记录在 `pixel-final-export-verification.json`。浏览器 download 事件没有收到通知是该原生保存流程的自动化边界，不能据此判定产品导出失败。模型最后涉及 Music/Pixel 工程文件导出的笼统表述不能替代这些实际 PNG 证据。

## 第二阶段：Comic 与跨模块恢复

初次测试沿用前述六个扩展并增加 Comic。`run_68fe7c6979e341bf8be86db662de2de9` 读了两章并创建唯一
作品 `comic-7842c10bb8b14e018fcee76905508389` v1，随后工具 schema 超过输入预算。修复错误边界后，
同会话 `run_388db204be964b4cadbe06dcef3c99e1` 在模型调用前正常结算为
AGENT_CONTEXT_BUDGET_EXCEEDED；`context-budget-client-after.md` 留有明确的恢复指引，已有作品未重复创建。

通过产品扩展设置停用 QA 中暂时无关的 Data、Workspace、Music、Visualization、Pixel，点击“立即重启”
后只激活 Story 与 Comic；期望状态和实际状态按原产品合同分开。新 Run
`run_43e2a828b7774cdb9f1708b9496571cf` 使用 33 个工具、schema 估算 16,476 tokens，读取原两章，
在同一作品创建一页三格和 12 个元素到 v2，并修正到 v5。第 9 Turn 请求被 Provider 拒绝；检查耐久
原生历史时未发现重复 call_id 或缺少 function output，不能据此认定上游故障或请求构造已完全正确。
后继短任务的首次模型请求也被拒绝，故不能把问题仅归因于长历史。本轮未新增 Provider fallback，
未更换模型，也未把该任务记为自主交付通过。

随后以原配置和 OS 凭据库进行一次受控 SDK 探针，仅记录异常类型、状态码和预先限定的诊断标记，
确认当前响应为 HTTP 402、余额不足。未保留原始正文或凭据。对比标准模型名称仅发生在未保存的
设置草稿中，冷启动已确认仍使用原 `deepseek-v4-flash`。不能据此追溯认定此前没有状态码证据的
所有 request rejected 均为 402，也不能宣布长历史构造已完全通过。

分类修复后的真实 Run `run_177f658627214933a218108562032fb0` 以
MODEL_PROVIDER_QUOTA_EXCEEDED 终止，只有一个失败 Turn、零工具调用；
`provider_retry_count=1` 是既有 Repository 对失败结算的记账，不代表再次调用。
`quota-run-classified.md` 与 `quota-connection-classified.md` 分别记录聊天与连接测试显示明确额度原因。
余额恢复前停止重复在线任务；本轮未执行充值、替换密钥或持久修改模型配置。

实际使用中继续完成：

- 编辑器导出固定 v5，原生保存对话框保存 `storyboard-v5.json`（3,852 bytes）。
- 冷启动暴露固定成果标签只查聊天缓存的问题；修复后无需重新导出即可恢复同一 v5，见
  `comic-cold-artifact-before.md`、`comic-cold-artifact-after.md/.png`。
- 新签名包 `1.0.0-dev.74b89bfdbf09`、digest
  `85e9cf7fb4426197c886b2e878fd93b893e44de1d958e582a0c5813446a35c28` 装入同一隔离目录后，
  项目菜单一次查看即进入作品库，具名作品仍可打开，见 `comic-direct-library-after.md`。
- 浏览器实际排版测得两处字幕框高度 36/33 px、scrollHeight 均 39 px；从编辑器将两处规范高度调整
  为 0.15，分别保存为 v6/v7，文字和其他内容不变，溢出提示消失，见 `comic-captions-adjusted.md`。
  再从编辑器导出固定 v7，旧 v5 仍保留。此处是人类直接编辑修正模型排版，不能算模型自行检查通过。
- v7 的原生 HTML 下载保存为 9,138 bytes。独立浏览器检查发现第三格对白压住字幕；从编辑器只将该
  对白 y 从 0.12 调至 0.22，保存 v8。只读核对 v5→v8 恰有这三处几何值改变，旧 v5 JSON 与规范
  修订完全一致，没有改写历史正文，见 `comic-final-verification.json`。
- 描边修复后的最终签名包为 `1.0.0-dev.0ae99e6f2689`，digest
  `997fedbec4b928987e557cf2c3d98b613d598cdad661d7a8e6f44615af0b9176`。冷启动恢复具名作品 v8，
  导出固定 v8，实际通过 Windows 对话框保存 `storyboard-v8.html`（9,229 bytes）；内容 hash 为
  `77ddcfffb1bf2807b75bda596f6b41cc02d86053d87126f8bc61a1e5f7bfef58`。
  在只含该导出的本机 HTTP 目录独立打开，六处文本框无溢出，第三格字幕与对白不重叠，六个角色名
  具有描边；截图为 `comic-v8-final-editor.png`、`comic-v8-export-final.png`，测量记录为
  `comic-v8-layout-verification.log`。唯一浏览器控制台错误为预览服务器 favicon 404，未计作零错误。

## 第三阶段：文件冲突、排队与重启

2026-11-07 13:07 的真实“测试连接”恢复成功，见 `recovery-model-probe-result.md`。
继续使用原模型和 OS 凭据配置，没有执行充值或替换配置。通过扩展设置仅激活 Workspace，
将不需要的 Story、Comic 停用并重启，避免把先前七扩展预算失败混入本轮文件验收。

第一轮实际创建 `发布冲突验收.md`，模型读取后申请状态行精确编辑。等待审批时，人类在磁盘保存新备注，
并在客户端排队一个只读核验任务，再关闭并重启整个 Electron 客户端。
`run_6d9d3fde6f604670aedd27c21aa1b060` 的待批操作和
`run_6e3fe4e5692444d994f354c463b89e0d` 的 queued 状态均恢复，后者启动前为零 Turn。
批准旧编辑后 hash 保护正确拒绝写入，但泛化“唯一锚点”提示令模型误判原因并额外读取一次，
随后说明冲突并结束；后继任务自动执行且读到人工备注。不能把两个 Run 的 completed 状态解释为编辑成功。
证据为 `file-conflict-after-restart.md`、`file-conflict-outcome-before.md`、
`file-conflict-restart-verification.json`；一次尝试停止任务时它已自行结束，未通过取消代替收尾。

修复后的签名 Workspace 包 digest 为
`ccee6d4f2484dd385bc89db0de56c312b1b86d444bbd248ff9d3c5b1ff7ea456`。
`file_write/file_edit/file_move` 工具版本升至 2；输入字段没有新增，FileWrite hash 字段说明明确新建与覆盖的区别。
新 Run `run_4239c01e23734ab790ed861f43c99340` 先读取第三轮备注，等待审批期间人类保存第四轮备注，
并排队只读任务后再次冷启动。UI 恢复“已排队”，批准旧编辑后模型直接说明文件已变更、停止写入，
没有再次读取或调用写工具；该编辑 Invocation 只执行一次。
后继 `run_6f3f3a3176414705a65bf47a21522123` 自动完成并读到第四轮备注。
结束后的磁盘 hash 与人工保存的
`90d1a587d3e01492662b9cf3980a9b0b455a189968ed9c47b82e11bf121f1291` 相同。
见 `file-conflict-fixed-restored.md`、`file-conflict-fixed-outcome.md`、
`file-conflict-fixed-verification.json`、`queue-correct-status-real.md`。

独立的真实文件浏览与分页复验：

- `workspace-stale-before.log` 记录外部新增文件不显示、旧内容无法刷新；修复后的
  `workspace-refresh-real-after.log` 确认同一已打开文件刷新到第三轮备注，并显示外部新增文件。
- 20,043 字符、806 行、52,915 bytes 的 Markdown 含中文和 emoji。首批显示 12,000 字符，
  此时外部保存新版本，再继续读取会明确报冲突、保留前缀、禁止拼接；显式刷新后可以读完。
  从真实“源码”视图的 DOM 重建文本，其 SHA-256 与磁盘文件均为
  `be7cead9183585f00e36170c0802a98f48d8190353403da7580b97eff89cbd60`，
  见 `workspace-pagination-verification.json`。未用 API 返回值冒充界面显示内容。
- `workspace-mode-preserved-real.log` 确认刷新后保持源码查看方式；初次绑定读取失败提供重试，
  不再当作“未关联文件夹”。读取归属、迟到分页、目标切换和手动恢复另外有固定回归。
- `approval-modern-confirmation.png` 为真实待批界面；默认理由是“编辑项目文件需要你的批准”，
  内部编号默认折叠。实际展开并核对路径、前后文本与当前 hash 后才批准。

随后在原会话发出新的明确修改指令，允许重新读取并保留第四轮备注。
`run_728c894f27ab47feb6726ffc63b22d01` 实际执行读取→审批→编辑→回读→交付，三个 Invocation
均 succeeded、attempt_count 均为 1，Run completed。独立从磁盘内容反向替换该唯一状态行，
所得 hash 与写前 hash 完全一致，确认仅“待验证”改为“验证中”、人工备注保持原样；写后 hash 为
`41fef8894f92aa374108f30756803f6a90ed763c3c2796d46815251ad135accf`。
通过真实成果按钮打开 Code Patch 的 Markdown 内容也一致，见 `file-positive-verification.json`、
`file-positive-outcome.md`、`file-positive-artifact.md`。
再关闭并重启客户端后，同一 Code Patch 标签恢复，Markdown 仍显示“验证中”和第四轮人工备注，
hash 仍匹配本次写入，见 `file-positive-artifact-cold.md/.png`；未重新执行编辑来恢复视图。

## 第四阶段：导航、草稿与审批后的报告接力

继续使用同一隔离客户端，先复用已有 SQLite 三行订单，再执行“全表聚合 → 新建 Markdown → 拒绝审批 → 明确修正并重新授权 → 保存和读回 → 冷启动打开”的真实模型任务。证据位于 `desktop/output/playwright/continuous-use-20261108/`，用户安装版与其配置未改动。

### 已修复的共享路径

1. **工作台历史挤占对话导航。** 每次读取样例会创建规范的耐久 Action Run，重载界面后可见的 `Table Preview` 从 2 个变成 3 个；导出也会产生同类记录。根因在 `/conversations` 把所有 Session 都当作对话，而非结果或运行持久化错误。
   现在在同一查询、分页前按既有 `request_json.source` 排除只有终态工作台操作的 Session。真实聊天、新建但尚无 Run 的对话、后续参与了聊天的操作 Session，以及任何未结束的运行继续可见。没有按标题或具体 DLC ID 隐藏，也没有删除记录；原 Session 详情与项目 Artifact 仍能读取。冷启动与再次点击数据样例后，数据正常返回三行，导航中 `Table Preview` 为 0，原有真实对话可见。
2. **项目切换丢失对话草稿。** 等待文件审批时，在输入区写字、切换到 Default Workspace 再返回，实测输入为空；审批仍在。旧对话 Composer 使用组件内 `useState`，只有新任务接入了既有 Workbench 的 `draftInput`。
   现在两者复用同一内存事实源，按项目草稿/Conversation identity 区分。异步发送结算捕获原 Workbench key，只在原草稿仍与提交内容相同时清理，并把引用清理限定到原对话；迟到的成功不清空新输入，失败保留原草稿。没有新增缓存、同步镜像或草稿磁盘存储。冷启动修复版后，两个项目的独立草稿、审批期间切换再返回均实际恢复；验收文本随后清除。
3. **停用扩展后的旧工作台没有恢复入口。** 打开历史“音乐”标签时只剩不可用说明。Host 的 `ProjectWorkbench` 现提供“管理扩展”，进入已有扩展设置，保留原 Dock/项目身份，不自动启用或重启。真实点击已验证到达扩展页。

方案先调查了既有 Session/Run 来源、Workbench scope、布局持久化与原 Settings 路由，沿用项目内实现。查询复用
[SQLAlchemy EXISTS](https://docs.sqlalchemy.org/en/20/tutorial/data_select.html#exists-subqueries)和
[SQLite JSON 提取](https://www.sqlite.org/json1.html#the_json_extract_function)；草稿归属符合
[React 的状态生命周期](https://react.dev/learn/preserving-and-resetting-state)。
变化位于 HTTP 读取投影与 Renderer 内部状态，不改 Frozen Kernel 生命周期、Public SDK/API v2 或耐久表结构；没有迁移、兼容层、额外运行时依赖或第二种 Session 模型。

### 真实任务结果与限制

- 首次 SQL 因 SQLite 复合查询的排序表达式而被执行端明确拒绝，Agent 随后改写成功；没有卡住或把失败当成结果。
- 我在批准前发现报告 SQL 把分组行和合计行再次做窗口求和，存在重复累计列，于是拒绝写入。Agent 明确说明文件未创建，也没有自行重试。之后给出明确的修改指令，模型使用分组统计与独立全表查询，重新申请审批，批准后写入并读回。
- 这不是模型一次自主交付通过：首次 SQL 和重复累计列仍是业务质量问题；本轮未给所有 SQL 增加专用规则或通用自然语言结论校验器来掩盖模型错误。
- 最终文件 `desktop/output/user-journey-20261107/学分分析验收/订单概览.md` 显示已完成 2 笔 / 1627.00、待处理 1 笔 / 169.00、全表 3 笔 / 1796.00。正常成果入口与冷启动后 Markdown Dock 均显示相同表格，没有页面横向溢出。
- 独立读取磁盘文件：2288 字节、51 个实际换行，没有被转义成普通文本的换行标记或错误的 `grand_amount_check`；SHA-256 为 `ab40d29442c7b80577384e6922654d3cd884840e10075e838c9e922340081be3`，与实际读回和界面元数据一致。既有 `发布冲突验收.md` 的 hash 仍为 `41fef8894f92aa374108f30756803f6a90ed763c3c2796d46815251ad135accf`，未被本任务修改。
- 临时启用的 Data / Visualization 已从界面恢复关闭并等到真实开关状态更新；其余可选扩展仍关闭，必需 Workspace 保持开启，客户端正常退出。首次清理日志在开关请求完成前读取了旧值，不作为恢复成功证据；以 `qa-cleanup-verified.log` 为准。

固定回归中，修正有效 fixture 后的导航反例在改前为 4 failed / 6 passed，草稿卸载反例在改前为 1 failed / 9 passed。初始导航 fixture 把 `session_sequence` 留成 0，额外触发了投影合同错误，已修正；不把这三项无效 fixture 失败计作产品缺陷。最终相关后端 30 项、前端全量 743 项通过；最后恢复入口调整另复验现有 5 项，不与全量相加。

截图：`action-thread-clutter-before.png` / `action-thread-clutter-after.png`、`draft-restored.png`、`disabled-workbench-recovery.png`、`report-table-verified.png` / `report-cold.png`。`action-preview-ui-verified.log`、`draft-ui-verified.log`、`approval-retry.log`、`report-cold.log` 记录实际界面结果。

## 第五阶段：三维成果、动画连续编辑与可玩样片

在同一隔离原生客户端中，通过正常安装界面安装并启用 Scene、Animation、Game 的签名开发包，继续探索三种非数据能力。最后使用的版本为 Scene `1.0.0-dev.4708054220ec`、Animation `1.0.2-dev.f0ccd7726034`、Game `0.1.0-dev.593f30a5fc9e`。完整包逐一通过签名、完整性及 Python/JavaScript 语法检查，没有绕过信任或激活边界。证据位于 `desktop/output/playwright/creative-workbench-20261108/`。

### 实际作品与确认的限制

- **三维小场景。** 通过层级、数值检查器、材质、灯光和相机制作“雨夜修表铺 · 灯与钟”：12 个对象、6 个材质、1 台主镜头。导出 v54 GLB 后独立核对 glTF 2.0 文件头、长度、节点、材质、相机和 `KHR_lights_punctual`。文件 14820 字节，SHA-256 `c405d0b9441aae1decb62dae27d43d285c0c20206de961f5695800e5a159dce9`。随后在当前场景中新增验证球到 v57、13 个对象，旧 v54 成果继续读取固定版本的 12 个对象。原生 Save 对话框实际完成保存，不把发起 Blob 下载当作落盘证明。
- **六秒循环动画。** 新建“雨夜修表铺 · 六秒摆动”，设置 6000 ms、30 fps、循环，旋转 Z 轨道在 0 / 3000 / 6000 ms 为 -0.6 / 0.6 / -0.6 rad。实际定位 1500 / 4500 ms 均为 0 rad，播放从末尾回到起点，暂停生效。v10 JSON 实际下载 959 字节，SHA-256 `6facc23a21210844af836c0a84472f10c98156e3a72fc90ad340c94e194b75af`，与成果 fingerprint 相同。随后新增标记到 v11，三行关键帧和已展开的列表仍在。此处是明确标注的局部 XY 运动预览；人类界面尚缺公开 Scene 成果对象绑定入口，不能声称已经让该三维时钟在完整场景中播放。
- **游戏工作台。** 创建“雨夜狐狸 · 生存样片”并添加可编辑的狐狸生存示例，实际连接 Phaser 4.2.1 执行器。v2、seed 42 的静止正式测试在 tick 785/3600 失利，报告包含生成、重叠、扣血和结束事件。随后把获胜规则改为 600 tick、场景更名为“森林 · 十秒演示”，形成 v4；带 2 条实际预览输入、seed 1 的正式测试得到 `won · 600/600 tick`，新旧报告分别保留。再次使用键盘向左移动的真实预览也走到 tick 600 获胜，连续重置五次只保留一张画布。v4 报告实际下载 2886 字节，独立读取 `source.version=4` 与 `report` 中的获胜、600/600 tick、seed 1 和引擎版本；SHA-256 为 `18688d4b47ac366667d2a6c345d5b22e3fbca798e9e06bc60d13729e1424994e`。
- **在线 Agent 限制。** 首次交给 Agent 的“三维场景 → 公开对象绑定 → 六秒动画”任务被模型服务额度/账单限制阻止，未开始执行工具。本阶段没有伪造模型结果或切换到模拟 Provider；以上创作来自正常工作台的人类操作，在线自主接力及完整 Scene/Animation 组合继续待验收。

### 源头修复与复用依据

1. **Scene 成果只有下载、没有画面。** workspace 成果页现通过已有公开 Representation 分页读取确切版本，逐页校验版本/hash/一致性，复用同一 Scene 分页投影和 Three 视口。只读模式去掉编辑辅助物、网格和写操作；保留主镜头、自由观察、聚焦及明确标注的工作室补光。inline 不创建 GPU。没有复制渲染器、添加模型或新 SDK 接口。关闭、隐藏、失活及读取取消均沿用既有生命周期清理。
2. **作品只保存在库组件的选择状态。** Scene 与 Animation 的创建/选择改为打开已有规范 Dock target，带作品名与准确 object/authority；不用额外映射或同步表维持身份。Animation 的几何符号也替换为既有 Host `clapperboard` 标准图标。Scene 聚焦同时同步自由镜头选项，避免实际视角和下拉框不一致。
3. **动画每次保存卸载整个内容区。** 原代码刷新时先清空 snapshot，导致关键帧列表、焦点和内容区反复重建。现在同一文档刷新保留内容组件，读取期间锁住编辑，耐久读回后更新；错误路径撤下失效内容。实际 v10 → v11 保存保留展开列表，延迟读回回归同时验证了编辑锁与单次提交，没有乐观改写版本。
4. **Game 初始化前销毁抛异常。** 创建示例时，旧预览清理无条件调用 `headlessStep`，在 Phaser 的 SceneManager 尚未就绪时强行销毁。真实浏览器反例在修复前 12 次提前取消均出现 `undefined.sys`。现在保留官方 `Game.destroy` 的下一帧销毁，仅当 Phaser 已运行且本工作台停下其循环时显式推进清理帧。修复后真实 Phaser 的 12 次提前取消、2 次就绪销毁、重复 destroy 全部通过，无浏览器异常、残留画布为 0；原生客户端的编辑/切换/五次重置也未再出现该错误。没有 catch 吞错、私有 `runDestroy` 调用或生命周期兼容层。
5. **作者验证入口不能编译当前图标导入。** 既有 author build 没有使用前端 tsconfig，无法解析全局图标的 `@/` 路径。构建复用 `desktop/tsconfig.app.json`，没有另建 alias 表。新增实际 Phaser 生命周期脚本与原生用户证据分开保存。

调查依据为项目已有公开 Representation/分页/Three 视口和 Phaser runtime；参照
[Three OrbitControls](https://threejs.org/docs/pages/OrbitControls.html)、
[Three 资源释放](https://threejs.org/manual/en/how-to-dispose-of-objects.html)、
[Phaser 4.2.1 Game 生命周期源码](https://github.com/phaserjs/phaser/blob/v4.2.1/src/core/Game.js#L643)与
[TimeStep.stop](https://github.com/phaserjs/phaser/blob/v4.2.1/src/core/TimeStep.js#L826)。
复用现有成熟实现并在真实 Representation 边界做一次操作适配；未新增运行时依赖、公共协议、迁移、跨 DLC 私有访问或 Frozen Kernel 变更。

阶段验证：前端全量 118 文件、751 passed；此后 Game 源码修复再跑相关 2 文件、8 passed，实际 Phaser 生命周期 14 次通过。Scene Artifact/Animation 组合后端 34 passed，原生 Three/动画针对性前端 22 passed，原生 Three Mixer/曲线/裁剪等 Node 检查 5 passed；测试类型通过。生产构建及 Token/bundle 门禁通过，初始入口 647746 B / gzip 195732 B。lint 0 errors、25 条现有 warning。实际包升级和执行证据独立于这些测试结果。

本阶段保留的后续问题：Scene 对象绑定的人类入口；Game 多次 Playtest 标签同名时的版本区分；Voxel、Shader、GitHub 及更多失败/断线组合。以上没有因本阶段通过而标为完成。

正常关闭客户端后从同一隔离 profile 冷启动，具名 Scene 标签直接恢复到 v57、13 个对象；旧 Animation v10 成果可重新进入当前 v11 文档。游戏 v4 工作台、两个历史 Playtest 继续可读，并再次导出固定 v4 游戏成果，只读 Phaser 预览也实际播放到 tick 600 获胜。冷启动记录含一条执行器旧 lease 的 `playtest.detach` 409 拒绝；没有 `sys` 异常或作品不可用，不将日志称作“零错误”。此外，当前场景推进后再次保存的 v54 GLB 与首次导出逐字节相同。

收尾通过正常设置界面将 Scene、Animation、Game 的启用标记恢复为 false，确认其他可选扩展也为 false、Workspace 为 true，随后正常关闭隔离客户端和作者验证进程。作品与签名包保留在 QA profile 中；用户安装版和其密钥、数据未改动。

## 第六阶段：纠正验收主体，实际由内部 Agent 创作

用户指出第五阶段的人工搭建不能证明 Agent 能完成工作。这一纠正成立：基础几何体来自 Scene 既有能力，先前作品的组合、编辑由操作者完成。以下重新验收只通过对话给内部 Agent 高层需求，操作者不提供对象参数、不补建物体、不补动画关键帧。隔离客户端、原有模型 `deepseek-v4-flash` 和 OS 凭据不变；此次在线调用已经恢复，不能继续用早先的额度错误解释当前行为。

### 原始失败与修复

首次要求独立创建修表铺、固定场景、绑定确切对象的六秒动画。`run_f0270941f2114ce7a11aafb50028af56` 执行 17 Turn / 27 调用，消耗 534020 token，却只新建空场景和两个材质，反复检查和改写计划；通过正常停止入口取消，持久状态为 `cancelled`。

沿真实 Turn / Invocation 和源代码发现两个通用缺陷：

1. 进度指纹包含计划文案及状态，重写计划可在没有新增领域事实时清零停滞计数。删除这部分指纹输入，沿用既有 Artifact / 有进展 Observation 的耐久证据；保留计划和完成约束。实际生产 Loop 的反例确认反复改计划被 `AGENT_NO_PROGRESS` 终止。
2. 52 个工具 schema 约占 24259 token。旧 32768 预算下第 10 Turn 丢弃全部 9 个原生历史 batch，`response_item_tokens=0`。现在只逐个移除最旧完整 Turn，最近一个完整模型/工具 Turn 不能静默丢掉；放不下时走已有 `AGENT_CONTEXT_BUDGET_EXCEEDED`。默认输入上限调整为 65536，显式小上限保持有效，调用数、轮数、超时和总成本限制不变。

先调查既有预算规划、原生 ResponseItemBatch、已有 native tool search 和官方原生上下文要求，再修复 Core 所属边界；没有新增依赖、发现层、领域重试、mapper 或第二种事实状态。[决策依据与成本权衡](../architecture/agent-context-continuity.md)记录调查和 Kernel 边界。

### 真正由 Agent 完成的交付

修复并重启隔离源码客户端后，仅提交一条继续完成的自然语言请求。没有重放取消 Run；新 Run `run_f05d55ba437441e99d8288ac16121b37` 使用 Agent/Prompt 4.1，最终持久状态 `completed`，21 Turn / 23 调用，其中 22 成功，1 次 `target_create` 参数被严格拒绝后由 Agent 自行改用 `scene_bind`。

| 成果 | 实际内容与身份 | 操作者核验 |
|---|---|---|
| Agent 独立创作 · 修表铺 | Scene `acaf3608c6244698b4f070c6566ec940` v10，35 对象、6 材质；木柜、桌灯、摆钟、凳子、地毯、两面墙、3 灯光及主镜头 | 点击 Agent 固定成果，在真实 Three 视口观察并截图；原生保存 GLB 后核对 glTF 2.0 文件头、35 节点、6 材质、1 相机和灯光扩展 |
| Agent 独立创作 · 摆钟六秒循环摆动 | Animation `9e30885b417d4945987e3739e91237d4` v8，6000 ms / 30 fps / 循环；`clock.pendulum` 的 Z 旋转在 0/1500/3000/4500/6000 ms 为 0/+0.2/0/−0.2/0 rad，保留曲线、片段和标记 | 实际下载 JSON，source 指向公开 Scene Artifact `artifact_fac8cb32e72c496b98a70d918faea7a2`，版本 10 / hash 精确一致；局部 XY 预览逐点定位一致，播放越过结尾回到起点，暂停后位置不再变化 |

GLB 实际 57848 字节，文件 SHA-256 `f7dbd6fbfffaa71e5424b6e33864e957ff9ab38982f4309122bd82f3e06c7ce7`；其中场景内容 hash 为 `440bf1aafa357cc4e554aef92f008e0155ebcfb04daaebdade857234826abc4d`。动画 JSON 实际 1555 字节，SHA-256 `556d9e69ec3f8a7930589c86ef1ff51ee3048f9e5c3e7559f3a6ac75fd5dabe8`，与最终 Artifact `artifact_ed83e2907f0149e796839afc418713aa` 一致。

只读 SQLite 审计完整核对两个 Run 的写工具目标：只有上述 Agent 自建场景及新动画，未写入第五阶段人工 Scene / Animation。操作者只负责提交需求、查看、播放、下载，不把这些验收动作计为 Agent 制作能力。最后 Turn 估计 55284 token，其中原生历史 24164、schema 24259，省略 batch 为 0；Provider 重试和协议修复均为 0。

### 仍然不能宣称完成的部分

- **成本。** 续作累计消耗 936215 输入/输出 token；多轮携带大量完整 schema 和推理历史，交付成功不等于高效。64K 是明确的默认成本取舍，不能用来宣称任意扩展数量的发现/容量问题已解决。
- **视觉与播放闭环。** Agent 最终如实说明没有可调用的场景渲染/播放工具，只做结构、来源、时序核验。操作者看到的是简易几何样片，主镜头仍有大面积空背景，不能评为高质量成品。局部 XY 回放不等于绑定对象已经在完整三维场景中播放；这一组合视图仍未验收。
- **呈现。** 17 张中间版本成果占据主要时间线，版本 8 还因显式导出重复出现；动画成果引用仍使用通用立方体图标。只读动画检查被呈现为“编辑动画”，也会误导用户对写入的判断。这些是实际发现的共享呈现问题，本轮没有用新卡片层或特殊分支掩盖。
- **验收脚本。** 首次播放检查等候 `v8 · 1 轨道 · 5 关键帧` 状态文案超时，因为播放标记提示替换该状态文案；改为检查实际选中文档版本、关键帧值、循环和暂停，复验通过。这不是持久版本丢失的产品缺陷。

改前有效反例为 3 failed / 11 passed，改后该集合 14 passed；Core 确定性集合 375 passed / 2 deselected，注册与 Scene/Animation 合同 12 passed，额外跨能力集合 19 passed。现有组合测试中的旧默认预算断言已同步，另保留显式 32768 的耐久预算失败路径；不把陈旧测试断言错误计成新产品问题。四个 Core 源文件 Mypy 通过，本轮相关源码/测试 Pyflakes 通过。

新证据独立放在 `desktop/output/playwright/agent-owned-20261108/`：`scene-v10.png`、`animation-v8.png`、实际 GLB/JSON、`agent-run-provenance.json`、`download-audit.json`、`animation-playback.log` 与回归日志。该目录不提交。原始失败和 Core 回归日志仍在第五阶段证据目录，不能把人工作品截图混作本阶段成果。

临时启用的 Scene / Animation 已通过正常扩展界面关闭，并等到两个真实开关变为 false 后核对全部列表：所有可选扩展关闭，必需 Workspace 开启（`cleanup-verified.log`）。未调整用户安装版本或凭据。当前工作区还含先前大量未提交改动；本轮范围的 `git diff --check` 通过，全局检查仍报告既有 `ConversationHistoryPanel.tsx` 文件末尾多一空行，不为此改动其他工作。

## 已执行验证

| 集合 | 结果 | 范围 |
|---|---|---|
| 并行审批恢复与原生批次 | 22 passed | 两个待批调用、批准/拒绝/过期、原生完整 outputs、取消及问题请求回归 |
| 取消和后继事件流 | 19 passed | Store 与 StreamRuntime 两个文件；新增两条反例在修复前均失败 |
| scope 拒绝、RunLoop、Story | 79 passed | 包含资源撤销/变更后的耐久失败结算，真实失败由客户端日志复现 |
| Workspace 包与文件变更安全 | 13 passed | 签名包激活、预览分页/路径/版本拒绝、1 MiB 最后一页、递归预算、junction 循环/越界及隔离 worker |
| 文件/故事/图标/时间线前端 | 27 passed | 直接加载 DLC 模块并通过 Host FileContent 渲染保存后的 Markdown |
| Agent Core + 内置装配合同 | 381 passed，2 deselected | 确定性集合及缩减后的内置工具集合 |
| 工程合同、结果 API、DLC Host 与装配/Runtime | 125 passed | 2 条现有依赖弃用警告 |
| Story 与能力指导 | 15 passed | 新增指导接入后的 owner 行为 |
| Music 包与能力指导 | 9 passed | 3/4、4/4、6/8 均每小节仅一个完整时值低音，双音模板的最少音数仍校验 |
| 混合提问与审批 | 28 passed | 同轮两问、审批→提问、提问→审批，分别正序/逆序回应，完整 native outputs 后才能继续 |
| 中断资源重验与恢复 | 60 passed | 尚未执行的请求失败；已中断执行但不可核对的结果仍 unknown，不自动重放 |
| 私有目录与并发文件写入 | 17 passed | 两个固定探针反例改前失败，改后通过；跨进程相同 hash 写入仍只有一个成功 |
| 最新后端组合 | 472 passed，2 deselected | Core、装配、Workspace/Music/Story、工程合同与目录初始化；其后 Workspace 指导独立复验 4 passed |
| Pixel 后端 | 110 passed | System、对抗输入与能力验证；包含 258 像素被规范错误码拒绝、256 像素通过的真实 PolicyGate 边界 |
| 前端全量 | 115 文件、707 passed | 含读取归属、具名 Dock 恢复、创建分派与手势时序修改；最后标准图片图标和测试类型调整后，受影响 30 项再次通过。固定反例的改前失败日志另存，不以最终通过抹去已发生的问题 |
| 前端测试类型、pyflakes、mypy | 通过 | 最终测试类型检查及 Core、脚本、受影响 DLC 的 pyflakes 通过；mypy 240 文件通过；无新增依赖 |
| 前端 lint 与生产构建 | 通过 | lint 23 条现有 warning；生产 Token 与 bundle 门禁通过，保留 chunk 提示 |
| 第二阶段预算错误与控制恢复 | 43 passed | RunLoop、ContextBudget、Terminalizer cancellation、Coordinator、Agent API；两个预算反例改前均逃逸异常，改后正常耐久失败 |
| Project 成果读取与既有 Artifact 合同 | 73 passed | HTTP 真实 SQLite 读取、跨 Project/不存在/删除后拒绝、Artifact Repository 与开放类型合同；保留一条既有依赖弃用警告 |
| Comic 包与 Story 组合 | 26 passed | 签名包与真实 Runtime 合同，不是在线模型自主交付证明 |
| 第二阶段前端全量 | 115 文件、711 passed | 随后清理读取反馈的 effect 状态更新方式，并复验受影响 4 文件 77 passed；不得将先前 707 项作为这一阶段最终结果 |
| HTTP 失败分类与模型诊断 | 49 passed | Agent Adapter、真实 API 边界与 SDK 工厂；402 不重试，401/402/429 分类及上游正文不泄漏；七条固定反例改前失败 |
| 模型设置页 | 5 passed | 包含实际父组件接收额度失败后持续呈现安全原因的反例，改前失败 |
| 第二阶段最终 Agent Core | 371 passed，2 deselected | 当前 `verification/tests/agent_core` 确定性集合；不是上面 381/472 项组合命令的同一范围 |
| 第二阶段最终前端全量 | 115 文件、712 passed | 含冷恢复、重试、项目切换、generation fence、额度诊断；串行运行 |
| 第二阶段最终静态与构建 | 通过 | 测试类型、pyflakes、mypy 240 文件、lint（0 error / 23 既有 warning）与生产构建；Token/bundle 门禁通过，仍有 650 kB chunk 提示。最后角色描边仅改 DLC 渲染器，单独语法检查及签名包真实导出复验通过 |
| 第三阶段文件与 ActionRun | 28 passed | Workspace 签名包、真实文件系统与跨进程写入、Creative 及 ActionRun 生命周期；五个文件系统反例改前失败，公共 operation 的无 hash 覆盖反例另行确认后失败，改后通过 |
| 第三阶段文件查看器 | 9 passed | 刷新、中文/emoji 分页、冲突保留、迟到响应、规范目标、绑定失败重试及源码模式保留；初始刷新、绑定重试和模式保留反例均改前失败 |
| 第三阶段最终 Agent Core | 371 passed，2 deselected | 含默认批准理由修改，保留原安全规则与决策顺序 |
| 第三阶段最终前端全量 | 115 文件、717 passed | 审批理由与详情调整后全量复验；受影响审批/时间线/可访问性 3 文件亦有 30 passed；没有只沿用前一轮全量结果 |
| 第三阶段最终静态与构建 | 通过 | 测试类型、Core/脚本/Workspace pyflakes、Core mypy 240 文件及 Workspace mypy 7 文件；lint 0 error / 23 既有 warning；生产 Token 和 bundle 门禁通过，保留 chunk 提示 |

第四阶段补充门禁：`npm run lint`（0 错误、25 条既有 Fast Refresh 警告）、`npm run typecheck:test`、`npm run build` 通过；生产入口 647,746 B、预算脚本 gzip 195,732 B，Token 与 bundle 门禁通过。两个改动 Python 文件通过 Pyflakes，HTTP 读取模块通过 Mypy。未重新运行整套后端或已验证的 Electron Main 集合。

表中结果针对各命令执行时的工作区；后续改动需跑对应受影响集合，不能把先前结果冒充最终全量验收。未执行 Frozen Python 3.14 Sidecar、安装包重装或多平台发布验证。

## 下一轮与保留空白

下表保留执行顺序；第 1 项已开展，但模型自主交付仍未通过；第 2 项已有上述真实冲突、冷启动和排队证据。13:07 模型连接已恢复，继续在线验收；早先余额不足的历史事实仍保留。每个场景先记录正常用户步骤与异常恢复，定位源码后修复权威边界，再运行最小充分回归。

| 顺序 | 真实任务 | 核验重点 |
|---|---|---|
| 1 | 将《雨夜修表铺》已有章节整理为三格分镜 | Story 公开读取、Comic 创建/对白/布局、具名 Dock、固定版本 HTML/JSON、错误及取消后的继续操作 |
| 2 | 同一文件的人类修改与 Agent 修改交错，审批期间重启引擎 | 冲突明确、草稿可处理、审批和队列可恢复；已开始但结果未知的写入不自动重放 |
| 3 | 建立场景并制作短动画 | Scene 对象身份、Animation 公开绑定、播放/停止、关键帧和重启恢复 |
| 4 | 体素小场景与着色预览 | Voxel 编辑/版本与 Scene 组合、Shader 编译诊断、GPU 执行回执和停用清理 |
| 5 | 使用既有 Pixel 图标制作可操作样片 | Game 素材来源、预览执行端、输入/停止/失活、有限运行报告和固定成果 |
| 6 | 查看本仓库状态并整理只读代码任务 | GitHub 鉴权与来源、分页/失败反馈；未经明确指令不发布评论、推送或变更远端 |
| 7 | 多能力任务、长上下文和重复操作收尾 | 工具发现的既有边界、证据预算、自然结束质量、冷启动、输入与成果展示的一致性 |

1. Story 当前通过激活/切换/显式刷新修正缓存，没有新增自动 Agent mutation 通知协议。后续调查共用的 owner 数据失效通知，不能新增 13 套轮询或第二套事实模型掩盖。
2. Story 检查使用有界 Context observations，长任务中的旧检查证据可能掉出窗口；需要基于持久证据设计，不能简单删除一致性检查。
3. MusicXML/MIDI 当前没有导出实现。不得把前端模块的 JavaScript export 或 MIDI 音高标记误认为文件导出能力；本轮指导如实声明此限制。
4. Pixel 已修复后台读取归属和绘制前注册时序，当前最终 712 项前端全量通过，实际编辑、接力、冷启动和 PNG 导出已核验；尚不能仅凭这些结果断言最初每个偶发时序失败都只有同一个原因。持续保留带延迟读取、失活及指针取消的边界验证。
5. Pixel 真实接力依赖用户补充指令收尾。当前模型面对较多完整 schema 和长推理时仍会重复检查、重复修改；ProgressGuard 已有持久事实指纹，本次 r6～r11 的内容摘要不同，没有证据将其认定为指纹遗漏。需继续用实际任务评估模型与上下文预算，不放宽完成条件来制造通过。
6. Scene / Animation 已按第六阶段由真实模型完成创建、固定导出和公开来源绑定；自主视觉审查、完整三维动画回放、Voxel、Shader、GitHub、执行过程中强制断线与更多任务交替仍未完成验收。等待审批时的冷启动和文件冲突已按第三阶段复验。培养方案验收中的三项保留问题仍见上一份业务记录。模型报告对文档状态、运行证据和“搜索未找到”的推断仍须业务核对。七扩展同时激活仍可能触及完整 schema 预算，64K 与明确错误提示都不是工具发现容量问题已经解决的证明。

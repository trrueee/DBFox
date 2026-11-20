# 通用开发底座收敛与验收

> 文档类型：实施与验证记录
>
> 状态：当前
>
> 最后核验：2026-11-16
>
> 基线：`d7f45a8be4a1992039f00e9e058d0e62d629e906`，Windows 11 x64

## 当前基线与实施范围

开始时 HEAD 与参考提交一致。工作区已有图标、品牌路径、Data vendor 生成文件及本机烟测目录；这些内容不作为本轮改动的基线证据，也不撤销。

生产链为 Electron EngineSupervisor → FastAPI lifespan → 签名 System DLC 装载 →
`compose_local_execution` → `build_product_run_loop` → Tool Registry / Policy / Approval /
Invocation → Workspace 冻结资源 → Sidecar LocalExecutionBroker → Windows Job Object。
`command_start` 只结算启动；Job 表持有运行事实；`command_result` 的新 Invocation 经既有
Settlement 发布 Artifact；Representation 读取保留日志；Dock 只保存身份和界面状态。

Session/Run/Invocation/审批仍归 Kernel 持久层，文件与 binding_generation 归 Workspace，
OS 句柄归 Broker，Job/日志归现有 SQLite，成果归 Artifact。没有计划新增状态权威、执行循环、
审批系统、成果存储或任务调度器。进程以当前用户权限执行，目录约束和 Job Object 不提供安全沙箱。

首轮现有 `test_local_execution.py` 与 `test_workspace_mutation_safety.py` 在本机通过 26 项。
这证明现有确定性执行与文件回归，不代表本轮真实模型、Renderer 或封装产物验收已通过。

## 最小改造决策

| 边界 | 已确认的情况 | 决策与依据 |
| --- | --- | --- |
| 取消 API | 捕获所有异常并返回 RUN_NOT_FOUND，存储故障也变成 404 | 只将 SQLAlchemy 的缺失行异常转成 404，保留统一内部错误边界 |
| SQL 结果读取 | SQL LIKE 未转义，而快照读取使用字面包含 | 复用 SQLGlot 的 LIKE/ESCAPE AST，一处构造字面模式；属于过滤语义错误，不能据此认定 SQL 注入 |
| DLC 编译 | Compiler 读取 ToolRegistry 私有 backend 集合并自行复制注册信息 | 将可写副本语义放回 Registry，保持编译阶段的事务隔离与正式工具元数据 |
| stdin | 资源解析与异步实际写管道之间没有绑定写锁 | 复用 Workspace 现有 execution_directory 租约，在副作用前验证代次及 Run/取消；不增加授权事实副本 |
| 日志读取 | UTF-8 增量解码没有在流末尾收尾 | 复用 Python codecs，在已结束的流末尾交付替换字符并验证跨页读取 |
| 静态检查 | Python 全局允许无类型函数；DLC JS 的 CI lint 入口与配置覆盖需核对 | 按模块收紧执行合同；为第一方 JS 配置实际可执行的静态门禁，保持 SDK 和签名包边界 |

采用的能力已经包含在项目依赖与平台中，不新增运行时依赖。Registry 的副本是现有编译事务的
资源边界；日志模式构造是 SQLGlot AST 的最小使用，不引入 SQL 执行旁路。

调查来源包括本仓库当前架构、相关提交和测试，以及官方
[Windows Job 查询](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-queryinformationjobobject)、
[TypeScript checkJs](https://www.typescriptlang.org/tsconfig/#checkJs) 与
[SQLAlchemy 字面 LIKE 转义参考](https://docs.sqlalchemy.org/en/20/changelog/changelog_12.html)。
SQLAlchemy 参考用于比较成熟转义语义；实际查询继续由项目已有 SQLGlot 生成。

## 验证与交付进度

阶段 A/B 已追踪上述生产链与最小改造。后续连续完成源头修复、失败路径回归、陌生 Python/Node
项目的确定性与真实本地模型任务、独立文件/退出码/日志检查、Dock 读取/停止/重连、构建及文档。
真实模型任务只给任务和验收目标，不提供内部工具名或修复步骤；失败按模型、发现性、合同、环境
和 Harness 分类。付费 API 不在授权范围内。远端 CI、安装升级及其他平台证据与本机验证分别记录。

## 首次暂停快照（2026-11-15）

本节保留首次暂停时的事实；后续状态以下文“续作验证”为准。

用户通过物理 Escape 停止了 Computer Use，桌面验收随即停止。以下为当时真实状态，不能据此宣称整个任务已交付。

已经修改：取消 API 只把缺失行转成 404；SQLGlot 使用显式 ESCAPE 生成字面包含模式；Registry 自身复制可写编译快照并保留进程监督元数据；stdin 在实际写入前取得 Workspace 绑定租约并核查 Run/取消；日志跨页解码保留 UTF-8 尾部并在终态排空，错误的未来游标有明确 409；托管 command_run 返回 execution_job_id，后续可由独立 command_result 调用交付成果。

文件 Tool、文件操作和文件 Representation 共用字符分页，输入明确字符单位，输出提供 next_offset，越界有修正指引。CRLF 精确编辑不匹配会说明换行原因，不会静默重写整份文件。Dock 空列表继续发现新任务；DLC JavaScript 有实际生效的 ESLint 门禁，并修复 GitHub Tree 的未定义变量。相关执行模块和 Registry 按模块收紧类型检查。

打包调查发现 electron-builder.yml 固定 43.4.1，而 npm 锁和安装内容均为 43.8.7。现有 staging 脚本从锁取得精确开发依赖，并核对安装版本，删除 YAML 中重复版本事实。Windows 解包目录已使用 43.8.7 生成。没有修改依赖锁，没有新增运行时依赖，没有新增 Kernel 状态、持久化表或迁移。

| 实际检查 | 结果与边界 |
| --- | --- |
| 完整系统确定性集合 | 本轮通过 1331 项，排除 137 项；此后新增的分页、命令引用和生命周期用例另以最终定向检查补证，不能将该次全量称为所有最终字节的全量验证 |
| Agent Core 确定性集合 | 375 通过，2 排除 |
| 最终执行、Workspace 包和工程合同定向集合 | 64 通过 |
| 最终文件变更与 Workspace 包定向集合 | 21 通过，和上一行有重叠 |
| Python 类型 | Engine、构建器及 Workspace 后端共 262 个源文件通过；此前 pyflakes 通过 |
| Renderer | 767 项通过，测试类型检查通过，lint 无错误但保留 19 条已有警告；DLC lint 无警告通过 |
| Electron Main/Preload | 38 项通过 |
| 生成 API | 正式命令生成后与 Git 中合同无实质 diff |
| Frozen Sidecar | 固定 CPython 3.14.6、python-build-standalone 20260804、哈希锁构建成功，最终运行时及发布合同探针通过 |
| 桌面构建 | tsc、生产 bundle、开发 Token 检查和 bundle 预算通过；Windows 解包应用生成，未做 Authenticode 签名 |
| 远端 CI | 已配置强制 Windows 托管执行门禁，未触发远端运行，不能称 CI 通过 |

真实 4B 千问使用生产 Sidecar/SessionCoordinator/RunLoop/Tool Runtime。Python 在
`.tmp/development-acceptance-source-05/python-evidence.json` 中记录退出码 1→0，只改 shipping.py；
TypeScript 在 `.tmp/development-acceptance-source-09/typescript-evidence.json` 中记录退出码 2→0，只改 src/duration.ts。
两次均独立复跑原项目检查并核对 Git diff。模型没有得到内部工具调用步骤或修复代码。
这两次模型没有发布正式执行 Artifact，因此只是修复和复验通过，不能称完整成果交付通过。
正式 command_result 关联文件成果、日志过期及读取的确定性生产 RunLoop 路径已通过回归。

其余真实模型尝试保存在同级 source-04 至 source-09 目录：包含仅报告建议、使用未注册短工具名、
重复无关读取和 AGENT_NO_PROGRESS。早期还存在验收驱动初始化、审批快照解析、pytest 继承父仓库配置、
批准范围过窄等 Harness 问题；已逐项区分并修正，没有将这些问题全部归因于模型。
9B 免费本地权重下载未完成，因停止操作而终止；现有默认模型配置没有更改。

桌面首次检查将其他签名夹具的运行时复制到封装应用，按预期触发同版本不同摘要的 DLC 拒绝，
实际 UI 显示启动失败。没有放宽包完整性检查，也没有把这个窗口计为 Dock 验收通过。
应使用同一冻结构建的 bundle 重新产生验收 Runtime。独立 smoke-sidecar 还发现 Python 夹具构建
子进程没有注入私有 Runtime，可能访问默认应用目录；本轮烟测已终止，此脚本接缝尚未修复。

## 首次暂停时的待办

- 用同一冻结构建来源完成真实模型的正式执行 Artifact、文件关联和实际 Dock 读取/停止/重连/失败重开。
- 更新已修改 DLC 的发布版本，保持同版本不可变摘要规则，再重建并重验发行包；当前为未发布的源码工作区。
- Workspace 的旧服务仍包含 Windows subprocess/taskkill 路径。正式 Windows 产品装配已替换为 Broker，但独立服务/旧 Worker 路径尚未退役；不能将其描述为已删除。需要保证停止语义唯一，并记录 POSIX 旧路径的支持范围与退出条件。
- 修复烟测构建子进程的 Runtime 隔离，再运行最终封装烟测、安装包与升级验证；macOS/Linux 未验证。
- 补齐当前架构和使用文档，并在最终收尾时审查所有增量及重新核验必要门禁。未提交任何改动。

## 续作验证（2026-11-16）

继续时重新核对 HEAD，仍为上述基线；所有实现是未提交工作区增量。关闭了 Windows 的
WorkspaceService subprocess 旁路并删除 taskkill 分支，独立服务在创建进程前明确要求 Host Broker。
POSIX 单次路径暂留，适用范围、维护责任、Invocation 观测及删除条件记录在
[执行架构](../architecture/local-development-execution.md#旧路径退出)。没有新增执行代理或迁移表。

已修改 DLC 的版本为 Workspace 3.0.4、Data 2.3.1、GitHub 2.0.1、Music 0.3.3、Story 0.2.2、
Voxel 0.1.1。继续保持相同发布版本对应不可变摘要；没有放松签名、版本或包摘要校验。
烟测两个 Python 包构建子进程现在先注入私有 Runtime；临时 Runtime 被 Git 忽略。

真实模型尝试还发现多行批处理请求被直接传给 cmd /c，产生语法错误。调查 Windows 官方
[cmd 合同](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/cmd)并实机复现后，
选择在现有 prepare/准入处拒绝换行，说明使用单条命令行、&& 或显式批处理文件。
没有自写 shell parser、拼接换行或隐藏脚本。CommandStart 版本增至 2；这条可公开的错误
通过原有准入反馈返回，未修改 Kernel 的通用参数脱敏规则。生产 RunLoop 的失败反馈恢复回归覆盖该行为。

| 续作检查 | 观察与范围 |
| --- | --- |
| Windows 旧路径拒绝、文件变更、Workspace 包与托管进程 | 39 通过，含真实 Job Object；随后 Shell 与逐流 EOF 修正的 18 项执行集合全部通过 |
| 工程合同、Workspace 包、Registry | 57 通过，与上一行部分重叠 |
| Python 静态检查 | pyflakes 通过；Engine、构建器与 Workspace 后端 262 个源文件 mypy 通过 |
| DLC JavaScript 与 Renderer 测试类型 | lint:dlcs、typecheck:test 通过 |
| 生产前端构建 | TypeScript、Vite、Token 检查、bundle 预算通过 |
| Windows 打包 | Electron 43.8.7 解包应用与 NSIS 1.0.4 生成；未做 Authenticode 签名或安装升级验收 |
| Frozen Sidecar 烟测 | 本机正常权限下通过令牌拒绝、Data 查询/工件、隔离 Worker、DLC 更新/回滚与重启恢复 |
| 封装 Electron 启动 | Ready、五个默认系统 DLC 的前端/样式 HTTP 200，未激活 DLC 资源 HTTP 403 |

`.tmp/development-acceptance-frozen-01` 首次失败属于驱动遗漏 Origin；已按冻结版合同补上桌面来源头。
`frozen-02`（中文任务）和 `frozen-03`（英文任务）均使用真实 4B 模型和最终来源 bundle；两项项目
独立检查都仍失败、没有实现 diff。记录保留了换行编辑失败、错误命令/脚本及未注册工具等反馈。
先前 source-05/source-09 的修复成功仍只是部分证据；不能用它们覆盖本轮失败或宣称完整自主交付可靠。
验收驱动现同时要求：模型复现失败并复跑相同命令至 0、零活动成员与输出收尾、仅改实现文件，
以及正式执行 Artifact supports 本次 code_patch。驱动收尾复用现有 WindowsProcess Job 句柄，
避免只 terminate PyInstaller 引导进程而遗留真正 Sidecar。没有修改默认模型或使用付费 API。

原生 Dock 通过 Computer Use 操作本次封装应用，使用同一发布 bundle，隔离 user-data 和 Runtime。
模型端为明确标注的本机脚本 Responses 服务，此项证明产品编排与真实 UI，不证明模型自主能力。
`native-dock-fixture-01` 暴露受限环境与桌面登录环境的夹具凭据不可见，已用布尔查询分别确认，
没有改凭据策略。后续夹具与窗口在同一登录环境准备。

- `native-dock-fixture-02`：关闭/重开日志和 Ctrl+R 后恢复同一个 Job，stdout/stderr 持续递增，
  SQLite 仅一条启动记录。切换新任务再返回也保留同一 Job；随后脚本模型构造响应失败，
  Run 失败按预期将后台 Job 清理为 cancelled/run_failed，不能算主动停止验收。
- `native-dock-fixture-03`：从 Dock 点击停止，独立 SQLite 核对 stop_requested、活动成员 0、
  output_finalized=1。正式 command_result 创建工件并 supports code_patch；原生界面打开日志及关联文件。
  文件被夹具外部修改后重开显示 SOURCE_CHANGED；恢复原字节再重开显示正确代码。
  将终态夹具时间老化八天后，经真实保留清理，日志行从 56 变为 0；同一工件仍显示退出事实，
  界面明确提示超出保留范围和无保留输出。没有把输出描述成永久完整证据。

本机独立事实在上述 Runtime 同级的 independent-jobs.json、independent-artifacts.json 与
provider-progress.json。执行工件为 artifact_7043ce6888dd4c3b97ad32685bb1e9f4，Job 为
job_cef1b34756d749ebb3e8431f81ccd1e9。验证后关闭夹具窗口、模型服务并清理测试凭据。

日志末尾修复还覆盖一个独立问题：stdout 只有部分 UTF-8 字节时不能阻挡 stderr。
采集器复用既有日志表，以每条流的一条零字节记录表示 EOF；分页按流恢复至多三个尾字节，
排空未完成字符，tail 的块数不被结束记录占用，读取也不会越过 Job 的已知采集游标。
没有迁移或新的输出状态表。历史无结束记录的终态日志仍可读取，删除条件见执行架构。
真实交错管道与新旧日志格式的失败路径回归已通过。

上述 Shell、EOF 字节已经重新生成 Frozen Sidecar、NSIS 和解包应用；Sidecar 与 Electron
封装烟测均通过。新增模型交付调查随后确认 Workspace 上下文只恢复 file_snapshot，
遗漏 code_patch，后续请求缺少实际修改的引用。先加入会失败的已签名包回归，再在现有
ContextContributor 同时恢复两类工件，并核对授权代次和当前文件 hash；片段明确类型，
整体限制在现有预算内。只使用已有 SDK/Artifact/Context 接口，没有新增工具、模型分支或
Kernel 规则。Workspace 包因此增至 3.0.4。相关包、装配与工程合同 58 项、pyflakes 及
262 个源文件 mypy 通过。最后增量的 Frozen Sidecar、Windows NSIS 与解包应用已生成，
Sidecar 和 Electron 封装烟测再次通过。

9B 免费本地模型 `qwen3.5:9b-q4_K_M` 已完成官方权重下载与 SHA-256 校验，
使用隔离配置、模型目录和 Runtime；用户原有默认 4B 配置未变，没有调用付费 API。
GGUF 主文件 SHA-256 为 `02d45dc1cf451ba2475ac33b301c2dd8f985abe4c182ce04a1f2f5bf0260278d`。
`frozen-04` 的 Python、TypeScript 都由真实模型读取失败诊断并修改实现，独立检查分别为
1→0、2→0，且只改变 shipping.py、src/duration.ts；测试与配置未改。

Python 在第二次普通用户输入后完成严格交付：执行工件
`artifact_bf1e7235c43d4184af822d932cdd7d2e` supports 修改工件
`artifact_279e8960ea544b53a2ddc1a0eabb99b7`，Job
`job_52ec44ada8c34b97a479ae4cd9b99a83` 退出 0、活动进程 0、输出已收尾。
最终封装 GUI 中实际打开该执行工件，读取两个 unittest 的 OK 日志，打开关联修改代码；
Ctrl+R 后恢复同一修改工件和内容。证据为 `python-delivery-evidence.json`、
`independent-jobs-delivery.json` 及原生 UI 观察；不是以模型的完成文字作为通过依据。

同一批 TypeScript 后续仍错把读取快照当作修改成果：第二次输入受 Provider request watchdog
影响；第三、四次有正式执行工件但关联错误；第五次在修复后的上下文已经包含实际 code_patch
时仍选择快照。因此上下文缺口与模型判断失败分别记录，不能声称补上引用就保证模型正确。
第五次收尾还出现沙箱用户创建的夹具被桌面用户 Git ownership 检查拒绝；完整进度与原始错误
保留在 `typescript-delivery-inputs-5-capture-error.json`，随后在夹具所有者下独立复跑仍为 0。
驱动的只读 diff 现只对本驱动创建的夹具按命令指定 safe.directory，不修改全局 Git 信任配置，
也不影响产品命令环境。此前失败未覆盖或重新归类为通过。

`frozen-05` 使用最终 3.0.4、干净会话及桌面登录环境再次运行 TypeScript。模型改成数值后
仍未实现舍入，独立完整检查 2→1，最后由既有 AGENT_NO_PROGRESS 终止重复尝试。
仅 src/duration.ts 改变，测试与配置未改；属于真实模型失败，不作为通过样本。
期间模型请求删除该实现文件，自动审批审查认为会破坏成果并拒绝批准；随后明确拒绝该
工具审批，模型改用带当前 hash 的写入。没有绕过删除审查或改变产品审批规则。

Renderer 最后定向检查 13 项通过。曾在模型与打包同时运行时出现一个既有绑定重试测试的
一秒查找超时；隔离运行该组 9 项及随后同一组 13 项均通过，没有放宽断言或超时。
System DLC 使用本机测试发布者密钥签名，与 Frozen Sidecar 的固定信任一致；
这不等于正式发行签名，Windows 安装包也未做 Authenticode 签名。

最终原生 GUI 续作也保留完整失败过程。TypeScript 第六次普通输入后，模型已识别并打开正确
修改工件，却仅声称关联已保存，实际没有创建工件，独立记录仍判失败。第七次普通输入后，
正式执行工件 `artifact_23fb605be25248f499f5267aace15bf1` 才实际 supports
`artifact_9f71d3f9ddf1413a826cf494125c7dad`。其 Job
`job_08100aa5f34c42cb8eaa8e64fbc57c8c` 退出 0、活动成员 0、输出收尾，原生 Dock 读取了
Node test 的 pass 1 / fail 0，并从关联文件打开同一修改工件，内容 hash 为
`4e179cba0ea2f7b8f6fc5db0ea6ef4f344bfdbbfce418675ca56df56f6e4a4e2`。
独立完整项目检查仍为 0，仅 src/duration.ts 有 diff。

这一轮还拒绝了模型提出的 `node -e` 打印“检查会通过”的请求，未执行也未计为检查证据。
新 Node 命令与原始失败命令的 argv 不同，因此
`typescript-ui-delivery-inputs-7-evidence.json` 的严格同命令交付判定仍为 false；
“正式关联已保存”和“严格同命令复验通过”分别记录，没有放宽原判定。

第八次输入仍用了不同的 Node 启动参数，严格判定保留 false。第九次输入明确引用项目公开
检查命令 `node --test test/duration.test.mjs`，没有提供 DBFox 内部工具名、参数字段或工件 ID。
这一轮属于按指定项目命令完成交付；不把它当作模型自主选择检查命令或一次输入完成交付的证明。
模型完成新的逐次审批、真实执行、读取终态与正式 command_result 调用，创建
`artifact_5408c95f7c874c16bc9700bc31f7ab84` supports 上述实际修改工件。
Job `job_26f9a3e07db4430392a58defea8e0ab5` 的程序、argv、shell_script、cwd 与原始失败
Job 一致，退出 0、活动成员 0、output_finalized=1；Run 为 completed。
独立完整项目检查再次为 0，仅实现文件有 diff，当前 hash 与修改工件 newSha256 一致且
不同于 oldSha256。`typescript-ui-delivery-inputs-9-evidence.json` 按原有严格条件判 true。
最终封装 Dock 实际加载这个工件，显示同一命令、pass 1 / fail 0、退出码 0 和关联修改文件。
验收窗口和其模型运行时随后关闭。

最后发布产物的摘要保存在 `.tmp/development-foundation-release/build-proof.json`：

| 产物 | SHA-256 |
| --- | --- |
| Frozen Sidecar | `8a2ef5ffe00371538cc946fccd16e2f4c8a9ace1c1134d65e742d13eef007236` |
| NSIS 1.0.4 x64 | `6787c6cc8ead1eed16da09e055c6ef2710fd05a146fbec673e4cdb0f6ad579d0` |
| Workspace 3.0.4 包摘要 | `a27d62875446a195101c4cacd58af02e72c616b43185c6a178e3ed018b6489df` |

远端 CI、正式签名、安装升级和 macOS/Linux 发布仍未验证。

## 交付判断与保留边界

源码改造、确定性生产 RunLoop 验证、真实本地模型修复、独立结果检查、原生工作台读取和
Windows 封装已完成本轮实施与验证。真实 9B 模型在第一轮自主读取项目与实际失败后完成两类
实现修复；Python 需两次输入完成严格交付，TypeScript 需九次输入且最后明确指定项目命令。
这些记录证明通用能力可以完成工作，也同时证明当前小模型的自主交付稳定性仍有缺口。
错误关联、虚构完成文字、未知工具、重复尝试与 Provider watchdog 失败均保留，不能用通过的
最终样本覆盖，也不能将脚本模型的确定性结果称为自主开发成功。

状态所有权保持不变；未新增 Agent 循环、审批系统、Job/Artifact 表、领域专用开发工具或运行时
依赖。公共变化为字符分页 next_offset、托管 command_run 的 Job 引用、明确的游标 409 和
Windows 单行 Shell 合同；相关工具版本及 DLC 发布版本已更新，没有数据库迁移。
仍需维护的退出项是 POSIX 旧单次路径、保留窗口内的历史日志末尾读取规则；负责人、观测和
删除条件见执行架构。外部编辑器不参加 DBFox 写锁，最终替换并非 OS 原子 CAS；本机执行
仍使用当前用户权限，未建设安全沙箱。发布平台、安装升级及正式签名边界如上，不扩大声明。

所有实现仍为基线 HEAD 上的未提交增量。原有用户资产和文档未撤销，验收 Runtime、模型权重、
签名私钥、日志和二进制均留在被忽略的本机目录；不作为源码提交内容。

# Windows 本机开发执行环境

> 文档类型：架构决策
>
> 状态：已接受
>
> 最后核验：2026-11-10
>
> 适用范围：Windows 11 x64、Workspace System DLC、Sidecar、Tool Runtime 与 Dock

## 决策

将持久进程的所有权交给 Sidecar 的 Local Execution Broker。Workspace DLC 仍提供项目绑定、目录解析与文件工具。经系统包签名和摘要验证的 Workspace 通过已解析的资源提供目录，Sidecar 在产品组合阶段注入 Broker。Agent 使用现有 RunLoop、资源授权、Tool Invocation 和逐次审批。原有的隔离 Worker 继续处理已经声明给它的 Workspace 文件工具。

把 Job 状态放进 Workspace Worker 会随 Worker 结束失去句柄。通过内部 RPC 向 Sidecar 转发需要为每次请求再建立权限绑定与故障语义。首发采用进程内的窄接口与既有 PolicyGate，DLC SDK 保持原合同。Tool Registry 只接受由 Host 显式登记、带准入与审批的进程监督 Tool。第三方包的 Compiler 和能力许可保持原有校验。

直接程序与 Shell 分离采用 VS Code 的任务模型思路，进程创建、日志游标和进程树管理采用 Windows 原生 API 与现有 SQLite/Alembic。持久 Job 以真实进程生命周期为准，参考 Codex 的统一执行接口。没有新增第三方运行时依赖。维护重点是 Win32 结构布局、句柄生命周期和实际封装版验证。[VS Code Task Provider](https://code.visualstudio.com/api/extension-guides/task-provider) · [Codex unified execution](https://github.com/openai/codex/tree/main/codex-rs/core/src/unified_exec) · [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)

## 状态所有权

| 状态 | 所有者 | 生命周期 |
| --- | --- | --- |
| Workspace 稳定 ID、目录摘要、绑定代次 | Workspace 私有 SQLite | 老绑定首次迁移继承现有资源版本。新绑定使用新代次。撤销和实际创建进程共用 Workspace 写锁 |
| Run、Tool Invocation、Approval | 现有 Agent 持久层 | 每次启动、Agent 停止和 stdin 写入分别获批。启动 Invocation 只结算启动 |
| OS 进程、Job Object、stdio 句柄 | 当前 Sidecar Broker | CreateProcessW 以 Job List 创建即绑定。子进程使用句柄白名单，Job 句柄保持不可继承 |
| Job、原始 stdout/stderr 分块、采集游标 | Sidecar 元数据 SQLite | 启动前先记录 Job 和 Invocation 关联。退出事实、日志与最后状态由 Broker 写入 |
| 执行 Artifact、文件关联 | 现有 Tool Settlement | 显式调用 command_result 创建 Artifact，Representation 读取该 Job 的保留输出 |
| 标签、滚动位置和选择 | Dock | 关闭、刷新和切换会话只影响投影。访问日志和停止都核对当前会话与 Workspace 代次 |

Job Object 默认禁止 breakaway，并启用最后句柄关闭时清理。终止确认使用 QueryInformationJobObject 查询的活动进程数。正常终态要求根退出码已知、活动进程为零、两个输出管道到达 EOF，且收集的字节已持久化。父进程先退出时，Job 保持运行。封装的 Sidecar 启动外部程序时恢复外部 DLL 搜索环境。[创建时分配 Job](https://devblogs.microsoft.com/oldnewthing/20230209-00/?p=107812) · [PyInstaller 外部程序说明](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#launching-external-programs-from-the-frozen-application)

启动线程用 Windows API 检查目标文件的可执行类型，并将系统错误返回给调用方。无效文件在进入进程创建前转为明确的启动失败，线程的原有错误处理模式随后恢复。[GetBinaryTypeW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getbinarytypew) · [SetThreadErrorMode](https://learn.microsoft.com/windows/win32/api/errhandlingapi/nf-errhandlingapi-setthreaderrormode)

## 工具与日志合同

| 入口 | 行为 |
| --- | --- |
| command_environment | 探测系统、解析工具路径与项目配置标志。版本、依赖和测试通过独立获批的命令验证 |
| command_start | 提交 argv 或显式 Windows cmd 脚本、工作目录、可选环境覆盖、时限及前后台模式，返回 Job ID |
| command_inspect | 查看退出码、活动成员与日志完成状态。用 after 与 next_cursor 分页，可短时等待或查看尾部 |
| command_stdin | 向已开启的管道写入最多 4096 字节，或发送 EOF。每次批准，有部分写入可能时明确反馈 |
| command_stop | 请求结束 Job 内的进程。最终清理由后续状态确认 |
| command_result | 终态后发布可读的执行证据，支持关联现有文件快照、修改工件或输出报告 |
| command_run | 兼容 Workspace 原有输入与输出模型。在 Windows 托管路径等待终态，其他平台沿用原执行路径 |

命令的 `cwd` 沿用 Workspace 的项目相对路径合同，省略或使用 `.` 时从绑定根目录运行。程序身份通过 `argv` 单独解析。模型收到程序位置和项目标志，审批与执行记录保留实际工作目录供用户核对。无效目录由 Workspace 返回可修正的原因，申请审批前即停止。

前台任务默认随 Run 结束。显式批准的后台任务可跨越 Run 的正常完成，最长两小时。Run 失败或取消、会话删除、绑定撤销和 Sidecar 退出均触发清理。Sidecar 重启为尚未结算的 Job 标记 interrupted，保留已有证据并禁止重放。

每个 Job 最多保留最近 8 MiB 原始字节，stdout 和 stderr 分开标记。游标表示采集顺序。旧游标到期后返回保留起点与截断标记，继续排空管道。后台维护会清理超过七天或总量 256 MiB 的终态日志。单次模型查看最多两个 4 KiB 原始分块，Dock 单页最多十六个。预览按 UTF-8 解码，非法字节使用替换字符。终态 Artifact 引用同一份保留日志，保留窗口变化后会反映在表示的指纹与游标。

本机执行使用当前系统用户权限，能访问该用户可访问的文件、网络和程序。工作目录用于选定项目，Job Object 用于管理进程生命周期。审批显示解析后的程序、参数或脚本、目录、时限与后台选项。直接模式只解析本机 EXE，批处理使用显式 Shell。默认子进程环境从有限变量清单构造，排除 DBFox 运行凭据。项目和日志中的文字没有批准权限。请避免在命令、环境覆盖或 stdin 中写入凭据。

## 失败矩阵

| 条件 | 可见结果与处理 |
| --- | --- |
| 用户拒绝，或目录、代次、解析出的程序身份已改变 | 按现有工具准入或审批过期语义处理。实际创建前再检查一次 |
| 原生程序无法创建或无法原子分配 Job | 启动失败，保存可追溯原因 |
| 根已退出，仍有成员进程 | 展示已知根退出码与活动状态，继续收集输出 |
| 超时、取消、撤销或退出 Sidecar | 请求终止，确认进程清空和输出收尾后写入对应终态 |
| 存储故障、终止无法确认或无法排空 | 关闭 Job 句柄。能写入时标记 unknown，重启时对遗留行标记 interrupted |
| Job 正常结束但日志已滚动清理 | 展示保留范围及已失效的游标，保留退出证据 |
| Dock 已打开而内容加载失败 | 标签和读取状态分别显示，读取失败可重试 |

实机通过项、模型服务阻塞和复验命令见 [本机开发执行验收](../quality/local-development-execution-verification.md)。

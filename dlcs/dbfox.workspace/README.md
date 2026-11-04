# dbfox.workspace

Official System DLC for Project-scoped local workspaces. The DLC owns the
workspace binding, path containment, bounded file read/write/edit/search,
command execution, Agent tools, context contribution, artifact contracts,
Connector, and file Dock. Core owns the native folder picker and the generic
Tool Runtime only.

Read and grep tools run in-process with `filesystem_read`. File mutation and
`command_run` use the existing isolated worker, require the matching signed
manifest permission, and enter the canonical Approval lifecycle. The worker is
a timeout/cancellation and process-tree boundary for trusted package code; it
is not described as an untrusted-code OS sandbox. Commands receive an argv
array, never a model-authored shell string, run below the bound workspace root,
inherit no DBFox secret-bearing environment variables, and return only a
bounded output tail. 目录扫描、grep 候选、单文件读取和命令总输出都有独立硬上限；
达到命令总输出上限时会终止进程树，而不是只截断展示后让子进程继续无限写入。

## 选型依据

实现复用了项目已有的 Tool Approval、isolated worker、package digest 和
ResourceRef，没有增加第二套终端执行器。进程创建使用 Python 标准库
[`subprocess`](https://docs.python.org/3/library/subprocess.html) 的 argv 与
`shell=False` 路径；超时后显式终止进程树。权限形态参考
[Claude Code 的分层工具权限](https://docs.anthropic.com/en/docs/claude-code/iam)
和 [OpenAI Responses 的 shell/apply-patch/approval 合同](https://platform.openai.com/docs/api-reference/responses-streaming/response/refusal)：
只读默认不审批，文件变更和命令按 Invocation 审批。没有引入 PTY、通用
shell parser 或第三方进程库。子进程环境使用运行工具所需的路径、区域与临时目录
白名单，不把任意宿主环境变量透传给模型选择的进程；代价是 `command_run` 不支持
管道、重定向、shell 内建命令，依赖自定义环境变量的命令也必须改用显式配置文件或
目标可执行文件参数。

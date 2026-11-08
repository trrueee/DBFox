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

文件快照和文件变更成果通过 `dbfox.workspace.file.v1` Representation 读取内容，
复用既有 Markdown/代码查看组件。每次最多读取 12,000 字符；分页检查原始
内容 hash。绑定被撤销、根目录版本变化或文件内容不再一致时明确拒绝读取，
不把最新文件冒充历史快照，也不在 Artifact 中复制整份文件内容。

文件工作台提供“刷新”，同时重新读取文件树和当前文件，并保留 Markdown 查看方式。
分页中发现内容 hash 变化时保留已读前缀、停止继续拼接，显式刷新后从头读取。
取消的旧读取和迟到分页不能覆盖新结果。具体文件身份只来自 Dock 的规范 target，
不再额外缓存路径与绑定；项目文件夹变化后需要从文件树重新选择。

`file_write/file_edit/file_move` v2：共用 WorkspaceService 执行写入前置条件。
`expected_sha256` 省略时只能新建文件，覆盖已有文件必须提供当前 hash；
精确编辑也必须匹配该 hash。新建使用不覆盖发布，覆盖在暂存完成后再校验 hash，
Windows 移动使用拒绝覆盖的 rename。工具返回明确的变更提示，public operation 返回
`WORKSPACE_CONFLICT` / HTTP 409，均不自动重新读取后写入。
写入结果描述本次提交的字节，不重新读取并把其他人的后续修改当作本次成果。

现有 SQLite writer reservation 覆盖 DLC 进程之间的写入，但外部编辑器不参加该锁；
hash 检查和最终替换之间并非文件系统原子 CAS。当前真实验证为 Windows，
其他平台的移动和不支持硬链接的 POSIX 文件系统未通过发布验收。

`file_search` v2：空 query 列出 `path_prefix` 的直接子项，非空 query 按大小写
无关的字面文件名/相对路径片段递归查找。名称搜索和 grep 共用有界目录扫描，
全树最多处理 10,000 条目录项并做一次终止探测，空目录和忽略项也计入预算；
不跟随目录 symlink/junction，不读取根目录之外的文件。`truncated` 明确表示
扫描或结果数量不完整。没有引入 glob 语法、无界 `os.walk` 或新的文件索引副本。

此处复用标准库 [`os.scandir`](https://docs.python.org/3.12/library/os.html#os.scandir)
逐项预算扫描，返回现有 WorkspaceDirectory 模型；同一有界遍历用于名称搜索
和内容搜索，而不是各自维护不同的资源树。文本读取 offset 上限与 1 MiB 文件
上限一致，避免已接受的大文件最后一页不可达。

`workspace_evidence` 能力指导区分文件中的状态陈述、静态审阅、保存成功和实际
执行证据。没有运行证据时不能把“文档记载完成”写成“验收通过”；搜索无匹配
或扫描被截断也不能证明整个项目不存在实现。指导通过既有公开贡献点装配，
不在 Core 增加文件业务规则，也不保证模型报告必然正确。

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

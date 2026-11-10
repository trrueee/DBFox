# 本机开发执行验收

> 文档类型：验证记录
>
> 状态：当前
>
> 最后核验：2026-11-10
>
> 平台：Windows 11 x64，系统版本 10.0.26200

## 已执行

| 验收 | 观察结果 | 验证范围 |
| --- | --- | --- |
| 陌生 Python 项目 | pytest 退出码 1，读取失败输出后修改实现，复跑退出码 0。Git diff 只包含实现修改 | 生产 RunLoop、签名 Workspace、真实 Python 与 pytest。模型决策为脚本 |
| 陌生 TypeScript 项目 | tsc 输出 TS2322，退出码 2。修改后退出码 0，Git diff 与通过证据一致 | 生产 RunLoop、真实 Node 和 TypeScript 编译器。模型决策为脚本 |
| Windows 原生执行 | stdin 往返，stdout/stderr 分流，主进程退出码 7 时子进程仍运行。停止后确认零成员和输出收尾 | 真实 Win32 Job Object。并发、重复投递、超时与启动失败使用独立断言 |
| 日志与权限 | 9 MiB 命令正常退出并保留尾部。旧游标标记截断。撤销后重绑同目录使旧授权失效 | 本机 SQLite、真实输出、历史分页与会话范围。来源会话之外的读取和停止被拒绝 |
| 封装版执行链 | 两次逐次审批，原生 stdin、退出码 0、正式 Tool Settlement、带会话范围的 Representation 和 Workbench 打开回执 | 冻结 Sidecar 内的真实生产代码。使用本机脚本 Responses 服务和测试工作台回执 |
| 封装版进程树和重启 | 根进程先以 7 退出。仅终止已核实的 Sidecar 进程后，系统确认子进程已退出。重启后原 Job 为 interrupted 且只存在一份 | Windows Job Object 关闭清理与 SQLite 恢复，使用本机脚本 Responses 服务 |
| Electron 与安装包 | Electron Host Ready，五个签名系统扩展的资源和样式加载为 HTTP 200。构建 Windows x64 NSIS 安装包 | 使用真实 Windows 登录会话的封装版烟测。本地验证包未做 Authenticode 签名 |

同一执行 Artifact 的文件关联、Job 停止与重连通过 API 和 Renderer 测试覆盖。Dock 使用正常日志分页接口，关闭标签不会终止进程。Data + Workspace Composition Bench 通过生产 RunLoop 装配完成跨能力交接。

Windows 实机异常测试曾在将普通文件传给 CreateProcessW 时阻塞。启动层增加文件类型检查和线程范围的错误处理设置后，非法 EXE 与超时的回归通过。

前端全量 763 项和 Electron Host 38 项通过。后端系统全量运行通过 1279 项，唯一失败为启动装配测试仍要求旧的单行写法。修正断言后，最终源码的定向后端门禁通过 456 项，包含 Core、工程合同、Workspace 迁移及本机启动异常。

## 本地模型复验

Windows 封装版使用 `qwen3.5:4b-q4_K_M` 完成真实 Responses 流式推理。Ollama 绑定回环地址，32,768 tokens 配置下模型与上下文占用约 3.83 GiB 显存，均由 RTX 4060 Laptop GPU 承载。两项任务的模型请求均由本机提供，云端连接测试端点在本地模式下返回 `LOCAL_MODEL_REQUIRED`。

| 任务 | 实际退出码 | 代码与交付 |
| --- | --- | --- |
| Python 结算舍入 | pytest 1 → 0 | 只修改 `billing.py`，通过 Job 产出可读取的执行日志工件 |
| TypeScript 时长计算 | tsc 2 → 0 | 只修改 `src/duration.ts`，通过 Job 产出执行日志工件并关联编辑工件 |

早期 16K 配置因工具定义与会话输入超过预算而停止。调整上下文预算、保留工具可选参数并明确相对工作目录后，TypeScript 验收通过。Python 首轮误用了绝对路径搜索，复跑时在任务中明确文件路径相对项目根目录，模型完成修复。审批测试只允许指定检查命令及实现文件修改。较早的云端验收曾返回 `MODEL_PROVIDER_QUOTA_EXCEEDED`。

本地模型改动复验通过 469 项相关后端测试、17 项执行和工具合同测试、765 项前端测试，以及最终 Electron 启动烟测。

## 工作区路径与审批恢复

Workspace 服务统一解析文件、搜索范围和命令目录。Tool Observation 与文件操作 API 使用 owner 的可公开错误原因。生产 RunLoop 回归发送绝对搜索范围和绝对命令目录，验证拒绝后能从绑定根目录继续，审批只出现在有效请求上。

真实运行中，未物化的工具名曾被正确拒绝，却在之后的审批恢复中引发 `KeyError`。这是 Frozen Core 的内部正确性修复。实时调度原本就不计入这种调用，恢复现在根据耐久的 `UNKNOWN_TOOL` 结算复原同一预算。DLC 贡献只能提供工具和指导，预算恢复由 Core 持有。公开合同、持久化格式和工具授权沿用原语义。

本地千问从普通任务描述完成 Python 修复，真实 pytest 退出码为 1 → 1 → 0，Git diff 只包含 `billing.py`。验收项目自带 pytest 配置。TypeScript 首轮重复调用未注册的短工具名并触发停滞保护，明确任务是类型检查失败后在冻结 Sidecar 中复跑，真实 tsc 退出码为 2 → 0，Git diff 只包含 `src/duration.ts`。两次通过的任务均从 Job 记录核对实际诊断与退出码，用户消息只描述任务和验证目标。

两项生产 RunLoop 回归均覆盖拒绝未知工具后恢复审批。459 项相关后端测试及 Windows 封装应用启动烟测通过。真实模型回归使用本地千问，工作区与审批恢复修复位于所有 Provider 共用的调用链。

## 尚未完成的验收

Windows NSIS 已构建，启动烟测运行解包后的应用。正式签名和安装升级另行验证。macOS 与 Linux 的单次 Workspace 命令路径保留，托管 Job 首发在 Windows 11 x64。

## 复验

从仓库根运行源代码验证。

```powershell
.\.venv\Scripts\python.exe -m pytest verification/tests/system/test_local_execution.py verification/tests/system/test_workspace_mutation_safety.py -q
.\.venv\Scripts\python.exe -m verification.bench run composition.data_workspace.scripted --output output/local-execution-composition
```

按 [本地模型安装说明](../architecture/local-model.md) 配置模型后，在两个新会话分别绑定有失败检查的 Python、TypeScript 项目。要求 Agent 先运行检查并读取真实失败，再修改实现、复跑检查和发布结果。比较失败与通过的 Job 退出码、关联文件与 Git diff。

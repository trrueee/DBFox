# 本地模型

> 文档类型：架构说明
>
> 状态：当前
>
> 最后核验：2026-11-23

Windows x64 上，DBFox 可以使用由 Sidecar 管理的 Ollama 模型。安装脚本将运行时、模型权重和推理临时文件放在指定的本地磁盘。应用数据目录只保存模型名称、权重摘要、大小、路径和上下文长度。

## 安装和使用

在 PowerShell 7.4 或更新版本中执行，关闭 DBFox 后运行：

```powershell
pwsh -NoProfile -File .\scripts\setup-local-model.ps1 -InstallRoot E:\DBFoxLocalModel
```

默认安装阿里通义千问 `qwen3.5:4b-q4_K_M`，上下文为 32,768 tokens，为工具定义、会话上下文和模型生成保留预算。安装时需要网络，选定的固定磁盘需要至少 12 GiB 可用空间。脚本校验固定版本 Ollama 压缩包的 SHA-256，下载模型后校验本机登记的模型和工具调用能力。下载中断时，重新运行同一命令可续传。

启动包含本功能的 DBFox，在 **设置 → 模型服务** 查看实际使用的模型、权重目录和大小，点击 **测试推理** 发送一次本机请求。输入框也显示本机模型。已有云端连接保存在原处，配置了本地模式时，发送消息和连接测试都不会使用这些连接。

开发或打包验收通过 `DBFOX_RUNTIME_DIR` 指定独立应用数据目录时，可将 `-ProfileRoot` 指到同一目录。一个运行中的 Sidecar 使用启动时读取的配置。更换模型或调整存储位置后重启 DBFox。

## 所有权

| 对象 | 所有者 |
| --- | --- |
| 模型版本和存储路径 | 应用数据目录中的 `local-model.json` |
| Ollama 实例和进程句柄 | Sidecar，复用 Windows Job Object |
| 已接纳 Run 的模型身份 | Run 的名称和请求中持久化的模型摘要 |
| 工具、审批、结果和取消 | 现有 Agent RunLoop 与 Tool Runtime |
| 设置页和 Composer | 引擎状态的 React Query 投影 |

侧车按需启动一个 Ollama 进程，绑定动态的 `127.0.0.1` 端口。只传递本机运行需要的环境，禁用 Ollama 云功能。引擎在发送对话前核对本机模型的名称与摘要，通过既有 Responses SDK 适配器完成流式传输和工具调用。启用本地模式后，配置错误、权重变化或启动失败以明确的错误结束请求。进程关闭或崩溃时由 Job Object 清理，后续请求按需启动新实例。

Host 内部区分具有启动副作用的 `endpoint()` 与只读 `running_endpoint()`：后者只在现有
进程仍活动且管理器未关闭时返回端点，不启动、重启或恢复模型。Bench 的结束遥测只使用
此只读查询；进程消失、连接失败或元数据无效时记录 `unavailable`，保留已经持久化的
Run/Trial 结果。遥测失败不替代任务失败原因，也不会触发模型请求或云端切换。

选择 Ollama 是因为其官方 Windows 运行时已提供量化权重管理、GPU 推理和兼容 Responses 的流式 API。发给 Ollama 的工具定义保留声明中的可选参数与默认值。持久化工具合同、执行校验和审批仍由既有 Tool Runtime 持有。DBFox 复用 HTTP SDK、上下文预算和进程树监督，新增的管理代码负责本机生命周期和配置，未新增 Python 或 Node 依赖。首发安装脚本和进程管理只支持 Windows x64。

- [Ollama Windows 运行时](https://docs.ollama.com/windows)
- [Ollama Responses 合同](https://docs.ollama.com/api/openai-compatibility#responses-api)
- [Qwen3.5-4B 权重与规格](https://ollama.com/library/qwen3.5:4b-q4_K_M)


## 真实任务验证

每个 Turn 构建一次工具快照，同时冻结声明参数与严格协议所需的 Schema。Ollama 使用快照内的声明参数，
包括可选项与默认值。执行仍校验同一快照记录的工具身份、输入合同和授权。

生产工厂将本地输出预算设为 `min(8192, context_length / 4)`，输入预算为
`context_length - output_token_limit - 1024`，32K 配置下输入为 23,552 tokens、输出最多 8,192。
8K 的已有配置仍预留 2,048 输出 token。此次调整依据真实文件生成耗尽原 2,048 上限并返回空
响应的复现，未修改权重、设备、整体上下文、并行或重试预算；本地验证范围见[Agent 交付可靠性复审](../quality/agent-delivery-verification.md)。
本地工具解析器可能在参数结束前不产生可读事件，因此本地 request/first-event/idle 受同一
240 秒整轮硬截止约束，避免短空闲窗口反复打断生成。取消仍持续探测，总 Run 时限仍为 900 秒。
工具 Schema、会话与观察均计入该预算。标称模型上下文不改变本机配置，也不会因此使用
通用 65K 上限。运行时拒绝与已接纳模型名称/摘要不符的配置，失败不切换云端。

Data Agent Bench 可通过 `--local-model-profile` 显式选择已有的本机 profile；不带这个
参数的旧云端评测入口仍需要明确凭据和 opt-in。不要将二者混为自动降级路径。验证期间
使用单独的 profile 副本，将 `state_dir`、`scratch_dir` 指向私有 D 盘目录并预先创建它们，
保留原模型名称、摘要、权重路径和上下文；不修改应用 profile，也不重复下载权重。

原三题各三次的生产 RunLoop 测量证明：4B 可以算出正确查询结果，但完整正文和引用
交付仍不稳定。新增两题各三次还发现一次只有检查计划、未计算却提前完成的回答；不能
把原三题数值正确外推为所有问题正确。查询成功后停止测试独占模型的故障验证确认：
任务明确失败、已有 Result 保留、不重放查询、不解析云端配置。当前结果及未验证的
9B、Electron、流式半途中断和安装包范围见
[Phase 0 记录](../quality/local-data-phase0.md)，不能把设置页“测试推理”通过当作业务能力通过。

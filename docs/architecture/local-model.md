# 本地模型

> 文档类型：架构说明
>
> 状态：当前
>
> 最后核验：2026-11-10

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

选择 Ollama 是因为其官方 Windows 运行时已提供量化权重管理、GPU 推理和兼容 Responses 的流式 API。发给 Ollama 的工具定义保留声明中的可选参数与默认值。持久化工具合同、执行校验和审批仍由既有 Tool Runtime 持有。DBFox 复用 HTTP SDK、上下文预算和进程树监督，新增的管理代码负责本机生命周期和配置，未新增 Python 或 Node 依赖。首发安装脚本和进程管理只支持 Windows x64。

- [Ollama Windows 运行时](https://docs.ollama.com/windows)
- [Ollama Responses 合同](https://docs.ollama.com/api/openai-compatibility#responses-api)
- [Qwen3.5-4B 权重与规格](https://ollama.com/library/qwen3.5:4b-q4_K_M)

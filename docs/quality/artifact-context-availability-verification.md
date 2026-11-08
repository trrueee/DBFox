# Artifact 上下文可用性修复验证

> 文档类型：质量证据
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：Core ContextAssembler 的结构化 Artifact 投影

## 问题与决策

Scene 独立 Adversarial Reviewer 使用真实签名 DLC、生产 RunLoop 产物和后续 SessionInput，证明 `available_artifact` 已拒绝的工件仍能通过选中引用进入模型上下文。近期贡献者输入、上一轮结果索引也绕过了同一校验。独立测试在修复前分别出现 6 个选中路径失败与 6 个贡献者/结果路径失败；测试代码只在 Scene 验证目录，不修改 Core。

Director 接受本次修复为冻结 Core 中现有读取边界的正确性修复。调查了 ContextAssembler 三处投影、ArtifactRepository 的来源证明与现有工具读取入口；采用直接复用 `available_artifact`。不新增 SDK、权限规则、映射模型、兼容分支、迁移、依赖或领域逻辑。来源权威仍由[已接受的 Invocation 设计](artifact-invocation-authority-review.md)决定。

## 最终行为

- 选中或附带的工件：只有证明可用后才投影标题、摘要、描述及 Representation；使用同一返回的规范 Artifact。
- 近期贡献者输入：对既有有界候选逐项证明可用，然后检查 payload 字节预算。未经证明的 payload 不进入 DLC 的上下文贡献者。
- 上一轮结果：工件索引、工具结果中的工件 ID/类型、计划步骤中的工件 ID 均经过同一可用性证明。完成但没有可用工件的 Run 不再宣称有可复用结果。
- 原有对话历史、工具自然语言摘要及失败/取消/部分完成的恢复说明保留；本修复不声称可以追溯清除已写入历史文字的信息。

仍保留同 Run 合法消费与跨 Run 的同 Session、生产者终态、顺序、非内部可见性及消费者资源版本边界。历史缺失生产者证明不会由 UI 选中状态补权。HTTP 用户历史展示与 Agent 执行权限仍分别处理。

## 作者验证

工作树 `D:/Project/DBFox-worktrees/creative-artifact-authority`，解释器 `D:/Project/DBFox/.venv/Scripts/python.exe`。以下为 Director 作者验证，独立 Scene 红队复验由其单独报告。

| 验证 | 结果 |
| --- | --- |
| ContextAssembler 定向集合 | 72 passed，10.66 秒；64 个组合覆盖两种输入引用、四种上一轮结局与八种来源状态 |
| 完整 Agent Core 确定性集合 | 314 passed、2 deselected，17.94 秒 |
| Visualization 签名包与资源边界集合 | 31 passed，16.99 秒；含 5 个真实 Data→Visualization RunLoop 组合与来源失效场景 |
| 静态检查 | ContextAssembler Mypy 通过；生产文件及测试 Pyflakes 通过 |

四个原有正例曾直接插入没有 Invocation provenance 的 Artifact，现改用真实 Session lease、Turn、ToolInvocationRepository.request、ArtifactRepository.persist_drafts 和工具结算；没有为测试放宽权限。新增组合也从同一真实生产链开始，再分别注入内部可见性、失败/缺失生产者、未来顺序、未终结生产 Run、陈旧资源版本或未完成 Artifact。正例同时断言可用内容仍存在，负例检查贡献者输入及最终模型消息。

```powershell
& D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/agent_core -q --tb=short -m 'not e2e and not integration and not real_llm'
& D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_dbfox_visualization_dlc_package.py verification/tests/system/test_resource_seam_closure.py -q --tb=short -m 'not e2e and not integration and not real_llm'
& D:/Project/DBFox/.venv/Scripts/python.exe -m pyflakes engine/agent/context.py verification/tests/agent_core/test_context_assembler.py
& D:/Project/DBFox/.venv/Scripts/python.exe -m mypy --no-warn-unused-configs --follow-imports=skip engine/agent/context.py --no-incremental
```

结构化候选数量和原有 payload/上下文预算保持有界；证明复用 Repository 的图深度及节点预算。本轮没有新增大规模性能声明、真实 LLM 声明或跨 Session 工件消费支持。

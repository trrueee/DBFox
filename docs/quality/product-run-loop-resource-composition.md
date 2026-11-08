# 生产 Agent 的资源解析装配修复

> 文档类型：质量证据
>
> 状态：当前
>
> 最后核验：2026-09-06
>
> 适用范围：Sidecar 创建 Agent RunLoop 的共享装配点

Shader 独立验证员使用真实 Electron、HTTP Sidecar 和官方原生 Responses adapter 接本机受控模型 SSE，首个 `shader_inspect` 在工具执行前失败：`No resolver is registered for resource scope kind 'dbfox.shader.studio'`。实际 Run 为 `run_a309431dd7d34b3897b3f55af76fe8f5`。此前同一环境的四个真实 ActionRun 能编译、观察 GLSL 错误、修复并预览；手工装配的 capability bench 也通过。这些通过不能代替正常 Agent 创建入口的证据。

## 根因与复用决定

已检查[生产装配根](../../engine/runtime_composition.py)、RunLoop/ToolDispatcher 和既有 runtime composition 测试，并核对历史 `132a29fb`。`build_product_run_loop` 传入工具、资源 provider、Context、Guidance 和 Artifact 合同，却漏传现有 attempt resolver。RunLoop 的默认空 resolver 因而无法解析任何需要该注册资源的工具。`build_dlc_action_runs_host` 及原 capability fixtures 已正确使用 `build_attempt_resource_resolver`，所以未暴露此装配遗漏。

采用唯一现有实现：生产工厂传入 `build_attempt_resource_resolver(snapshot=snap)`，与该次工厂创建的 registry/providers/Artifact 合同使用同一个快照。没有改变 SDK、ResourceRef、权限、存储、迁移、重试、Loop 或 Tool Runtime，也没有增加领域分支或解析 fallback。

这属于 Core 外层装配的正确性修复，符合[Kernel宪章](../architecture/core-kernel-constitution.md)的行为保持修复规则：能力 owner 已注册正确 resolver，不能从 DLC 修补 Host 漏传参数；变化仍 capability/provider-neutral、owner-bound 且未知资源拒绝。已有 API v2 包与冻结调用无需迁移，无兼容层或清理债务。

## 验证

Shader 独立工程师新增直接调用生产工厂的签名包 fixture，Director 原样复现 **1 failed / 3.19秒**，错误与真实 Sidecar 完全相同。该文件在 Shader 独立工作树随其验收提交，未为了引用它提前集成未通过门禁的产品。

根分支新增[生产工厂的跨能力回归](../../verification/tests/system/test_product_run_loop_capabilities.py)：复用 Scene/Voxel suite 的真实签名安装、入场、资源与独立 scorer；将 fixture 的手工构造入口替换为真正生产工厂，只控制模型 Responses，不注入 registry、resolver 或工具结果。修复后 Scene 创建及 Voxel 创建/修改/inspect/导出均通过完整 owner/Artifact/领域断言，**2 passed / 5.19秒**。原[装配合同](../../verification/tests/system/test_runtime_composition.py) **10 passed / 1.10秒**，pyflakes 通过；后续单文件mypy通过，根工程合同45 passed / 3.15秒。

根完整确定性回归为System **823 passed、135 deselected、51条既存告警 / 441.52秒**，Agent Core **314 passed、2 deselected / 20.96秒**，进程均正常退出。Shader独立生产工厂fixture修后1 passed / 2.99秒；Pixel独立工程师另用真实工厂完成document引用后的inspect→layers→rect，三个Invocation成功，仅外部模型受控。共享源补丁73ad76f0已同步八个候选工作树。Shader工厂与提交取消回归最终3 passed / 8.34秒。Shader独立工程师随后在冷重签ad83881d候选上完成同一Sidecar原生Agent复验：4.65秒、9个原生Tool调用、8个Artifact，Shader Dock全程为0；真实编译错误后检查诊断、仅移除错误token，再真实编译/预览成功并固定版本导出。独立完整报告还需收束窄Dock、CAS、stress与生命周期，当前复验只关闭生产工厂遗漏。本文的签名领域测试不等于成功 GPU、安装包或真实 LLM 智能证据；独立浏览器结果将按实际执行补记。

# 创作 DLC 的原生工具搜索组合验证

> 文档类型：质量验证
>
> 状态：当前
>
> 最后核验：2026-09-07
>
> 适用范围：三、四个签名 DLC 在默认生产 RunLoop 中的确定性协议与领域组合

## 结果和范围

采用[原生工具搜索决策](../architecture/bounded-tool-discovery.md)后，三能力和四能力组合均在生产默认 32768 输入预算下完成。测试真实使用 OpenAI Python SDK、Responses SSE Adapter、生产 RunLoop、签名包安装、ToolDispatcher、资源授权与 SQLite；只以 `httpx.MockTransport` 控制外部模型 HTTP 响应。它证明协议处理和领域执行链，不能证明真实模型的搜索选择质量、token 用量或费用。

| 安装能力 | 成功路径的 HTTP 请求数 | 托管搜索次数 | 领域调用 | 不可变 Artifact | 完整请求估算峰值 |
| --- | --- | --- | --- | --- | --- |
| Scene、Voxel、Pixel | 16 | 14 | 12 成功、3 次预期跨 owner 拒绝 | 12 | 25198 |
| Scene、Voxel、Pixel、Shader | 19 | 17 | 15 成功、3 次预期跨 owner 拒绝 | 15 | 32711 |

两组成功路径明确选择支持协议的 `gpt-5.4`；另两组使用原默认 `gpt-4o-mini`，确认不发送 tool search、不自动更换模型，并保留原全量 schema 的预算拒绝。四个测试 2026-09-07 运行结果为 **4 passed in 26.44s**。没有提高 RunLimits，也没有新增查询/选择控制工具或删除领域操作。

Shader 组合覆盖持久文档创建、局部重命名和固定修订导出；它没有调用 GPU，不是跨媒体渲染测评。真实 GPU 和窄/宽 Artifact 验证见[Shader 独立报告](shader-independent-verification.md)。

## 已验证的行为

- 每个包经正常签名、信任、安装、启用后注册；工具 wire name 保持唯一。
- SDK 收到完整工具定义与延迟加载标志；模拟服务器返回官方搜索调用、搜索输出和正常函数调用，搜索项真实进入耐久 Turn 和后续请求。
- ID、当前版本和下一步修改参数来自公开工具观察，没有读取 owner 私有数据库或导入 DLC 私有模块。
- Scene 保留未选中对象，仅移动狐狸；Voxel 仅修改指定区域；Pixel 的局部编辑保留其他像素。内容由固定 Artifact Representation 独立读取验证。
- Shader v1 和 v2 Artifact 保持各自标题与版本；导出没有虚构编译或预览结果。
- 将另一 owner 的私有 selector 传给工具被拒绝。成功 Invocation 的冻结 ResourceRef 仍属于对应 owner，包摘要仍匹配安装包。
- 停用 Voxel 后只移除其贡献与表示，其他 owner 继续可用；重新启用后原固定修订仍可读。
- 工具观察、领域上下文和完整请求均有预算断言；已加载的 schema 不因 `defer_loading` 而从历史预算中消失。

## 原失败与撤回范围

原生产三能力测试在根 `88fcb110` 上撤回自定义目录后重新运行，仍在 `ContextBudgetPlanner.fit` 抛出 `ContextBudgetExceeded: Tool schemas consume the complete model input budget`。这确认根因并未随 Shader CSS 修复消失。

用户授权撤掉自定义设计后，仅恢复其涉及的六个生产文件，并删除未提交的 `engine/tools/builtin/catalog.py`。原字节、工作树补丁和文件摘要已保存在仓库外的 `D:/Project/DBFox-worktrees/creative-program/recovery-before-native-search`。随后在保留原领域验收断言的基础上，将组合测试外部模型边界下移至 HTTP，移除了配合自定义目录的脚本选择逻辑。

原用户已有的 Story、Workspace、SDK、生成 API 和其他未提交改动，经备份摘要逐文件核对未变。备份不作为产品依赖，不纳入发布。

## 命令和待完成项

```powershell
.venv/Scripts/python.exe -m pytest verification/tests/system/test_creative_dlc_composition.py -q --tb=short
```

测试位于 [生产组合回归](../../verification/tests/system/test_creative_dlc_composition.py)，模型与目录支持规则由 [Adapter 回归](../../verification/tests/agent_core/test_openai_model_adapter.py)覆盖，预算和历史裁剪由 [预算回归](../../verification/tests/agent_core/test_context_budget.py)覆盖。

仍须分别完成真实端点对历史裁剪后重新搜索的验证、真实模型任务质量评测、其余 16 个 DLC 产品，以及原始要求的各项跨媒体任务。上述四个用例没有证明 20 个 DLC 同时启用时的容量。候选数量继续增长时，须实测官方 namespace 的目录压缩是否必要，不能沿用四能力数字宣称任意规模可用。

本报告由集成作者维护。[独立审查](native-tool-search-review.md)接受当前架构，并补充六个权限、审批、包版本、取消和 Coordinator 终止反例；它们均通过，协议/预算/组合独立复跑 49 项通过。

集成验证：系统确定性集合 1047 passed、135 deselected、51 项既有警告，752.77 秒；文档归档和 Shader 交接页眉修正后工程合同 45 passed，3.32 秒；最终 Core 集合 339 passed、2 deselected，23.18 秒；三个生产文件 mypy 通过。系统集合启动后补充的消息等价预算修复另经最终四组合与预算回归验证，未将早期完整集合冒充随后新修改的全量重跑。

# Creative DLC 首批联合验证

> 文档类型：质量证据
>
> 状态：当前
>
> 最后核验：2026-09-06
>
> 适用范围：Scene、Voxel、Pixel 在隔离联合工作树中的生产 Runtime 编排

Director 在 `codex/creative-composition` 的独立工作树中组合真实签名包，复用正式 PackageService、Runtime snapshot、Tool registry、资源绑定、RunLoop、Context、SQLite 与 Artifact Repository。当前默认生产工厂联合门禁失败：旧夹具手工设定128000 prompt预算，不能证明默认32768预算的产品路径可完成任务。验证代码没有导入任何 DLC 私有模块，也没有新增 Composition DLC 或 Core 抽象。

Historical composition evidence copied at user handoff. Current completion and review states are maintained in [the main handoff](../creative-program-handoff.md); the default-budget gate remains failing. Source code is in the separate composition worktree.

## 默认生产工厂故障

测试现直接调用 `build_product_run_loop(session_factory=factory, snapshot=snapshot)`，仅替换外部模型；手工注入registry、resolver、completion及RunLimits均已删除。三次创建成功，第4次prepare在模型调用前失败，原断言全部保留。以临时只读诊断核对的四轮 `(schema数, 估计token)` 为 `(13,3530)`、`(31,14886)`、`(45,22010)`、`(60,31942)`。最后一轮总预算32768，系统说明和耐久结果已无法容纳；最初把错误误判为首轮，现以实际调用轨迹纠正。

`materialization._strict_input_schema` 已使用官方SDK的 `pydantic_function_tool`；调查没有发现一份完整工具合同被错误重复追加。三个DLC共52个领域工具，其完整输入约束在同时可发现后共同占用预算。Pydantic官方命名类型别名可复用 `$defs`，将19处已有匿名类型改为Python3.12 `type` 的隔离试验得到30068，仍报 `Required system exceeds the model input budget`。试验已完全撤回，三个owner合同 `git diff --exit-code` 通过。没有增加依赖、改变canonical字段或提高预算。

以下历次通过结果保留为手工128000预算夹具的历史证据。当前真实工厂结果为 **1 failed / 4.04秒**，不得据历史通过标记默认跨DLC编排完成。修复需要保留全部必需增量工具和既有Invocation权限；通用按需工具发现仍处于调查阶段。

## 候选与命令

候选包括 Scene `50ccf2b7` 加独立终审 `37d9f8bf`，Voxel `0a908b00` 加修复 `b55ce7fb`、历史视图 `e587edd6`，Pixel 后端 `113f5334`、工作台 `5af763d0` 与历史索引修复 `b6987f23`（联合树 `4c2aa3b1`）；共享 Context 和 Artifact 引用修复继承根开发分支。此处组合候选不等于把尚未通过独立门禁的 Voxel/Pixel 合入主开发树。

最新联合候选另含 Voxel 样式/controls `e6267551` 与完整性修复 `61002688`、提交/历史修复 `25b1e76e`，Pixel 百帧/回执修复 `5f222e4e`，以及共享 stdout `883e6bb7`、树重复激活 `b3c9225d`。Scene 新生命周期候选 `5cdc6242` 已通过独立真实Electron验收并加入本联合树（69971139）。

```powershell
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_creative_dlc_composition.py -q --tb=short --show-capture=no
```

联合测试 (source file: `D:/Project/DBFox-worktrees/creative-composition/verification/tests/system/test_creative_dlc_composition.py`) 首次通过 **1 passed / 15.26秒**；Voxel 最新修复合入后再通过 **1 passed / 9.45秒**；Pixel 历史索引修复合入后通过 **1 passed / 12.50秒**。测试编写时修正了三个 fixture 假设：registry 还包含7个Core工具；Scene export 使用 expected_version；Pixel 表示类型是 sprite.v1。没有改动产品迁就测试。

Pixel 百帧与 Voxel controls 候选组合通过 **1 passed / 8.97秒**，最新 Voxel 完整性候选再次通过 **1 passed / 6.42秒**。最终Voxel25b1e76e后通过 **1 passed / 10.49秒**，再加入Scene5cdc6242后通过 **1 passed / 7.07秒**。再加入共享生产工厂resolver修复73ad76f0与Pixel出生/标签分页修复88e7c7d1（联合树afe3c604），通过 **1 passed / 8.08秒**。不同运行时间不作为性能提升结论，原联合测试断言未弱化。

## 实际验证的边界

| 项目 | 已验证结果 |
| --- | --- |
| 同 Runtime 激活 | 3个完整签名包同时激活，52个领域工具与7个Core工具的wire name无碰撞 |
| 单 Run 增量创作 | 15次工具请求；12次成功、3次预期拒绝。分别创建三种作品，局部修改至v3，导出12个真实不可变工件 |
| 模型事实来源 | 世界/文档ID和版本只取正式 function_call_output；没有从私有存储或评分器回填模型 |
| 私有资源隔离 | Scene接收Voxel ID、Voxel接收Pixel ID、Pixel接收Scene ID的selector均拒绝；各成功Invocation只绑定所属owner的一个正式资源 |
| 保留未修改内容 | Scene只移动fox，keep仍在[9,0,0]；Voxel保留8格并只改一格颜色；Pixel保留9个非透明像素并只改单像素颜色 |
| 工件正确性 | 全部工件通过同Run正式producer证明；通过注册的公开Representation独立读取对象、chunk与RGBA，并核对固定版本和fingerprint |
| 有界上下文 | 各Observation不超过25,600 bytes，三领域Context片段合计不超过12,000字符 |
| 停用与恢复 | 停用Voxel只移除该owner工具/表示；Scene/Pixel历史表示仍能读取；恢复Voxel后原v3与8格内容保持 |

历史夹具证明在显式128000预算下，生产Tool链可以编排三种独立创作媒介；默认工厂的容量故障仍未修复。没有消费另一领域私有状态，也没有新增联合持久状态的必要性。跨媒体资产消费（例如Pixel→Game）仍要在对应消费者完成后验证，不能据此宣称已有完整Composition产品。

## 门禁归属

本报告是Director的联合检查，不替代各DLC独立 Verification 或 Adversarial Reviewer。Scene此前已有正式13类bench、真实Electron编辑/导出/清理及68项独立红队；本结果供其本地集成决策使用。Voxel亦已完成独立Verification和Adversarial并集成；Pixel独立Verification已完成、另行Adversarial进行中，Shader独立Verification进行中。最终批次架构审计与四项稳定后的平台模式审计尚未执行。

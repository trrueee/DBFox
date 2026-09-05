# Creative DLC Program 接续记录

> 文档类型：质量证据
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：当前 Creative DLC 多 Agent 开发计划及独立门禁

机器状态维护在 [program-status.json](../../dlcs/program-status.json)。本计划仍涵盖 Scene/Voxel/Shader/Pixel、后续 Game/Comic/CAD/Animation、必要的 Composition 与第二波十二项能力，不因本次中断缩减范围。

## 当前进展

三个工作者已成功恢复。Scene 独立红队完整复验 **68 passed / 133.03秒**（35项领域、33项工件攻击），六项已确认问题均关闭；真实 Electron 已验证修复后的引用按钮和公开请求 schema。Scene 进入 integration candidate，仍需跨 DLC 验证。

Voxel 独立验证正在执行真实生产 Electron 与故障测试，已发现并复现导出前缺少导航检查、操作回执未核对固定 revision 两项缺陷，Director 正在修复。Shader 作者转任 Workbench Engineer，实现真实 WebGL2 执行器与 CodeMirror 编辑器。Scene 独立审查者结束该角色后转任 Pixel 独立 Verification Engineer。

此前三个工作者曾因账户 usage limit 中断，Director 当时完成了可执行的本地检查与候选保存；该中断保留在机器状态的 execution_history。没有以作者测试替代独立终审，所有 Creative DLC 的 integrated 继续为 false。

## 已保存候选

| DLC | 工作树 | 自有提交 | 已验证与剩余门禁 |
| --- | --- | --- | --- |
| Scene | `D:/Project/DBFox-worktrees/creative-scene` | `50ccf2b7`，84文件 | 真正编辑工作台、签名 RunLoop 13类、独立真实 Electron 编辑/导出/清理证据已保存；恢复后的独立红队68项通过，待跨 DLC 验证。 |
| Voxel | `D:/Project/DBFox-worktrees/creative-voxel` | `0a908b00`，45文件 | 47后端+14正式RunLoop用例通过，64³压力作品及导出留证；独立生产Electron验证与红队待执行。 |
| Pixel | `D:/Project/DBFox-worktrees/creative-pixel` | 后端 `113f5334`；工作台 `5af763d0` | 27工作台fixture通过；真实完整签名包的33后端/RunLoop测试通过。作者Canvas视觉证据使用受控transport；生产Electron、12类bench、狐狸骑士压力任务及独立红队待执行。 |
| Shader | `D:/Project/DBFox-worktrees/creative-shader` | `f6dde52a`，22文件 | 44后端测试、10模块Mypy通过，稳定JSON合同及真实RunLoop/ActionRun结算已保存。GPU回执仍为协议模拟；真实执行器、编辑工作台及独立验证未完成。 |

这些候选保存在各自分支，尚未作为完整 DLC 合入主开发树。根工作树 `D:/Project/DBFox` 的 `codex/creative-program` 已接入共享正确性修复；既有用户 dirty 基线继续保留，未整体暂存或提交。

## 本次共享修复与回归

- `078cee32` / 根 `e24d2423`：ContextAssembler 选中工件、近期贡献者输入、上一轮工件/工具/计划引用统一调用既有 `available_artifact`。没有改变来源权威、跨Session权限、SDK或模型。[上下文证据](artifact-context-availability-verification.md)。
- `d1d6bc29` / 根 `67468a07`：恢复工件面板九处乱码文案；60项定向回归通过。
- `00d43bfe` / 根 `96403e71`：真实引用按钮曾发送不合规范的 `object.kind="artifact"`，导致后端入场校验失败；现在直接用既有 artifactId 表达身份，68项回归和typecheck通过。[引用入场证据](artifact-reference-admission.md)。

根完整 Core/System 确定性集合 **886 passed、137 deselected，118.88秒**；工程合同 **45 passed，3.19秒**。Scene 候选工程合同 **45 passed，3.25秒**。原有51条框架弃用/预期重复归档告警没有导致失败。最后引用修复仅改前端发送处及回归，不增加后端 schema 或新的权限路径。

Scene 五文件接续运行曾为117通过/5失败：三个失败确认上述非法引用问题；两个用例仍假设完成Run在所有工件不可用时必须保留恢复索引。后者改用支持的 bounded_partial 状态，保持索引存在并继续断言非法ID不会出现，没有移除泄漏断言。修复后31项工件攻击通过（68.54秒），前次其余91项已通过；这些是Director接续结果，独立Reviewer需要重新审阅测试调整。

## 恢复调度

完整原始Lead模板、基线备份与角色交接均保留在 `D:/Project/DBFox-worktrees/creative-program`，无需从头重建工作树。

1. Scene 独立 Adversarial Reviewer 已交付最终通过结论，测试调整另增完成Run无可用工件时省略恢复索引的两项攻击；精确保存本轮证据后转任 Pixel 独立 Verification Engineer。
2. Voxel Verification 由未参与该产品的 `/root/pixel_workbench` 承担，使用完整 `voxel-independent-verification-handoff.md`。结束后再明确切换独立红队阶段。
3. Shader Backend 工作者已正式转任 Workbench Engineer，使用 `shader-workbench-handoff.md`。同属作者角色，之后不能自评 Shader 独立红队。
4. Pixel 使用 `pixel-independent-verification-handoff.md`，完整执行12类bench、十类压力修改与实际Electron验证。
5. Director 在独立 `creative-composition` 工作树组合 Scene/Voxel/Pixel 候选，验证正式 Runtime 多领域编排及资源/工件隔离；候选进入验证树不等于合入主开发树。
6. Phase B 出现通过完整门禁的稳定结果后按总计划启动 Game/Comic/CAD/Animation；只有证明普通多DLC编排不足时才创建Composition DLC。

根与各工作树中用户原有混合文档改动未整体提交。新增的架构澄清补丁分别保存在外部 `artifact-authority-documentation.patch`、`artifact-context-documentation.patch`，可精确区分任务增量。未提交SQLite、日志、凭据、安装包或运行时目录。Shader/Scene hash-pinned vendor均核对了工作树、Git index和实际checkout字节一致。

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

三个工作者已成功恢复。Scene 独立红队完整复验 **68 passed / 133.03秒**（35项领域、33项工件攻击），六项已确认问题均关闭；真实 Electron 已验证修复后的引用按钮和公开请求 schema。随后通过三owner联合验证，Scene已合入本地 `codex/creative-program`：候选 `6fee68f7`、独立终审 `7062e7f6`。合入后169项后端/bench/工程回归、12项前端和typecheck通过。

Voxel 独立验证已完成实际 Electron 历史下载逐 chunk 核对、3D 拾取、大世界、并发 CAS 与清理重启，正在整理最终报告；其发现的导航先决检查和回执完整性缺陷已由 Director 在 `b55ce7fb`、`e587edd6` 修复并复验，独立红队仍待单独执行。Pixel 独立验证发现的历史索引回退及缺失父版本已在 `b6987f23` 修复，21项故障与15项 bench 测试复验通过，真实桌面验收继续。Shader 已完成真实 Chrome WebGL2 作者探针和12项工作台 fixture，完整工作台交付与独立生产 Electron GPU 门禁尚未完成。

此前三个工作者曾因账户 usage limit 中断，Director 当时完成了可执行的本地检查与候选保存；该中断保留在机器状态的 execution_history。没有以作者测试替代独立终审。当前仅Scene的integrated为true，其余继续完整门禁。

## 已保存候选

| DLC | 工作树 | 自有提交 | 已验证与剩余门禁 |
| --- | --- | --- | --- |
| Scene | `D:/Project/DBFox-worktrees/creative-scene` | 候选 `50ccf2b7`；终审 `37d9f8bf` | 真正编辑工作台、签名 RunLoop 13类、独立真实 Electron 编辑/导出/清理与68项红队通过；三owner联合检查通过，已本地集成。 |
| Voxel | `D:/Project/DBFox-worktrees/creative-voxel` | 候选 `0a908b00`；修复 `b55ce7fb`、`e587edd6` | 独立36项故障、14类CLI bench与24项前端通过；实际Electron 64³/128³、历史导出、拾取、并发和清理已有证据，最终报告整理中，红队待执行。 |
| Pixel | `D:/Project/DBFox-worktrees/creative-pixel` | 后端 `113f5334`；工作台 `5af763d0`；索引修复 `b6987f23` | 33作者后端及27前端通过；独立14类CLI bench、21项故障和15项bench测试通过，8份PNG逐像素核对。生产Electron与独立红队继续。 |
| Shader | `D:/Project/DBFox-worktrees/creative-shader` | 后端 `f6dde52a`；工作台尚未提交 | 44完整签名后端、12前端fixture通过；实际Chrome WebGL2编译、驱动报错、2×2纹理和双pass像素探针通过。尚非生产Electron独立证据。 |

各候选保存在独立分支；Scene已通过完整门禁并合入本地开发树，Voxel/Pixel/Shader仍未完成集成。根工作树 `D:/Project/DBFox` 的 `codex/creative-program` 已接入共享正确性修复；既有用户 dirty 基线继续保留，未整体暂存或提交。

## 本次共享修复与回归

- `078cee32` / 根 `e24d2423`：ContextAssembler 选中工件、近期贡献者输入、上一轮工件/工具/计划引用统一调用既有 `available_artifact`。没有改变来源权威、跨Session权限、SDK或模型。[上下文证据](artifact-context-availability-verification.md)。
- `d1d6bc29` / 根 `67468a07`：恢复工件面板九处乱码文案；60项定向回归通过。
- `00d43bfe` / 根 `96403e71`：真实引用按钮曾发送不合规范的 `object.kind="artifact"`，导致后端入场校验失败；现在直接用既有 artifactId 表达身份，68项回归和typecheck通过。[引用入场证据](artifact-reference-admission.md)。

根完整 Core/System 确定性集合 **886 passed、137 deselected，118.88秒**；工程合同 **45 passed，3.19秒**。Scene 候选工程合同 **45 passed，3.25秒**。原有51条框架弃用/预期重复归档告警没有导致失败。最后引用修复仅改前端发送处及回归，不增加后端 schema 或新的权限路径。

Scene 五文件接续运行曾为117通过/5失败：三个失败确认上述非法引用问题；两个用例仍假设完成Run在所有工件不可用时必须保留恢复索引。后者改用支持的 bounded_partial 状态，保持索引存在并继续断言非法ID不会出现，没有移除泄漏断言。修复后31项工件攻击通过（68.54秒），独立Reviewer随后审阅调整，另增完成Run无可用工件时省略恢复索引的两项攻击，最终68项完整通过。

## 恢复调度

完整原始Lead模板、基线备份与角色交接均保留在 `D:/Project/DBFox-worktrees/creative-program`，无需从头重建工作树。

1. Scene 独立 Adversarial Reviewer 已交付最终通过结论，测试调整另增完成Run无可用工件时省略恢复索引的两项攻击；精确保存本轮证据后转任 Pixel 独立 Verification Engineer。
2. Voxel Verification 由未参与该产品的 `/root/pixel_workbench` 承担，使用完整 `voxel-independent-verification-handoff.md`。结束后再明确切换独立红队阶段。
3. Shader Backend 工作者已正式转任 Workbench Engineer，使用 `shader-workbench-handoff.md`。同属作者角色，之后不能自评 Shader 独立红队。
4. Pixel 使用 `pixel-independent-verification-handoff.md`，完整执行12类bench、十类压力修改与实际Electron验证。
5. Director 在独立 `creative-composition` 工作树组合 Scene/Voxel/Pixel 候选，验证正式 Runtime 多领域编排及资源/工件隔离；候选进入验证树不等于合入主开发树。
6. Scene已形成通过完整门禁的稳定结果。Game/Comic/CAD/Animation独立工作树和完整Lead模板已准备，工作者结束当前独立验收后轮转进入下一批；只有证明普通多DLC编排不足时才创建Composition DLC。

联合检查与报告保存在 `D:/Project/DBFox-worktrees/creative-composition`，测试提交 `6c18369a`。真实单Run执行15次请求（12成功、3次跨owner私有selector预期拒绝），产出12个有producer证明的工件；公开表示核对局部修改，停用和恢复Voxel保持另外两owner与原内容。Voxel修复后通过9.45秒，加入Pixel索引修复后通过12.50秒。该Director联合检查不替代各领域独立验收，也不代表跨媒体资产消费已实现。

根与各工作树中用户原有混合文档改动未整体提交。新增的架构澄清补丁分别保存在外部 `artifact-authority-documentation.patch`、`artifact-context-documentation.patch`，可精确区分任务增量。未提交SQLite、日志、凭据、安装包或运行时目录。Shader/Scene hash-pinned vendor均核对了工作树、Git index和实际checkout字节一致。

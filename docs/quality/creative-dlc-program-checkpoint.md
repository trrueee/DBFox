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

Voxel 独立验证报告已提交 `6467337c`，随后正式进入独立红队。新攻击发现摘要计数、回执冒领其他请求 revision、前端缺页/内容替换；Director 修复 `6100268` 已通过83项后端回归、8模块类型检查与独立32项前端测试，最终红队与重签浏览器门禁仍开放。Pixel 候选 `5f222e4e` 支持至多256帧且保留总像素预算；独立42项故障/bench、CLI15/15及真实200帧编辑、重启、375px和下载逐像素核对完成，验收报告正在收尾，另行红队尚未开始。Shader 的完整构建、类型检查、Lint和GLSL300实际驱动检查已通过，工作台作者证据冻结继续。

Scene 已集成后的追加调查证实 Control-held 原生监听器及 React DOM 清理顺序两个回归。隔离候选 `5cdc6242` 将14项作者前端测试全部转绿，primitive字节不变；独立真实Electron生命周期复验尚未完成，根分支暂未合入此修复，不能把旧普通卸载证据扩大为新条件已通过。

此前三个工作者曾因账户 usage limit 中断，Director 当时完成了可执行的本地检查与候选保存；该中断保留在机器状态的 execution_history。没有以作者测试替代独立终审。当前仅Scene的integrated为true，其余继续完整门禁。

## 已保存候选

| DLC | 工作树 | 自有提交 | 已验证与剩余门禁 |
| --- | --- | --- | --- |
| Scene | `D:/Project/DBFox-worktrees/creative-scene` | 原候选 `50ccf2b7`、终审 `37d9f8bf`；新修复 `5cdc6242` | 原候选已集成；新生命周期回归14作者测试通过，独立复验待执行。 |
| Voxel | `D:/Project/DBFox-worktrees/creative-voxel` | 验收 `6467337c`；红队修复 `6100268` | 实际Electron 64³/128³、历史导出、拾取、并发和清理已验；新红队继续，候选83后端/32前端通过，尚未集成。 |
| Pixel | `D:/Project/DBFox-worktrees/creative-pixel` | 产品 `5f222e4e` | 35作者后端、28前端通过；独立25故障+17bench、CLI15/15、实际200帧编辑和下载通过。独立报告收尾、红队待执行。 |
| Shader | `D:/Project/DBFox-worktrees/creative-shader` | 后端 `f6dde52a`；工作台尚未提交 | 44完整签名后端、12前端fixture通过；实际Chrome WebGL2编译、驱动报错、2×2纹理和双pass像素探针通过。尚非生产Electron独立证据。 |

各候选保存在独立分支；Scene已通过完整门禁并合入本地开发树，Voxel/Pixel/Shader仍未完成集成。根工作树 `D:/Project/DBFox` 的 `codex/creative-program` 已接入共享正确性修复；既有用户 dirty 基线继续保留，未整体暂存或提交。

## 本次共享修复与回归

- `078cee32` / 根 `e24d2423`：ContextAssembler 选中工件、近期贡献者输入、上一轮工件/工具/计划引用统一调用既有 `available_artifact`。没有改变来源权威、跨Session权限、SDK或模型。[上下文证据](artifact-context-availability-verification.md)。
- `d1d6bc29` / 根 `67468a07`：恢复工件面板九处乱码文案；60项定向回归通过。
- `00d43bfe` / 根 `96403e71`：真实引用按钮曾发送不合规范的 `object.kind="artifact"`，导致后端入场校验失败；现在直接用既有 artifactId 表达身份，68项回归和typecheck通过。[引用入场证据](artifact-reference-admission.md)。
- 根 `883e6bb7`：ready握手关闭readline后继续排空子进程stdout，避免日志填满pipe阻塞整个Sidecar。33项Electron测试、真实子进程4MiB因果探针通过；Pixel独立真实Electron连续1100HTTP全部200且没有重启。[stdout证据](engine-stdout-liveness.md)。
- 根 `b3c9225d`：普通/虚拟树已选中叶点击或Enter可重新打开已关闭tab；9项测试、typecheck、Lint及完整构建通过，实际Voxel重开待独立补证。[树激活证据](tree-resource-reactivation.md)。

根完整 Core/System 确定性集合 **886 passed、137 deselected，118.88秒**；工程合同 **45 passed，3.19秒**。Scene 候选工程合同 **45 passed，3.25秒**。原有51条框架弃用/预期重复归档告警没有导致失败。最后引用修复仅改前端发送处及回归，不增加后端 schema 或新的权限路径。

Scene 五文件接续运行曾为117通过/5失败：三个失败确认上述非法引用问题；两个用例仍假设完成Run在所有工件不可用时必须保留恢复索引。后者改用支持的 bounded_partial 状态，保持索引存在并继续断言非法ID不会出现，没有移除泄漏断言。修复后31项工件攻击通过（68.54秒），独立Reviewer随后审阅调整，另增完成Run无可用工件时省略恢复索引的两项攻击，最终68项完整通过。

## 恢复调度

完整原始Lead模板、基线备份与角色交接均保留在 `D:/Project/DBFox-worktrees/creative-program`，无需从头重建工作树。

1. Scene 独立 Adversarial Reviewer 已交付最终通过结论，测试调整另增完成Run无可用工件时省略恢复索引的两项攻击；精确保存本轮证据后转任 Pixel 独立 Verification Engineer。
2. Voxel Verification 由未参与该产品的 `/root/pixel_workbench` 完成，已正式切换独立红队，完整交接为 `voxel-adversarial-handoff.md`。
3. Shader Backend 工作者已正式转任 Workbench Engineer，使用 `shader-workbench-handoff.md`。同属作者角色，之后不能自评 Shader 独立红队。
4. Pixel 使用 `pixel-independent-verification-handoff.md` 完成独立验证并收尾；该验证员随后执行有界 Scene 新生命周期复验，见 `scene-controls-regression-handoff.md`。Pixel红队另行安排。
5. Director 在独立 `creative-composition` 工作树组合 Scene/Voxel/Pixel 候选，验证正式 Runtime 多领域编排及资源/工件隔离；候选进入验证树不等于合入主开发树。
6. Scene已形成通过完整门禁的稳定结果。Game/Comic/CAD/Animation独立工作树和完整Lead模板已准备，工作者结束当前独立验收后轮转进入下一批；只有证明普通多DLC编排不足时才创建Composition DLC。

联合检查与报告保存在 `D:/Project/DBFox-worktrees/creative-composition`，测试提交 `6c18369a`。真实单Run执行15次请求（12成功、3次跨owner私有selector预期拒绝），产出12个有producer证明的工件；公开表示核对局部修改，停用和恢复Voxel保持另外两owner与原内容。Voxel修复后通过9.45秒，加入Pixel索引修复后通过12.50秒。该Director联合检查不替代各领域独立验收，也不代表跨媒体资产消费已实现。

根与各工作树中用户原有混合文档改动未整体提交。新增的架构澄清补丁分别保存在外部 `artifact-authority-documentation.patch`、`artifact-context-documentation.patch`，可精确区分任务增量。未提交SQLite、日志、凭据、安装包或运行时目录。Shader/Scene hash-pinned vendor均核对了工作树、Git index和实际checkout字节一致。

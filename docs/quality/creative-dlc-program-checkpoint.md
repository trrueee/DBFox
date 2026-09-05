# Creative DLC Program 接续记录

> 文档类型：质量证据
>
> 状态：当前
>
> 最后核验：2026-09-06
>
> 适用范围：当前 Creative DLC 多 Agent 开发计划及独立门禁

机器状态维护在 [program-status.json](../../dlcs/program-status.json)。本计划仍涵盖 Scene/Voxel/Shader/Pixel、后续 Game/Comic/CAD/Animation、必要的 Composition 与第二波十二项能力，不因本次中断缩减范围。

## 当前进展

Voxel 已完成独立 Verification `6467337c` 和另行 Adversarial `f095d35f`，七类确认缺陷已由 `61002688`、`25b1e76e` 修复并独立关闭。最终冷签名 Electron 证明实际已选资源重开、600次HTTP全部200、64³/128³世界、历史全部chunk及原生下载逐字节相等、Control-held清理和停启代际隔离。候选及证据已精确合入本地 `codex/creative-program`，最后集成提交 `bb9a00a4`。根分支197项后端/bench/工程回归通过（168.18秒），59项Voxel/Scene/Tree前端通过（10.38秒），typecheck通过；产品、vendor、独立测试和suite与最终隔离分支一致。[最终对抗报告](voxel-adversarial-review.md)保留成本和覆盖限制。

Scene 原稳定候选已集成；新增生命周期修复 `5cdc6242` 的真实 Electron 独立复验现已通过普通及Control-held四次卸载、原生callback identity清理、GPU/RAF/observer/poll停机、重开Orbit/拾取/Inspector/Gizmo，以及拖拽中关闭和generation切换后的迟到响应。独立证据ea720a8f已与修复一同合入根分支fd3d8cfb/1ec34c12；根14项前端（4.65秒）与45项工程（3.14秒）通过，产品/vendor与独立验收候选一致。

Pixel 独立验证完整提交 `6ed057d0`：42项故障/bench、CLI15/15、真实200帧编辑、1100次HTTP、CAS无重放、375px布局与原生PNG下载逐像素核验完成。另行Adversarial发现非法出生版本与tag完整成员工具入口两个问题，88e7c7d1已修复；77项既有回归、18项独立首轮复验及20项新增Artifact攻击通过，最后冷签名复验进行中，当前未集成。Shader 作者冻结 `4df3568d`；Director已完成15类生产RunLoop领域测评、17测试和CLI15/15，包括62-stage/438486-byte大型文档、128uniform和双pass程序化作品十次修改。没有模拟成功GPU；独立验证已完成真实ActionRun编译/错误/修复/预览、双pass纹理四角逐字节核验与256²原生PNG下载。真实Agent暴露共享工厂resolver遗漏，正常窄Dock暴露窗口断点错误，事务末尾暴露取消窗口；分别由2bd3fa75、003eb7ec、ad83881d修复。最后冻结候选的同Sidecar原生Agent、GPU、窄Dock和生命周期复验进行中，之后仍需另行红队。

Game Lead已在独立 `creative-game` 工作树完成作者25项规范及固定Phaser4.2.1真实Chrome探针，修复受hash守卫的VisibilityHandler销毁监听；现在实现唯一owner后端，独立架构和最终门禁尚未完成。Comic/CAD/Animation工作树和完整Lead指令已准备，第二波十二项能力及必要的Composition仍在原计划内。当前四个并发槽按明确角色轮转，容量错误恢复不改变独立门禁或原范围。

| DLC | 当前候选与阶段 | 未完成门禁 |
| --- | --- | --- |
| Scene | 5cdc6242生命周期修复与ea720a8f独立证据已集成 | 后续跨媒体Composition与常规维护 |
| Voxel | 25b1e76e + f095d35f，已集成至bb9a00a4 | 后续跨媒体Composition与常规维护 |
| Pixel | 88e7c7d1，独立验证完成、红队修复复验中 | 独立Adversarial、本地集成 |
| Shader | ad83881d，领域bench通过、真实GPU复验中 | 真实Electron独立Verification、完整GPU stress、另行红队及集成 |
| Game | 作者架构及引擎探针完成，后端实施中 | 产品实现及全部原始门禁 |

根工作树原有用户dirty baseline保留。各自精确提交，不整体暂存、提交运行时数据库或扩大作者证据的证明范围。

## 本次共享修复与回归

- `078cee32` / 根 `e24d2423`：ContextAssembler 选中工件、近期贡献者输入、上一轮工件/工具/计划引用统一调用既有 `available_artifact`。没有改变来源权威、跨Session权限、SDK或模型。[上下文证据](artifact-context-availability-verification.md)。
- `d1d6bc29` / 根 `67468a07`：恢复工件面板九处乱码文案；60项定向回归通过。
- `00d43bfe` / 根 `96403e71`：真实引用按钮曾发送不合规范的 `object.kind="artifact"`，导致后端入场校验失败；现在直接用既有 artifactId 表达身份，68项回归和typecheck通过。[引用入场证据](artifact-reference-admission.md)。
- 根 `883e6bb7`：ready握手关闭readline后继续排空子进程stdout，避免日志填满pipe阻塞整个Sidecar。33项Electron测试、真实子进程4MiB因果探针通过；Pixel独立真实Electron连续1100HTTP全部200且没有重启。[stdout证据](engine-stdout-liveness.md)。
- 根 `b3c9225d`：普通/虚拟树已选中叶点击或Enter可重新打开已关闭tab；9项测试、typecheck、Lint及完整构建通过，实际Voxel已选leaf关闭后原地重开已独立通过。[树激活证据](tree-resource-reactivation.md)。

先前根完整 Core/System 确定性集合 **886 passed、137 deselected，118.88秒**；工程合同 **45 passed，3.19秒**。Scene 候选工程合同 **45 passed，3.25秒**。原有51条框架弃用/预期重复归档告警没有导致失败。最后引用修复仅改前端发送处及回归，不增加后端 schema 或新的权限路径。

Scene 五文件接续运行曾为117通过/5失败：三个失败确认上述非法引用问题；两个用例仍假设完成Run在所有工件不可用时必须保留恢复索引。后者改用支持的 bounded_partial 状态，保持索引存在并继续断言非法ID不会出现，没有移除泄漏断言。修复后31项工件攻击通过（68.54秒），独立Reviewer随后审阅调整，另增完成Run无可用工件时省略恢复索引的两项攻击，最终68项完整通过。

本次生产工厂修复复用既有frozen resolver并保持同一snapshot，根 **823项System / 441.52秒、314项Agent Core / 20.96秒**全部通过；Scene/Voxel实际工厂与Shader/Pixel独立工厂用例通过。没有扩大Core或SDK合同。[生产装配证据](product-run-loop-resource-composition.md)。

## 当前调度

完整Lead模板和交接保留在 `D:/Project/DBFox-worktrees/creative-program`。

1. `/root/pixel_workbench` 完成Voxel独立红队后，正式转任Shader独立Verification；完整补充交接为 `shader-independent-verification-handoff.md`。
2. `/root/voxel_lead/domain_architect` 完成Pixel独立验证后，完成Scene有界生命周期复验ea720a8f后，正式执行Pixel另行Adversarial；不得把原故障用例改名充数。
3. `/root/scene_lead/domain_architect` 完成Shader作者候选后，正式转任Game Lead，执行完整 `lead-game.md`。
4. Director维护本地集成、Shader领域bench及三owner联合验证。独立 `creative-composition` 候选不等于所有DLC已经集成；只有普通多DLC编排确实不足才创建Composition DLC。

联合检查与报告保存在 `D:/Project/DBFox-worktrees/creative-composition`，测试提交 `6c18369a`。真实单Run执行15次请求（12成功、3次跨owner私有selector预期拒绝），产出12个有producer证明的工件；公开表示核对局部修改，停用和恢复Voxel保持另外两owner与原内容。Voxel修复后通过9.45秒，加入Pixel索引修复后通过12.50秒，最终Voxel25b1e76e后通过10.49秒，加入已独立通过的Scene5cdc6242后通过7.07秒，加入Pixel88e7c7d1与生产工厂修复后通过8.08秒。该Director联合检查不替代各领域独立验收，也不代表跨媒体资产消费已实现。

根与各工作树中用户原有混合文档改动未整体提交。新增的架构澄清补丁分别保存在外部 `artifact-authority-documentation.patch`、`artifact-context-documentation.patch`，可精确区分任务增量。未提交SQLite、日志、凭据、安装包或运行时目录。Shader/Scene hash-pinned vendor均核对了工作树、Git index和实际checkout字节一致。

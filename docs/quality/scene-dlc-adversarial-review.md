# Scene 独立对抗审查

> 文档类型：质量证据
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：`creative-scene`，Scene 产品及其实际经过的共享 Artifact 边界

独立审查已恢复并完成。候选 `50ccf2b7` 上本轮两个对抗测试文件 **68 项通过**，退出码 0；六项确认问题均已独立复验关闭。真实 Electron 引用入口也已复测：当前 Host 发出合法的 Artifact ID 引用。后续读取仍受 Session、producer proof 与 exact Input fence 约束，不因点击引用而获得 document authority。

## 评审基线与系统地图

审查者未参与 Scene 产品实现；此前独立 Verification 已结束，本轮新增攻击用例并重新执行，不将作者或先前通过数作为对抗证明。初始基线为 `354f57a7` 和当时 Scene 未提交文件，最终复验候选为 Director 保存的 `50ccf2b7f19ca709d4a5b2dddc2859bd7ae6a378`。领域及共享修复均由 Director 实施；审查者只新增验证与证据。`.codegraph` 不存在，依约跳过；已重新阅读完整 Lead 模板，采用 staged-quality-review 的证据等级与复用准则。没有修改产品代码、SDK、共享 Bench schema 或通用授权规则。收尾提交仅保存独立测试、浏览器脚本、报告及精选证据。

主要路径是 Scene 工具/typed human operation → 唯一 SceneStore SQLite 事务 → immutable revision + receipt → 正式 Invocation Artifact；Scene Workbench 从有固定版本的分页构造显示投影，拖动只提交增量操作。模型从注册 Resource 目录及当前 Invocation 绑定获得操作权限；Workbench 的 object/locator/Artifact ID 是提示信息。Artifact 读取还须证明 producer Invocation、显式 lineage 和跨 Run exact Input fence。高风险边界因此在领域解析、事务末尾、历史 resolver 和模型结构化上下文投影。

产品使用现有 ToolRuntime、ActionRun、Pydantic、stdlib sqlite3、Host React 和官方 Three.js。搜索 `engine`、`sdk`、`dbfox_dlc_api.py`、`desktop/main` 未发现 Scene 类型/错误码泄漏；Scene backend 无 engine internal import，前端自有代码无直接 fetch/WebSocket 外链。第三方 vendor 不作为手写业务源码审查。

## 确认问题与最小修复点

| 编号 | 级别 | 修前实证 | 修复位置与状态 |
| --- | --- | --- | --- |
| SCENE-A1 | P2 | `schema_version: Literal[1]` 接受 `true`、`1.0`；SQLite 只替换这两个值而保留原 hash，读取仍成功。 | `dlcs/dbfox.scene/backend/contracts.py:117` 的 SceneDocument：改为 strict integer 且范围固定 1。原 4 个失败断言独立复验通过，已关闭。 |
| SCENE-A2 | P2 | 正式 `scenes.apply` 接受 `visible="false"`/`0`、position 中 `true`/数字字符串并提交 v2；类型错误未在声明的领域标量边界拒绝。 | 同文件 `:22` 起 Integer/Boolean/Number/Coordinate 等字段严格校验，保留 JSON list→tuple 的表示转换。原 4 个失败断言独立复验通过，unknown/null 仍拒绝，已关闭。 |
| SCENE-A3 | P2 | SQLite revision 的 title/count/status 单列损坏后与 canonical document 不一致，`get_revision` 仍返回；原 hash 不覆盖这些独立摘要列。 | `dlcs/dbfox.scene/backend/store.py:234` 的 `_revision_from_row` 统一验证大小、schema、hash、摘要、head/max version、状态和直接 parent，目录返回项也走此边界。原 3 个失败断言与新增 7 类 head/parent/list 破坏均通过，已关闭。 |
| SCENE-A4 | P1 | `ArtifactRepository.available_artifact` 已拒绝工件，但 ContextAssembler 仍将其放进 selected_artifacts、recent_artifacts contributor 输入及 previous_run_outcome。 | 共享 `engine/agent/context.py:716`、`:785`、`:1131` 三个入口复用唯一 availability；Scene 合入 `c4f0b7fe`。独立攻击覆盖三个入口及 failed/cancelled/bounded_partial 上轮结果、plan/tool 结构化引用，已关闭。 |
| SCENE-A5 | P3 | 真实 Artifact Dock 顶部引用按钮显示 `����Ի�������`，点击功能仍执行。 | `desktop/src/features/dock/dockViewContent.tsx:162`，Scene 合入 `3e545297`。本轮真实 Electron 捕获按钮为「加入对话上下文」，已关闭。 |
| SCENE-A6 | P2 | Host 发出 `object.kind="artifact"`，不符合 namespaced ReferencedObject.kind，消息在 SessionInput 入场前被 schema 拒绝；点击成功不能证明可提交。 | 同文件 `:153` 起 emitter 只发送既有 label/artifactId，Scene 合入 `c4d24b25`。保留旧形状拒绝断言，独立复验新形状三种 fence 场景及真实 UI 引用，已关闭。 |

A1/A2 的范围是领域输入与损坏检测，不据此声称越权写入。A3 的复现需要损坏本地数据库；修复在唯一 DB row→Revision 读取边界完成，没有新镜像或兼容层。A4 则可在正常 mutation 后引用 pre-write refs 工件时触发 stale-fence 不一致；internal、failed/missing producer、future sequence、nonterminal owner 属于额外白盒防线攻击。它没有使 Scene Tool 获得额外写权限，但会把正式读取已拒绝的结构化工件信息发给模型，影响跨 Run 上下文隔离。

最小复现命令（本树根目录）：

```powershell
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_scene_dlc_adversarial.py -q --tb=short --show-capture=no
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_scene_artifact_adversarial.py -q --tb=short --show-capture=no
```

领域首轮 **11 failed / 10 passed in 36.00s**。原断言未为产品修复降级；修复后含新增崩溃/并发等攻击为 **32 passed in 58.14s**，之后新增的结果丢失再删除、停用 resolver、8 MiB 持久化上限也已分项通过。共享 selected-context 首轮修正验证 fixture 后 **6 failed / 5 passed in 28.82s**；额外两个结构化入口为 **6 failed / 21 deselected in 14.32s**。Fixture 的 lease owner、typed model 字段和异常种类修正不计作产品缺陷。

## Artifact 与 document 引用的实际支持范围

新的正式签名 Scene RunLoop 连续 create→object_create→export，三个产物证实：创建 payload v1 / refs library@1；mutation payload v2 / refs document@1；只读导出 payload v2 / refs document@2。三者在其自身 Run 都能通过 producer proof；下一个仅请求当前 document@2 的同 Session Input 中，正式 availability 依次为 **拒绝、拒绝、允许**。这符合 producer 输入事实与跨 Run exact fence，不是把 mutation refs 改成 post-write 版本的理由。

同 Run 的额外来源只在明确 `derived_from` 指向已证明工件时成立；未声明 lineage、使用 `supports` 代替或形成循环均拒绝。该证明只服务工件依赖，没有让工具的私有 selector 继承来源资源权限。

真实 Electron 已重新执行两种按钮，并核对运行的签名包中 frontend/index.js、model.js、viewport.js 与当前审查文件逐字节相同。该前端包沿用上一阶段签名 digest，未用于证明后续 strict backend 修复。首次观察及源码 hash 见 [初始引用证据](../../verification/bench/capabilities/dbfox_scene/evidence/browser-reference-adversarial.json) 与 [初始截图](scene-browser-evidence/scene-artifact-reference.png)；其中通用引用的非法 object 形状和乱码是修复前事实。

候选恢复后再次运行真实 UI，见 [修复后引用证据](../../verification/bench/capabilities/dbfox_scene/evidence/browser-reference-adversarial-after.json) 与 [修复后截图](scene-browser-evidence/scene-artifact-reference-after.png)。捕获的通用引用只有 label/artifactId，没有 object 或 authority；按现有请求边界将 artifactId 命名为 artifact_id 后，实际捕获值通过公开 ConversationInputReference 与 ConversationInputRequest schema。浏览器阶段没有发送付费模型请求；入场后的 inspect/edit 与 Artifact 可用性由正式签名 RunLoop 对抗测试验证。

| 用户入口 | 实际引用内容 | 后续 Run 支持范围 |
| --- | --- | --- |
| Scene Studio「引用到 Agent」 | document authority(kind/id) + object 当前 version；无 Artifact | 服务端从当前目录绑定 document head。独立正式后续 Run inspect v2→transform v3 通过。 |
| Host Artifact Dock「加入对话上下文」 | label、artifactId；没有 object 或 document authority | 合法通过请求 schema；Artifact-only 不扩充 Input refs。异 Session 或 exact source refs 不匹配时不能读取该工件；原引用 ID 仍只是用户附带提示。 |
| 同 Session 当前导出 + 显式 document 引用 | 当前 document authority 与导出 Artifact ID 并列 | 当前 export 的 producer refs 可匹配，允许作为工件上下文；旧 mutation 工件 refs 仍不能因此升级。 |
| Project Workbench 导出后引用到新聊天 | 产物来自独立 ActionRun Session；Project draft 当前 Conversation 为 null | 新聊天不满足产物同 Session 读取条件。可从工件的「编辑当前场景」打开当前 Scene，再用 document 引用完成创作；不承诺把历史工件跨 Session 自动导入。 |

本轮分别测试 document、Scene 自有 export reference 形状、Host 实际 Artifact-only 形状、联合 document 形状和异 Session。将 Scene 自有 `referenceFor + artifactId` 测试冒称 Host 通用 Artifact 引用已通过，会掩盖没有 authority 的区别。

## 攻击覆盖与证据强度

| 边界 | 本轮新增攻击 | 断言 |
| --- | --- | --- |
| 类型/损坏 | schema bool/float/string/null，nested scalar、unknown/URL/null，摘要与 head/parent/list 破坏，超 8 MiB 空白填充 | 入口或读取失败；错误值不能规范化后蒙混通过 hash |
| 事务/恢复 | receipt INSERT 触发失败；独立子进程在真实产品事务 receipt 写入点 `os._exit(73)`；revision 插入后 commit 前取消 | head/revision/entity reservation/receipt 无部分残留；同 ID 可合法重试 |
| 结果未知 | 注册 mutation 提交后取消响应，再由人类删除 | 历史 resolver + exact receipt 恢复原 v2 Artifact，当前 head 保持 v3，没有重放 |
| 并发 | 两个线程同时执行正式 human typed operation 与注册 ToolRuntime；同 ID 不同 payload | 只有一个 CAS 成功，稳定对象没有 lost update；复用 ID 的不同输入拒绝 |
| 权限/生命周期 | 用已绑定 Scene A 的私有 selector 指向项目 B；停用后新 snapshot 解析旧 ref；恢复后历史读取 | 目标 B 无修改；停用无 resolver，恢复状态保留；deleted 历史读取不授权普通写入 |
| 预算/资源 | 501 对象请求；150 个最长 Unicode 名称及长数值的灯光，通过完整 RunLoop 分页；导出 URL/path/version 参数 | 整批拒绝无残留；模型分页实体完整、无重复遗漏、显式 continuation，Observation ≤25 KiB、Scene context ≤4000 chars；外部资源参数拒绝 |
| 工件证明 | exact producer、输入版本与输出版本、同 Run lineage、跨 Run 顺序/status/visibility/source fence；失败/取消/部分完成 Run 的 plan/tool 引用 | 三个结构化上下文入口与正式 availability 一致；原始引用 ID 和历史自然语言 plan note 不授予 authority |

对抗 fault injection 只放在验证层：sqlite trigger 与子进程终止制造真实事务失败，实际领域写入仍由产品执行。没有实现私有替代 store、下载器、授权协议或全场景替换链。真实浏览器本轮只运行引用/导出按钮，不进行模型付费调用；最后通过应用关闭退出本次 Electron，启动器 exit 0，命名 Playwright `scene-red` 已 detach。精选证据不含 SQLite、日志、token；隔离 Runtime 保留在仓库外。

## 复用判断与限制

字段级 strict validation 沿用已有 Pydantic，而不加输入 mapper 或手写数字解析；官方文档支持字段严格约束，并明确 JSON 验证与 Python 对象验证存在差异。[Pydantic strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/)。事务和崩溃恢复继续依赖 sqlite3/SQLite 的原子提交机制，本轮进程终止测试检验产品事务是否正确包围 revision/head/receipt，没有另造恢复日志。[SQLite atomic commit](https://www.sqlite.org/atomiccommit.html)。通用 Context 应调用现有 Artifact availability，不应维护第二份资源权限集合。

本轮不重复审查 Three vendor 全部第三方源码，不证明实际 LLM 自主创意能力、任意 GPU、原生保存对话框点击或硬盘断电硬件故障。10k 完整分页读取约 20 秒仍沿用上一阶段实测限制，并非本轮重新测量。历史 revision 按既定 retention 保留；本轮不引入自动项目清理或无依据的新配额。

最终结论：本轮 Scene 独立对抗审查通过，已确认的 P1/P2/P3 均有修复后独立证据，没有未闭环的已确认问题。结论限于本报告列明的候选、攻击和支持范围，不表示整个 Creative Program 完成，也不扩大历史 Artifact 的跨 Session/跨版本读取权限。

## Director 中断期间接续记录（历史）

独立 Reviewer 因 usage limit 停止后，Director 执行现有五个 Scene 文件，得到 **117 passed / 5 failed，171.84秒**。失败中三项在 SessionInput 之前即因实际 Host 的 `object.kind="artifact"` 被 canonical schema 拒绝，确认新增 **SCENE-A6 / P2**：点击加入引用成功不代表消息可以提交。正式 UI emitter 已改为只发送 label 和既有 artifactId，保留后端 namespaced Object 合同；共享提交 `00d43bfe`，Scene 合入 `c4d24b25`，见 [入场修复](artifact-reference-admission.md)。原始非法形状保留为拒绝回归，三种新形状继续覆盖同 Session、联合 document 和异 Session fence。

另两项失败是恢复索引用例仍断言 `previous_run_outcome is not None`，而修复后的完成 Run 在所有工件均不可用时正确省略该索引。Director将这两个用例的上一轮结果设为真实支持的 bounded_partial，让恢复索引仍存在后继续检查没有任何非法工件 ID；没有删除防泄漏断言或放宽生产权限。

这些调整后 **31项 Artifact 攻击全部通过，68.54秒**；前次其余91项已通过且产品未再变化。A4的selected/recent/previous泄漏在本地接续复跑中已消除，A5纯文案已修复，A6入场修复的68项共享前端回归及typecheck通过。上述结果由Director产生，不改称独立审查者复验；当时仍未通过独立终审，Scene integrated 为 false。该历史门禁由下节的恢复后独立结果接续。

## 恢复后的独立复验与交付

独立检查 Director 的测试调整后，保留旧 `object.kind="artifact"` 非法形状的 schema 拒绝断言，新 Artifact ID 形状仍分别验证同 Session、联合 document 和异 Session。两个 previous-run 测试改用 bounded_partial 是为了保留恢复索引并继续查漏；为防止遗漏原完成分支，另增 `test_completed_prior_run_without_available_artifacts_omits_recovery_index` 的 internal/failed-producer 两个参数，用真实完成 Run 证明三个工件都不可用时索引为 None。没有修改产品或削弱泄漏断言。

2026-09-05，从本 worktree 根执行：

```powershell
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_scene_dlc_adversarial.py verification/tests/system/test_scene_artifact_adversarial.py -q --tb=short --show-capture=no
```

结果 **68 passed in 133.03s，exit 0**，其中领域攻击 35 项、Artifact 攻击 33 项。这是恢复后的独立执行，不引用 Director 的通过数替代。两个测试文件 pyflakes、引用浏览器脚本 `node --check` 与 `git diff --check` 也通过。最后独立执行工程合同 `test_documentation_file_names_are_stable_and_portable`：**1 passed in 1.42s**；报告所有相对文件链接存在，JSON 证据位于 suite-owned evidence 目录。

本轮专属交付：

- [领域攻击测试](../../verification/tests/system/test_scene_dlc_adversarial.py)
- [Artifact 攻击测试](../../verification/tests/system/test_scene_artifact_adversarial.py)
- [真实引用浏览器脚本](../../verification/bench/capabilities/dbfox_scene/browser-reference-adversarial.cjs)
- 初始及修复后引用 JSON、两张截图（见上文链接）
- 本独立报告

修复后浏览器仅使用本任务启动的隔离 Electron。通过应用窗口关闭退出，启动器 exit 0，命名 Playwright `scene-red` 已断开。没有本轮遗留的 route、下载 hook 或调试附加；仓库外隔离 runtime 留存，无删除或提交。此前获授权运行官方 Visualization vendor 构建产生的五个字节修正文件保留为未提交变更，不属于本次 Scene 交付。

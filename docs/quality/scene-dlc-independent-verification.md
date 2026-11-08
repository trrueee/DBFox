# Scene 独立验证

> 文档类型：质量证据
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：Windows x64，`creative-scene` 工作区，Scene 独立 Verification Engineer

## 范围与方法

验证者此前参与 Voxel 后端与通用 Host 导航审议，未参与 Scene 实现，独立性成立。本轮不是后续独立 Adversarial Reviewer 的终审。已完整阅读外部 Lead 模板，特别是 I/J/K/L；作者的后端测试和 Workbench fixture 不计作本人的独立证明。最终独立结果为 **22 项 pytest 通过、统一 CapabilityBench CLI 13/13 通过**；真实 Electron 编辑、导出导航、表示流下载、作用域取消和停用恢复均已执行。

新 suite 位于 `verification/bench/capabilities/dbfox_scene`，复用共同 manifest、TrialOutcome、reporting、Alembic metadata、正式签名包与 production RunLoop/ToolDispatcher/ToolRuntime。模型边界复用 ScriptedProvider 的原生 Responses 事件；动态 scene ID/version 只能来自实际 function_call_output，不从 Store 回灌。评分器可以通过正式注册的只读 project operation 检查 canonical 历史文档，与模型决策隔离。

这是确定性运行机制和领域结果验证，不是实际 LLM 创意质量评分。12 类能力案例及一个狐狸神殿压力场景均已定义；压力场景主体 63 个稳定命名节点，随后添加灯光/相机/供品，覆盖添加、删除、局部变换、层级重构、主灯降低 20%、歧义不写、冲突拒绝、人类直改、undo/correction、最终材质 refinement。歧义回答后由新的用户澄清输入继续同一 Session，其余 create/edit/inspect 在各自 Run 内连续执行，不为每次修改换 Run。

## 已确认缺陷与复验

| 编号 | 生产路径证据 | 状态 |
| --- | --- | --- |
| SCENE-V1，P1 | `scene_create` 已成功且有耐久 Artifact，但 `AgentObservationRecord.model_output_json.facts` 为 `{}`，模型拿不到 scene ID/version。Scene 工具没有覆盖 BaseTool 默认投影；默认仅保留 count 等通用字段。作者 ToolRuntime 直接读取 output 未覆盖这一边界。 | Director 已添加 DLC `project_observation`；独立 RunLoop simple-creation 已通过，原缺陷复现用例保留。 |
| SCENE-V2，P1 | 同 Run 创建后 object_create 已在领域事务提交 v2，但 Artifact 结算报 `TOOL_OUTPUT_CONTRACT_FAILED`。`engine/agent/repositories/artifact.py` 的 `_prepare_drafts` 用最初 Run authority 校验新 draft；ToolDispatcher 已按当前 Invocation 正确绑定新 Scene。最初 authority 是 library，所以合法 Scene invocation 的资源不能通过 Artifact 子集检查。 | Director 的权威边界修复 `8ba14f69` 合入本树 `354f57a7` 后，独立完整 22 项及 CLI 13/13 通过。不清空 resource_refs，不通过每次新 Run 掩盖。 |
| SCENE-V3，P1，Host lifecycle | 真实 Electron 首次启动后签名 Scene 注册产生两条同 digest CSS；`scenes.artifact` 正式 ActionRun 成功，`openArtifact` 在第一次 `assertCurrent` 即拒绝，尚未发送 Session GET。只读 CDP Debugger 证明 lease aborted=true、navigationActive=false、scopeMatches=true，而 Scene 消费方 controller aborted=false。`extensionLoader.ts` 在等待 import 后、调用 register 前没有 epoch 检查；并发 register 可把同 ESM 的全局 host 指向已撤销 registration。 | Director 修复已合入 `dbc2b98c`；独立关闭旧 Electron/Engine 后冷启动，实际 Session GET 和 RunArtifacts GET 均 200、openArtifact resolve。随后 V5 修复后完整可见下载链也通过。 |
| SCENE-V4，P2，Host Tree | 10,000 对象的 Large Root 折叠时只显示一个树节点，DOM 却仍有 10,000 treeitems、60,357 elements。真实加载包含 899ms 主线程长任务，层级折叠未减少子树挂载。 | Director 修复已合入 `a0dc0840`；独立真实 Electron 复测折叠仅 1 treeitem/414 elements，展开挂载 22 虚拟行，可滚至 Node 9999，再折叠回 1。 |
| SCENE-V5，P1，Host Dock 可见性 | V3 修复后正式导出→Session GET→RunArtifacts GET 均成功，activeDockKey 已是新 Artifact 且 canonical artifactsById 已载入，UI 却仍显示 Scene Studio，无下载按钮。`coreDockViews.tsx:34` 的单 Artifact 可见性要求当前 Conversation，Project draft 工作台的 activeConversationId=null，合法 ActionRun 工件被隐藏。 | Director 修复合入 `4b9957d1`。Host 验证归属后填现有 tab.projectId，Timeline 保持原 Session 规则。独立冷启实际 Artifact Dock、Scene Artifact renderer、下载按钮及磁盘文件均验证通过。 |

V1 复现命令：`D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/bench/test_scene_bench.py -q --tb=short -k simple-creation`。修复前唯一失败检查是 `scene_observed`，Invocation succeeded 且 Artifact 存在，facts 为空。

V2 复现命令：同文件加 `-k invalid-recovery`。create succeeded、故意无效 parent 被拒绝、reinspect 显示 v1、合法 object_create 的 Invocation failed；正式只读操作看到 canonical 已变为 v2。修复前完整 suite 首轮为 **1 passed / 12 failed**，部分后续不可发现工具是此前失败导致 Run 进入收尾的后果，不单独计为产品缺陷。

## 独立故障验证

`D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_scene_dlc_verification.py -q --tb=short --show-capture=no` 首轮 **8 passed in 14.70s**。覆盖真实 frontend/index/model/viewport/vendor 和 primitive bytes 的签名包，停用贡献清理与重新激活保留状态；Runtime 调用前取消/超时；提交后取消/超时而结果未知的精确 receipt 恢复；current head 的 expected/frozen 双检查；损坏内容和未知 owner schema 拒绝。

这些故障测试使用签名注册工具与正式 Runtime；提交后丢失响应的故障注入仅设置取消/延迟，实际领域事务仍由产品方法执行。它们不是全套 RunLoop 创作通过结论。加入正式 RunLoop Artifact 历史固定测试后，相同命令 **9 passed in 17.03s**：由真实持久 Artifact 读取的 v1 在人类编辑到 v2、soft delete 到 v3 后仍固定，不能用请求参数覆盖 version，伪造 Project 被拒绝。

## 最终 RunLoop 与创作结果

在本树根目录、`354f57a7` 加 Scene 未提交产品/验证文件的状态执行：

```powershell
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/bench/test_scene_bench.py verification/tests/system/test_scene_dlc_verification.py -q --tb=short --show-capture=no
D:/Project/DBFox/.venv/Scripts/python.exe -m verification.bench run capability.dbfox-scene.scripted --output docs/quality/scene-bench-report
```

第一条 **22 passed in 33.73s**，即 13 个能力/压力案例和上述 9 个独立故障案例。第二条 exit 0、**13/13**；原始输出随后原样移动到 suite 自有 [正式报告目录](../../verification/bench/capabilities/dbfox_scene/evidence/scene-bench-report/report.md)，符合 docs 不接纳 JSON/二进制文件的工程合同。后续运行应将 `--output` 指向新的仓库外目录或 suite evidence 子目录。模型 Scene context 最大 **2522 chars**，Observation 最大 **21302 bytes**；完整 Run/Invocation/Artifact、包 digest、来源 refs 和评分结果保留在同目录 `trials.json`。

狐狸神殿压力场景执行 24 次工具调用、26 个模型回合，最终 **v18 / 67 节点 / 2 材质**，Artifact 为 `artifact_5ee1fb9bc3034b20b726a9996d2ec75f`。领域评分核实十类持续修改、稳定 ID、局部修改的无关对象不变，以及歧义、无效请求和 no-op 没有追加文档版本。通过这个持久 Artifact 的注册 Representation 导出 glTF 76249 bytes、GLB 60656 bytes，官方 Khronos validator `2.0.0-dev.3.10` 对两者均为 **0 errors / 0 warnings / 0 infos**。作品、SHA-256 和 source-version/fingerprint 见 [导出证据](../../verification/bench/capabilities/dbfox_scene/evidence/scene-bench-report/export-evidence.json) 与 [可重复创作说明](../../dlcs/dbfox.scene/examples/fox-temple.md)。

## 真实 Electron 第一轮证据

使用 suite 的 `browser_fixture.py` 构建完整签名包、实际项目与 canonical 场景；`browser-launch.mjs` 仅准备父进程隔离环境，启动真实 Electron Main/Preload/EngineSupervisor 与真实 Vite，未替换 operations、Renderer 或下载 API。令牌由 EngineSupervisor 管理，仅在父子进程环境与内存使用，未写入证据文件。Playwright CLI 通过只绑定本机的 CDP 连接，实际导航到工作台。签名包 digest、正式 Run/Invocation/Artifact 与版本详见 [初轮耐久审计](../../verification/bench/capabilities/dbfox_scene/evidence/browser-initial-durable.json)，测量条件详见 [测量记录](../../verification/bench/capabilities/dbfox_scene/evidence/browser-measurements.json)。

实际 pointer 拖动 Three TransformControls 红色轴使 `qa-cube` 从 v2 保存到 v3，检查器把 Y 改为 1.5 后保存 v4；每次 `scenes.apply` 返回 changed_ids 仅 `qa-cube`，最终位置 `[0.7288495407201738,1.5,0]`，另一个灯未变。刷新后仍保留。WebGL2 使用本机 RTX 4060 Laptop GPU/D3D11，canvas 1470×1087，未使用 fake renderer。导出按钮已通过真实 `scenes.artifact` 创建四次正式 ActionRun/Invocation/Artifact（后续重复点击是人工诊断，不是产品自动重放），每次 tokens/cost 为零，但因 V3 不能把这称为完整下载链通过。

10,000 对象场景经过 102 次正式分页读取，约 17.94 秒显示；JS heap 约 119.45 MB，主线程长任务 899ms 和 51ms。全场景聚焦后执行 45 次 orbit pointer move，3 秒 RAF 采样的 p95 间隔 20.8ms、最大 25.1ms，无超过 50ms 长任务。这些采样包含空闲间隔，不代表真实渲染 FPS，亦不推论低端硬件表现。DOM 折叠问题单列 V4。

V4 修复后沿用同一 canonical 场景，折叠 DOM 降至 1 个树节点/414 个元素，JS heap 约 82.43 MB，加载长任务为 118ms 与 71ms；展开后挂载 22 个虚拟行，实际滚到尾部可见 Node 9999，ARIA sibling count 为 9999，再折叠恢复 1 行。完整读取仍为 102 页/19.60 秒，本轮不宣称整体加载提速。对比图：[修复后折叠](scene-browser-evidence/scene-10000-collapsed-after.png)。

精选快照见 [真实编辑](scene-browser-evidence/scene-edited.png)、[10k 折叠层级](scene-browser-evidence/scene-10000-collapsed.png)、[10k 聚焦旋转](scene-browser-evidence/scene-10000-orbit.png)、[修复后可达尾行](scene-browser-evidence/scene-10000-last-node.png)。

## 真实导航、下载与生命周期复验

修复后使用新的隔离 Runtime、重建签名包并冷启。最终包 digest 为 `21ceabee97f28f37d63627d8445ddf93747e6fa554e08f2d73166bef09e6ccc7`。试图将同版本不同 digest 包放入旧 fixture 时，正式安装器正确拒绝 `conflicting_digest`，未绕过检查。最终 [耐久审计](../../verification/bench/capabilities/dbfox_scene/evidence/browser-final-durable.json) 保留 4 个正式 ActionRun/Invocation/Artifact；[浏览器最终检查](../../verification/bench/capabilities/dbfox_scene/evidence/browser-final-checks.json) 保留下载、取消、停用恢复的对应身份与结果。

真实导出按钮经 `scenes.artifact`、ActionRun、Session GET、RunArtifacts GET 和唯一 canonical 投影打开实际 [Scene Artifact Dock](scene-browser-evidence/scene-artifact.png)。实际下载按钮读取注册 Representation 流，生成 Blob 后触发 Electron DownloadItem。成功下载 Artifact `artifact_05a7954fdd4a4c09935ba274f540ad35` 对应 Run `run_2f99dcde36814270b6e4d0202901fb5b`；GLB **2164 bytes**、glTF **2421 bytes**，两次 Native `done=completed`，received=total，磁盘 SHA-256 与 Renderer 只读 Blob digest 一致。保存作品位于 [GLB](../../verification/bench/capabilities/dbfox_scene/evidence/browser-download/interactive-scene.glb)、[glTF](../../verification/bench/capabilities/dbfox_scene/evidence/browser-download/interactive-scene.gltf)。`node dlcs/dbfox.scene/validate-gltf.mjs output/playwright/interactive-scene.glb output/playwright/interactive-scene.gltf` 对二者均为 0 errors/warnings/infos。

下载测试显式控制的是**原生保存路径边界**：verification-only Electron bootstrap 在官方 `will-download` 中调用 `item.setSavePath`，路径严格限于本树 `output/playwright` 两个固定文件名，文件由 Electron 自己接收和写入，没有将 Renderer Blob 直接写文件冒充下载，也未改生产 Main/CSP。默认 Electron 下载通常使用保存对话框；`setSavePath` 是官方绕过该对话框选择路径的接口。[Electron DownloadItem 文档](https://www.electronjs.org/docs/latest/api/download-item/)。因此本轮不声称自动化了原生保存对话框点击。

初次使用 CDP `Browser.setDownloadBehavior(allow)` 时，两份流已 200、Blob 仍可读取且哈希正确，Native item 收完字节后 interrupted、savePath 为空；切回 default 后，item 收完字节保持 progressing 等待保存选择。该自动化边界诊断保留在最终检查中，不把 POST 200 或 toast 作为下载成功证据。最终用 default 加上述受控 SavePath 后磁盘验证通过。

作用域取消测试只延迟真实 Session GET 的 200 响应，未构造虚假 JSON。正式导出已生成 `artifact_15025b7146d64fa88f71f843d7e83baa` 后，实际 UI 切到 Default Workspace，再释放响应并切回 Scene Browser QA；两个作用域都没有该晚到 Artifact tab。检查仅读现有 Store 投影，未写入；route 在 finally 撤销。随后正式 DLC 停用和 Engine 重启使 CSS、canvas、Scene Workbench 都为 0，重新激活并重启后 CSS=1、canvas=1，QA Cube 状态仍在。显式重启旧端口关闭时观察到一次 `/dlcs/activation` 连接拒绝，恢复后新加载为 0 console errors、1 Electron warning。

所有本次命名 Playwright 连接、CDP Debugger、路由延迟和受控下载 hook 已撤销；仅本次启动的 Electron/启动器通过应用关闭结束，最后启动器 exit 0。仓库外 `dbfox-scene-browser-20260905` 与 `dbfox-scene-browser-final-20260905` 临时 Runtime 保留，不提交 SQLite、日志或 token。只保留 suite、测试、精选截图、白名单审计、报告和导出作品。

收尾检查：suite 与两份独立测试的 Pyflakes 通过，15 个浏览器脚本 `node --check` 通过，26 个本地 Markdown 链接及 evidence JSON 语法通过，`git diff --check` 通过。完整 `test_engineering_contracts.py` 首轮 **44 passed / 1 failed**：既有 `test_visualization_vendor_is_reproducible_offline_and_csp_safe` 发现 Visualization vendor manifest 记录 796160 bytes、实际 bundle 796175 bytes，为已确认的 Windows CRLF 生成文件偏差。按 Director 授权在 `desktop` 执行现有 `npm.cmd run build:visualization-vendor`，未手改 manifest 或断言，重跑同一工程集合为 **45 passed in 3.13s**。生成的 Visualization 文件不属于本轮 Scene 交付，不提交。docs 命名单项也独立 **1 passed in 1.10s**；JSON/导出文件已移到 suite evidence。

当前 Verification 阶段已完成。独立红队仍未执行；真实 LLM 自主创意能力、原生保存对话框点击以及不同硬件性能不在本次通过结论内。10k 场景完整分页加载约 20 秒仍是可见限制。

# Shader DLC 调查与独立合同审议证据

> 文档类型：验证证据
>
> 状态：草案
>
> 最后核验：2026-09-05
>
> 适用范围：Shader DLC 编译路径可行性与独立 Domain Architect 审议；不是实现验收报告。

架构提案见 [Shader DLC](../architecture/shader-dlc.md)，机器状态见 [program-status.json](../../dlcs/dbfox.shader/program-status.json)。

## 当前结果

- 已完整阅读 Director 实例化的 Shader Lead 模板，并按当前任务逐项研究 canonical model、正式 DLC boundary、编译器与浏览器执行路线。
- `.codegraph/` 不存在于本工作树，按 AGENTS 指令跳过 CodeGraph；使用源码检索。
- 独立 worktree `creative/shader` 中原有用户未提交基线未修改或提交。只新增 Shader 专属文档与状态。
- Khronos glslang 是成熟 GLSL/ESSL validator；其官方 Web binding 走 Vulkan/SPIR-V，不作为 WebGL ESSL 编译成功替代。
- 生产 CSP 没有 eval/WASM 许可；native packages 被现有 package contract 禁止；不添加这些依赖、不改 Core/SDK。
- Director 复核后允许优先验证现有 machine operations + activation 隐藏 Canvas 的 DLC-local 派生计算路径。尚无真实执行验证结果。
- Music 的 Basic Pitch 在 UI 操作后上报后端，但 Agent 仍要求先在 Studio 转录；不能把它描述为无人值守闭环的已验证先例。

## 必须如实保留的验证缺口

Director 在仓库外完成一个编辑器兼容性探针：固定 `codemirror 6.0.2`、锁文件解析的
`style-mod 4.1.3` 与 `esbuild 0.28.2`，官方 npm audit 报告 0 vulnerabilities。
在与生产相同的 HTTP CSP 下，将真实 CodeMirror EditorView 安装到 ShadowRoot；其上游
[style-mod 官方实现](https://github.com/marijnh/style-mod/blob/master/src/style-mod.js)
使用标准 constructed stylesheet。浏览器测得 0 个 style 元素、1 个 adopted stylesheet、
正确的 relative 定位及五行编辑区域；程序修改与 Playwright 的实际键盘输入均在编辑器中生效。
控制台仅有 favicon 404，没有 CSP 错误。未修改 CSP，未修补上游库。

探针、固定依赖和浏览器记录保存在仓库外
`D:/Project/DBFox-worktrees/creative-program/codemirror-review`；浏览器与临时服务已关闭。
这支持后续继续评估 CodeMirror 6，不代表 Shader 编译、GLSL 高亮、错误定位、Shadow DOM
可访问性、卸载或打包 Electron 已通过。正式 vendor 仍应在 Shader owner 的构建中锁定、
记录许可证并完成相应测试。

未实施 backend、Workbench、compute request/receipt、tests、bench 或 example。独立 Domain Architect 审议已在本轮完成；独立 Adversarial Reviewer、Shader DLC 真实 GPU smoke 和 packaged Electron 仍未完成。Scene 组在开发 Chrome 的 WebGL2/CSP 证据不记作 Shader 生产验证。

首轮调度共有四个并发槽，当时 Director + Shader Lead + Scene Backend + Voxel Backend 占满；Shader Lead 只做有边界的调查。2026-09-05 Director 另行分配 `/root/shader_architect` 完成独立 Architect 阶段，尚未将其分配为实现或红队，不把 Lead 自审记为独立审议。

## 独立 Domain Architect 审议

审议者 `/root/shader_architect`，工作树 `creative/shader`，基线仍为 `2dc62653` 加原用户未提交基线。本阶段只修改本页和同一份 [Shader 架构文档](../architecture/shader-dlc.md)，没有实现源码、共享锁文件、Core 或 SDK 改动；没有执行 DLC 测试或作测试通过声明。

实际读取：完整 Shader Lead 模板、AGENTS、CONTRIBUTING、文档规范/术语表、Core Kernel 宪章、DLC platform/extension/capability 合同、SDK Tool/operation/resource/observation 接口、frontend loader 与 owner operation 实现、Electron window 配置、Music/Story 现有 store/tool/projection，以及相关 Git 提交历史。`.codegraph` 不存在，使用 rg/源码读取；官方资料覆盖 WebGL2、WebGL FBO/readback、KHR_parallel_shader_compile、Electron visibility/throttling、PyPNG。CodeMirror 官方 reference 页面本轮返回 Internal Error，未把失败访问当作库不可用；复用 Director 已有真实 ShadowRoot 探针与上游 style-mod 源码证据。

结论：现有 typed machine operations 可以表达单次 Tool 与 activation GPU executor 之间的真实执行边界，**允许进入实现**。Resource 仍为每 Project 一个 `dbfox.shader.studio`；无新增 Core seam、永久计算队列、第二套 Run lifecycle、native/WASM、CSP 放宽或外部服务。详细数据/API/预算/恢复规则只在架构文档第 7 节维护。

本轮修正的实现前风险：

| 发现 | 已冻结的处理 |
| --- | --- |
| 原预算允许 16×1 MiB texture，完整 base64 snapshot 超出 Host 单次操作上限 | 单 texture 1 MiB、总 raw 4 MiB，完整 compute.next <= 8 MiB；显式设置 output 上限，拒绝超限 |
| 只按当前 studio generation 解析会拒绝历史 invocation 的 reconcile | revisions 记录 studio generation，resolver 历史只读；正常写分离 CAS；receipt lookup 不重放 |
| BaseTool 默认 projection 不保证模型获得 document/object/version | 每个 Tool 显式 ToolObservationProjection；created_refs/report id/版本进入有界 facts，source 只按页提供 |
| 首轮没有冻结 uniforms、pass 输入、纹理行序、像素成功条件 | 完整 v1 字段、前向有序 pass、typed local refs、反射检查、独立 FBO/readPixels、top-left RGBA 与 PNG 编码边界 |
| 同 ESM 重复 register、晚到 attach/detach 可能撤销新执行器 | local monotonic token + registration_counter，exact epoch/lease，旧回调只处置自己的资源 |
| 关闭 Dock 与隐藏整个 Renderer 被混淆 | executor 独立于 Dock；hidden 停止领取，lease/deadline 收敛，恢复只服务未来显式请求 |
| KHR completion=true 可能来自 context lost | completion 后仍检验实际 COMPILE_STATUS/LINK_STATUS、反射、GL error 和 isContextLost |
| 同步 GPU 调用不能被 Python cancellation 立即抢占 | 后端独立 deadline 拒绝晚到结果，释放本地资源；即时 GPU 抢占仍不作承诺 |
| unknown 写/计算和持久报告缺少恢复语义 | 同事务 receipt/report，reconcile 只查已提交证据，缺失 unknown；不自动重新执行 GLSL |
| owner 历史无总预算及 undo hash 重复风险 | 256 MiB payload 计费配额，保留历史，hash 不唯一，undo 生成新版本 |

官方核验：[WebGL2 规范](https://registry.khronos.org/webgl/specs/latest/2.0/)、[WebGL framebuffer/drawing buffer 规则](https://registry.khronos.org/webgl/specs/latest/1.0/)、[KHR_parallel_shader_compile](https://registry.khronos.org/webgl/extensions/KHR_parallel_shader_compile/)、[Electron BrowserWindow visibility](https://www.electronjs.org/docs/latest/api/browser-window#page-visibility)、[PyPNG 官方文档](https://pypng.readthedocs.io/en/latest/)。WebGL latest 页面为 editor draft；本轮未依赖新增 experimental API，选用既有 WebGL2 compile/link/FBO/blit/readPixels 功能。源码核验 `desktop/main/index.ts` 没有设置 backgroundThrottling，结合 Electron 官方默认 true 得出隐藏窗口不可保证持续计时的限制。

报告对 pending scope settlement 平台修复的处理：Director 已告知 Artifact repository 对 Run 初始 refs 与当前 invocation refs 错配另有独立修复；本领域仍输出真实 invocation scope。该通知是外部协调信息，本轮没有在 Shader 树重现或修复 Core，也不会清空 refs 或每个 Tool 新建 Run 来绕过。

后续实现者必须按冻结合同验证 signed package activation、Dock 关闭下 production Tool 的 Generate → Compile Error → Inspect → Repair → Preview；测试模拟 bridge 回执不能算真实 GPU 证据。12 类 benchmark、10 类创作 stress、真实 Workbench 和未参与实现的独立 Adversarial Review 均未完成。若本 Architect 后续转为 Engineer，红队必须另派人员。

文档校验：对两份 UTF-8 文件逐行检查尾空格/不可见字符并解析相对 Markdown 链接，结果 0 问题；`git diff --check` 通过。因为这两份文件仍为未跟踪的新文档，另行执行的内容/链接检查覆盖了 git diff 默认不会检查它们的情况。本轮未修改 program-status.json，由 Director 在角色交接时同步机器状态。

## 下轮成功证据

需要在不打开 Shader Dock 的情况下，生产 Tool 创建文档并生成无效源、真实编译错误、读取错误、局部修复、成功链接和真实像素预览。回执要验证 owner/package/epoch/invocation/version/hash/nonce/deadline；错误、取消和过期回执不能发布成功 Artifact。Human 编辑与 Agent 编辑必须共享 SQLite CAS。所有实验需保留可复现命令、真实输出和明确平台范围。

## 后端作者阶段：2026-09-05

状态：当前。角色 `/root/scene_lead/domain_architect` 从 Host correctness 工程转任 Shader Backend Engineer；其未参与此前 Shader 独立架构审议。本节是作者实现与验证，不是独立 Verification 或红队。工作树 `D:/Project/DBFox-worktrees/creative-shader`，实现基线 `1f001436`（Director 已合入 generic navigation/loader/tree 与 Invocation Artifact authority）；未修改 Core、SDK、前端、其他 DLC、共享锁或用户 dirty baseline。

实现包括 strict canonical/Input contracts、17 个 typed mutation tags、13 Tools、12 project operations、4 machine operations、SQLite CAS/历史/tombstone/object ids/分 actor receipts/256 MiB payload quota、单瞬时 compute slot、3 Artifact types、4 Representations 和显式有界 Context/Observation。实际模型生成的 [contracts.schema.json](../../dlcs/dbfox.shader/contracts.schema.json) 是 Workbench 字段交接，测试逐 operation 对比 input/output schema，防止手写契约漂移。

复用：标准库 sqlite3/事务、hashlib/base64/json/difflib、Condition/monotonic；公共 DLC SDK 负责 Resource、Tool、ActionRun、Artifact 和 Representation。未新增 Core/共享依赖、兼容 fallback、第二套 Run、自动重放或双写文档。PyPNG 使用未修改的官方 0.20220715.0 源码（82781 bytes，SHA-256 `b1c6211078af892bbe975f948d40e19f2e9ec064994f635b6e431b5c55e56830`）和 MIT 许可证；仅 Writer 编码已有 validated RGBA，不使用 Pillow 产品依赖或上游 decoder 处理用户压缩图。vendor provenance 保留官方 PyPI archive/hash。

新增获 Director 批准的 `texture_bytes` 只读页已写入同一架构第 7.7 节；它解决重新打开工作台读取既存纹理的具体需要，不改变 Tool scope 或增加 HTTP/Run。测试重组原字节并核 hash，覆盖末页、旧 revision 删除后读取、错 Project/revision/null/bool/hash override 与读取取消 probe。

验证命令均从 Shader 工作树根运行：

```powershell
& 'D:/Project/DBFox/.venv/Scripts/python.exe' -m pytest verification/tests/system/test_shader_dlc.py -q --tb=short
& 'D:/Project/DBFox/.venv/Scripts/python.exe' -m pyflakes dlcs/dbfox.shader/backend verification/tests/system/test_shader_dlc.py
& 'D:/Project/DBFox/.venv/Scripts/python.exe' -m mypy --no-warn-unused-configs --follow-imports=skip --no-incremental --exclude 'vendor' dlcs/dbfox.shader/backend
git diff --check
```

pytest **44 passed**，最终以 `a349c89b`（已含共享 Context 消费授权修复）复跑通过；pyflakes 无输出；mypy 自有 10 个 Python 模块通过（上游 png.py 保持原样，不用类型检查改写 vendor）。覆盖真实 SQLite reopen、同事务批次失败回滚、CAS 竞争单赢家、studio frozen fence、noop、undo 重复内容、128 active document 限额、tombstone 恢复、source/pass/uniform/bool/null/数值预算、owner 计费与 payload/hash/head/generation/identity 损坏 fail-closed。

正式宿主证据：

- 通过实际 Ed25519 构建、信任安装、ContributionCompiler 启用、禁用贡献撤销、再次启用，验证持久文档恢复和新 backend epoch。当前 frontend 尚未交付，测试仅在临时目录复制实际 backend、移除临时 manifest 的 frontend entry 后构建 backend-only 包；没有伪造 renderer 或将其计为完整桌面包。以后真实 frontend/index.js 存在时，同测试直接签名完整源码包。
- 真正的 project `documents.export/compile/preview` → Host action_runs → ToolRuntime → completed AgentRun → durable Artifact，验证具体 returned IDs 和 exact source。compile/preview 使用测试线程提交的**模拟 GPU 协议回执**，所以只证明生产动作/结算路径，不证明平台编译或像素生成。
- 签名 backend 下生产 RunLoop 完成 9 次同 Run Tool：create → source inspect → exact patch → stale rejection → inspect → no-op → undo → source diff → export。scripted Provider 仅从正式 `function_call_output` 读取下一步 document/stage/version；没有从 store/fixture偷取 ID。验证实际持久 Invocation、Observation、Artifact 数量与 Artifact refs 等于该生产者的冻结 Invocation refs；未清空 refs 或每次编辑另建 Run。
- bridge 负例包括 package/claim/invocation/document/version/hash/request_hash、重复 counter、新 client 抢占、旧 detach、deadline/cancel/重启/迟到 complete、非法 compiled/rendered/pixel 组合。计算交接后直到 SQLite 最后提交检查仍保留原 epoch/lease/deadline fence；同一 document 中途更改拒绝证据，另一 document 修改不影响已领取 snapshot。
- 故障注入令 report 已 INSERT 但 receipt 前抛错，事务内 report/计费整体回滚；已有 report/receipt 之后无 executor 的正式 ToolRuntime reconcile 返回相同输出和 Artifact draft，缺 receipt 返回 unknown，不重跑 GLSL。
- 已知 2×2 RGBA 验证 bottom-left → top-left 只翻转一次；PNG 逐像素 round trip，另用独立 stdlib 检查 PNG signature/IHDR、每块 CRC 与 DEFLATE 原始扫描行。Representation sample 返回同一 top-left 像素。此已知输入测试不是 WebGL readPixels 实证。

测试范围的限制：尚无真实 Electron WebGL compile/link/reflection/FBO/KHR/context-loss/CSP/Dock-closed 证据；没有真实驱动性能或立即抢占保证；Workbench、12 类 benchmark、10 类连续 stress 和未参与实现者的 Adversarial Review 均待后续角色。项目删除公开 hook 当前不存在，未假装实现。共享 Context 对 selected/recent/previous Artifact 的当前消费授权补充已由 Director 单独集成；本 owner 未改 Core 或扩大 authority。

本 DLC `.gitattributes` 将 vendored png.py 与 PyPNG-LICENSE 标为 `-text`，避免 Windows autocrlf 改写已审阅上游字节；工作区、Git index 及 index checkout 的 SHA-256 一致，源码与许可证分别保持上述 provenance 的原始 hash。其他用户改动不进入本提交。

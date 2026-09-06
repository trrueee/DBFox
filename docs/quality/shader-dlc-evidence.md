# Shader DLC 架构审议与作者验证证据

> 文档类型：验证证据
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：Shader DLC 前期调查、独立 Domain Architect 审议和 Backend/Workbench 作者验证；不是独立最终验收报告。

架构提案见 [Shader DLC](../architecture/shader-dlc.md)，机器状态见 [program-status.json](../../dlcs/dbfox.shader/program-status.json)。

## 前期调查记录

- 已完整阅读 Director 实例化的 Shader Lead 模板，并按当前任务逐项研究 canonical model、正式 DLC boundary、编译器与浏览器执行路线。
- `.codegraph/` 不存在于本工作树，按 AGENTS 指令跳过 CodeGraph；使用源码检索。
- 调查阶段只新增 Shader 专属文档与状态；独立 worktree `creative/shader` 中原有用户未提交基线未修改或提交。
- Khronos glslang 是成熟 GLSL/ESSL validator；其官方 Web binding 走 Vulkan/SPIR-V，不作为 WebGL ESSL 编译成功替代。
- 生产 CSP 没有 eval/WASM 许可；native packages 被现有 package contract 禁止；不添加这些依赖、不改 Core/SDK。
- Director 复核后允许优先验证现有 machine operations + activation 隐藏 Canvas 的 DLC-local 派生计算路径；当时尚无真实执行结果，后续作者证据见本页末节。
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

## Workbench 作者阶段：2026-09-05

状态：当前。Director 将 `/root/scene_lead/domain_architect` 从已完成 Backend 转任 Workbench Engineer；这是同一实现作者，不是独立架构复审、Verification 或红队。冻结基线 `69563a79` 已含 Director 独立合入的 Artifact authority/navigation、Loader、Tree 重开和 stdout drain 修复。本轮未修改 Core、SDK、backend、共享锁或其他 DLC 产品代码；生产 build 按既有脚本重建的 Music/Visualization vendor 噪声保持在提交范围之外。

实现范围：CodeMirror Source 工作台、Passes/Uniforms/Textures/History typed forms、当前版本/CAS/未保存草稿/显式冲突选择、当前与历史只读 Dock、正式 Agent references、3 个 immutable Artifact 视图、公共 Representation 导出、独立于 Dock 的 activation executor，以及共用的真实 WebGL2 compile/link/reflection/FBO/pass/render/readPixels 实现。能力字段仍取 [冻结 schema](../../dlcs/dbfox.shader/contracts.schema.json)。Human publication 捕获原 workbench scope 与 AbortSignal；卸载后不跳转，缺 navigation 不启动新 ActionRun，未知结果不重放。

复用证据：CodeMirror 6.0.2 与各官方精确依赖使用 DLC 自有 npm 锁，`npm ci --ignore-scripts` 在官方 registry 成功，audit 0 vulnerabilities；重新构建字节相同。产物 415700 bytes，SHA-256 `418c6c4622c8e9413977a829b9ac91ac7850ca143da727d36aa411b156c811f6`，16 份上游 MIT 许可证见 `frontend/vendor/LICENSES.txt`。CodeMirror 使用官方 `@codemirror/legacy-modes/mode/clike` shader mode、HighlightStyle 和上游 constructable stylesheet；没有手写编辑器/GLSL parser、运行时 CDN、新 renderer 库或 CSP 放宽。前端 PNG codec 是浏览器标准能力，后端 PNG Writer 不变。

提交前另验三个 frontend vendor 文件的工作区、Git index 和独立 index checkout 字节 hash 相同；`.gitattributes -text` 生效。组合 LICENSES 只由 build 脚本生成，保留原许可证正文；源码 bundle/provenance 不因 Windows autocrlf 改写。

### 自动作者验证

从工作树 `desktop/` 执行：

```powershell
npm.cmd test -- --run src/features/dlc/__tests__/dbfoxShaderFixture.test.ts --maxWorkers=1
npm.cmd run typecheck:test
npm.cmd run lint
npm.cmd run build
```

结果：**13 passed，最后一次 4.00 s**；测试类型检查通过；lint/design-contracts 0 errors、5 个既存共享文件 warnings，无新增 owner warnings；完整生产 build 包括 tsc、Main/Preload、Vite、production token 和 entry budget 通过，entry 619609 raw bytes / 186162 gzip bytes。另用既有 desktop ESLint API、`@eslint/js` recommended 和 browser/node globals 对 owner 的 10 个 JS/build 模块单独检查通过，因为 desktop 默认 ESLint 只检查 TS/TSX。两个 control-regex 局部允许用于 driver 文本清理，保留了明确解释，没有全局关闭规则。

Fixtures 直接从真实 owner ESM 源码构建，通过现有 staged Host 测试边界验证贡献注册/清理、asset digest、分页固定版本与 source/texture hash、首 metadata 版本不符拒绝、读取消、draft rebase 的改变/删除冲突、实际 CodeMirror DOM 与 typed uniform CAS、正式行引用、历史只读/不轮询、不匹配 Artifact fingerprint 拒绝、Representation 卸载取消、缺 navigation 与晚到 navigation。executor fixtures 注入 device stub，覆盖 late attach、lease 在异步编译期间续期、exact completion proof、unknown handoff 不重放、hidden 后丢弃旧像素/visible 新 epoch；这些仅为协议证据，不是 GPU 证据。

Workbench 源码落盘后的 system suite 已跑 **44 passed，15.26 s**，实际 frontend + backend 的 Ed25519 完整签名包安装/启用/禁用/再启用成立。原后端 Tool/RunLoop/ActionRun 门禁保留，GPU receipt 仍为模拟协议回执。本阶段未因后续纯样式/历史读前端修改重复 44 项无关后端检查。

### 真实浏览器作者检查

使用命名 Playwright CLI 会话 `shader-workbench` 和任务专属 Chrome，载入实际 `renderer.js` / CodeMirror / Studio；HTTP 测试页使用从 production appProtocol 读取的等价严格 CSP。未开启 unsafe-inline/unsafe-eval 或关闭 WebGL 安全限制。探针显示 `WebGL 2.0 (OpenGL ES 3.0 Chromium)`、`WebGL GLSL ES 3.00`，KHR_parallel_shader_compile=true；没有读取 unmasked renderer 指纹。它验证实际 Chrome/驱动行为，**不等同打包 Electron 的 dlc-asset 协议、Main/Preload/Sidecar 或正式 Tool authority 链路**。

| 实际输入/交互 | 实测结果 |
| --- | --- |
| 2×2 gl_FragCoord gradient | compiled/rendered=true；bottom-left RGBA `[64,64,127,255,191,64,127,255,64,191,127,255,191,191,127,255]` |
| 原文第 3 行 NOT_VALID | 实际 GLSL syntax error、stage/link failure，compiled/rendered=false，行号为 3 |
| ESSL 100 | 驱动产生 DBFOX_REQUIRES_GLSL_ES_300 错误；不把追加检查行映射为用户源码行 |
| ESSL 300 尾部 `//` 无终止换行 | 编译成功，固定后缀前的换行有效 |
| 未闭合 `/*` 或 `#if 0` | 实际 EOF/conditional driver failure；没有伪修复或虚构定位 |
| 活跃 gain 未配置 | UNIFORM_MISSING，compiled=false |
| 2×2 red/green/blue/white top-left texture | upload/readPixels 翻转后逐字节与原 RGBA 相同 |
| 后续 pass 采样前一 pass | 两 pass 真实绘制，最终像素与首 pass 逐字节相同 |
| CodeMirror ShadowRoot/CSP | 0 个 style elements，1 个 adopted stylesheet，无 CSP 错误 |
| Studio 挂载前 executor 领取 compile | 真实编译返回成功；这里的 compute operation 为内存测试边界，不是 production Tool 结算 |
| 实际键盘错误→诊断跳转→修复→Ctrl+S | dirty draft 显示、真实 Line 22 错误、跳回 fragment，修复以 expected_version=1 保存 v2，恢复实际像素 |
| uniform gain 改为 0.65 | 明确 typed uniform_update，保存 v3 |
| v3 草稿期间模拟外部 v4 | 保存禁用且本地文本保留；明确比较两版源码，再选择保留草稿和 Save 才成为 v5，无自动重放 |
| 390×844 窄窗 | 修复过矮嵌套滚动后 source 380 px、preview 805 px，工作台 scrollWidth=clientWidth=359，编辑区自身可横向读长行，页面无横向溢出 |

UI 页持续显示 “AUTHOR BROWSER HARNESS … memory operation boundary, not production HTTP”。外部修改是测试页明确的 fault injection；导航仅记录返回 identity，没有把 memory ActionRun 当作真实 Artifact 发布。截图为实际页面，不是 mockup：[桌面](shader-studio-desktop.png)、[窄窗源码](shader-studio-narrow.png)、[窄窗预览](shader-studio-narrow-preview.png)。桌面截图保留 v2，窄窗最终截图为重载后 v1；它们不是同一事务的 before/after 对照。

本机可复查的非提交探针位于 `D:/Project/DBFox-worktrees/creative-shader/output/playwright/shader-probe/`：`server.py`、`probe.js`、`ui.js`、`ui.html`、`ui.bundle.js`、`interactions.cjs`、`layout.cjs` 与 `real-webgl-results.txt`；完整 build 输出为 `production-build.log`。这些为作者临时测试资产，按仓库规则不提交，也不是 suite-owned benchmark。运行时实际使用的 CLI 命令为：

```powershell
# 工作目录为本工作树根；server.py 使用本机测试端口 18831
npx.cmd --offline --package @playwright/cli playwright-cli --session shader-workbench run-code --filename output/playwright/shader-probe/interactions.cjs
npx.cmd --offline --package @playwright/cli playwright-cli --session shader-workbench run-code --filename output/playwright/shader-probe/layout.cjs
npx.cmd --offline --package @playwright/cli playwright-cli --session shader-workbench eval window.probeResults
```

interactions 脚本从已产生冲突的浏览器状态继续；完整键盘操作与先前截图路径记录于该会话输出。独立验收应使用正式已安装包重新建立全链路证据，而非依赖作者 memory harness 状态。

### 交接与明确剩余项

作者实现候选可冻结，`program-status.json` 记录当前角色与验证。Director 已另行接手 `verification/bench/capabilities/dbfox_shader` 与对应 suite test，未将作者临时探针复制到 Core。后续非作者需完成生产 Electron/CSP 与关闭 Dock 的正式 RunLoop → 真正 compile error → inspect → repair → render/PNG，确认已安装包 digest/epoch/claim/deadline、FBO 不完整、真实 context loss、同步驱动阻塞/取消边界、最大 pass/source/texture 预算、benchmark/stress 和独立 Adversarial Review。作者未承诺 GPU 即时抢占或恶意 publisher attestation，DLC 全量完成状态仍为 false。

## 独立 Electron 窄 Dock 修正（2026-09-06）

独立验证在1440×902的真实Electron窗口发现正常Dock只有319.3 CSS px，工作区却保留340+270 px两列，scrollWidth为610 px；点击源码页签会带动父区域横向滚动。原800/480 px断点以整个窗口为准，因此作者390 px窗口测试未覆盖此布局。

复用浏览器原生[CSS容器查询](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Containment/Container_queries)：在既有owner根节点声明具名inline-size容器，两组宽度断点依据实际容器切换；减少动态效果仍按设备媒体查询。没有增加DOM包装、JavaScript宽度镜像、ResizeObserver或依赖。原13项前端fixture通过（5.95秒），lint与设计令牌合同通过（0错误，5个既存共享警告）。fixture不提供布局证据，实际窄Dock修复复验由独立工程师在重新签名安装的候选中完成。

## 独立取消提交窗口修正（2026-09-06）

独立工程师在签名包与真实ToolRuntime的shader_create路径，只在原save_receipt完成SQLite INSERT与配额计账后触发取消信号，保留原事务未提交。工具报告取消，公开documents.list仍出现新文档及generation1，原用例1 failed / 3.79秒；Director原样复现1 failed / 3.26秒。

复用已有check_cancelled与SQLite回滚：mutate和save_report均将末次取消检查移到save_receipt之后、返回并退出原事务之前。这样所有领域写入、回执与配额计账完成后仍核验取消；没有新增事务、队列、重试或补偿层。已提交的相同identity仍按原receipt返回；提交本身与稍后到达的取消之间没有操作系统级原子承诺。

回归中44项作者合同、实际生产工厂和原create-fence均通过（合计46项）；同期独立工程师正在新增report分支，第一次夹具把compute.next的idle当成立即有请求，因此该集合另有1项未到达注入点的失败。按公开轮询合同修正后，独立两分支2 passed / 7.11秒。创建缺陷有真实修前失败；报告分支是对同形提交路径的覆盖，不伪称已有第二份修前产品失败。store的pyflakes通过。最后真实Electron重签与GPU/窄Dock复验待独立报告记录。

## 大型单次模型调用的上下文恢复调查（2026-09-06）

原领域测评一次创建60个源码模块时，存储已成为v2，脚本下一步却找不到该次function_call_output；改为三个模块一批后覆盖了同规模作品，但尚不能解释该现象。Director先查实际PromptAssembler、ContextAssembler._response_batches、token估算与已有test_context_budget.py，再通过[新增生产工厂回归](../../verification/tests/system/test_shader_prompt_budget_recovery.py)确认原因。

本次使用实际build_product_run_loop和完整签名Shader owner，只控制外部模型。单次modify的JSON输入为438254 bytes，60份source各7075 bytes，共424500 bytes。既有预算策略按完整model Turn移除过大的native function_call及其output，避免孤立call/output；同时保留已有durable_evidence_ledger中的成功状态、文档UUID/v2和两次写入的Artifact ID。这是现有明确的预算行为。原suite ShaderScript只消费native outputs，不能把其missing_observation断言当作产品丢写或工具结算失败。

新受控模型观察到ledger后不重放mutation，而是正式shader_inspect读取documents→固定v2的stages→source，然后shader_export。最终Run completed，6个真实Invocation全部成功且attempts=1，只有一次shader_modify，head仍v2，3个正式Artifact；通过公开分页完整读取62个stage，60份新source逐字相同。检查还要求保留的native call/output成对，ledger确有两份Artifact身份。最后 **1 passed / 5.70秒**，pyflakes通过。

没有修改Core、owner或旧suite的15项数据；没有从私有SQLite、评分器或Human结果补写模型观察。该回归证明受控模型可以遵守既有恢复合同，不能承诺任意真实模型都能自行采取正确恢复策略。独立GPU验收的已冻结产品字节保持不变。

## 正式文档Artifact空值合同修正（2026-09-06）

独立真实Agent的8个Artifact中，4个document-revision都带正式payload.report_id=null，前端parseLocator却只允许省略或字符串，四个卡片均不能解析；compile-report/preview卡片正常。独立fixture直接读取实际producer输出，原1 failed / 1.79秒；Director原样复现1 failed / 1.14秒。

权威后端ArtifactLocator已明确Id|None=None，因此只在前端现有解析条件接受null，保持原输入对象、不删除或转换字段，其他错误类型仍拒绝。未改SDK、后端、Artifact producer、表示一致性或来源权限，没有兼容映射。原13项作者UI与独立真实payload回归合计 **14 passed / 5.90秒**。已请独立验证员在重新签名候选上完成固定源码打开及JSON下载，不能用解析通过代替真实卡片行为。

## 独立红队驱动的持久证据与完整读取修正（2026-09-06）

独立 Reviewer 在正式 owner 边界复现：0/2 历史可绕过 count/max；重算 hash 后的 receipt Summary 可以偏离源 revision；pass 重排只改变 hash 而 changed_ids/diff 为空；已存 report 接受矛盾编译状态及外部对象诊断；实际原生严格 schema 的可选 null 被 Input 全面拒绝。原持久化 9 项均失败，Director 原样复现。后续 report 3 项、实际 schema 3 项也有独立修前失败；这些模拟负报告只证明协议，不能作为真实 GPU 证据。

前端原对象/源码页重建不能证明完整文档一致性，独立捕获正式页后有 7 项篡改失败。修复复用现有 get/Representation 返回原规范文档的有界字节页，先校验 SHA 再解析，不复制另一套前端领域模型，不修改 Agent 细粒度读取预算。原始失败 fixture 保留；Reviewer 重新捕获 31 个正式字节页并以同等攻击继续验证，同时增加分页/base64/长度攻击。

实现细节与复用决策见[架构 7.9 节](../architecture/shader-dlc.md#79-完整文档读取与持久证据一致性)。没有新增 Core seam、表、迁移、依赖或兼容层。新增风险限于完整读取需要传输文档原字节；每页和总体预算固定，实际大型桌面加载性能由独立新签名包复验记录。

Director 本轮运行 82 项后端得到 81 passed、1 个尚未更新的合同快照失败（75.19 秒）。快照现从注册的实际 Pydantic 模型重新生成，并增加 Representation 参数快照断言；不是手改生成文件。同步作者 transport fixture 后，作者 13 项、独立 Verification 9 项和独立 Red Team 15 项前端合计 **37 passed / 7.60 秒**，测试类型检查通过。独立新增后端和最终候选验收数字分别由各自报告维护；本节不将旧作者测试冒充新攻击。

补充源头检查又复现 2 项报告问题：已存 CONTEXT_LOST 可被当作编译证据；在内部 make_report 后注入非 rendered 尺寸会提交，但随后读取会拒绝。后者属于内部派生损坏，不能声称合法 CompleteInput 可绕过原有校验。现统一保存/读取的像素字段约束，运行错误集合由既有 compute 与持久 Report 校验共用；保持原 Tool 的 GPU_UNAVAILABLE 结算。

Reviewer 另以负驱动边界输入独立复现 UTF-8 残码点从一条日志污染下一条的失败。修复只为每个独立字符串使用独立标准 TextDecoder，保留 stream 模式丢弃截断尾部，按实际保留字节计费；没有自制 UTF-8 decoder。原攻击 **1 passed / 1.20 秒**，GL 资源释放断言保持。更新快照后的作者全套 **44 passed / 10.73 秒**；后续作者与独立 compute 合计 **53 passed / 26.01 秒**。全部后端 pyflakes、改动的 5 个 Python 模块 mypy 通过；新签名包桌面复验仍待独立工程师交付。

## 窄 Artifact 网格修正（2026-09-06）

独立验证员最终冷签名截图 `docs/quality/evidence/shader-independent/final-cold-gpu.png` 显示：Studio 窄布局已修复，但 preview Artifact 的完整 pixel hash 仍使默认 grid 列按最小内容宽度扩张，画布和下载按钮超出 Dock。Director 核看原截图后，仅将 Artifact 单列设为 `minmax(0,1fr)`、直接子元素允许收缩并让长文本换行。保留原画布尺寸与导出字节；不隐藏溢出来掩盖内容。该纯 CSS 修复交独立原生宽窄截图与边界测量，不用 jsdom 的零布局尺寸充当验证。

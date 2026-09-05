# Shader DLC：统一文档与执行路径提案

> 文档类型：架构提案
>
> 状态：已接受
>
> 最后核验：2026-09-05
>
> 适用范围：`dbfox.shader`；独立 Domain Architect 已完成实现前合同复核。后端候选已有作者验证，真实工作台/GPU 与独立交付门禁仍未完成。第 7 节是冻结合同。

## 1. 调查结论

建议将作品语言固定为 **WebGL 2 / GLSL ES 3.00**，在随 DBFox Electron 发行的 Chromium 中执行真实的 `compileShader`、`linkProgram` 和绘制。`compile` 和 `render_preview` 必须在 Workbench 未打开时仍可由生产 Tool Runtime 调用；不能把前端上报的成功布尔值当作编译证明。

现有 SDK 没有专门的后台浏览器调用面，但源码支持在 DLC activation 时启动独立于 Dock 的前端模块，并通过 owner-bound machine operations 交接派生计算。独立审议接受在现有边界内实施此 DLC-local 路径，不新增 Host。关闭 Shader Dock 不影响执行器；整个 Renderer 隐藏、暂停或不可用时不承诺继续计算。尚无真实闭环/发布验证；没有放宽 package/CSP 合同，也没有用正则、语法树扫描或开发机 Chrome 冒充生产编译。

### 已核验的约束

- [`engine/dlc/package_contract.py`](../../engine/dlc/package_contract.py) 第 13–21 行禁止 `.pyd`、`.so`、`.dylib`、`.dll`、`.exe`、`.bin`、`.node`；包上限 50 MiB、单文件 20 MiB。
- [`desktop/main/appProtocol.ts`](../../desktop/main/appProtocol.ts) 第 13 行只允许本地签名资源脚本；没有 `unsafe-eval` 或 `wasm-unsafe-eval`。
- [`engine/dlc/api.py`](../../engine/dlc/api.py) 的 `BackendExtensionHost`、`ExtensionToolRunContext` 与 [`sdk/frontend/index.d.ts`](../../sdk/frontend/index.d.ts) 的 `FrontendExtensionHost` 没有后台浏览器执行面。Tool 的跨 DLC Representation 读取只支持 JSON。
- [`runtime-dlc-platform.md`](runtime-dlc-platform.md) 的依赖政策只允许标准库、SDK 和 DLC 内相对导入的纯 Python 依赖，禁止运行时安装，R8A 未授权通用子进程 Host。
- 读过 Music 的不可变修订及事务、Story 的 owner operation、Visualization 的受限前端解释器模式、GitHub 的私有 state 模式；均不能代替实际 GLSL 编译器。
- 最近 Host/SDK 相关提交包括 `ffbcfca2`、`117361f8`、`2dee1ba2`、`bae0c37d`、`132a29fb`；此次未发现已有后台浏览器 seam。调查没有修改这些历史或用户基线。

### 方案比较

| 方案 | 结果与原因 |
| --- | --- |
| Chromium WebGL 2 + DLC 自有渲染模块 | 采用方向。浏览器平台 API 提供实际 ESSL 编译、链接、uniform 反射、离屏绘制；不需要 eval、WASM 或新原生发行物。拟复用正式 machine operations 交接 Tool 派生请求。 |
| Three.js `WebGLRenderer` / `RawShaderMaterial` | 可用于更丰富的几何预览。当前仅全屏三角形 + 多 pass，直接使用标准 WebGL 2 较小，不需要重复封装 Three 场景模型。后续若需要 scene material preview，优先消费 Scene representation。 |
| Khronos glslang 原生 validator | 成熟且可校验 ESSL；当前包合同禁止它的可执行/原生产物。验证通过也不能证明实际 WebGL link 与渲染成功。 |
| `@webgpu/glslang` / 官方 JS binding | 上游 `glslang.js.cpp` 明确使用 `EShClientVulkan` 和 SPIR-V target，不能作为 WebGL ESSL validator；JS/WASM build 还遇到当前 CSP 与后端运行时缺口。 |
| moderngl / PyOpenGL + native context / headless-gl | 原生扩展、驱动与 context 发行依赖；无法在当前纯 Python DLC 包合同内成为经验证的发布路径。 |
| 系统 `opengl32.dll` 的 ctypes 调用 | Windows OpenGL 驱动能力不等于随应用发行的 WebGL/ESSL 契约；自行探测 Electron 内部 ANGLE DLL 又制造内部耦合。不能据开发机安装情况作支持承诺。 |
| activation 前端隐藏 canvas + typed operations | 优先验证。Dock 无需打开；仅处理由生产 Tool 创建的单次只读派生请求。拒绝 durable SQLite job queue、自动重试、第二套 Run 状态机；renderer 不可用时明确失败。 |
| 开发机 Node/Chrome、下载浏览器、外部编译服务 | 仅可用于开发验证；不能假设用户机器已安装，不能运行时下载或要求收费服务。 |
| 自制 GLSL parser/interpreter、纯 Python WASM 解释 glslang | 本轮没有找到同时解决完整 ESSL 编译、WebGL 语义、离屏渲染、性能和发布验收的已验证组合；不采用新造编译器来掩盖缺口。 |

官方依据：[Khronos glslang](https://github.com/KhronosGroup/glslang)、[官方 JS binding 的 Vulkan/SPIR-V target](https://github.com/KhronosGroup/glslang/blob/main/glslang/OSDependent/Web/glslang.js.cpp)、[WebGL specification](https://registry.khronos.org/webgl/specs/1.0/)、[Three WebGLRenderer](https://threejs.org/docs/pages/WebGLRenderer.html)、[Electron 离屏渲染](https://www.electronjs.org/docs/latest/tutorial/offscreen-rendering)。Electron 文档的 GPU 模式支持 WebGL；其软件 output-device 示例不能被理解为通用 WebGL 软件后备保证。

## 2. 建议的唯一事实源

Resource 为 `dbfox.shader.studio`，每个 Project 一个粗粒度创作空间；资源 id 与 project identity 绑定。资源发现只读，可返回尚未创建首个文档的 version 0 空空间，不偷偷写数据库。ShaderDocument、pass、stage、uniform、texture 是该 Resource 下的 Object，不另造 Object authority。

`ShaderDocument` v1：

- `id`、`schema_version`、`title`、`version`、`language = glsl-es-300`；
- `stages`：稳定 stage id、vertex/fragment 类型、UTF-8 source；语法错误可以保存；
- `passes`：有序列表、稳定 id、所用 vertex/fragment stage id、明确前向输入、输出尺寸与 clear color；
- `uniforms`：稳定 id、GLSL 名字、明确 scalar/vector/matrix 类型、有限数值、唯一作用 pass；
- `textures`：不可变 RGBA8 内容 hash、尺寸与名字；采样与 pass/texture 输入统一由 pass binding 表达；
- `preview`：最终输出 pass、固定取样时间、输出尺寸；Workbench 棋盘背景属于 view state；
- 一个明确的最终 pass；依赖图无环且禁止同帧读写同一 target。反馈时序另立版本，不隐式启用。

DLC 自有 `state.sqlite3` 保存 studio generation、document head、不可变 revisions、operation receipt、不可变计算报告与已验证 texture bytes。texture 使用 SQLite BLOB，避免跨文件双写；PNG 使用同一批经校验 RGBA 派生，不作为另一份可写像素状态。资源 version 随每次文档语义写递增；document version 仅在该文档内容改变时递增。无效、stale、no-op、编译和预览不递增。resource generation 与 document head 在同一个 SQLite 事务内更新。

每个 revision 记录其提交时的 studio generation。Resource resolver 返回指定历史 generation 的只读 studio handle，并按 `revision.studio_generation <= frozen_generation` 选择文档修订；不能以当前 head 拒绝历史 resolver。正常写先核对 receipt，再在同一事务检查当前 studio generation 等于 Tool frozen ref、当前 document version 等于 expected_version。恢复只查已存在 receipt，不重新执行操作；这两个职责分开才能支持同一 Run 的 create → modify → compile 和崩溃恢复。

编译结果、预览像素、GPU handle、code editor 草稿均不是文档权威。诊断和预览是绑定确切 document hash/version、pass、renderer 版本、设备能力摘要与固定时间的不可变派生证据。文本编译错误允许保存在文档中；结构合法不等于编译通过。

## 3. 25 项合同回答

| 问题 | 提案 |
| --- | --- |
| 1 Resource | 每 Project 一个 `dbfox.shader.studio`，粗粒度授权，不以 UI focus 授权。 |
| 2 Object | Document、stage、pass、uniform、texture；稳定 owner-local id。 |
| 3 Selection | pass/stage、代码行范围、uniform 焦点；作为 reference locator，不扩权。 |
| 4 canonical document | 上述 ShaderDocument；只用 WebGL2/ESSL300 一套语言语义。 |
| 5 durable facts | studio generation、文档 head、不可变 revision、operation receipt、计算报告、纹理内容；原子性与配额见第 7 节。 |
| 6 view state | editor cursor、未提交草稿、面板宽度、selected pass、临时播放时间、GPU 对象。 |
| 7 Agent context | 文档 id/version/hash、pass 图计数、uniform 摘要、编译状态与有限诊断、对象引用。 |
| 8 不进 context | 全部源代码、纹理字节、像素数组、GPU 内部信息、路径、秘密；源代码按 stage/行段显式读取。 |
| 9 version | 每个语义写一个原子 revision；no-op 不增；undo 生成新的递增 revision。 |
| 10 stale invocation | 同时验证 frozen Resource ref 与输入 expected_version；事务检查失败返回 conflict，不悄悄更新为最新版本。 |
| 11 Human/Agent 冲突 | 共用一个 store operation；UI 保存需已读 expected_version；保留本地草稿并显示冲突，用户/Agent 显式重读后修改。 |
| 12 operation log | 需要：按 human request id / Agent invocation id 分离身份空间，记录 parent/new version、操作种类、影响对象、规范输入 hash 与同事务结果。receipt 不用 content hash 作为唯一键。 |
| 13 undo | 指定历史 revision + 当前 expected_version，恢复内容形成新 revision；不把版本计数回滚。 |
| 14 diff | 两个不可变 revision 间的 stage 文本 diff 与 uniform/pass/texture 结构 diff，分页且上限明确。 |
| 15 crash | SQLite 原子提交；修订与 receipt 同事务。历史 hash 允许重复；unknown 写和丢失的临时计算不自动重放。损坏状态 fail-closed，不重建空作品。 |
| 16 deactivate | Host 移除贡献；Workbench dispose 监听、timer、GPU resources；DLC 计算执行器必须撤销 epoch/claim 并拒绝晚到结果；不删 durable document。 |
| 17 Project 删除 | 当前 `engine/api/projects.py` 没有正式删除流程或公开 lifecycle hook。不预建无人调用的清理层；显式 document delete 只写 tombstone、保留历史和 Artifact，不 import Core DB 猜测项目存活。未来正式协调 API 出现后再接入。 |
| 18 大作品 | 第 7 节统一规定文档、source、texture、GPU、传输和 owner 历史预算；任一超限拒绝，不静默裁剪。 |
| 19 bounded results | 每个 Tool 显式实现 SDK `ToolObservationProjection`。普通 facts <= 8 KiB，按需 source 页 <= 16 KiB，最多 20 条摘要诊断；返回完整后端 output 不等于模型可见。像素和 bridge claim 不进入 Observation。 |
| 20 approval | 本地 reversible document edits 不额外审批；不接收任意文件路径/URL；本轮不做外部发布和执行任意 shell。 |
| 21 retry | Inspect 可重试；所有 write/compute Tool 禁止自动 retry，恢复只查 receipt。计算重做必须由明确的新 invocation 发起；Host 管理 Run/Tool 取消，DLC 只撤销这次临时 GPU 请求。 |
| 22 非幂等 | create 使用 expected_generation，文档修改使用 expected_version；相同 actor/id 和规范输入只返回原结果，不同输入复用 id 拒绝。unknown 不自动重放。 |
| 23 Artifact | 不可变 document revision、compile report、preview；Artifact 来源与 resource refs 由生产 Tool Runtime 结算。普通保存不为了写 state 绕建 action Run，明确发布 Artifact 的 Action 才使用 action_runs。 |
| 24 Representation | `dbfox.shader.document.v1`（分页 JSON）、`dbfox.shader.compile-report.v1`（分页 JSON）、`dbfox.shader.preview.v1`（元数据或 <= 32×32 RGBA JSON 采样）；`dbfox.shader.preview-png.v1` 流式 PNG 供 UI。跨 DLC Tool 不能假定能读取 PNG stream。 |
| 25 Composition | 其他 DLC 消费不可变 document/preview 元数据；不读 Shader 私有 SQLite，不把 runtime GPU handle 传给另一 DLC。需要 binary stream 的组合先由 Director 检查正式能力。 |

## 4. Tool 与 Workbench

必需 Tools：`shader_create`、`shader_inspect`、`shader_modify`、`uniform_set`、`texture_bind`、`pass_create`、`compile`、`inspect_compile_error`、`render_preview`，另提供 delete/undo/diff/export。`shader_modify` 是有界 typed operations 的原子批次；source 修改需指定 stage 和精确旧片段，或显式替换该 stage，不能替换整个 ShaderDocument。添加/移除 pass、绑定 texture 均检查引用完整性。完整字段与同源 Human operations 见第 7 节。

Workbench 使用真正 code editor（拟评估 CodeMirror 6，锁定 DLC-local 依赖及许可证）、双 stage tab、pass 图列表、live canvas、uniform slider/vector/color 编辑器、diagnostic 行定位、编译/固定帧预览/undo 控件。可本地即时预览未保存草稿，但其标签必须表明未保存且不是 durable 编译证据。Human 保存和 Agent tools 共用同一 domain operations/store；当前版本变化时只刷新已提交 projection，不能覆盖未保存草稿。

编译的准确成功条件为各 stage `COMPILE_STATUS` 与 program `LINK_STATUS` 全部成功，并检查绑定 uniform/texture 与反射结果相容；错误保留 stage/line/message 和截断标记。前端只格式化驱动诊断，不能用格式化器决定是否编译成功。`compile` 可以成功完成一次计算而输出 `compiled=false` 和不可变诊断 Artifact；Observation 必须直接说明编译失败，不能把 Tool 的传输成功显示成作品编译成功。`render_preview` 编译未通过时只返回诊断，不产生 preview Artifact；真实成功必须实际 draw、readPixels 和后端像素校验。

## 5. 优先验证现有边界内的派生计算

### 源码证明

- `desktop/src/features/dlc/extensionLoader.ts:141` 在 activation 阶段调用 `module.register(staged.host)`，不依赖 Dock；`:53` 调用 `deactivate`；`:46` 与 `:220` 的 projection epoch 阻止旧贡献复活。
- `desktop/src/features/dlc/types.ts:33` 定义 register/deactivate；同 package module 会复用，因此 Shader 自身 register 必须幂等且先中止旧执行器，不能每次注册多一个 timer。
- `desktop/src/features/dlc/extensionHost.tsx:372` 的操作调用绑定 owner id，`projectId` 可省略。操作的正式 scope 是 `machine`，不是 `global`。
- `engine/api/dlc_operations.py:119` 从当前 activation snapshot 找 owner operation；`:203` 仅 project 操作要求项目；`:296` 在 threadpool 单次执行 handler；typed 输入/输出上限为 10 MiB Host ceiling。这个面可以传输已经由 Tool 授权得到的有界派生输入，不应成为任意 Project 文档读取 API。
- `desktop/src/lib/api/client.ts` 只自动重放 GET/HEAD/OPTIONS，操作为 POST，不自动重放。
- `engine/tools/runtime/base.py:316` 提供 `cancel(invocation_id)`，正式 Tool context 提供取消状态；Tool 的派生计算等待与取消无需修改 Core。
- Music `frontend/index.js:388–391` 实际执行 Basic Pitch 后调用 `audio.commit_transcription`，证明浏览器派生值可经 typed operation 归 owner；但该动作由 AudioStudio 按钮触发，`backend/contributions.py:525` 明确要求先在 Studio 完成转录，**不是无需 Dock 的 Agent 闭环先例**。

### 拟定执行路径

1. Shader frontend `register` 初始化独立于 Dock 的 canvas/WebGL2 context，通过 `compute.attach` 提交 client id、单调 registration counter、package digest 与标准 WebGL 能力，领取后端生成的 epoch/lease。没有 WebGL2 或 Renderer hidden 时 unavailable；不打开 Dock、不要求独立 Chrome/Node。
2. `compile` / `render_preview` 生产 Tool 先从 frozen resource scope 读唯一 store，验证文档 expected_version/hash，生成一个短期派生 request。request 只在运行 Tool 的 DLC 内存注册表中存在，不能由 machine operation 创建、选择任意 Project 或修改文档。无 durable queue、无后台自动重试。
3. 一个 owner machine `compute.next` 按 epoch/lease 领取至多一个已授权请求；返回 source/pass/uniform/texture 的有界 snapshot。请求绑定 invocation、document id/version/hash、package digest、deadline 和随机 claim。claim 不进 Agent context/Artifact/log，不做 OS vault 长期秘密，不写业务 SQLite。领取请求不接受 Project/document selector；它只能读取已经被该 Tool 授权的 snapshot。
4. 受信 DLC 代码使用真实 `compileShader`、`linkProgram` 和 `getShaderInfoLog/getProgramInfoLog`；只有 `COMPILE_STATUS` 与 `LINK_STATUS` 成功才报告 success。预览执行真实 draw/readPixels，固定尺寸时间，不接收 model JavaScript、不调用 eval。
5. `compute.complete` 只接受匹配 epoch/claim/request hash/version/deadline 的结果；结果只交给运行 Tool 的等待对象，不能直接发布 Artifact 或改 canonical document。Tool 在事务中再次检查取消、文档 head 未变化、schema/字节预算，然后提交不可变报告与 invocation receipt，由 Runtime 结算 Artifact。文档在计算中已变更则拒绝 stale；另一个文档的修改不会使此精确 snapshot 的计算失效。
6. Tool cancel/timeout 撤销 claim，后续回执确定性拒绝。deactivate 本地立即中止 timer/回调并释放 GL resource，`compute.detach` 只作 best effort；Renderer 关闭/断线、GPU unavailable、backend 重启均明确失败，未送达 detach 由后端 lease/deadline 收敛。新 attach epoch 不接管旧请求。
7. UI live preview 复用相同 DLC compile/render module，但未保存草稿不是 durable 编译证据。保存仍走唯一 backend operation；派生执行器不决定 Run/Turn/Approval/retry/terminalization。

标准库锁/Condition 或 Event 只用于一个 transient invocation-to-compute 交接槽，不构建调度框架。无持久 pending/running job、后台重试器或独立终态机；第 7 节规定一个活跃 request、10 秒 deadline 和明确传输预算，性能仍需实际测量。

### 信任与取消限制

当前 Frontend Host 注释明确它是 trusted same-realm registration，不是进程/DOM/network 沙箱。随机 claim 能拒绝未领取、错绑定与重放回执；它不能证明一个恶意但已受信的 DLC 真正调用过 GPU。当前 SDK 不提供 renderer attestation，不能声称“不可伪造的 GPU 证明”。本方案的边界与现有受信 DLC 一致；模型的 GLSL 源码只作为 GPU compiler 数据，接触不到 claim/Host 对象。验收必须调用真实浏览器路径，不能用手写成功回执充数。

WebGL compile/link/status/readPixels 可能阻塞 renderer；后端 deadline 可独立终结 Tool 并拒绝晚到结果，无法承诺立刻抢占已提交的 GPU 工作。可调查标准 `KHR_parallel_shader_compile`，不能把它当必备且普遍存在。需要取消/压力测试确认用户可接受性。

原生 Worker 也不能未经验证地假设可用：生产文档在 `dbfox-app:`，DLC asset 在 `dlc-asset:`；Worker 初始脚本有 same-origin 要求，当前没有 blob/data worker CSP 授权。因此不能借 Blob worker 绕过 CSP，也不能声称可用 Worker.terminate 实现已验证的强制 GPU 取消。依据：[Worker 构造器](https://developer.mozilla.org/en-US/docs/Web/API/Worker/Worker)、[KHR_parallel_shader_compile](https://registry.khronos.org/webgl/extensions/KHR_parallel_shader_compile/)。

### 何时才提出 Host seam

只有上述现有 typed operations 路径的真实验证发现不可接受缺口，且另一个独立 capability 也证明同一必要边界，才按 Core 宪章评审可选 owner-bound 离屏模块执行面。候选将是签名 ESM module + bounded JSON + invocation/deadline/generation 的通用执行合同，Electron Main 复用自带 Chromium；绝不添加 shader/pass/uniform 到 Core，也不放宽 CSP、native package 或任意 subprocess。当前**不请求或实施该 Host 变更**。

## 6. 验证与余项

本轮完成独立合同审议，无实现、无测试通过声明。后续必须完成：

- 实际 Backend/Workbench/Verification 专员和未参与实现的 Adversarial Reviewer；独立 Architect 为 `/root/shader_architect`。受槽位限制时记录角色交接，Architect 后续实现时不再充当独立红队。
- canonical model、stale/version/no-op、SQLite crash/partial failure/corruption/restart、unknown 不重放、生命周期、输入资源预算、前后端一致性测试。
- 真实生产 Tool path 的 Generate → invalid Compile → inspect error → local Repair → Compile → PNG Preview，在 Workbench 关闭时运行；不是 mock 编译，不绕过 Dispatcher。
- 12 类 deterministic capability benchmark 和复杂示例至少 10 次不同增量修改（含用户编辑、冲突、undo）；检查局部请求没有整篇替换。
- 发布模式 CSP 与实际打包 Electron 验证；开发机 Chrome 的结果仅作开发证据，不能代替发布证据。
- Program status 只有 Director 可标记 `integrated`。本阶段返回仅为释放调度槽，完整 DLC 交付继续保留。

## 7. 独立审议冻结的实现合同

本节由独立 Domain Architect `/root/shader_architect` 在读取当前源码和官方平台资料后制定。它约束下一阶段实现，尚不表示行为已通过验证。若实际平台验证否定某项，先记录证据并修订此处，不能在实现中偷偷增加另一套协议。

### 7.1 数据、数值与资源预算

所有 model 均禁止未知字段。整数使用严格整数、拒绝 bool；浮点拒绝 bool、NaN 和 infinity。数值不得靠截断、取模或 clamp 变成合法输入。JSON 的可选字段采用“省略表示不修改”，删除使用带类型的 remove 操作，不能依赖 `null` 穿过 Tool 的序列化路径。对源代码只在输入边界统一 CRLF/CR 为 LF；其余文本、顺序和空白不做隐式重写。

| 边界 | 冻结值 |
| --- | --- |
| ID / 标题 | owner 生成 UUID；title 1–120 字符、trim 后非空；GLSL uniform/sampler 名为 ASCII identifier、1–64 字符，禁止 `gl_` 前缀和保留 builtins |
| Project / 文档 | studio id 等于 Host Project id；每 Project 最多 128 个未删除文档；schema_version=1，language=`glsl-es-300` |
| source | 每 stage <= 256 KiB UTF-8；文档总和 <= 512 KiB；每行 <= 2,048 UTF-8 bytes；每 stage <= 16,384 行 |
| canonical JSON | 不含 texture bytes 的完整规范文档 <= 1 MiB；source 在这个唯一文档内，不另外维护可写 source 表 |
| 对象 | stages 2–64、passes 1–32、uniforms 0–128、textures 0–16；每 pass 最多 8 个 sampler bindings |
| texture | 原始 top-left RGBA8，宽高各 1–512；byte_length 必须等于 width×height×4；单张 <= 1 MiB、文档引用的唯一内容合计 <= 4 MiB |
| GPU targets | 每 pass 宽高各 1–512；所有 pass 合计 <= 2,097,152 pixels（8 MiB RGBA8 color attachments）；preview 宽高各 1–256 |
| mutation | apply 一次 1–64 个 typed operations，普通 mutation 编码 <= 768 KiB；包含一次 texture_create 的 apply 总 JSON <= 1,500,000 bytes、除纹理字段外仍 <= 768 KiB；一个 apply 最多上传一张纹理 |
| compute transport | `compute.next` 的完整 JSON <= 8 MiB（含 base64 纹理）；`compute.complete` <= 1 MiB；超过则拒绝，不分页续领同一请求或另建下载链 |
| compute lifetime | owner 只有一个活跃请求；busy 返回明确错误；请求总 deadline 10 秒，Host Tool timeout 12 秒；健康 lease 5 秒，visible executor 每 500 ms 轮询/续租 |
| report | 总 JSON <= 256 KiB；最多 128 条 diagnostic、单条 message <= 1,024 字符；所有 driver raw log 合计 <= 64 KiB；超过保留 truncated 计数 |
| 模型预算 | 普通 facts <= 8 KiB；source/diff provider_payload <= 16 KiB；诊断摘要 <= 20 条且每条 <= 256 字符；无像素、base64、lease、完整文档 |
| owner 历史 | 文档修订、纹理 BLOB、receipt、报告与 preview RGBA 的已记账 payload 合计 <= 256 MiB；事务预先计费，满额拒绝新增写/计算证据，仍可读已有作品 |

owner 配额由同一事务内的持久字节计数约束真实持久 payload；SQLite 自身页、索引和 WAL 有额外开销，不把此数描述成磁盘硬上限。不能为腾空间自动删旧修订、receipt 或 Artifact 源；版本迁移/删除历史需未来明确合同。读取每个 BLOB/JSON 前先检查数据库长度与单项预算，解码后复算 hash 和 schema；损坏或配额计数不一致 fail-closed。SQLite 使用标准库事务和 `PRAGMA user_version` 的本 owner 迁移，不接入 Core Alembic，不写第二套日志/缓存基础设施。

### 7.2 ShaderDocument v1 的精确语义

`stages[]` 项为 `{id, kind: vertex|fragment, title, source}`。允许未使用的 stage，删除仍被 pass 引用的 stage 拒绝；复用 stage 的所有 pass 一起受其修改影响。不会补写 `#version` 或 precision，缺失或错误由实际 ESSL compiler 诊断。

`passes[]` 是执行顺序，项为 `{id,title,vertex_stage_id,fragment_stage_id,width,height,clear_color,bindings}`。stage kind 必须匹配；clear_color 是 4 个 [0,1] 有限数。每个 binding 为 `{name,source,filter,wrap}`，其中 source 是 `{kind: texture,texture_id}` 或 `{kind: pass,pass_id}`，filter=`nearest|linear`，wrap 只允许 `clamp`。pass 输入只能引用列表中更早的 pass。引用自己、向后引用、重复 sampler 名、读写同 target、dangling references 一律拒绝。排序使用显式 `pass_reorder` 提交所有 pass id 的精确排列并重新验证，不能自动拓扑修复用户输入。

每个 pass 使用固定全屏三角形 `drawArrays(TRIANGLES,0,3)`，vertex shader 通过 `gl_VertexID` 产生位置，不提供隐式 mesh、VAO attributes、depth、blend、mipmaps、feedback 或时间历史。active vertex attributes、uniform blocks、uniform 数组/结构、非 sampler2D texture 类型均为明确的 v1 binding error。RGBA8 FBO 要 `FRAMEBUFFER_COMPLETE`；创建失败或 GL error 不降尺寸、不跳过 pass。

`uniforms[]` 项为 `{id,pass_id,name,type,value}`，type 为 `float|int|bool|vec2|vec3|vec4|mat2|mat3|mat4`。向量/矩阵是一维固定长度数组，矩阵 column-major、上传 transpose=false。float 分量范围 [-1e6,1e6]，int 是 int32，bool 必须为 bool。每个 pass 内名字唯一，不能与 sampler binding 重名。可供 UI 编辑的配置允许被 compiler 优化掉，报告为 inactive；每个 active non-sampler uniform 必须有同类型配置或为下述 builtin，缺失、类型错误或超出真实设备 limits 均拒绝，不猜测默认值。

只保留两个自动 builtin：`u_resolution: vec2` 为该 pass 的实际 target 尺寸，`u_time: float` 为 canonical preview.time_seconds；它们可在 source 中省略/被优化掉，但使用时类型必须一致。Workbench live playback 可用本地时间覆盖进行带“未冻结预览”标签的显示；生产 preview 始终使用文档中的固定时间。

`textures[]` 项为 `{id,title,width,height,format: rgba8,content_hash}`。content_hash 由 backend 对 raw bytes 算 SHA-256，输入不指定权威 hash。字节在 owner SQLite 按内容寻址，规范文档只引用一次；不同 texture id 可引用相同 bytes。upload 不接受文件路径、URL、JS 或压缩格式，UI 可用已授权本地选择器/浏览器解码得到有界 RGBA 再上传。纹理 top-left rows 在 WebGL 上传边界翻转一次，GL UV 采用 bottom-left；不依赖 typed-array 上传时浏览器自动翻转。

`preview` 为 `{pass_id,width,height,time_seconds}`，time_seconds ∈ [0,86400]。先按各 pass canonical 尺寸渲染，再用标准 WebGL2 `blitFramebuffer(...,NEAREST)` 将最终 pass 缩放到 preview 指定矩形；允许用户明确设置不同宽高比，不能暗改宽高。readPixels 从最终独立 RGBA8 FBO 读取，不依赖默认 drawing buffer 跨帧保留。像素回执标为 bottom-left，backend 在一个边界转为 top-left 规范 RGBA，并计算 hash。PNG 是这些字节的无损编码，v1 不承诺色彩管理或跨 GPU 的逐像素相同结果。

### 7.3 同一 store 的 Tool 与 Human operations

以下为 local Tool 名；provider wire name 继续由 Host materialize。每个 Tool 都声明本 owner 的 `dbfox.shader.studio` required resource；Project 从正式 scope 得到，不接受模型输入 Project id。所有 Document id 的访问都再验证属于此 studio。

| Tool | 输入与操作 |
| --- | --- |
| `shader_create` | `{title,expected_generation}`；创建一个带可编译默认 vertex/fragment/pass/preview 的文档，所有对象 id 在后端生成，并通过 facts 返回 |
| `shader_inspect` | `{document_id?,version?,section,stage_id?,offset?,limit?}`；section=`documents|summary|stages|passes|uniforms|textures|source`；documents 不带 document id，其余必带；source 必带 stage id |
| `shader_modify` | `{document_id,expected_version,operations}`；执行下述 typed operation 批次，只提交一个 revision |
| `uniform_set` | `{document_id,expected_version,uniform_id,value}`；只改已有 uniform 的值，其他配置由 typed operations 管理 |
| `texture_bind` | `{document_id,expected_version,pass_id,name,source,filter,wrap}`；设置唯一 sampler 名的 binding，引用已存在 texture/更早 pass |
| `pass_create` | `{document_id,expected_version,title,vertex_stage_id,fragment_stage_id,width,height,clear_color,bindings}`；追加一个 pass，返回生成 id |
| `compile` / `render_preview` | `{document_id,expected_version}`；读取本次冻结 scope 下精确 head，发起一次临时 GPU 请求，不改文档；render 在同一次请求中先 compile 再 draw |
| `inspect_compile_error` | `{report_id,offset=0,limit=20}`；读取授权 studio 中指定 immutable report；返回确切 document version/hash，不能把上次 report 当作当前编译状态 |
| `shader_delete` | `{document_id,expected_version}`；写 tombstone revision，不物理删除历史、texture 或 report |
| `shader_undo` | `{document_id,expected_version,target_version}`；将目标修订内容和 deletion 状态复制成新的 revision；已有相同内容是 no-op；允许 undo-of-undo |
| `shader_diff` | `{document_id,from_version,to_version,section,stage_id?,offset=0,limit=20}`；section=`summary|source`；source 只对一个 stage 输出有界 diff |
| `shader_export` | `{document_id,expected_version}`；明确创建文档 revision Artifact，不运行 GLSL |

`shader_modify.operations` 的 tag 为 `rename_document`、`stage_create`、`stage_replace`、`stage_patch`、`stage_remove`、`pass_create`、`pass_update`、`pass_remove`、`pass_reorder`、`uniform_create`、`uniform_update`、`uniform_remove`、`binding_set`、`binding_remove`、`texture_create`、`texture_remove`、`preview_set`。create 的 id 不由调用方选择；同批次需要引用新对象时使用局部 `ref`（1–32 ASCII identifier，整批唯一），只可向后引用，提交结果返回 ref→生成 id。这个映射只存在于单次原子操作输入边界，不成为持久模型或第二份 authority。需要引用的字段均采用 `{id: UUID}` 或 `{ref: local_ref}` 的严格 union，不用特殊字符串前缀猜测其类型。

`stage_patch` 指定 `{stage_id,old_text,new_text}`，old_text 非空且必须在已读 stage 中精确出现一次；0 次或多次拒绝，不模糊匹配，不靠行号碰巧覆盖。`stage_replace` 显式携带该 stage 的完整 source。`pass_update` 与 `uniform_update` 只接收允许的完整字段，删除用 remove，不接受任意 JSON Pointer。`texture_create` 接收 `{title,width,height,rgba_base64,ref?}`；同 apply 最多一个 texture_create，仍受总 request budget；base64 严格解码。参照删除、重复名字、最终 pass 被删除等以整个批次的最终文档校验，允许显式在同批中拆除引用并完成结构重构。

Human project operations 为：

| Operation | 规则 |
| --- | --- |
| `documents.list` | `{offset=0,limit=20}` → summaries、total、studio_generation；limit 1–50，不含全文 |
| `documents.get` | 与 shader_inspect 的单文档部分同源；首次返回 version/hash，后续页固定 version |
| `documents.head` | `{document_id}` → id/version/hash/deleted；供 visible Workbench 每秒检查，不加载完整文档 |
| `documents.create` | shader_create 输入加 request_id；幂等 receipt 以 human actor 区分 |
| `documents.apply` | shader_modify 输入加 request_id；一份 store/validator，不创建 Action Run |
| `documents.undo` / `documents.delete` | 同名 Tool 输入加 request_id；与 Tool 共用事务和 receipt |
| `documents.revisions` | `{document_id,offset=0,limit=20}`；固定 current version 后分页不可变历史，limit<=50 |
| `documents.diff` | 与 shader_diff 同源；不在 UI 复制 diff 规则 |
| `documents.compile` / `documents.preview` / `documents.export` | 对应 Tool 输入加 request_id；调用 `context.require_action_runs()`，明确持久发布这次结果；返回真实 session_id/run_id/artifact_ids 和 bounded outcome |

普通变更返回 `{document:{id,title,version,content_hash,deleted},studio_generation,changed,changed_ids,truncated,created_refs}`，changed_ids<=64、created_refs<=64，总 <= 8 KiB；详情重读。shader_create 的 created_refs 固定返回 `vertex`、`fragment`、`pass` 的默认对象 id，使 Agent 可继续局部修改。reads 分页 limit<=50。source 按完整行分页，offset 是 zero-based line offset，实际返回同时受 16 KiB 预算，给出 next_offset/has_more；其他对象页 <= 32 KiB。diff 先按对象 id/hash 比较；只有指定 stage 两端都 <= 64 KiB/2,048 行才用标准库 difflib 产生 <= 16 KiB 的文本差异，更大只返回 hash、行数和 inspect locator。不能为 diff 放大整文档到 context。

每个 Tool 的 `project_observation` 明确给出下次调用需要的 document/object/ref id、version/hash、changed/no-op、report id、compiled、diagnostic 页和分页游标。source 内容只经 <= 16 KiB 的 provider_payload 显式提供；不依赖 BaseTool 默认仅保留 count 的 projection。禁止使用后端测试直接取 id/version 帮 scripted Provider 填下一次 Tool 输入。

Context contributor 只从正式 input.resource_refs 与 recent_artifacts 读本 owner 的历史身份，最多返回一个 <= 4,000 字符的 resource fragment，列出 studio generation、最多 8 个 document 的 id/title/version/hash/计数、exact-version 最新报告的 compiled 状态和截断指示。没有 exact-version 报告就写“未编译”，不把旧成功继承给新文档。内容是资料，不含系统指令、完整 source 或纹理。Workbench onAsk 传递同一 studio Resource reference 及 document/stage/pass 的有界 locator；选中对象和本地草稿不增加 authority。

### 7.4 事务、恢复与派生证据

store mutation 的顺序为：严格输入/owner 校验 → 在事务内按 `(project,actor,request_or_invocation_id)` 查 receipt → 验证重复输入 hash → 查 exact frozen generation/head/expected_version → 计算最终文档和引用一致性 → 比较规范内容 → 配额 → 写 revision、head、studio generation、receipt → commit。Human 没有 frozen Tool ref，只对 expected document version（create 为 expected_generation）做 CAS；不伪造 ResourceScopeRef。即使 no-op 也写小 receipt，但不增加 version/generation。receipt 只保存有界操作结果、输入 hash 和影响 id，不复制完整文档。content_hash 计算规范的领域内容及 deletion 状态，排除 version、generation、created_at 和 receipt；重复内容可在新版本再次出现，因此 hash 上不能建 unique constraint。各实体 id 永不重新分配；删除、undo、恢复后历史引用语义不变。

Tool `reconcile` 根据原 invocation、原输入和原 resource identity 查 receipt：已提交返回同一结果/Artifact source，缺失返回 unknown，不从查不到 receipt 推导“安全重放”。正常执行的相同 id、相同输入可返回既有 receipt，不再验证它仍是当前 head；不允许通过重复输入改变 scope/actor。Python runtime 的 recovery 使用 SDK `ToolReconciliation`，不自行 terminalize Run 或修改 Core SQLite。

计算回执先在内存交接，不直接进入数据库。运行 Tool 检查 lease、deadline、取消和原文档仍为当前 head 后，将 schema-validated report 与 invocation receipt 在一个事务内持久化；成功 preview 同事务保存有界 top-left RGBA bytes。编译失败是 `compiled=false` 的报告，GPU/context/unavailable/timeout 是操作错误，没有“成功预览”。进程在报告提交后、Host Artifact 结算前崩溃时，reconcile 重建同一不可变 Artifact draft，不再运行 GPU；提交前崩溃则保持 unknown。DLC 报告不能替 Host 宣称 Tool 已成功 terminalize。

诊断 report 包含 `{id,document_id,version,content_hash,kind,compiled,rendered,diagnostics,log_truncated,capabilities,elapsed_ms}`；preview 另有 width/height、pixel_hash 和 pixel_format=`rgba8-unorm`，不记录 GPU 私有路径、unmasked renderer、lease 或 source全文。标准 VERSION/SHADING_LANGUAGE_VERSION 字符串 <= 256 字符，GL limits 是白名单有界整数；这些信息是平台说明，不是设备可信认证。

Artifact types 是 `dbfox.shader.document-revision`、`dbfox.shader.compile-report`、`dbfox.shader.preview`。payload 只存 owner document/report/revision/hash 的不可变定位与摘要，正式 resource_refs 由调用的 scope 产生；不清空 scope 或每次新建 Run 回避 Host 结算问题。Representation 查询仅在传入 Artifact 的 exact locator 上读取：document 提供 metadata/object/source 页；compile-report 提供 diagnostics 页；preview 提供 metadata 或 <= 32×32 nearest RGBA JSON 采样；preview-png 以流返回后端无损编码。跨 DLC 组合消费这些表示，不读 Shader state.sqlite3，不自行 fetch 本地 URL。

### 7.5 临时计算交接与激活边界

只注册四个 owner machine operations，均不接受 Project selector：

| Operation | 输入 / 输出 |
| --- | --- |
| `compute.attach` | 输入 `{client_id,registration_counter,package_digest,available,capabilities}`；counter>=1；输出 `{epoch,lease,lease_ms,server_status}`，epoch/lease 为后端生成的随机值 |
| `compute.next` | 输入 `{epoch,lease,registration_counter}`；输出 `{status:idle|busy|request,...}`，若 request 包含 request_id、claim、invocation_id、document id/version/hash、request_hash、remaining_ms、kind 与完整有界 snapshot |
| `compute.complete` | 输入 `{epoch,lease,registration_counter,package_digest,request_id,claim,invocation_id,document_id,version,content_hash,request_hash,result}`，result 为 `{compiled,rendered,diagnostics,logs,rgba_base64?,width?,height?,row_order?}`；所有输出量和组合关系由 backend 校验；返回 `{accepted:true}` 仅代表交接成功 |
| `compute.detach` | 输入 `{epoch,lease,reason:deactivate|hidden|context_lost|network_error}`；撤销该 epoch 并唤醒等待者；旧 epoch 不能撤销新执行器 |

后端 `DlcRuntimeInfo.package_digest` 是包身份权威；attach 传入 digest 必须匹配，不能信任自报值。`client_id` 在一次 ESM module 生命周期内固定，`registration_counter` 每次 register 开始递增；后端记录同 client 最大 counter 并拒绝迟到的更小 counter。新 client 在当前健康 lease 仍有效时返回 busy，防止无因替换；健康 lease 已过期才允许接管，旧请求同时撤销。相同 attach input 的网络结果不确定时不能盲目重发；该次 frontend registration 停止并显示 unavailable，下一次明确激活/恢复建立新 counter。

module 的每个异步回调都捕获本地 registration token。register 开始先停止旧 timer、AbortController 和 GL 工作；await attach/next/complete 后先检查 token，旧回调只能释放自己的 epoch/context，不能修改全局 active 指针或清理新执行器。deactivate 先同步撤销本地 token/事件/timer，网络 detach 不阻塞释放。Host 的同 ESM 复用与迟到 register 不能成为两个后台轮询器。不得在每个 Dock mount 时 attach，也不得由关闭 Dock 的 cleanup 关闭 activation executor。

next 在 visible 期间每 500 ms 续 lease；没有待处理请求时立即 idle，不在 HTTP threadpool 内做长轮询。一个 GPU 请求正在异步等待 KHR completion 时仍可续租，但 next 返回 busy，绝不领第二个请求。后端等待使用 monotonic clock 和标准库 Condition/Event，至少每 50 ms 检查取消/lease/deadline；结果只保留到本次 Tool 取走或终止。完成 POST 结果不确定时不重发 GPU 或回执；既有 backend waiter 可能已接收，Tool 的既有生命周期独立收敛。

remaining_ms 由 backend monotonic deadline 计算，frontend 用 performance.now 作为本地预算参考；不能用客户端时钟延长后端期限。所有 request/epoch/claim 字段长度有界（UUID 或 32-byte random token 的固定编码）。后端只保留当前 client/counter/epoch，接替后旧 epoch 始终无效；不会为任意 client id 建立无界历史 registry。result.rendered=true 必须同时 compiled=true、kind=preview、尺寸精确匹配 canonical preview、row_order=bottom-left、严格 base64 解码长度为 width×height×4；编译失败或 kind=compile 不允许附带像素。后端重新计算像素 hash，不接受上报 hash 作为事实。

`visibilitychange` 到 hidden、pagehide、context lost、operation 网络错误都会停止领取并撤销本地 token，尝试 detach。visible 恢复或 context restored 只可建立新的 epoch 服务未来显式请求，不恢复旧计算、不修改作品、不重新触发 compile Tool。backend 重启清空瞬时槽；旧 epoch/claim 必须 unknown。DLC backend 没有公开 deactivate callback，不能声称同步后台取消已由 callback 保证；真正收敛依据是现有 Tool cancellation、frontend detach 和独立 deadline。

真实编译顺序为先 compile 各 stage、link 各 program，再利用存在的 KHR completion 非阻塞轮询；完成后验证 COMPILE_STATUS/LINK_STATUS、反射、GL error 和 `isContextLost()`。扩展在 context lost 时要求 completion query 返回 true，因此 completion=true 从来不等于编译成功。扩展缺失时仍走实际平台 API，并明确可能同步阻塞；不伪造 async 完成，不用正则代替编译。官方依据：[KHR_parallel_shader_compile](https://registry.khronos.org/webgl/extensions/KHR_parallel_shader_compile/)。

当前 [Electron 窗口配置](../../desktop/main/index.ts) 未关闭 backgroundThrottling；官方默认值为 true，hidden/minimized 影响 visibility。执行器因此使用显式 visible lease，不把隐藏应用时延长计时器当作耐久计算。Dock 关闭的正常 Agent 路径仍是必验场景；最小化窗口允许及时 unavailable/timeout，恢复后无自动重放。依据：[Electron BrowserWindow](https://www.electronjs.org/docs/latest/api/browser-window#page-visibility)。

这条交接不是临时兼容层：它处在 Python Tool 与浏览器 GPU 的真实执行边界，只传递一次授权计算的输入和回执。它不封装其他 DLC，不重复 Run lifecycle，不承载 retry 或 canonical state。若后续正式通用 Host GPU 执行能力满足相同预算/绑定并获宪章批准，删除此四个 machine operations 和本地槽，保留 Shader store、计算合同和同一 GLSL renderer；在此之前不再加一层通用 dispatcher。

### 7.6 复用决定与验证责任

持久化采用 Python sqlite3、json/hashlib/base64/secrets/threading/time，文字差异采用有界 difflib。GLSL 使用 WebGL2 原生 API；没有理由引入 Three.js 仅包一层 fullscreen triangle，也不引入 glslang/native/WASM。Workbench 使用已探针验证的 CodeMirror 6 官方 ShadowRoot/constructed stylesheet 路径，锁定 DLC-local vendor、记录 MIT 许可证；不复制 editor、语法 parser 或修改 CSP。后端 PNG 采用未修改的纯 Python PyPNG 0.20220715.0（MIT）最小 vendoring；来源/hash/许可证取已核验 archive，产品不依赖 Pillow。PyPNG 只做编码，自己对宽高、行长和输出预算作边界检查；不把库的 decoder 当作允许不可信压缩图片导入的承诺。依据：[PyPNG 官方文档](https://pypng.readthedocs.io/en/latest/)。

复用带来的主要风险为 CodeMirror vendor 体积/升级、WebGL 驱动差异与同步 GPU 阻塞、PyPNG 上游更新频度；无新增 Core 依赖、供应商账户或网络运行时。退出成本限于 DLC owner 自己的 editor adapter 与 PNG encoder 调用；不复制上游分叉、不创建额外可写模型。

独立 Verification 必须从正式 Tool function_call_output 获得下一步 id/version，完成 12 类 benchmark 和 10 类连续创作修改。store 单测可以模拟计算交接的错误输入，但真实闭环证据必须在安装/激活后的签名完整 DLC、关闭 Shader Dock、实际 Chromium WebGL2 和 production RunLoop/Tool Runtime 上产生；backend 伪造 complete 的测试不能计为 GPU 编译成功。至少单独覆盖：

- 32 pass 预算、前向引用与循环、inactive/missing/type-wrong uniform、RGBA 翻转、FBO 不完整、context lost 与 KHR completion=true。
- concurrent human edit、receipt 输入复用、undo-of-undo、历史 generation resolver、报告提交前后 crash、quota 和损坏状态。
- attach 迟到、same ESM 重复 register、旧 detach、超时/取消后的 complete、Renderer hidden/recovery、deactivate/reactivate，无 canonical mutation/自动重放。
- 正常 ToolObservationProjection 可继续局部修改，source/diagnostic/context 严格有界；Artifact 的实际 frozen invocation scope，真实预览 PNG 及独立解码。
- CodeMirror 的真实键盘编辑、诊断跳转、uniform 直接修改、保留 dirty draft 的冲突处理、资源卸载、生产 CSP 与打包 Electron。

架构复核通过只表示以上合同可以交给实现；性能/打包/真实 GPU/独立红队的余项仍是交付门禁。

### 7.7 实施时批准的纹理只读页补充

Director 在后端实施阶段确认：既存纹理 bytes 只在 Tool compute snapshot 中可见，无法供重开后的 Workbench 恢复未冻结 live preview。因此复用现有 `documents.get` 与 immutable `dbfox.shader.document.v1` Representation 增加 `section=texture_bytes`，不增加 operation、Host seam 或下载 HTTP。

Human get 必须携带 `document_id`、固定 `version` 和该 revision 内的 `texture_id`；Representation 从不可变 Artifact 取得 Project/document/version，参数只能指定 texture_id。offset 是原始 RGBA 字节，严格整数非负；limit 1–16384，完整返回 ≤ 32 KiB。返回外层 offset/next_offset/total/has_more，以及 `texture_bytes:{texture_id,content_hash,total_bytes,rgba_base64}`。末页允许为空；超过 total 的 offset 拒绝。逐页均读取并验证已有 immutable BLOB 的 hash/layout，客户端完整重组再校验 content_hash。不同 Project、不同 revision 无此 texture、显式 null、bool 数值、hash/path/URL override 均拒绝。

读取不建 snapshot/Run/receipt、不修改文档。历史 texture 删除后旧 revision 仍可读。`shader_inspect`、自动 Context 和耐久 ToolObservation 不加入纹理 base64；人类 get 与明确请求的 Composition Representation 共用同一纯读取实现。公开 operation/Representation context 没有取消 probe，Host/前端 AbortSignal 负责丢弃停止的读取；本领域纯读取函数也接受取消 probe 并在读取前后检查，不能宣称 HTTP abort 抢占了已开始的 SQLite read。

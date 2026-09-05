# DBFox Shader

状态：当前。后端与完整工作台作者候选已完成；真实 Chrome WebGL2 作者检查通过，生产 Electron 联合闭环与独立交付验证待完成。

每 Project 一个 `dbfox.shader.studio` Resource，id 是 Project id，version 是 studio generation。ShaderDocument、stage、pass、uniform、texture 是 owner 对象。`state.sqlite3` 是唯一持久事实源；源码可保存编译错误，保存成功不等于编译成功。

字段与预算以 [已接受架构第 7 节](../../docs/architecture/shader-dlc.md#7-独立审议冻结的实现合同) 和实际模型生成的 [contracts.schema.json](contracts.schema.json) 为准。后者包含所有 16 个 operation 的 input/output、scope、字节上限及完整 canonical Document schema；测试检查它与注册模型完全一致。

## 操作与读取

12 个 project operations：`documents.list/get/head/create/apply/undo/delete/revisions/diff/compile/preview/export`。普通修改直接进入同一个 store；compile、preview、export 是显式 Host Action Run，返回 `session_id/run_id/artifact_ids/outcome`。所有写入需 UUID `request_id`；create 用 `expected_generation`，其他写入用 `expected_version`。返回的 mutation 形状是 `{document:{id,title,version,content_hash,deleted},studio_generation,changed,changed_ids,truncated,created_refs}`。

create 默认返回 `created_refs.vertex/fragment/pass`。一次 apply 含 1–64 个 `kind` discriminated operations；创建对象的 `ref` 是本批次唯一 ASCII 名，引用字段只能是 `{id: UUID}` 或 `{ref: local_ref}`，后者必须指向较早 create。`stage_create.stage_kind` 选择 vertex/fragment。`pass_update`、`uniform_update` 和 `preview_set` 省略字段表示保持，所有输入显式 null 均拒绝。remove 是单独 typed operation。

`documents.get` 默认 summary，metadata 包含 preview 与对象计数。`stages` 页只含 stage 元信息；源码必须用 `section:source, stage_id` 按完整行读取。后续页必须带首次读取的固定 document `version`，用返回 `next_offset/has_more` 继续，不能把不同版本拼接。普通页 limit ≤ 50，source 完整响应 ≤ 16 KiB，其他页 ≤ 32 KiB。

工作台重开后用 `documents.get` 的 `section:texture_bytes` 重组纹理。必须提供 document_id、固定 version、该 revision 中的 texture_id；offset 为原始字节，limit ≤ 16384。返回 PageResult 的 `texture_bytes:{texture_id,content_hash,total_bytes,rgba_base64}` 与外层 `offset/next_offset/total/has_more`。完整重组后核对 SHA-256，再交给本地预览。删除 texture 后仍可按旧 revision 读取。不能传 hash、路径、URL 或另一个 document 作为替代定位。这个读取不生成 Run、receipt 或文档修订；Tool inspect 与自动 context 不提供这些字节。

`documents.head` 仅返回 `{id,version,content_hash,deleted}`，供可见工作台检查外部更改。它不读取 source/texture BLOB；实际加载走 get 的内容/hash/schema 校验。`documents.revisions` 后续页带固定 current `version`，采用从新到旧的不可变版本页。

## 临时 GPU 执行协议

激活 executor 独立于 Dock mount，使用 WebGL2。机器操作仅 `compute.attach/next/complete/detach`，不接受 Project selector，不创建作品、Run 或 Artifact；只有正在执行的正式 Tool 可以建立临时请求。

- attach 输入 client_id、递增 registration_counter、Host 提供的 package_digest、available、白名单 capabilities；输出 epoch、lease、lease_ms=5000、server_status。相同 client 的旧 counter 拒绝；新 client 不能抢占健康 lease。
- visible executor 每 500 ms 用 `{epoch,lease,registration_counter}` 调 next。输出 `{status:idle|busy|request,request?}`。request 是嵌套对象，包含 request_id、claim、invocation_id、document_id/version/content_hash、request_hash、remaining_ms、kind、snapshot。snapshot 是 `{document,textures:[{content_hash,rgba_base64}]}`，总响应 ≤ 8 MiB。
- complete 必须原样回送所有绑定字段以及 package_digest。result 为 compiled/rendered、diagnostics、logs、log_truncated，可选像素字段。成功 preview 要 compiled=true、rendered=true、精确 canonical preview 尺寸、row_order=bottom-left、严格 base64 和精确 RGBA 长度。compile 或非 rendered 结果不得带任何像素字段。compiled=false 必须有 error diagnostic；compiled=true 不得有 error。输入中的诊断/日志引用必须属于本 snapshot。
- `CONTEXT_LOST/GPU_ERROR/FBO_INCOMPLETE/EXECUTOR_UNAVAILABLE/COMPUTE_TIMEOUT` 属运行错误，不保存成功报告。complete 的 accepted 只表示交接；Tool 还会检查原 document head、epoch/lease/deadline/cancellation 并提交报告与 receipt。另一个 document 的修改不会使已经领取的精确计算结果失效。
- detach 的 reason 为 deactivate/hidden/context_lost/network_error。旧 epoch 不能撤销新的 executor。hidden、网络错误、context lost 或 activation 更换时停止领取，清理本地资源；重新激活只服务未来显式请求，不恢复旧计算。

owner 只有一个瞬时请求。deadline 10 秒，Tool timeout 12 秒，后端每 50 ms 检查取消/lease/deadline；无持久 GPU 队列或自动重试。GL 同步调用可能阻塞 renderer，后端不能保证即时 GPU 抢占。claim/lease 不写入 SQLite、日志、Artifact 或模型 context；同 realm trusted renderer 回执不是对恶意 publisher 的 GPU attestation。

13 个 Tools：`shader_create/inspect/modify`、`uniform_set`、`texture_bind`、`pass_create`、`compile`、`inspect_compile_error`、`render_preview`、`shader_delete/undo/diff/export`。普通观察 facts ≤ 8 KiB，source/diff 只进入 ≤ 16 KiB provider_payload；最多 20 条有界诊断。每次新调用使用 Host 冻结的真实 studio authority，不接受模型传 Project id。

## 历史、恢复与表示

每次有效编辑同时增加该 document version 和 studio generation；no-op、stale、invalid、compile/preview/export 不增加它们。删除写 tombstone。undo 复制目标内容及删除状态到新 revision；可 undo-of-undo，重复内容 hash 不唯一。项目删除的公开 SDK hook 当前不存在，本 DLC 不读取 Core 数据库猜测生命周期。

receipt 以 `(project, human|agent, request_id|invocation_id)` 隔离，输入 hash 含原操作和 Tool 的冻结 generation。相同 identity 的不同输入拒绝；已提交相同输入返回原结果。reconcile 只读取原 receipt 和不可变源，缺失是 unknown，绝不重新执行 GLSL。报告、top-left RGBA 和 receipt 在同一 SQLite 事务提交；提交前失败整体回滚，提交后 Host 结算失败可重建原 Artifact drafts。

revision、texture、receipt、report、preview 的 payload 总额 ≤ 256 MiB；SQLite 页、索引、WAL 另有开销。满额拒绝新增 payload，保留已有读能力；不自动删除历史。读前核验数据库长度/类型和持久计费，读后核验 schema/hash、对象身份及引用。heads/generations/history 不一致拒绝；不默默回退、修补或迁移未知 schema。

Artifact types 是 `dbfox.shader.document-revision/compile-report/preview`。Representation：document.v1 的 `page`（含批准的 texture_bytes）；compile-report.v1 的 `diagnostics`；preview.v1 的 `metadata/sample`（sample ≤ 32×32、nearest、top-left RGBA JSON）；preview-png.v1 的 `export` stream。Artifact exact locator 决定读取源，参数不允许覆盖 Project/document/version/hash；历史删除后仍可读取。PNG 用未修改 PyPNG 0.20220715.0（MIT）编码，官方源码/许可证/hash 在 backend/vendor；产品不依赖 Pillow，不解码压缩纹理输入。

## 后端验证与角色

Backend Engineer `/root/scene_lead/domain_architect` 是本实现作者，不是 Shader 独立红队。执行命令（工作目录为本仓库根）：

```powershell
& 'D:/Project/DBFox/.venv/Scripts/python.exe' -m pytest verification/tests/system/test_shader_dlc.py -q --tb=short
& 'D:/Project/DBFox/.venv/Scripts/python.exe' -m pyflakes dlcs/dbfox.shader/backend verification/tests/system/test_shader_dlc.py
& 'D:/Project/DBFox/.venv/Scripts/python.exe' -m mypy --no-warn-unused-configs --follow-imports=skip --no-incremental --exclude 'vendor' dlcs/dbfox.shader/backend
```

44 项作者验证通过，含实际 SQLite、正式 ToolRuntime、真实 ActionRun/RunLoop/Artifact 结算。Workbench 源码落盘后，同测试已使用实际 frontend + backend 签名完整包验证安装和生命周期。桥接测试的 GPU 回执仍是模拟输入，只证明协议；真实编译和像素的作者 Chrome 探针另列于 [质量证据](../../docs/quality/shader-dlc-evidence.md)。生产 Electron、关闭 Dock 的正式 Tool/GPU 联合闭环、benchmark/stress、独立 Verification/Adversarial 仍是交付门禁。

## Shader Studio 工作台

在 Project 资源树打开 Shader Studio，创建或选择文档。Source 页使用 CodeMirror 6 的 GLSL 高亮、行号和键盘编辑，Ctrl/Cmd+S 保存当前文档所有改动过的 stage。仅写入 typed `stage_replace` 操作，SQLite 仍是文档事实源。未保存草稿只在本 activation 的内存中保留，退出或禁用 DLC 会清除；有修改的草稿关闭再打开 Dock 可以继续编辑。历史报告的行号链接打开固定版本的只读工作台，另有 Open current document。

Passes 管理 vertex/fragment stage、按序执行的 pass、目标尺寸、clear color 和 texture/previous-pass bindings；Uniforms 直接编辑 float/int/bool、向量、矩阵和 RGB 快捷输入；Textures 可创建有界纯色 RGBA 或通过 Host 文件选择器导入 PNG。PNG 在浏览器标准 codec 解码前检查签名/IHDR 尺寸与压缩文件预算，得到 RGBA 后只提交一次 texture_create，不保存文件路径。后端不引入图片 decoder。History 分页显示 revision、结构/source diff 和恢复为新 revision，删除文档保留历史。

Preview locally 编译当前草稿并显示真实 WebGL 像素，不生成 Artifact。Live draft preview 延迟 600 ms 响应修改；固定尺寸、最终 pass 与时间由显式配置保存。Compile & publish、Render & publish、Export revision 使用既有 project ActionRun，完成后由 Host 的 `workbench.openArtifact` 打开耐久产物。没有该导航能力时明确阻止 publication；网络结果未知时提示检查历史，不重试。不可变 Artifact 视图只走公共 Representation，支持只读源码、诊断、PNG 预览/下载和 revision JSON（含原纹理字节）下载。

工作台以 1 秒可见窗口 head 检查同步外部修改。没有草稿时读取新固定版本；有草稿时保留原 source/version 并禁止写入。Inspect latest & rebase 只自动带过目标 source 未变的草稿；同一 stage 冲突显示两版 CodeMirror，必须明确选择后再次保存。Ask Agent 传正式 Studio Resource、document/stage/pass Object、version 和行 locator；未保存的行不会伪装成 canonical 引用。

activation executor 在注册时创建，独立于 Dock。编译与本地预览共用 `frontend/renderer.js`：真实 compile/link/reflection、RGBA8 FBO、前向 pass 与 readPixels。GLSL 版本由实际驱动处理原文后的固定预处理检查，原 source/hash 不改变；生成行不伪装成用户行号。隐藏、卸载、context lost、网络错误会终止本地领取并释放资源；重新可见或显式 Reconnect 只接新请求。同步驱动调用仍不能保证立即抢占。

CodeMirror 是本 DLC 的固定版本离线包，没有运行时 npm/CDN。`frontend/vendor/provenance.json` 记录官方 registry、完整性与 16 份上游 MIT 许可证；`.gitattributes` 保持 vendor 字节。构建与作者检查：

```powershell
# 工作目录 dlcs/dbfox.shader
npm.cmd ci --ignore-scripts
npm.cmd run build
# 工作目录 desktop
npm.cmd test -- --run src/features/dlc/__tests__/dbfoxShaderFixture.test.ts --maxWorkers=1
npm.cmd run typecheck:test
npm.cmd run lint
npm.cmd run build
```

13 项作者 frontend fixtures 通过。真实 Chrome 的生产等价 CSP 探针验证 CodeMirror ShadowRoot、GLSL 错误/修复、纹理行序、两个 pass 和窄窗口交互；其中 operation 边界是明确标识的内存测试替身，不能当作生产 HTTP、Electron 或正式 GPU Tool 结算证据。作者 Backend/Workbench 为同一角色线程，不是独立红队。

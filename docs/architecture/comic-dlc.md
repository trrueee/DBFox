# Comic DLC 的 canonical 模型与公共编辑合同

> 文档类型：架构设计
>
> 状态：当前
>
> 最后核验：2026-09-07
>
> 适用范围：dbfox.comic 作者候选；独立发布门禁尚未完成

Comic 拥有视觉叙事表达。Story 的人物事实、关系和世界设定不进入 Comic 私有数据库；角色标签只是这份作品内的视觉位置说明。独立 Comic 不依赖 Story 安装。跨能力 Agent 在同时获准的资源上读取公开观察，再调用 Comic 工具；本版本不假造 Story Representation 或自动同步协议。

## 调查与选择

已检查项目 Story/Scene/Voxel/Pixel 的公共注册和固定 Artifact 路径、标准库 SQLite 事务、浏览器 SVG/HTML 与 Konva Text。选择在真正的 DLC/Host 边界直接使用 `dbfox_dlc_api`，持久化采用 Python sqlite3，文字采用 SVG foreignObject 内的浏览器 HTML 排版。没有新增 Core 服务、数据库表、SDK 方法、领域 mapper、第二条 RunLoop 或 Story 数据副本。

[SVG foreignObject](https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Element/foreignObject) 可直接容纳 HTML 内容；[Konva Text](https://konvajs.org/api/Konva.Text.html) 已有换行与行高能力。实际 Chromium 152 探针比较中文/换行、英文长句、emoji/组合字符，三组 HTML/Konva 高度分别均为 104/132/48 px；序列化 SVG 经 Image.decode 与 canvas 编码也成功。探针见 `verification/testkit/comic-renderer-probe.cjs`。

生产仅用一个 `frontend/render.js`，供 Studio、历史 Artifact 和自包含 HTML 使用。用户文本先在 JSON/script 边界转义 `<` 和行分隔符，再用 `textContent` 插入；不拼接用户 HTML/XML/CSS/URL。字符整形与 Unicode 换行交给浏览器；溢出检测只读取 DOM scroll/client 尺寸并给出提示，不另写排版器。下载 HTML 是固定作品内容与同一渲染器；JSON 是同一 canonical 数据。不存在 Python/JS 两套文本测量逻辑。

Konva 调研固定为 10.3.3、MIT，npm registry integrity 为 `sha512-j3Rrn504bYFwJ0zV0ZbSOQRsM9KMBLOpEq6xZuyIjbaKeFbBXwgiM5SA4IDq4nwM1l49GVKs66Mo+sl7+4G7PQ==`，仅探针从固定版本 URL 加载。未选择它的原因是当前 DOM 命中、HTML 文本与完整 HTML 导出已满足需求，Canvas 增加包大小及对象生命周期维护，没有实际收益。生产不依赖探针网络、Konva、外部字体或付费 API。浏览器 foreignObject 的外部矢量软件兼容性有限，因此生产承诺 HTML/JSON，不承诺通用 SVG/PDF 输出。

## 唯一事实与容量

`ComicProject` schema 1 包含 title 与有序 Pages。每页有尺寸、背景、有序 Panels；每面板有局部矩形、背景、Shot、有序视觉元素。Shot 属于面板，没有独立可失配身份。所有 Page/Panel/Element ID 在作品内唯一，删除后的 ID 仅允许通过 undo 恢复，不能分配给新对象。bubble 的 speaker_id 必须指向同面板角色；删除关联角色前必须取消对白关联。局部矩形在父级 0..1 范围内，宽高至少 .02，禁止越界、NaN、Infinity 和 bool 冒充数值。

每作品最多 128 页、每页 24 面板/128 元素、总计 4096 元素；每页文字及镜头说明合计最多 64000 UTF-8 bytes。正文最多 8 MiB，历史最多 1024 修订或 128 MiB，精确回执最多 8192 条。每 Project 最多保留 256 作品（含 tombstone）。达到上限明确失败，不静默删除旧作品、截断正文或回执。目录每次 1–32 条，UI 分页取目录、只加载当前页；diff 的 offset 上限 16384 覆盖两份最大文档对象集合的并集。工具完整条目观察进一步限制到约 24 KB，保留可继续的 offset；不能以半条 JSON 续页。

## 统一 25 问

| 问题 | 当前实现 |
| --- | --- |
| 1 Resource | Project 的 Comic Library 与带修订的 Comic document。Host 提供实际授权集合。 |
| 2 Object | Page/Panel/CharacterPlacement/Bubble/Caption/VisualNote 稳定 ID；Shot 是 Panel 的结构化属性。 |
| 3 Selection | 页、面板或元素的 UI 选择；onAsk 使用所属 Comic authority 与内部对象 locator/version，不提升授权。 |
| 4 canonical document | 经过 Pydantic 合同验证的 ComicProject 完整文档；排序 JSON 的 SHA256 是内容身份。 |
| 5 durable facts | DLC data_path/comic.sqlite3：Project membership、head/status、不可变 revision/parent/hash/producer、精确请求回执及用过的 ID。Core 的 SQLite 继续拥有 Run/ToolInvocation/Artifact。 |
| 6 frontend state | 页/选中对象、视图、缩放、滚动、拖动与表单草稿，均是可丢弃投影；不进入 Core 状态机。作品 tab 的 authority/ID 由 Host Dock 保存。 |
| 7 context | 授权资源 ID/version 和数量摘要、分页检查工具观察、成功写入的 revision summary/Artifact。 |
| 8 excluded context | 全量作品、渲染字节、整页 JSON、私有 Story 数据、SQL/凭据/本地文件路径。Agent inspector 不提供 UI 的 full-page 分支。 |
| 9 version | 一次 canonical 真变化产生 v+1；no-op、重复同请求、失败均不增加版本。export 不改 canonical 版本。 |
| 10 stale invocation | frozen ref、resolved revision、expected_version 与当前 head 必须一致。任意错配先失败，禁止盲重放。 |
| 11 human/Agent conflict | UI 与 Agent 进入同一 ComicStore.write CAS 事务。冲突保留表单草稿，取消草稿/刷新后重新明确编辑；不自动重基或覆盖。无草稿时可见页面每 1.8 秒重新读取，拖动期间暂停。 |
| 12 operation log | 不用操作重放重建作品。精确回执指向唯一已提交修订与结果，request hash 绑定 Project/action/完整输入。 |
| 13 undo | 复制指定历史文档为新修订，继续 CAS；不改历史，不重新分配 ID。作品级删除为终态，历史仍可审计。 |
| 14 diff | 两个明确版本的对象增删/变化字段、前后 hash、顺序变化；分页，不返回全量对白。读取固定版本查看具体内容。 |
| 15 crash | WAL/FULL + BEGIN IMMEDIATE，提交前最后一次取消检查。提交前回滚；提交后由 exact receipt reconcile。SQLite chain/head/hash 不一致拒绝读取；reconcile 与 Artifact 读取还校验精确 producer receipt。 |
| 16 deactivate | Host 回收 owner 注册；前端取消读取/导出导航、timer、拖动及对象 URL，移除样式。epoch 与 alive 阻止迟到回调跨 generation。已经提交的写入保留事实，不自动重放。 |
| 17 Project delete | Host Project-scoped operation admission 与资源授权阻止已删除 Project 的访问。公共 SDK 没有 Project-delete data-GC hook，故不私建扫描器/私有 Host 导入；DLC 孤立历史数据保留，后续只通过真实生命周期合同回收。 |
| 18 large works | 有界 page directory/fixed page 与 panel/element 窗口；不把 128 页同时装进 DOM/context。每页最多 128 视觉元素。 |
| 19 bounded result | UI 输出上限 256 KiB；读工具 observation 24 KB 完整条目与续页；写入仅 Summary。完整历史 JSON/HTML 通过 Representation stream（64 KiB chunks）。 |
| 20 approval | 本地可撤销文档编辑，policy warning 且 requires_approval=false；没有外部执行、文件任意写入或网络 permission。Host 继续拥有通用审批能力。 |
| 21 retry | 固定版本 inspect/diff retry_safe，最多一次重试。写入和 export 使用 reconcile；UI 不自动 retry。 |
| 22 non-idempotent | create/增量编辑/undo/delete 初次请求可写入；唯一请求 ID 的 exact receipt 去重。不同输入复用 ID 拒绝。取消/timeout/断线不得换 ID 自动重放。 |
| 23 artifact | 每个成功工具可产出 dbfox.comic.revision；UI 导出经真实 ActionRun/ToolRuntime 完成。summary 与 producer receipt、资源范围共同校验。 |
| 24 Representation | dbfox.comic.document.v1 的固定 summary/pages/page/export_json/export_html；只有真实 Artifact + provenance 才可读取。 |
| 25 composition | 同时获准的 Agent 用公开工具；其他 DLC 通过 Host Artifact Representation 读取固定版本，不读取 comic.sqlite3、不私有 import、不镜像 Story。 |

## 工具与工作台

20 个工具由同一份 14 种领域 operation 合同派生，再加 create/inspect/diff/undo/delete/export；不存在同一工具重复注册或兼容协议。14 种 operation 包含原始八个工具及 note、element update、page reorder、object delete、page/panel property update。UI operations 也验证同一 ApplyInput；UI 没有独立 document 写入接口。

Studio 支持 page/storyboard、鼠标 move/resize、方向键、Escape、对象列表、属性表单、对白编辑、历史 diff/undo、固定工件和 Agent handoff。颜色遵循 Host UI tokens，作品颜色属于文档内容。角色画面是具有 standing/walking/seated/reaching 与朝向的视觉占位，不声称插画/骨骼动画。尚未保存的草稿是临时 view state，关闭/卸载视图会丢弃，保存动作才产生耐久修订。

## 验证与未决项

[作者证据](../quality/comic-author-candidate.md) 区分后端、生产 scripted RunLoop、实际 Electron 与共享 Host 窄 Dock 问题。没有真实 LLM 或 GPU 调用；脚本模型证明合同和路径，不证明模型创作质量。独立审查、故障注入与当前根 Host 组合门禁由主任务安排，作者不得把这些计为完成。

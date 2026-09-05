# Pixel DLC：像素画与 Sprite 动画

> 文档类型：架构方案
>
> 状态：已接受
>
> 最后核验：2026-09-05
>
> 适用范围：`dbfox.pixel` Capability DLC 后端与 Canvas Workbench

本文是 Pixel 首轮实施的唯一合同。独立 Domain Architect 已核验并修正严格类型、事务查重、锁层、历史容量和表示边界，结论为 **accepted（接受本页修正后的方案）**。后端现已实现，33项作者测试通过，包括签名包激活、真实同Run增量编辑和Human ActionRun导出。Canvas Workbench已实现并通过27项前端作者fixture及真实浏览器视觉检查；独立 benchmark/stress、签名Electron验收与红队尚未完成；作者验证不代替最终独立评审。实际证据见 [Pixel 验证证据](../quality/pixel-dlc-evidence.md)。

目标作品为 **32×32 狐狸骑士，4 帧待机、6 帧攻击**。用户和 Agent 必须能增量修改同一作品；Workbench 必须包含画布直接绘制、颜色板、图层、帧时间线、标签播放和撤销。

## 1. Host 接口与调查结果

本方案使用 [Capability DLC 合同](agent-core-capability-dlc-contract.md)、[DLC Runtime](runtime-dlc-platform.md)、[Artifact Representation](artifact-representation-visualization.md) 和 [公开前端声明](../../sdk/frontend/index.d.ts)。后端只从 `dbfox_dlc_api` 使用 Host 合同。不得修改 Core、公开 SDK、共享依赖锁或另一 DLC。

已检查的项目实现：

| 实现 | 可复用的原则 | 不复制的部分 |
| --- | --- | --- |
| Music `backend/store.py`、`contributions.py` | owner SQLite、Resource provider/resolver、静态 Guidance、修订 Artifact | 乐谱模型、音频依赖，以及禁止同内容重复修订的 hash 唯一索引 |
| Story `backend/contributions.py` 与当前合同 | project-scoped typed operations、对象与 Resource 分离、冲突错误 | 世界事实、章节表与 Story 私有接口 |
| Visualization `backend/authored_dataset.py` | 通过正式 Representation 网关读不可变成果 | Vega 文档和 DataFrame 业务模型 |
| Music 前端与公开 SDK | Host 注入 React、Connector、Dock、Artifact View、typed reference | 全局乐谱缓存、私有 Renderer API、领域回退字段 |
| Runtime 公开 API | `is_cancelled()`、owner operations、`require_action_runs()`、精确 ResourceScopeRef | 第二套 Run、Approval 或重试调度器 |

项目当前 Python 产品依赖没有 PNG 编码器。Pillow 只在 `requirements-dev.txt` / `requirements-dev.lock` 中，不能推断 Frozen Sidecar 或可安装 DLC 支持 Pillow。Pixel 路径的 Git 历史查询为空，不代表全部外部 issue 已检索。

选型：

| 需求 | 采用 | 理由与代价 |
| --- | --- | --- |
| PNG 输出 | 原样 vendored **PyPNG 0.20220715.0** | 纯 Python、无额外依赖、MIT、支持内存流；避免 native DLL/PYD 和共享锁变更；纯 Python 大图较慢，靠像素预算限制 |
| 画布 | 浏览器 Canvas 2D 与 Pointer Events | 官方平台能力；整数像素绘制、关闭插值；无前端 bundle、WASM、eval 依赖 |
| 耐久事务 | Python 标准库 `sqlite3`，显式事务 | 复用 SQLite CAS、WAL 和回滚，不自行实现日志恢复协议 |
| 输入和文档校验 | Host 已有 Pydantic | 严格对象合同、有界集合和跨字段 invariant；不新建映射模型 |
| 局部绘图算法 | DLC 内纯领域函数 | 填充、整数线段、矩形、stamp 和区域变换是本领域操作语义；不自研图像文件编解码器 |

[PyPNG 官方分发页](https://pypi.org/project/pypng/0.20220715.0/) 允许随应用分发单文件。Director 在仓库外准备了固定归档及 MIT 许可证；本次独立复核归档公开哈希 `739c433ba96f078315de54c0db975aee537cbc3e1d0ae4ed9aab0ca1e427e2c1`、本地 `png.py` 82,781 bytes、SHA-256 `b1c6211078af892bbe975f948d40e19f2e9ec064994f635b6e431b5c55e56830` 与 provenance 相符。Backend现已将文件原样加入产品，测试逐字节核对SHA；采用原样 vendor，仅调用 `Writer(width,height,greyscale=False,alpha=True,bitdepth=8,interlace=False).write(BytesIO,rows)`；不暴露 Reader、路径/CLI、外部图片导入、任意 writer 参数。输入只能是已校验 canonical 的合成 RGBA。源码导入均为标准库；含 CLI 的 `os/msvcrt` 分支不构成外部运行时依赖。旧版本和单维护者仍需 owner 后续跟踪，未进行完整漏洞库/源码安全审计，不能声称没有漏洞。Pillow 只做后续独立解码验证，不进产品依赖。

Canvas 选型依据：[MDN Canvas 2D](https://developer.mozilla.org/en-US/docs/Web/API/CanvasRenderingContext2D)、[关闭图像插值](https://developer.mozilla.org/en-US/docs/Web/API/CanvasRenderingContext2D/imageSmoothingEnabled)。事务依据：[Python sqlite3](https://docs.python.org/3/library/sqlite3.html#transaction-control)、[SQLite 事务](https://www.sqlite.org/lang_transaction.html)。不新增兼容层或跨 DLC 私有依赖；退出 PyPNG 只需替换 PNG 输出边界，文档格式不依赖它。

## 2. Canonical model 与对象边界

| 概念 | Pixel 定义 |
| --- | --- |
| Resource | `dbfox.pixel.document`，ID 为 `pixel_<uuidhex>`，version 为规范十进制 `str(revision)`；属于一个 Project |
| 创建入口 Resource | `dbfox.pixel.library`，ID 为 Project ID，固定 version `1`；无可写业务状态，只允许在该 Project 创建文档 |
| Object | `dbfox.pixel.frame`、`dbfox.pixel.layer`、`dbfox.pixel.tag`，ID 只在父文档内有意义 |
| Selection | frame ID、layer ID、整数矩形；是上下文提示，不扩张 authority |
| Canonical durable state | Canvas、Palette、Layers、Frames/Cels、Animation Tags 及修订关系 |
| View state | 缩放、画布滚动、选中色、工具、选择矩形、当前帧、播放进度、未提交笔迹 |
| Derived state | 当前帧合成图、时间线缩略图、播放光标、PNG、sprite sheet、diff 摘要 |
| Artifact | `dbfox.pixel.revision`，只保存 document/project/revision/hash/尺寸/数量等有界元数据 |
| Representation | `dbfox.pixel.sprite.v1`，从 Artifact 指定的不可变修订读取 metadata、frame、PNG、sprite sheet |
| Operation | 有明确目标、前置版本及严格参数的领域变化；不是整文档覆盖 |

`PixelDocument` schema v1：

```text
schema_version: 1
title: string (1..160)
canvas: {width: 1..128, height: 1..128}
palette: ordered PaletteEntry[1..256]
  PaletteEntry = {name: string <=80, color: #RRGGBBAA}
layers: ordered Layer[1..16], bottom to top
  Layer = {id, name, visible: bool, locked: bool}
frames: ordered Frame[1..256]
  Frame = {id, duration_ms: 20..2000, cels: Cel[one per layer]}
  Cel = {layer_id, pixels: palette-index[width * height]}
tags: AnimationTag[0..16]
  AnimationTag = {id, name, frame_ids: ordered unique IDs, loop: bool}
```

所有自有模型 `extra="forbid", frozen=True, strict=True`；每个整数用 `Field(strict=True)`，布尔字段也严格校验。ID 为 `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`；layer/frame/tag 名称1..80字符。`schema_version` 必须是严格整数且等于1，不能仅依赖 `Literal[1]`：当前 Pydantic 的 Literal 即使 strict 仍接受 `true`。像素和坐标禁止 bool、浮点、数字字符串。palette index 0 名称固定 `Transparent`、颜色固定 `#00000000`；其他项只能 `#RRGGBBFF`，颜色统一大写，拒绝其他 alpha。合成时从下到上选最上层 visible 非零索引，透明输出 RGBA `[0,0,0,0]`。Layer `visible` 与 `locked` 是作品事实；临时 solo/hover 才是 view state。

Canonical 全字段非 null。操作可选项明确分两类：默认参数的省略/null 归一为声明默认（如 filled=true、clip=false、transparent_mode=replace）；局部 update 参数的省略/null 都表示不修改，不能擦掉字段，至少提供一个实际 update 字段。required ID、version、index、坐标、布尔标志不可 null。归一化只在该严格输入模型完成一次，发生于 input hash 与领域计算之前；不新建 Human/Agent 两套操作模型。规范 JSON 使用 UTF-8、排序键、紧凑分隔符、`ensure_ascii=False, allow_nan=False`。64KiB 输入预算指经过解析/归一化的规范 JSON，不能虚称 owner 已限制 Host 解析前的 HTTP 字节流。

每帧恰有每图层一个 cel；frame/layer/tag ID 分别唯一，标签引用必须存在。像素是行优先索引，不能包含未定义调色板项。总像素槽 `width * height * frame_count * layer_count <= 262144`，canonical JSON UTF-8 不超过 2 MiB。128×128、256 帧、16 图层是单轴上限，不承诺它们可同时达到。32×32、10 帧、8 图层只占 81920 槽。

为防止隐式破坏对象关系：删除标签引用的帧默认拒绝；显式 `remove_from_tags=true` 才移除相关引用，并删除变空的标签。最后一帧或最后一图层不能删除。调色板修改保留索引身份，不提供重排/隐式删除。

帧内 cel 按当前 layers 顺序存储，恰好各一份；标签 frame_ids 有序、非空且最多64个唯一现存 ID，frame 重排不改变标签显式顺序。对象创建不可复用该文档历史使用过的同 kind ID；undo 可恢复原身份。创建文档默认 frame `frame_1`（100ms）、layer `layer_1`（name=`Layer 1`,visible=true,locked=false），默认 palette 为 Transparent/#00000000、Ink/#181825FF、White/#FFFFFFFF。自定义 palette 必须整体符合透明槽规则。

## 3. 耐久存储、版本、并发与恢复

唯一存储为 `host.runtime_info.data_path/state.sqlite3`，不访问 Core DB。表的职责为：

1. `documents`：ID、Project ID、head revision、active/deleted、时间；目录标题从 head 投影。
2. `revisions`：document ID、revision、parent revision、document JSON、content hash、status、操作摘要、author、时间。主键 `(document_id, revision)`；content hash **不唯一**。
3. `receipts`：owner 固定 `dbfox.pixel`、Project ID、actor、mutation/invocation ID、操作名、input hash、document ID、前置版本、结果版本及有界结果。唯一键至少含 Project、actor、ID。
4. `object_identities`：`(document_id,kind,object_id,created_revision)` 的不可变出生记录，只用于禁止历史 ID 复用；不镜像对象名称、像素或当前是否存在。与 revision 同事务新增，undo 恢复旧 ID 不重复创建记录。

SQLite schema `user_version=1`。初始化事务只接纳空库或受支持版本；拒绝未知版本和损坏状态，不能重建空库掩盖损坏。后续迁移逐版、事务化并有独立回滚测试。数据库连接按调用开启/关闭，WAL、foreign_keys、busy timeout 明确设置。

写入流程为：验证严格输入与精确 Resource 身份 → `BEGIN IMMEDIATE` → 在事务内查同 ID receipt 并校验完整输入绑定 → 验证当前 head/status、expected_version 和 frozen version → 读取/校验 canonical → 计算全部变更 → 校验完整文档和预算 → 最后检查取消 → 原子插入 revision/对象出生记录、CAS 更新 head、插入 receipt → commit。事务外查重不能替代事务内查重；同 ID 双写必须得到同一结果，不能让第二个调用误报 stale。CAS UPDATE 还须检查受影响行数。

首版最多128个 active 文档/Project；owner 总历史配额128MiB，计算规范 revision JSON、receipt/result、出生记录及每行固定开销，不是 SQLite/WAL 实际磁盘硬上限。配额内计数与写入在同事务完成；超额拒绝新增耐久行，不做静默 GC，已有 revision/Artifact 仍可读取。No-op receipt 也计入配额，已有 exact receipt 返回不新增费用。Canonical JSON 每修订≤2MiB；读数据库时先检查长度，再严格 JSON/模型解析并核对 hash、identity、revision、status。非法 JSON、坏索引、缺 cel、非有限值、未知 schema 或错 hash 一律 fail closed，不用空白文档替换损坏。

`expected_version` 对 **Agent 和人类都必填**。Agent 除了 expected version，还必须确认解析后的资源 ID、Project、revision 与 Invocation scope 精确一致。Host 每次调用重新绑定当前版本不能替代模型从 inspect 获取的前置版本，否则旧意图可能作用于新状态。

两个并发写者针对 revision 17，只允许一个推进到 18，另一个返回 `PIXEL_CONFLICT`；UI 提示重新读取，不能自动重放、隐式 rebase 或覆盖。未改变内容的合法操作保存 receipt 并返回 `changed=false`、原 revision；不制造空修订。重复 ID、相同 input hash 返回原结果；重复 ID、不同 input hash 返回 `PIXEL_RECEIPT_MISMATCH`。Human 和 Agent receipt 命名空间必须区分。

actor 由调用路径固定为 `human` 或 `agent`，禁止输入自报。Receipt 的规范输入绑定包含本地操作名、Project、document/library 身份、expected_version、归一化 operation；Agent 再绑定 frozen kind/id/project/version 与 invocation_id。reconcile 允许历史 resolver 先返回精确旧 handle，但只读匹配 receipt；不得把 frozen scope 更新成 head、跳过 selector 或重新执行。对象权限仍只来自其父 document。创建使用 library scope 和严格 expected_version=0。

工具写入 `retryable=false, recovery="reconcile"`。reconcile 只通过完整 receipt 匹配查证结果，禁止重新运行操作。resolver 可以返回 scope 对应的历史修订用于查证；正常写入仍 CAS 当前 head。取消和 timeout 由 `context.is_cancelled()` 在计算边界和 commit 前检查。已经 commit 后的取消不能虚构回滚，必须由 receipt 证明已应用并交 Host 结算。

Undo 从同 document 的明确 active 历史 revision 恢复内容，parent 仍为当前 head；必须 CAS 当前 active version。内容实际变化时追加 revision，允许 hash 与历史相同；恢复当前相同内容是 no-op。revision/status 属于生命周期事实，content_hash 只覆盖规范 PixelDocument，不包含 revision/时间；delete/restore 即使内容不变也追加 status 修订。Diff 比较明确 from/to revision，目录按 frame/layer/tag/palette 分页≤16项；像素只返回计数和每 cel 边界矩形，不返回巨大逐像素补丁。

文档删除是可恢复 tombstone 修订，provider 隐藏 deleted 文档；project-scoped `documents.restore` 可 CAS tombstone head 恢复。历史 Artifact 仍引用原修订，保留读取能力。当前公开 SDK 没有 Project 删除通知；本版保留自有数据，不猜测 Core 表或创建清理轮询。后续由真实通用生命周期合同解决物理清理。DLC deactivate 由 Host 撤销 contributions，前端释放播放、请求、监听、投影；耐久数据保留供 reactivate。

Tombstone 保存删除前 document；restore 只能从当前 deleted head 追加 active 修订，不能接受任意 replacement。新 Tool 无法从隐藏的 deleted document 取得 authority，因此 Agent restore 使用同 Project library；必须再校验所选 document 的 Project，不能用文档字符串越界。全局明确 undo/delete/restore 可恢复锁定状态；普通 apply 的锁不能以 frame_delete 绕过：删除含任一 locked layer cel 的帧必须先显式解锁。Frame create/duplicate 可给 locked layer 建立新的 cel，允许读锁定来源；palette 修改、可见性和 duration 属于独立作品参数，不代表修改被锁定 cel 的索引内容。

## 4. 工具与 typed owner operations

所有工具输入均不接受 Project ID 来扩大权限；从 library/document handle 得到已授权 Project。document 工具以 `document_id` selector 绑定精确 Resource。

| Tool local name | 领域输入与行为 |
| --- | --- |
| `pixel_create` | library ID、title、width、height、初始 palette；创建空白第一帧和第一图层，返回 ID |
| `pixel_documents` | library ID、include_deleted、page/page_size≤8；同Project有界目录，供恢复前检查 |
| `pixel_restore` | library ID、document ID、expected_version；只恢复同Project tombstone，Artifact refs仍用library |
| `pixel_inspect` | document ID、可选 frame/layer/region、page；有界元数据/局部像素，不返回全作品 |
| `pixel_fill` | frame、layer、seed x/y、palette index；四邻接 flood fill；可选有界矩形 |
| `pixel_line` | frame、layer、x0/y0/x1/y1、palette index；整数线段，包含端点 |
| `pixel_rect` | frame、layer、x/y/width/height、palette index、filled；整数边界 |
| `pixel_stamp` | frame、layer、x/y、width/height、palette indices、transparent_mode；局部图案 stamp，最多4096格 |
| `palette_set` | palette index、name/color；改现有槽或在末尾追加，不移动其他索引 |
| `frame_create` | 新 frame ID、插入位置、duration；初始化透明 cels |
| `frame_duplicate` | source frame ID、新 frame ID、插入位置；复制 cels，ID 不复用 |
| `layer_create` | 新 layer ID、name、插入位置；为所有帧增加透明 cel，先验证总预算 |
| `region_transform` | frame/layer、source rect、translate/flip_x/flip_y/rotate_cw、copy/move；先取源快照再写，禁止重叠遍历污染 |
| `pixel_apply` | 最多128个严格 discriminated operations，原子应用；支撑成段笔迹和批量结构变化 |
| `pixel_undo` | document ID、expected version、restore revision；新建恢复修订 |
| `pixel_delete` | document ID、expected version；追加可恢复tombstone，隐藏当前Resource但保留历史 |
| `pixel_diff` | document ID、from/to revision、page；同文档有界 diff |
| `pixel_export` | document ID、expected version；正式 Tool 产生 revision Artifact，表示可下载 PNG/sheet |

所有修改工具均包含 `expected_version`，并共享同一纯领域 `apply_operation()` 与同一个 Store 提交函数。`pixel_apply` 还包括 `frame_update`、`frame_delete`、`layer_update`、`layer_delete`、`tag_set`、`tag_delete`、`rename`；每项有独立严格模型，不接受任意 JSON Patch、函数名或代码。锁定图层拒绝像素变化，结构更新必须显式解锁后才能删除。

越界坐标默认拒绝；region transform 可以显式 `clip=true` 裁剪目标，不能静默改变边界语义。输入整体不超过64 KiB，每项及总像素预算分别校验。所有业务错误固定、有界，不传播 SQLite 路径或异常栈。Inspect/diff保留完整页条目；如果丰富的cel diff在请求页大小下超过16KiB，返回明确预算错误，调用者缩小page_size并从page=0重读。不会悄悄截断条目或改变页偏移。Human目录仍可每页32项，Agent目录每页8项，确保长标题下的Tool预算。

Workbench RPC 合同：

| Operation | 输入 | 输出 |
| --- | --- | --- |
| `documents.list` | page=0、page_size=16（1..32）、include_deleted=false | `{documents:DocumentSummary[],has_more}` |
| `documents.create` | title、width、height、palette=null、expected_version=0、mutation_id | MutationResult；初始 frame/layer ID 如第2节 |
| `documents.get` | document_id、可选 revision | metadata（不含 pixels）、revision、hash、status |
| `documents.head` | document_id | revision、hash、status |
| `frames.read` | document_id、revision、frame_id | 该帧所有 cels 和 palette；上限2 MiB，供画布 |
| `documents.apply` | document_id、expected_version、mutation_id、operations | revision、hash、changed、changed IDs/regions |
| `documents.undo` | document_id、expected_version、mutation_id、restore_revision | 同 apply |
| `documents.delete` / `documents.restore` | document_id、expected_version、mutation_id | 同 apply、status |
| `documents.export` | document_id、expected_version、mutation_id | `{run_id,session_id,artifact_ids}`，来自正式 action Run |

Human mutation ID 每次用户手势生成一次；网络断开后保留已提交 ID 用于查证，但不自动重发写请求。显式导出通过 `context.require_action_runs().start()` → `pixel_export` → `complete()` 产生正式 Artifact；一般画笔手势调用 typed owner operation，进入相同 Store，不新造 Agent Run。

`documents.export` 是 Host ActionRun 边界，不等同 owner 文档写事务。当前 `DlcActionRunsHost.start()` 未指定 session 时先新建 Session，因此不能宣称其 idempotency_key 单独提供跨新 Session 的 exact duplicate 防护。UI 对未知导出不自动重发。实现若要支持同 mutation_id 返回原导出结果，须在 owner receipt 同键预留并绑定输入，完成后记录真实 run/session/artifact IDs；未完成预留只能报 `PIXEL_EXPORT_UNCONFIRMED`，禁止创建第二个 Run。该记录只防重复，不调度或恢复 Run，Host 仍独占 Run 生命周期。

后端最小字段合同：

- `DocumentSummary={project_id,document_id,revision:int,parent_revision:int|null,content_hash,title,width,height,frame_count,layer_count,palette_count,tag_count,status}`；`MutationResult` 在此基础加 `changed:boolean,changed_pixel_count:int,changed_frame_ids,changed_frame_ids_truncated:boolean,changed_layer_ids`；变化frame ID最多128个，超出时显式truncated=true，其余通过分页diff读取，不附全 pixels。
- `documents.get={document_id,revision:int|null}` 返回 `{summary,document}`，document 为第2节 metadata（frames只含id/duration，无cels）；`documents.head` 返回 `{document_id,revision,content_hash,status}`。
- `frames.read={document_id,revision,frame_id}` 返回 `{document_id,revision,content_hash,canvas,palette,frame}`，frame 含该帧全部 cels；读取同一完整 revision 行，不能另查最新 palette。显式把 `DlcOperationSpec.max_output_bytes` 设为2MiB，不能沿用Host默认1MiB。metadata get 上限512KiB。
- `documents.apply={document_id,expected_version,mutation_id,operations:[1..128]}`；单工具写输入为 `{document_id,expected_version,operation:<同一模型>}`。Human IDs≤128字符，Agent直接用context.invocation_id。undo使用 `restore_revision`；delete/restore无附加业务参数。`documents.revisions={document_id,before_revision:null,limit:16}` 返回 `revisions` 摘要与 `next_before_revision`；`documents.diff`/`pixel_diff` 用 `from_revision,to_revision,kind,page,page_size`。

所有 operation 的 `kind` 必填；frame/layer字段统一为 `frame_id,layer_id`，palette字段为 `palette_index`。矩形统一 `rect={x,y,width,height}`（width/height正整数，右下边界不包含）。不得加入同义字段适配层。

| kind | 其余字段与默认 |
| --- | --- |
| `fill` | frame_id,layer_id,x,y,palette_index,rect=null；四邻接填充，seed必须在限制rect内 |
| `line` | frame_id,layer_id,x0,y0,x1,y1,palette_index；含端点的确定整数线 |
| `rect` | frame_id,layer_id,rect,palette_index,filled=true |
| `stamp` | frame_id,layer_id,rect,pixels,transparent_mode="replace"；最多4096格，长度严格相等；over跳过0 |
| `palette_set` | index,name,color；index仅可小于等于当前palette长度，等于长度才追加；0固定 |
| `frame_create` | frame_id,position,duration_ms=100；position为0..当前帧数 |
| `frame_duplicate` | source_frame_id,frame_id,position；从开始时的来源帧复制cels和duration，不复用ID |
| `frame_update` | frame_id,duration_ms=null,position=null；至少一个字段，重排位置为0..帧数-1 |
| `frame_delete` | frame_id,remove_from_tags=false；锁层/最后帧约束见上文 |
| `layer_create` | layer_id,name,position；默认visible=true,locked=false；预先验证全部帧slot预算 |
| `layer_update` | layer_id,name=null,visible=null,locked=null,position=null；至少一个字段 |
| `layer_delete` | layer_id；禁止锁层/最后层 |
| `tag_set` | tag_id,name,frame_ids,loop=true；存在则局部身份更新，不存在则创建并查出生记录 |
| `tag_delete` | tag_id |
| `rename` | title |
| `region_transform` | frame_id,layer_id,rect,transform,destination:{x,y},mode="copy",clip=false；transform为translate/flip_x/flip_y/rotate_cw，mode为copy/move |

region transform 先读取整个 source snapshot；move 清除原source，再将包含透明0的结果写入destination。rotate_cw的局部映射 `(u,v)→(height-1-v,u)`，目标宽高互换；flip_x/flip_y 分别反射局部横/纵坐标。clip只裁剪目标，source始终必须完整在画布内；move+clip会明确丢弃越界部分。128项按顺序原子作用在临时文档，各项前检查锁/引用与分配预算，各项读取其开始时的源；任一失败全部回滚，不能把坏操作跳过。

## 5. Context、Artifact 与跨 DLC 表示

自动 Context 最多4个 fragment，每个不超过2000字符，只包含已授权文档的 ID、revision、尺寸、帧/图层数量、有限标签摘要和如何 inspect 的引用信息。不得自动注入像素、全帧内容、PNG/base64、整个 palette 或未授权 Project 目录。动态文档标题与标签是 untrusted data，不进入 Guidance。

`pixel_inspect` 详细像素最多返回单帧单图层16×16；输入 `{document_id,revision=null,kind="frames",page=0,page_size=16,frame_id=null,layer_id=null,rect=null}`，后三项必须同时提供才返回局部像素。kind为frames/layers/tags/palette；每页最多16项。tag目录只给frame_count和前8个frame ID，并标注truncated，不能16项各塞64个长ID冲破预算；完整tag顺序由表示metadata分页读取。默认只给摘要；Tool 输出上限16KiB，耐久Observation facts保留摘要/计数/版本/目录与selection，不保存像素细节；局部像素只进入本Run临时provider_payload，以便模型实际检查。完整function_call_output包装在作者测试中同时检查字节和字符预算≤18KiB。

`dbfox.pixel.revision` schema_version=1，payload为上述 DocumentSummary。Artifact refs 必须是本次合法 Invocation scope；create/restore绑定library，由不可变payload标识文档；后续修改使用当次document scope，不能清空refs或退回初始library来逃过Host检查。

`dbfox.pixel.sprite.v1` operations：

| operation | 结果 |
| --- | --- |
| `metadata` | 尺寸、frame ID/duration、tag ID/frame IDs、palette 摘要；有界分页 |
| `frame` | 指定 frame、region（最大32×32）的合成 RGBA 数组与坐标；JSON，有界消费 |
| `png` | 指定 frame 的 PNG byte stream，`image/png` |
| `sheet` | `{tag_id:null}`；按tag顺序或document frames顺序排列的PNG byte stream；优先横向，超过8192宽时按行排成无padding网格，坐标由sheet_layout给出 |
| `sheet_layout` | 与sheet相同参数，JSON返回frame_id、x/y/width/height、duration、总尺寸；最多64项 |

每次读取验证 Artifact type/schema、payload、document/project/revision、hash，固定 `consistency="durable_snapshot"`。不能根据当前 head 替换历史内容；错误参数、hash 不匹配、缺失或损坏修订 fail closed。输出只允许 owner 内存字节流和安全文件名，不接受本地输出路径、远程 URL 或外部程序。

PNG与sheet明确声明 `result_kind="stream", media_type="image/png"`，不把JSON格位塞进二进制结果；metadata/frame/sheet_layout是JSON。metadata参数 `{kind:"frames"|"layers"|"palette"|"tags",page:0,page_size:16,tag_id:null}`；tag_id只用于读取一个tag的完整有序frame ID页，普通tags列表仍截断预览。frame参数 `{frame_id,rect}`，最多32×32，输出row-major扁平RGBA（长度width*height*4）；png参数 `{frame_id}`。参数拒绝未知字段/非严格整数；representation不接受override document/project/revision。sheet像素数≤262144、最长边≤8192，PNG输出预算2MiB，编码前验证规模，按行生成。每个表示的布局、像素与duration都来自同一Artifact revision。

Composition DLC 可通过公开 `read_artifact_representation()` 获得 metadata 和局部 RGBA，Human 下载经 Host stream；不导入 PixelStore，也不把帧或图层冒充 Resource。未来 Game 动画消费 tags、frame duration 与同一 immutable revision，不能混入新 head。

## 6. Workbench 与人类编辑

左侧提供 palette 和 layer stack，中间为整数缩放画布，底部为可选中帧时间线，右侧为选区 inspector 和播放预览。键盘提供 B 画笔、E 橡皮、F 填充、R 矩形、V 选区、空格播放和 Ctrl/Cmd+Z 撤销，输入框内不截获快捷键。

Pointer down 固定 document/frame/layer/expected version，使用 pointer capture 收集临时线段；Pointer up 把最多128段作为一次 `documents.apply` 提交。Pointer cancel、失去 capture 或卸载丢弃未提交手势。提交前 Canvas 只显示标明的临时笔迹；成功才读取 committed frame，冲突后清除草稿并刷新，不能让 optimistic 投影成为事实源。

选择矩形、颜色和播放进度只保存在 component/view state，key 为 `workbenchScopeId + projectId + documentId`。`onAsk()` 使用父 document authority、选中 frame/layer object 和精确 locator/revision；label/locator 不能扩大权限。

目前 SDK 没有 owner 文档变更订阅。活跃、可见画布可每1秒读取轻量 `documents.head`，revision 变化后用可取消请求重读；写入后立即读回。切换项目、文档、scope、DLC epoch 或卸载时 abort 全部读请求，销毁计时器和动画，忽略旧请求结果。此轮询只投影 owner state，不读取 Core DB，也不重试写操作。

动画以 frame 的 duration 与 tag 的有序 frame IDs 播放；播放暂停不改 canonical。缩略图和 preview 由已读取的指定 revision 派生，不维护另一份可写动画模型。空白状态允许直接创建；用户可创建/复制/删除帧，编辑时长与标签，添加/隐藏/锁定/删除图层，修改 palette，移动/镜像选区和撤销。

实现入口为 `frontend/index.js`、`model.js`、`index.css`。前端复用Host注入React、语义设计令牌和原生有标签表单；SDK当前仅提供Tree/CodeArtifact，它们不适配像素编辑表单，因此没有自建另一套通用UI框架或引入第三方绘图依赖。Canvas 2D负责呈现，Pointer Events负责捕获，ResizeObserver选择整数适配缩放，requestAnimationFrame只负责播放；所有像素与结构编辑仍进入后端typed operations。

同一修订的帧只读缓存最大受262144slots约束，先读选中帧，再以2个并发读取剩余帧；读取会核对document/revision/hash/canvas/palette和cel身份，拒绝混合版本。正常显示、绘制前后的canonical数据没有第二份可写状态。Deactivation主动释放指针捕获，即使Host尚未移除组件；scope变化的React key重新初始化视图。

导出在一个被捕获的scope和AbortSignal内完成。缺少Host可选导航方法在创建ActionRun前失败。已知导出身份可只重试导航；未知导出停用当前工作台的新导出并提示原mutation ID，禁止自动发起另一个Run。Artifact视图通过公开stream下载，至多保留当前预览与上一次下载的Blob URL，替换/卸载/deactivate时释放。

## 7. 验证与退出门禁

必须有单元、真实 Runtime/Tool、Workbench 和独立 adversarial evidence，详见 [验证证据](../quality/pixel-dlc-evidence.md)。至少覆盖：

- 文档/对象增删改、invalid reference、malformed input、帧/标签一致性、预算拒绝；
- SQLite 重启、进程中断/事务回滚、损坏库、未知 schema、receipt 成对提交；
- stale scope、stale expected version、双写竞争、重复调用与不同输入重用 ID；
- cancel、timeout、未提交/已提交恢复、不自动重放、deactivate/reactivate；
- UI 真实绘制、选择、帧切换、palette/layer、播放、撤销、Agent 修改后刷新和旧请求隔离；
- PNG 由成熟库交叉解码核对像素，Artifact 固定修订，Representation 不跨 owner/resource；
- 生产 Tool path 创建目标作品，再执行至少10类持续修改，包括模糊/冲突指令拒绝和人类编辑后的 Agent 修改。

没有以上证据不得声明 DLC 完成。只有 Program Director 可以标记 integrated。Domain Architect方案核验、Backend与Workbench实施/作者验证已完成；独立Verification与Adversarial Reviewer仍待执行。

Director曾报告同Run创建document后的通用Artifact authority错配。Pixel实际RunLoop测试先复现 `TOOL_OUTPUT_CONTRACT_FAILED / ArtifactDraftContractError`，随后Director把独立Host修复 `8ba14f69` 合入本worktree（对应提交 `8b70c89c`）。同一个测试不作放宽即通过 create→rect→inspect→line→export 五个Invocation、单Run、最终revision3，动态ID/version仅来自正式function_call_output。没有清空refs、私自扩权或每次新建Run。该后端集成证据不代表完整Workbench或独立stress已经通过。

## 8. 模板25项边界回答

| # | 问题 | 冻结答案 |
| --- | --- | --- |
| 1 | Resource | 每Project一个library，每PixelDocument一个version-fenced document |
| 2 | Object | 文档内frame/layer/tag稳定ID，palette槽索引；均不另授authority |
| 3 | Selection | 指定frame/layer的整数rect，仅作view state与引用 |
| 4 | Canonical | 第2节PixelDocument；唯一palette/layers/frames/cels/tags |
| 5 | SQLite事实 | head、完整不可变revision/status、精确receipt、对象出生记录 |
| 6 | Frontend state | 工具、颜色选择、缩放、选区、播放游标、临时笔迹、临时solo |
| 7 | Context | 已授权ID/version/尺寸/数量、有限标签摘要、inspect入口 |
| 8 | 禁止Context | 全文档/全帧pixels、PNG/base64、完整palette、他Project数据 |
| 9 | Version | 有变化一次事务追加一次revision；no-op仅receipt；delete/restore追加status |
| 10 | Stale Invocation | 新写同时核验frozen scope、expected_version、head；409冲突不执行 |
| 11 | Human/Agent冲突 | 同一Store/CAS，只能一方成功，另一方重新inspect，不隐式rebase |
| 12 | Operation log | revision操作摘要与精确receipt即可；不建第二套可写事件源 |
| 13 | Undo | 同document active历史内容恢复成新修订，可重复历史hash；重复相同内容no-op |
| 14 | Diff | 明确from/to的按目录分页及cel变化计数/矩形，不返回全像素patch |
| 15 | Crash | SQLite事务回滚；commit后由原receipt reconcile，不自动重演 |
| 16 | Deactivate | Host撤contributions；UI abort请求、清RAF/计时器/监听/缓存，owner数据保留 |
| 17 | Project删除 | SDK无通知，保留owner历史；不偷读Core或轮询删库 |
| 18 | 大作品 | 262144slots/2MiB canonical硬预算，context目录分页，画布单帧读取 |
| 19 | Tool bounded | 规范输入64KiB/128ops、输出16KiB、自动context≤4×2000字符 |
| 20 | Approval | 本版本地可撤销创作不自设额外确认；策略由Host ToolPolicy执行；无外部发送/路径写入 |
| 21 | Retry | 历史只读可重读；canonical写只精确receipt reconcile；未知导出不重发 |
| 22 | 非幂等 | create/编辑/结构变化/undo/delete/restore与新ActionRun；mutation/invocation ID约束重复 |
| 23 | Artifact | 正式Tool或ActionRun输出revision summary，refs保留合法Invocation scope |
| 24 | Representation | metadata/frame/sheet_layout JSON，png/sheet二进制；固定历史修订且核对hash |
| 25 | Composition | 仅公开read_artifact_representation读已授权成果；不得读SQLite/import PixelStore |

最小实施顺序：严格canonical/operation模型与纯领域apply → 单个SQLite Store/CAS/receipt → provider/resolver/context与正式Tools → project operations/ActionRun → PyPNG表示 → Canvas Workbench。没有必要引入通用mapper、渲染器、数据库repository接口或私有导出HTTP。先写领域和事务必要测试，再以实际SDK包激活与生产RunLoop关闭真实系统边界；本次只读评审未写产品代码或测试文件。

## 当前历史索引完整性

`PixelStore._document_index` 为 `_revision` 与 `documents.head` 共同检查owner head、最大已存revision、head父行/状态/hash形状。`_revision` 同时要求所读固定历史版本的父行存在，并保留canonical字节、hash与对象出生记录检查。目录读取通过 `_revision`，不能把回退head伪装成旧作品；损坏状态直接报错，不自动重建或修复。head轮询只查索引列，完整正文仍在后续固定版本读取时校验。没有添加第二份耐久事实源。


## 数百帧规模修正

原64帧单轴限制没有满足数百帧目标；独立生产合同200帧回归先失败于position<=63。沿用唯一规范文档、既有分页inspect/diff、PyPNG与单帧固定revision读取，把frame/position/tag/summary统一为最多256帧。262144slots、2MiB canonical、64KiB输入、16KiB Agent输出与128MiB历史配额保持不变；32×32×256×1正好达到像素槽上限，不承诺256帧与16图层可同时达到。

超过128个变化帧ID时，MutationResult的changed_frame_ids_truncated=true，不能把其前128项解释为全部变化；完整变化走原分页diff。该字段默认false准确覆盖旧64帧版本至多128个前后ID的回执，无需改写旧SQLite行。Renderer metadata上限512KiB仅容纳256长ID帧及16个完整标签，Agent的inspect/Context预算没有变化。PNG复用PyPNG，layout与编码使用同一无padding行列计算，边长8192和总像素槽预算不提高。

Workbench时间线每页最多32个缩略图，提供页跳转；选中身份跨刷新保留，跳页不写耐久状态。已选帧优先读，剩余帧保持最多两个并发只读请求，全部绑定同一revision/hash；这仍可能使长动画首次预览等待，实际耗时由独立生产桌面验收记录。

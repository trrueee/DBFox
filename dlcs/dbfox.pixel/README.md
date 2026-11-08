# Pixel Art Studio

> 文档类型：实现指南
>
> 状态：当前
>
> 最后核验：2026-11-07
>
> 适用范围：`dbfox.pixel` 0.1.0 后端与 Canvas 工作台，Extension API v2

Pixel 提供可增量编辑的像素画与 Sprite 动画文档。后端与 Canvas Workbench 已实现并通过各自作者验证。独立 capability benchmark、持续创作 stress、完整签名 Electron 验收与红队仍待完成，不能据此声明 DLC 已完成。

完整权威合同见 [Pixel 架构](../../docs/architecture/pixel-dlc.md)，实际验证与限制见 [质量记录](../../docs/quality/pixel-dlc-evidence.md)。Backend 只通过 `dbfox_dlc_api` 接入 Host，自有 SQLite 位于 Host 分配的 `data_path/state.sqlite3`，不读取 Core 元数据库。

## 编辑流程

Human 通过 project-scoped operation 进入同一个 Store；Agent 使用正式 Tool。一次直接绘制手势生成一个稳定 `mutation_id`，带上开始手势时读取的 `expected_version`。成功后用返回的 `document_id`、`revision` 读取同一修订；冲突后重新检查，禁止自动重发写请求。

创建输入示例：

```json
{"title":"Fox Knight","width":32,"height":32,"expected_version":0,"mutation_id":"create-knight"}
```

调用 `documents.create` 后获得平铺的 `MutationResult`，含 `document_id`、`revision`、`content_hash`、尺寸、数量、`status`、`changed` 和变化计数。默认第一帧为 `frame_1`、图层为 `layer_1`。同一返回结构用于 apply、undo、delete、restore。

批量编辑示例（替换 document ID 和版本）：

```json
{
  "document_id":"pixel_0123456789abcdef",
  "expected_version":1,
  "mutation_id":"gesture-unique-id",
  "operations":[
    {"kind":"rect","frame_id":"frame_1","layer_id":"layer_1","rect":{"x":8,"y":6,"width":16,"height":20},"palette_index":1,"filled":true},
    {"kind":"frame_duplicate","source_frame_id":"frame_1","frame_id":"idle_2","position":1},
    {"kind":"tag_set","tag_id":"idle","name":"Idle","frame_ids":["frame_1","idle_2"],"loop":true}
  ]
}
```

`documents.get` 返回 `{summary,document}`，document 仅有目录及 metadata，frames 不含 cels。`documents.head` 是轻量只读 `{document_id,revision,content_hash,status}`，供可见工作台检查版本。`frames.read` 必填 `document_id,revision,frame_id`，一次读取该帧全部 cels 与同修订 palette，输出上限2MiB。不要从新 head 获取 palette 并与旧帧混合。

已注册12个 operations：`documents.list/create/get/head/apply/undo/delete/restore/revisions/diff/export` 与 `frames.read`。精确参数模型位于 [contracts.py](backend/contracts.py)。Agent 有18个工具：`pixel_create/documents/restore/inspect/fill/line/rect/stamp/apply/undo/delete/diff/export`、`palette_set`、`frame_create`、`frame_duplicate`、`layer_create`、`region_transform`。单领域写工具使用 `{document_id,expected_version,operation}`，operation 的 `kind` 必填；创建、目录和 restore 工具还需精确 `library_id`。

写工具合同 v2 和 `pixel_authoring` v2 明确 `stamp.pixels` 为一维行优先数组，数量必须
恰好等于 `rect.width * rect.height`，16×16 即 256 个。手工设计图案优先用简单矩形、
线条或同一原子批次中的小行带，避免长数组计数错误。数量错误使用标准
`PydanticCustomError` 的静态规则类型，经原 PolicyGate 向模型报告字段位置与规则，
不回显原始输入，也不自动补齐或裁掉错误像素。

## 版本、预算与锁

每个文档有独立 version-fenced Resource，版本为规范十进制字符串；frame/layer/tag 是父文档对象。事务追加不可变修订、CAS head 和精确 receipt；相同 ID/输入返回原结果，不同输入重用 ID 拒绝。No-op 不追加内容修订，undo 将历史内容恢复为新修订，允许重复历史 hash。对象 ID 一经出生不能给新对象复用，undo 可以恢复原身份。删除为可恢复 tombstone，历史 Artifact 保留。

Canvas 每轴1..128；总像素槽≤262144，最多256帧、16层、256调色板槽、16标签。Canonical≤2MiB；一次操作≤128项、规范输入≤64KiB；owner历史逻辑配额128MiB。达到配额拒绝新增耐久行，不删除旧历史。槽0固定透明，其余颜色只接受不透明RGBA。锁层拒绝绘制与删除；删除任何帧须先解锁其各 cel。

Tool输出≤16KiB，目录工具每页≤8；Human目录每页≤32。Inspect/diff每页≤16项；极丰富diff若超过预算会明确要求缩小页面，不会截掉对象字段或丢失连续页位置。Context最多4×2000字符，不含像素。Inspect最多16×16像素仅进入本Run临时Provider窗口，耐久Observation facts保留ID、revision、目录、选择和计数。

## 导出与依赖

`documents.export` 必须经 Host ActionRun 调用 `pixel_export` 并完成正式 Artifact。返回 `{run_id,session_id,artifact_ids}`；同一 `mutation_id` 由 owner reservation/receipt 查重，开始Run前预留完整16KiB结果额度。如果上次结果未知，明确拒绝重放，不创建另一个 Run。Workbench 在导出开始前捕获 Host、scope 和 AbortController，并用同一 AbortSignal 调用 operation 与可选 `openArtifact`。缺失导航方法时不会创建 Run；已知成果的导航失败可重新打开原成果，未知导出会停用当前工作台的新导出并显示原 mutation ID，禁止自动创建替代 Run。

`dbfox.pixel.revision` 保存有界 summary；`dbfox.pixel.sprite.v1` 从固定修订提供 `metadata`、最大32×32合成 `frame` RGBA、`sheet_layout` JSON，以及 `png`、`sheet` 的 `image/png` 字节流。Sheet按文档帧顺序或tag显式顺序排列；超过8192宽时分行，使用sheet_layout的逐帧坐标。所有读核对文档/Project/revision/hash与Artifact provenance，拒绝路径、URL或任意编码器参数。

PNG由原样 vendored PyPNG 0.20220715.0 Writer 编码，见 [许可证](backend/vendor/LICENCE) 和 [provenance](backend/vendor/provenance.json)。它只有标准库依赖；产品不使用Pillow。`.gitattributes` 保持 upstream bytes 在 Windows checkout 后不变。Reader/CLI不暴露给产品输入，不安装共享依赖、不需要本地二进制或网络服务。

## 验证和打包

仓库根运行：

```powershell
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_pixel_dlc.py -q --tb=short
```

签名激活与真实RunLoop测试使用完整后端和真实 Canvas 工作台，逐字节核对签名包中的前端文件；不使用后端阶段的隔离 frontend stub。本轮后端与对抗相关集合 110 项通过，工作台 fixture 30 项通过；真实 Electron 的有限业务流程记录在[连续使用记录](../../docs/quality/continuous-product-use-20261107.md)，不能据此宣布全部发布门禁通过。不要将临时测试包或 SQLite 数据提交。

## Canvas 工作台

从项目资源进入 Pixel Studio，创建或打开作品。左侧提供透明槽、调色板、图层栈，中央为整数缩放 Canvas，底部为帧时间线，右侧提供选区、动画预览与标签。小窗口按顺序滚动；适应画布自动选整数缩放，手动缩放保持到当前文档视图结束。

目录与具体作品使用不同的 Host Dock 身份。创建或打开作品后，以规范 document
对象目标和作品名打开标签，重建视图时直接按目标恢复；不再只在组件内保存当前
document ID。返回目录会聚焦既有目录标签。入口和标签图标使用 Host 的标准图片图标。

- B 画笔、E 橡皮、F 四邻接填充、R 矩形、V 选区；矩形可选空心。拖动临时笔迹标为未提交，松开后以最多128段的一次 `documents.apply` 保存；超限整笔取消，不截断。方向键定位、Enter 绘制一格、Esc 取消。输入框内不会截获快捷键。
- 时间线每页最多32个缩略图，可直接跳转页；可新建、复制、重排、删除帧，修改20..2000ms时长。删除标签中的帧必须明确勾选移除引用；有锁层时禁止删帧。图层支持添加、隐藏、锁定、改名、排序和删除；调色板支持命名、改色与追加，透明槽固定。
- V拖选或填写选区范围；可水平/垂直镜像、顺时针旋转、移动或复制。越界默认拒绝；显式裁剪会提示移动可能丢弃目标外像素。历史面板可选明确修订，撤销追加恢复修订。
- 标签保存显式帧顺序与循环选项，可调整顺序。播放仅使用同一修订的帧缓存，按各帧时长播放；不写回播放状态。选区交给 Agent 时只授权父document，并携带frame/layer/rect/revision定位。

读取缓存严格绑定 document/revision/hash/palette；首次先读选中帧，再以最多两个并发只读请求加载剩余缩略图。活跃可见视图每秒检查 `documents.head`，绘制、写入或输入框编辑时不覆盖草稿。CAS冲突清除草稿并读取已提交状态，写请求从不自动重发。scope/Project/document/epoch变化及deactivate会取消请求、指针捕获、播放RAF、ResizeObserver、可见性监听和样式；旧结果不能导航或发起Agent引用。

读取状态绑定现有 AbortController：后台检查不能解锁另一个手动读取，结束、隐藏或
取消只释放自身持有的读取状态。手势的注册和身份切换清理在绘制前完成，避免首次
笔迹被稍后执行的 Effect 清掉；停用后不能开始新的指针或键盘绘制。

导出的固定修订成果通过公开 `dbfox.pixel.sprite.v1` 显示PNG预览，并下载单帧PNG或按标签顺序的Sprite Sheet。修改当前作品不会改变旧成果。下载使用正常浏览器/Electron下载流程，无文件路径输入、私有Filesystem或外部图像URL。

前端作者验证：

```powershell
cd desktop
npm.cmd test -- --maxWorkers=1 src/features/dlc/__tests__/dbfoxPixelFixture.test.ts
npm.cmd run typecheck:test
npm.cmd run lint
npm.cmd run build
```

30 项组件 fixture 通过。原有浏览器作者视觉检查使用受控 operation transport 与真实
Canvas，不能替代真实后端。本轮另使用签名包、SQLite 与可见 Electron，实际创建、
绘制、框选旋转、复制帧、刷新、播放并把引用交给真实模型；冷启动后具名标签恢复。
通过原生保存对话框下载 16×16 PNG 与 32×16 两帧 Sprite Sheet，并逐像素核对该
修订的两帧。此有限样本不能替代全部尺寸、标签顺序和多行 Sheet 的发布门禁。
模型本次仍依赖补充指令收尾，失败尝试与验证范围见质量记录。

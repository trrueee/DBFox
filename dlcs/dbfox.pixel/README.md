# Pixel Art Studio

> 文档类型：实现指南
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：`dbfox.pixel` 0.1.0 后端，Extension API v2

Pixel 提供可增量编辑的像素画与 Sprite 动画文档。当前后端已实现并通过作者验证；Canvas Workbench、独立 capability benchmark、持续创作 stress 与红队尚待完成，不能据此声明 DLC 已完成。

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

## 版本、预算与锁

每个文档有独立 version-fenced Resource，版本为规范十进制字符串；frame/layer/tag 是父文档对象。事务追加不可变修订、CAS head 和精确 receipt；相同 ID/输入返回原结果，不同输入重用 ID 拒绝。No-op 不追加内容修订，undo 将历史内容恢复为新修订，允许重复历史 hash。对象 ID 一经出生不能给新对象复用，undo 可以恢复原身份。删除为可恢复 tombstone，历史 Artifact 保留。

Canvas 每轴1..128；总像素槽≤262144，最多64帧、16层、256调色板槽、16标签。Canonical≤2MiB；一次操作≤128项、规范输入≤64KiB；owner历史逻辑配额128MiB。达到配额拒绝新增耐久行，不删除旧历史。槽0固定透明，其余颜色只接受不透明RGBA。锁层拒绝绘制与删除；删除任何帧须先解锁其各 cel。

Tool输出≤16KiB，目录工具每页≤8；Human目录每页≤32。Inspect/diff每页≤16项；极丰富diff若超过预算会明确要求缩小页面，不会截掉对象字段或丢失连续页位置。Context最多4×2000字符，不含像素。Inspect最多16×16像素仅进入本Run临时Provider窗口，耐久Observation facts保留ID、revision、目录、选择和计数。

## 导出与依赖

`documents.export` 必须经 Host ActionRun 调用 `pixel_export` 并完成正式 Artifact。返回 `{run_id,session_id,artifact_ids}`；同一 `mutation_id` 由 owner reservation/receipt 查重，开始Run前预留完整16KiB结果额度。如果上次结果未知，明确拒绝重放，不创建另一个 Run。Workbench 应在导出开始前捕获 scope，并用原 AbortSignal 调用 Host 可选 `openArtifact` 导航；当前后端不实现导航或下载路径。

`dbfox.pixel.revision` 保存有界 summary；`dbfox.pixel.sprite.v1` 从固定修订提供 `metadata`、最大32×32合成 `frame` RGBA、`sheet_layout` JSON，以及 `png`、`sheet` 的 `image/png` 字节流。Sheet按文档帧顺序或tag显式顺序横向拼接。所有读核对文档/Project/revision/hash与Artifact provenance，拒绝路径、URL或任意编码器参数。

PNG由原样 vendored PyPNG 0.20220715.0 Writer 编码，见 [许可证](backend/vendor/LICENCE) 和 [provenance](backend/vendor/provenance.json)。它只有标准库依赖；产品不使用Pillow。`.gitattributes` 保持 upstream bytes 在 Windows checkout 后不变。Reader/CLI不暴露给产品输入，不安装共享依赖、不需要本地二进制或网络服务。

## 验证和打包

仓库根运行：

```powershell
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_pixel_dlc.py -q --tb=short
```

签名激活与真实RunLoop作者测试在临时目录放置明确的 frontend stub，用于隔离 Backend；产品目录没有伪工作台。正式分发必须等 Workbench 实现后，用仓库 `build_dlc_package_from_source`/DLC CLI 打包真实前后端并重新验证。不要将临时测试包或 SQLite 数据提交。

# Voxel World Studio

状态：草案。Backend 与 Workbench 在同一 `VoxelWorld` 上工作；本文件是当前 API 合同，验证证据另见 `docs/quality/voxel-dlc-evidence.md`。

## Canonical 与权限

`dbfox.voxel.library` 的 id 是 Project id，版本为 1；每个 `dbfox.voxel.world` 的 id 是 `world_<uuid>`，版本为正整数。Layers、palette slots、regions 是 world 内对象。Host 对每个新 ToolInvocation 从当前 Project descriptor 绑定资源版本；同一 Run 可以 create → edit → inspect → edit。每次新修改仍要求 frozen version、input expected_version、当前 head 相同。历史 resolver 保留被删除的 immutable revision，以便 reconcile 原收据。

尺寸每轴 1..256；16³ uint8 chunk；offset 为 `x + 16*z + 256*y`。0 永久为空，palette 0 为 `Air/#000000`；非零 palette 为不透明 RGB。Bounds 是 `{"min":[x,y,z],"max":[x,y,z]}` 半开区间，越界拒绝而不裁剪。最多16 layers、128 named regions、256 palette slots、64KiB metadata、128 active worlds/Project、8192 live nonempty chunks/world；单次几何操作最多2,097,152候选格点。Owner 历史预算128MiB，超限拒绝新写入，保留读取与已有历史；不自动清理旧Artifact。

Layers 数组从底到顶，最上层非零值覆盖下层；visibility、camera、selection、slice、active brush/layer 是 UI view state。`locked` 是 durable 编辑限制。Metadata 是 `{description:string,tags:string[]}`。WorldDocument 是 `{schema_version:1,size,title,status,palette,layers,regions,metadata}`，其中 layer 为 `{id,name,locked}`，palette 为 `{index,name,color}`，region 为 `{id,name,bounds}`。

## Typed project operations

调用 `host.operations.invoke("worlds.get", input, {projectId})`，具体调用签名遵循 SDK。所有输入拒绝未知字段、非整数坐标。所有 human mutations 提供唯一 `mutation_id`；同ID同payload返回原收据，同ID不同payload拒绝。create 的 `expected_version` 固定为0，其余写入必填当前正整数版本。客户端断线后先读取head，不自动重放。

| Operation | Input | Output |
| --- | --- | --- |
| `worlds.list` | `{include_deleted?:false,limit?:32,after?:null}` | `{worlds:WorldSummary[],next_after}` |
| `worlds.create` | `{title,size?:[64,64,64],expected_version?:0,mutation_id}` | `MutationOutput` |
| `worlds.get` | `{world_id,version?:null}` | `WorldSummary + {document:WorldDocument}` |
| `worlds.apply` | `{world_id,expected_version,mutation_id,operation}` | `MutationOutput` |
| `worlds.configure` | `{world_id,expected_version,mutation_id,operation}` | `MutationOutput` |
| `worlds.undo` | `{world_id,expected_version,mutation_id,target_version}` | `MutationOutput` |
| `worlds.delete` | `{world_id,expected_version,mutation_id}` | `MutationOutput` |
| `worlds.revisions` | `{world_id,before_version?:null,limit?:32}` | `{world_id,revisions,next_before_version}` |
| `worlds.diff` | `{world_id,from_version,to_version,limit?:32,after?:null}` | `{world_id,from_version,to_version,metadata_changed,changed_chunk_count,chunks,next_after,truncated}` |
| `worlds.chunks` | `{world_id,version,limit?:16,after?:null,since_version?:null}` | `{world_id,version,since_version,chunks,next_after,metadata_changed}` |
| `worlds.snapshot` | `{world_id,version?:null,mutation_id}` | `{run_id,session_id,artifact_ids}` |

`WorldSummary` 包括 `world_id,project_id,version,parent_version,title,status,size,content_hash,chunk_count,nonzero_count,layer_count,palette_count,region_count`。`MutationOutput` 增加 `changed,changed_chunk_count,changed_voxel_count,operation_kind`。No-op 的 `changed=false` 且 version 不变；undo 恢复 target 的内容为新的递增revision，支持undo-of-undo。`worlds.snapshot` 是显式 Host action Run；普通绘制、编辑直接使用project operation。

Chunk page 每项为 `{layer_id,coord:[cx,cy,cz],hash,values:number[4096]|null}`，null表示已清空。页面至多16 chunks，按返回的opaque `next_after`翻页，必须保持目标version和since_version不变。初次请求所有当前非空chunks；since_version请求差异，包含空墓碑。编辑后先刷新WorldSummary/document，再从旧version到新version取delta；不要每笔全世界刷新。Layer删除和palette更新会令metadata_changed为true。

## Geometry operation payloads

`operation.kind` 为下表之一，`layer_id` 始终是写入目标。Copy、mirror、boolean、extrude 的 source_layer_id 必填，且来自同一world，源读取总是操作开始时的snapshot。写锁定层拒绝；读取锁定层允许。

| kind | 其余参数与行为 |
| --- | --- |
| `fill` | `layer_id,bounds,palette_index`；写0可擦除 |
| `box` | `layer_id,bounds,palette_index,hollow?:false,thickness?:1,clear_inside?:false`；默认保留空心内部原内容 |
| `sphere` | `layer_id,center:[x,y,z],radius,palette_index,hollow?:false,thickness?:1,clear_inside?:false`；整数中心、平方距离<=radius² |
| `extrude` | `layer_id,source_layer_id,bounds,axis:"x"|"y"|"z",depth,direction?:1`；direction为±1，source在axis轴必须一格厚，延展额外depth层非air内容 |
| `replace` | `layer_id,bounds,from_index,to_index` |
| `copy_region` | `layer_id,source_layer_id,bounds,destination:[x,y,z],mode?:"replace"`；replace连air复制，over跳过air |
| `mirror` | copy_region参数加 `axis`；对source局部坐标反射后复制，destination等于bounds.min即原位镜像 |
| `boolean` | `layer_id,source_layer_id,bounds,mode:"union"|"intersection"|"difference"|"xor"`；union优先target颜色，intersection保留target颜色，difference清除source占用位置 |

Configure payloads：`{kind:"rename",title}`、`{kind:"palette_put",entry}`、`{kind:"palette_remove",index}`、`{kind:"layer_put",layer}`、`{kind:"layer_remove",layer_id}`、`{kind:"layer_order",layer_ids}`、`{kind:"region_put",region}`、`{kind:"region_remove",region_id}`、`{kind:"metadata_set",metadata}`。layer_put更新已有layer或添加新layer；layer_order必须恰好列出当前所有layer一次。仍被当前chunk使用的palette不能删除。删除非空layer是明确的可撤销修改；locked layer必须先解锁。

## Agent Tools、Artifact 与 Composition

Tools：`voxel_create`、`voxel_inspect`、`voxel_fill`、`voxel_box`、`voxel_sphere`、`voxel_extrude`、`voxel_replace`、`voxel_copy_region`、`voxel_mirror`、`voxel_boolean`、`voxel_configure`、`voxel_undo`、`voxel_delete`、`voxel_export`、`voxel_diff`。Geometry Tool输入是 `{world_id,expected_version,operation:<对应payload>}`，省略human mutation_id；configure/undo/create输入同operation去掉mutation_id。Inspect输入 `{world_id,version?,bounds?,layer_id?,object_offset?:0,object_limit?:16}`，只返回有界摘要与对象页，不把chunks塞入context。Export输入 `{world_id,version?}`。

修改与export输出immutable `dbfox.voxel.snapshot` Artifact，payload为WorldSummary，不含cells。JSON Representation `dbfox.voxel.world.v1`：`manifest`参数 `{}`，`chunks`参数 `{limit?:16,after?:null,since_version?:null}`；world/version来自Artifact且不可覆盖。其他DLC经公开 `context.read_artifact_representation` 消费，不能导入本DLC内部代码、读私有SQLite或声明本owner之外的required_resources。

## 生命周期与持久化

SQLite保存world身份/head、append-only world_revisions、append-only chunk_versions及exact operation_receipts。Metadata没有第二份可写副本；hash不唯一。几何改动、CAS head和receipt在一个事务提交。Reconcile只读原收据，不重放动作。取消在计算期间和提交前检查；提交后未知结果从receipt恢复。损坏chunk、解压超长、非法palette、未知数据库schema均fail closed。

禁用由Host移除active contributions；Workbench卸载需释放Three.js controls/mesh/material/renderer、监听与RAF。历史durable data保留。Host当前没有Project删除hook，Project删除后owner状态保留；不宣称自动清理。Uninstall默认保留owner数据。

128MiB历史配额计算编码metadata、chunk payload、receipt及每条记录的开销预算，不代表SQLite索引和WAL的瞬时文件大小上限。没有静默历史回收；历史查询通过chunk坐标/版本索引读取，长期大量小修订的延迟仍需在真实使用中观察。

## 后端验证

2026-09-05，Windows x64：当前47项后端与14项能力bench联合通过（61项，39.45秒），没有排除或xfail。共享Host Artifact权限修复 `76091eef` 合入后，原先失败的同Run增量用例通过；包含真实Host action Run保存Artifact、完整签名源码包启用/禁用/重新启用、八种几何操作、逐Invocation版本绑定、并发CAS、原收据reconcile、事务中断、损坏chunk、百万体素与context分页预算。历史失败与修复后的完整命令见[验证记录](../../docs/quality/voxel-dlc-evidence.md)。

```powershell
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_voxel_dlc.py -q --tb=short
D:/Project/DBFox/.venv/Scripts/python.exe -m pyflakes dlcs/dbfox.voxel/backend verification/tests/system/test_voxel_dlc.py
D:/Project/DBFox/.venv/Scripts/python.exe -m mypy --no-warn-unused-configs --follow-imports=skip --no-incremental dlcs/dbfox.voxel/backend
```

Mypy与pyflakes通过。Director编写的14项生产RunLoop能力bench已通过，包含128³世界和64³狐狸神社十类持续修改；仍需独立验证员复核bench评分及真实桌面流程。上述证据不代替最终独立对抗审查。

## 查看和保存固定快照

三维视口点击方块会把选区缩到该格，并切到对应切片；拖动旋转，切片与选区工具继续通过正式 CAS 修改。选择和隐藏图层均为显示状态。

保存快照后，成果工作台显示导出时的固定版本与全部可见图层；内联卡片可打开同一个成果。读取通过 Host Artifact Representation 的 `manifest/chunks`，不跟随当前世界 head。世界继续修改或被删除，不改变已保存的历史成果。

“下载世界快照 JSON”包含 `schema_version:1`、`representation_type:"dbfox.voxel.world.v1"`、`artifact_id`、`manifest` 和完整 `chunks` 数组，每块为 `{layer_id,coord,hash,values}`。它是公开表示的离线文件，隐藏图层也会保存；文件不包含私有路径或数据库。面板卸载或DLC停用会取消在途读取并释放GPU与下载URL。当前不提供此文件的导入操作。

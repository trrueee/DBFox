# Scene DLC 领域合同

> 文档类型：架构说明
>
> 状态：已接受
>
> 最后核验：2026-09-05
>
> 适用范围：`dbfox.scene`；实现状态由本 DLC 的 `program-status.json` 记录

`dbfox.scene` 在公开 Extension API v2 内提供本地 3D 创作能力。本文冻结领域边界；后端、Workbench与独立验证已实施，当前进行单独的对抗审查及修复。全部门禁完成前不标记集成。

## 模型与所有权

唯一 canonical durable model 是 `SceneDocument { schema_version:1, title, settings, geometries, materials, objects }`。DLC SQLite 保存项目归属、当前版本、不可变版本、操作与回执；Three scene graph、glTF、GLB 都是单向生成的派生形式。

- Resource：一个 `dbfox.scene.document` 对应一个 Scene；一个 `dbfox.scene.library` 对应一个 Project 的创建能力。library 的 ID 是 Project ID，版本为 `1`。
- Object：geometry、material、mesh/group/light/camera 节点。内部 ID 不是 Resource，不扩大 authority。
- Selection：前端选中 ID 集合；通过 `onAsk` 的 `authority + object + locator` 形成引用，不能直接产生执行授权。
- View state：Orbit 相机、hover、选中项、gizmo 模式、面板与树展开状态、临时拖动预览。它们不进入耐久场景。
- Artifact：`dbfox.scene.revision` 保存 scene/project/version/hash、计数和有界摘要，不能复制整份场景。
- Representation：`dbfox.scene.document.v1` 从 Artifact 固定版本读取，提供分页对象/材质/geometry catalog 与 glTF/GLB 导出流。

几何模型为稳定 `Geometry { id, primitive }`，primitive 限定 Three.js 的固定低细分 `box/sphere/cylinder/cone/plane/torus`。不接受路径、URL、代码、shader 或不受控的顶点数组。尺寸统一通过 Object scale 表达。

`Material { id, name, base_color:[r,g,b,a], metallic, roughness, double_sided }` 使用线性 RGB；所有数值有限有界。`Object { id, name, kind, parent_id, position, rotation, scale, visible, ...kind_fields }` 的 kind 是 mesh/group/light/camera。mesh 引用 geometry/material ID；light 与 camera 的参数属于同一节点，不复制 transform。light 首版为 point/directional/spot；camera 为 perspective，`yfov` 使用弧度，`znear > 0` 且 `zfar > znear`。viewport 的环境补光是 view helper。

坐标系：右手、Y 向上、米制；rotation 是 Euler XYZ 弧度，transform 相对于 parent。scale 必须正且有限。Three plane 位于 XY、圆柱与圆锥沿 Y。所有 ID 在 Scene 内稳定；引用必须存在，parent hierarchy 无环且深度不超过 64；删除父节点必须显式指定 subtree 行为。

所有整数、实数和布尔scalar严格校验，坐标不接受bool或数字字符串；schema_version必须是严格整数1。JSON数组仍可按正式JSON合同读为内部tuple，不通过全模型strict破坏这一边界。规范文档解析前检查8MiB预算；SQLite读取统一验证document/hash与title、对象/材质计数相符，版本/head/status及直接parent关系有效。派生摘要列不能成为独立事实来源，损坏时明确失败且不改写原记录。

## 操作、冲突与恢复

领域工具包括 scene_create、scene_inspect、object_create、object_duplicate、object_transform、object_reparent、object_delete、object_update、material_create、material_update、material_assign、light_create、light_update、camera_create、camera_update、scene_settings_update、scene_undo、scene_diff、scene_export。不提供 document replace。批量 operation 最多选择/创建 500 个对象，一次接受的批量操作形成一个 revision；transform 使用明确的绝对 local TRS，不猜测模糊选择或隐式重基。

所有修改携带 `scene_id, expected_version`；Tool 同时验证冻结 `ref.version`。Workbench typed project operations 与 Agent tools 调用同一领域 store，不建立另一份文档或业务规则；显式生成 Artifact 的操作调用 `context.require_action_runs()`。此分工复用已有 project-scoped operation seam，无需拖动鼠标时产生新 Conversation。

SQLite 使用标准库事务与 CAS：

`BEGIN IMMEDIATE → receipt → active/expected/frozen/head fence → apply/validate → append revision → CAS head → receipt → COMMIT`

表包含 `scenes`、`scene_revisions`、`operation_receipts`。receipt 绑定 invocation ID、owner、project/scene、operation/input hash 和确切结果 revision。同 invocation 不同输入必须拒绝；不能查当前 head 冒充原结果。`content_hash` 不设唯一约束。Undo 在当前 head 上追加恢复指定历史内容的新版本；重复历史内容合法。no-op 返回 changed=false，不递增版本。

Resolver 解析 frozen version 指定的历史不可变 revision，不强制该版本仍为 head。因为 Host 的 handler 在 execute 和 reconcile 前都先 resolve，强制 current head 会阻断“领域事务已提交，Core 尚未结算”的恢复。正常执行由领域事务检查 live head；reconcile 只读精确 receipt。Soft delete 保留历史供恢复，不重新授权普通修改。

取消在计算前与提交前检查；提交后 receipt 是已发生事实。write 使用 `retryable=false,recovery=reconcile`；inspect/diff/immutable Representation 可安全重试。崩溃时 SQLite 保证 revision/head/receipt 一致，不自动重放不确定写入。

## 有界读取与导出

- 最多 10,000 个节点、1,000 个材质；canonical JSON 最多 8 MiB；任何批量操作最多 500 个对象。
- context 只放 scene/version/title/counts、有限对象摘要、diff 与分页提示，总量不超过 4,000 字符；不放顶点、二进制、全量场景、历史或 frontend state。
- inspect/diff/Representation page 最多 100 项；Tool 输出只含计数、有界 ID 与 truncated 标记。
- 前端读取必须绑定 revision，不能将不同 head 的分页结果拼成一个 Scene。direct edit 始终提交它实际显示的版本；冲突刷新后重新决定。
- glTF/GLB 由 immutable revision 导出；共享 primitive buffer，禁止外链；响应前核验不超过 32 MiB。GLB 用二进制 stream，不经 operation base64。

## 生命周期与当前 SDK 限制

Host snapshot 撤销 backend/frontend contributions；frontend disposer 必须释放 RAF、WebGL、Orbit/TransformControls、observer 和 listener。DLC SQLite 保留，reactivate 从其耐久版本恢复。

当前公开 SDK 没有 Project deletion hook，Project API 也未提供删除路由。自动清理 DLC 私有数据无法接入现有公开合同，必须作为明确平台缺口报告，不能私读 Core DB 或伪造清理证明。Scene 提供自己的作品删除；未来 Project 删除能力成立后再接正式 lifecycle seam。

本地可撤销编辑无需额外 approval；首版不支持外部发布、网络素材、任意文件系统写入。Core、共享 SDK、共享锁文件均不添加 Scene 类型或分支。

## 调查与复用决定

已阅读贡献合同、SDK、Music/Story/Visualization/Workspace/GitHub 实现、Music DirectBench、相关历史提交与质量规范。沿用公开 API、Pydantic、sqlite3、Host React 与 Host Tree；不复制 Music 的 content-hash 唯一索引，也不复制其强制 head resolver 恢复缺口。Workbench 使用官方 Three.js OrbitControls/TransformControls，DLC-local package 与 lock 固定 `three 0.185.1`、构建工具 `esbuild 0.28.2`，两者 MIT；不改 desktop node_modules 或根锁文件。

Three 官方 primitive 在离线 build 时生成固定 geometry buffers；后端标准库仅承担 canonical Scene 到 glTF 2.0 节点/材质/容器的单向格式边界，不自研 tessellation。完整 Three GLTFExporter 已调查；目前后端没有 JavaScript Runtime seam，首版只实现已冻结的格式子集。增加纹理/动画/骨骼前重新评估完整成熟 exporter，不持续扩张自定义格式引擎。

官方资料：[TransformControls](https://threejs.org/docs/pages/TransformControls.html)、[GLTFExporter](https://threejs.org/docs/pages/GLTFExporter.html)、[资源清理](https://threejs.org/manual/en/cleanup.html)、[glTF 2.0](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html)。2026-09-05 从官方 npm registry 执行 audit，固定依赖报告 0 vulnerabilities；这不等于无未知漏洞。首次镜像 registry 不支持 audit，随后显式查询官方 registry。

## 待执行验收

由实际 Backend、Workbench、Verification、Adversarial Reviewer 专员接续完成实现。覆盖同内容 undo、两连接 CAS、receipt 精确匹配、提交后崩溃恢复、stale resolver reconcile、父子删除、cycle、非有限数、规模上限、历史 Artifact 固定版本、所有 primitive 导出与 Khronos validator。

CapabilityBench 复用 `verification/bench/framework/schema.py` 与 production Tool path，拥有独立 cases/schema/runtime/scorer；Director 注册共享 catalog。至少覆盖模板 12 个案例和狐狸神殿连续 10 次修改，检测局部请求引发全场景重建的行为。Frontend 必须验证真实 Three viewport、selection、direct manipulation、状态同步和 cleanup；不能用 JSON viewer 代替。

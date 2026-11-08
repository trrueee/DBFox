# Scene Studio

> 文档类型：使用与实现说明
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：`dbfox.scene` 1.0.0 源码；完整产品验收仍以独立验证证据为准

Scene Studio 提供本地三维场景编辑。用户检查器、鼠标变换和 Agent 工具都修改同一个版本化 SceneDocument。场景库、对象、材质与版本保存在 DLC 自有 SQLite；Three 场景图只负责显示。

## 使用工作台

在项目资源连接器中打开 **Scene Studio**，输入名称创建场景，或从场景列表打开已有作品。添加菜单支持立方体、球、圆柱、圆锥、平面、圆环、组、点光源、平行光、聚光灯和透视相机。选择组时，新对象添加到该组内。

- 左侧采用 Host Tree。点击树项或视口对象选择；复制和删除明确作用于整个子树。
- 视口拖动旋转，右键平移，滚轮缩放，`F` 聚焦。`W/E/R` 切换移动、旋转和缩放；可选择局部或世界坐标。按 `Esc` 取消当前拖动。`Ctrl/Cmd+D` 复制，`Delete` 删除子树，`Ctrl/Cmd+Z` 恢复上一版本。这些快捷键只在视口获得焦点时生效。
- 检查器编辑名称、可见性、局部位置/旋转/缩放、父级、材质分配和材质参数、灯光参数、相机参数。一个区块有未保存输入时，其他编辑动作锁定；保存或取消后继续。材质修改影响所有引用该材质的网格。
- 坐标为右手系、Y 向上、米制；旋转为 Euler XYZ 弧度，缩放必须正。更换父级保留局部变换，因此世界位置可能变化。颜色输入为线性 RGB/RGBA。
- 视角菜单可查看作品中的透视相机；聚焦会回到编辑视角。视口补光、网格、相机线框和选择框仅为辅助显示，不导出到作品。
- **引用到 Agent** 发送正式 `authority + object + locator`，包含实际显示版本。引用对象不会扩大场景资源权限。

## 保存、冲突与导出

场景分页首次读取当前版本，后续对象、材质、geometry 页固定该版本。每次写入携带实际显示的 `expected_version` 和一次生成的 `request_id`；UI 禁止重入，不自动重放失败或结果不确定的修改。后台在工作台可见且没有未结束拖动时每 5 秒检查新版本，干净状态自动同步；有草稿时保留输入并显示新版本提示。**放弃草稿并刷新** 才替换输入。

鼠标变换仅在视口中预览，完成一段拖动后提交一次绝对局部 TRS；失败回到最后显示的 canonical 变换。撤销通过 `scenes.undo` 创建新的恢复版本，历史版本不会被覆盖。

**导出工件** 通过正式 ActionRun 创建不可变版本 Artifact。Scene Artifact 视图使用 Host `representations.stream` 提供 GLB/glTF 下载；可从工件重新打开当前场景编辑。导出保留作品几何、层级、材质、光源和相机，隐藏对象不导出。

工作台使用 API v2 的可选 `host.workbench.openArtifact` 打开新工件。导出等待前捕获工作区作用域，同一取消信号贯穿 ActionRun 请求与导航；卸载、切换作用域或停用后不能打开晚到的结果。缺少该能力的旧 Host 显示升级提示并停止导出。正式导航合同与通用校验见[Host 合同](../../docs/architecture/dlc-artifact-navigation.md)；真实浏览器的完整导航下载验收仍待完成。

Agent 工具显式提供有界 Observation，包含场景 ID、版本和局部修改结果。`scene_inspect` 与 `scene_diff` 保留完整条目，并返回 `returned`、`next_offset`、`has_more`、`observation_truncated`。模型必须按 `next_offset` 继续读取；较大内容受 24 KB 事实预算限制，不能假设每页实际返回请求的 `limit` 条。

## 实现与复用

- [领域合同](../../docs/architecture/scene-dlc.md)与 `backend/contracts.py` 是 canonical schema 和操作语义的权威说明。
- `frontend/index.js`：Host 连接器、Dock、Tree、检查器、编辑锁、同步、引用和 Artifact renderer。
- `frontend/model.js`：固定版本分页与只读层级投影，不保存第二份耐久状态。
- `frontend/viewport.js`：官方 Three 派生图。稳定 ID 保留 Object3D、mesh 和共享 geometry；局部编辑原地更新材质/参数，消失对象和资源才释放。
- `frontend/index.css`：DLC 命名空间样式与 Host 设计令牌；不注入 inline style 标签。
- 官方 `three@0.185.1`、OrbitControls、TransformControls 及固定 primitive 来源见 `frontend/vendor/provenance.json`。前后端采用同一官方 primitive 定义，避免自行实现 tessellation。Workbench 不增加共享依赖或兼容层。

官方参考：[变换控件](https://threejs.org/docs/pages/TransformControls.html)、[OrbitControls](https://threejs.org/docs/pages/OrbitControls.html)、[Three 资源清理](https://threejs.org/manual/en/cleanup.html)。DLC deactivate、视口离开可见区域或卸载时释放 listener、observer、RAF、controls、geometry、material、renderer；后台读取和下载同时取消，Blob URL 撤销。

## 验证

在 `desktop/` 运行：

```powershell
npm.cmd test -- src/features/dlc/__tests__/dbfoxSceneFixture.test.ts --maxWorkers=1
npm.cmd run typecheck:test
npx.cmd eslint src/features/dlc/__tests__/dbfoxSceneFixture.test.ts
node scripts/check-design-contracts.mjs
```

Fixture 覆盖真实 Host Tree/SDK 注册和表单、revision 分页、CAS、冲突、重入、外部同步、清空灯光范围、Artifact 流与 cleanup。Three 测试使用官方对象/矩阵/控件，并只替换 WebGLRenderer，验证父子坐标、保留实例和 GPU 资源释放；它不能替代真实浏览器的 WebGL 绘制、拖动和 CSP 验收。生产 Tool path、独立浏览器 QA、规模压力与对抗评审由 Program 验证角色提供证据。

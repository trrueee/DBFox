# Scene DLC 验证证据

> 文档类型：质量证据
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：`creative/scene` 工作区中的新增 `dbfox.scene`

当前未达到集成门禁。后端和 Workbench 已实现；独立 RunLoop 验证发现的观察投影与 Artifact 结算问题已修复，详见[独立验证](scene-dlc-independent-verification.md)。正式创作、真实 Electron 编辑与导出均有独立证据。红队又发现 Core 结构化上下文绕过工件可用性证明，修复已集成并在独立复验中；最终红队尚未完成。

## 已执行

- 独立 Domain Architect 完成模型、版本与恢复边界审议；见[领域合同](../architecture/scene-dlc.md)。
- `npm run build`（`dlcs/dbfox.scene`）：固定 Three 0.185.1、esbuild 0.28.2，生成离线 ESM
  vendor 772,431 bytes 与六种官方 primitive 数据 120,012 bytes。来源、MIT 许可证、SHA-256
  记录于包内 `frontend/vendor/provenance.json` 和 `frontend/vendor/licenses/three-MIT.txt`。
- Windows 本地 Chrome + Playwright CLI 0.1.19 加载相同 vendor bytes；HTTP 返回与生产相同的
  CSP 指令（`script-src 'self' dlc-asset:`，不添加 eval/WASM 权限）。真实 WebGL 2 创建成功，
  OrbitControls 与 TransformControls 初始化成功，渲染 14 个 draw calls，中心像素读取为
  `[64,127,64,255]`。控制台仅缺少探针 favicon 的 404；没有 shader、模块或 CSP 错误。
  探针与浏览器已关闭，临时文件位于仓库外，不参与产品打包。
- Backend Engineer 执行 `python -m pytest verification/tests/system/test_scene_dlc.py -q --tb=short`：
  28 passed in 10.81s。覆盖 10,000 对象增量创建与分页、CAS 竞争、历史版本、同内容撤销、
  取消与回执恢复；Pyflakes 与 Mypy（6 个源码文件）通过。这些是实现者的测试，不能替代独立审查。
  签名激活测试使用隔离 frontend stub，不能证明实际工作台加载成功。
- Director 对真实 `export_scene` 输出的四份文件执行官方 Khronos `gltf-validator 2.0.0-dev.3.10`：
  六种 primitive、材质、非均匀父级 TRS、三种灯光和相机的 glTF（68,598 bytes）/GLB（52,964 bytes），
  以及空场景 glTF（303 bytes）/GLB（324 bytes），均为 0 errors、0 warnings、0 infos。
  `dlcs/dbfox.scene/validate-gltf.mjs` 提供固定版本的可重复校验入口，拒绝外部资源和超过 32 MiB 的文件。
  构造用文件位于仓库外；这是导出器组件验证，不是正式创作压力任务。

底层探针只证明当前机器上的 vendor/CSP/WebGL 兼容性。它不证明 Electron `dlc-asset` 激活路径、
完整 Scene Workbench、键盘/拖动/CAS、人机同步或停用清理已经通过。

## 独立验证与后续门禁

Director 修复后重新执行后端作者集合：30 passed in 10.68s，新增检查创建/修改/导出身份版本、失败无成功事实、完整 Unicode 条目的预算分页续读；6 个源码文件 Mypy/Pyflakes 通过。观察结果使用现有 SDK `ToolObservationProjection`，未改 Core 默认投影。

接入独立 Host 导航提交后，Scene Workbench fixture 为 11 passed in 4.09s，测试类型检查通过。新增旧 Host 明确拒绝、导出与导航共用 scope/signal、卸载取消并拒绝晚到导航。随后真实Electron发现同ESM重复register会遗留CSS link；Director在DLC register中先移除自身旧link，新增真DOM重注册与deactivate清理回归后为12 passed in 4.82s，类型检查通过。通用Host又修复迟到注册与Action Run页签可见性，44项导航回归和全量516项通过。这些fixture控制网络/图形边界，不能算真实Electron全流程证据。

独立真实签名包/Electron已验证WebGL2、真实指针拖动和检查器局部修改；10,000对象折叠树
的Host修复已复测为1个treeitem、414个总DOM元素，展开22个虚拟行且尾部可达。完整读取仍
需102页、19.60秒。随后独立 Verification Engineer 完成正式 RunLoop 与故障集合 **22 passed**、
统一 CapabilityBench **13/13**，狐狸神殿十类持续修改与正式 Artifact glTF/GLB 官方校验通过。
真实 Electron 导出导航、Representation 流、DownloadItem 落盘及哈希校验、scope 晚到取消、
停用/恢复均通过。下载测试控制官方原生保存路径边界，没有自动化保存对话框点击；独立红队仍未完成。
具体状态由 `dlcs/dbfox.scene/program-status.json` 维护；最终由 Director 决定集成。

独立 Verification Engineer 的正式 RunLoop、故障注入与五项缺陷复验由[独立验证记录](scene-dlc-independent-verification.md)维护。该记录区分作者验证、确定性运行机制、真实浏览器边界与尚未执行的红队终审。

## 对抗审查期间的权威边界修复

独立Reviewer首批21项攻击为11失败/10通过，确认三组P2：schema_version的Literal接受true/1.0；嵌套可见性/坐标接受字符串、数值布尔；SQLite摘要列可与规范document不一致。Director修复现有contracts和store，不修改独立测试：用严格scalar约束保留合法JSON数组合同，在唯一row→Revision读取处核验文档预算、规范hash、派生摘要及版本/head/parent/status。目录结果也经过相同读取校验；未新增依赖、迁移、Core接口或另一份可写模型。

首次作者30项与独立攻击21项联合为51 passed，43.76秒；随后进一步收紧integer输出/Artifact字段并执行完整作者+RunLoop+故障回归。实际Workbench fixture12项通过（25.07秒），后端pyflakes和mypy6文件通过。最终独立复验与Artifact权限攻击仍由Reviewer进行，不据Director回归关闭终审。

补充 head/parent 一致性修复后，作者后端集合为 **34 passed，12.11 秒**；独立红队当时的32个领域攻击全部通过（58.14秒），包括缺失/回退head、缺失/跳级parent、目录摘要篡改、进程硬退出回滚与提交前取消。共享上下文修复见 [Artifact 可用性验证](artifact-context-availability-verification.md)，不放宽跨Run或跨Session消费。

生成的Three bundle与primitive数据通过本DLC `.gitattributes` 保持跨Windows检出字节不变；工作树实测仍分别为772431/120012 bytes，SHA-256与既有provenance吻合。保留上游GLSL字符串中的空白，不为补丁空白检查改写已固定哈希的第三方代码。

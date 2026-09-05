# Voxel 独立验证

> 文档类型：质量证据
>
> 状态：当前
>
> 最后核验：2026-09-05

本阶段由未参与 Voxel 产品实现的独立 Verification Engineer 执行。Director 编写的 14 案例 suite 是被审对象；新增故障断言、评分身份检查、真实 Electron 操作、证据及本报告由独立验证员负责。产品缺陷均交 Director 修复，没有在验证侧重写产品或放宽权威合同。本报告不代表后续 Adversarial Reviewer 已通过，也不代表集成发布批准。

主体桌面验收针对产品 `e587edd62cff1f9c647c45d42152d93e0dafe277`，实际加载签名包 digest `ee6365217774f9fe4fefc8f9ba942aabde904dff765b7bc65db2ed0395df5f5b`。最后检查发现的键盘监听器和样式合同缺陷由 Director 修复为 `e6267551ae0d8f0ed66764c8422638fc0ddf77ee`，独立冷重签包 `50b8e47c15254435af8bc616216eae7e467bd5687c1b63aa2d8bfb36579e91b1` 已通过真实 Control-held 卸载、大世界与新样式窄布局复验。

## 权威边界与评分审查

复用项目既有签名安装、迁移、Runtime snapshot、工具注册、原生 Responses function calling、生产 RunLoop、公开 world operation 与 Artifact Representation。没有新通用执行器、镜像世界数据库、领域几何 oracle 或第三方验证依赖。只有模型 Responses 事件使用脚本；执行、幂等、Invocation、Observation、Artifact、世界版本、签名加载和实际桌面均为产品路径。浏览器使用真实 Main、Preload、EngineSupervisor、React Host、侧车和 DLC；Vite 提供开发 renderer，并非打包安装程序验收。

独立审查确认模型的 world/version 来自用户所选身份和真正交付的观察；Human operation 的结果只进入验证证据，下一段 Agent 必须重新 inspect。几何期望来自 case 的明确坐标、数量、图层和区域条件，scorer 只用公开读取检查结果与局部性。新增检查要求 Observation 集合与持久记录完全相等，Invocation/Artifact 身份唯一，Artifact 的 producer 必须是同 Run/Session 的成功 Invocation，工具名、refs、观察所含 Artifact 及 provenance 对得上。没有清空 refs、拆开普通连续修改 Run 或变更用例答案来规避失败。领域 CLI 原先导入不存在的根 conftest，改为正式 verification conftest 后可独立运行。

强化后的 [14 案例独立报告](../../verification/bench/capabilities/dbfox_voxel/evidence/independent/report.md) 全部通过：最高 context 1,573 字符、观察 1,942 字节。狐狸神社用 44 次工具调用、46 个 Turn，最终 64³、v38、23,386 个 layer cells、60 chunks、4 层、8 个调色板项、3 个 region。[独立导出](../../verification/bench/capabilities/dbfox_voxel/evidence/independent/export-evidence.json) 从固定 Artifact 的正式表示产生。脚本化策略不能证明真实 LLM 的自主审美、创意规划或自然语言理解。

## 独立发现与修复

| 问题 | 原始证据与边界 | 修复与复验 |
| --- | --- | --- |
| 缺少 Host `openArtifact` 时仍先保存快照 | 原作者 fixture 允许一次 snapshot；独立断言零写入失败 | Director 在 ActionRun 前检查导航能力；保持独立零请求断言 |
| Receipt 合法 JSON 篡改可伪装成功 | 首轮 malformed 拒绝，但 world/project/version/hash/count 五个合法变形被接受；进一步 changed_voxel_count 变形也失败 | Director 核对请求/receipt 列、固定 revision 的完整 summary 与 base/result 实际块字节差。独立 15 种结果及 4 种列变形拒绝且四表不变 |
| 缺少 3D picking 与历史工作台/下载 | 实际 Electron 只能看当前世界，旧 Artifact 仅摘要 | Director 补齐 Raycaster instance picking、固定 manifest/chunks 只读视图和真实 DownloadItem；下面为实际复验 |
| 原生键盘监听器未清理 | 实际 CDP 在 detached canvas 仍见 keydown；独立普通卸载和 Control-held 两分支失败，后者还留下 document.keyup | Director 先挂载再连接、layout effect 先释放后卸载；固定 Three 源的断连遗漏用可重建小补丁处理；独立原断言保留 |
| 样式违反设计合同 | 命名空间、px 字号、650 字重、`!important`、未注册 CSS 变量及应用硬编码色 | Director 在产品 CSS 修复，不改检查器 |

[发现记录](../../verification/bench/capabilities/dbfox_voxel/evidence/independent-found-defects.json) 保留原失败和一次验证断言纠正：owner `ToolReconcileResult.status=not_applied` 经正式 Runtime 映射为公开 `ToolResult(status=failed, error_code=TOOL_RECONCILIATION_NOT_APPLIED)`。before-commit timeout/cancel 原测试错误地期待公开 not_applied，核对权威合同后纠正；这两例不是产品缺陷。

补丁复用既有 Three/OrbitControls；本地版本 disconnect 没释放按下 Control 动态注册的 keyup。产品构建脚本验证 `three@0.185.1` 原 tarball SHA-512，只允许匹配一次的源替换，保留原/补丁源 SHA-256、产物 hash、MIT 许可、owner 与上游修复后的移除条件。没有运行时调用私有控件方法的包装层。此补丁仍是明确需要升级清理的维护项。

## 实际 Electron 证据

隔离目录位于仓库外，正式签名包经支持的安装路径进入真实 Host；没有改 registry、伪造 package version 或使用 renderer 内存代替 owner store。Electron 43.4.1，1440×902、DPR 1.5；窄屏用同一真实 renderer 改为 560×1000。旧产品到新产品的同版本开发替换先关闭专用 Electron，再正式停用/卸载（保留数据）并重新签名安装。

| 实际流程 | 观察结果 | 证据 |
| --- | --- | --- |
| 3D、Orbit、三轴切片、调色板、键盘 | 32³ hollow world v2；三轴鼠标矩形分别提交 v3/v4/v5；隐藏 Base 后预览为 0，恢复不写世界；方向键移动焦点、Space 产生 v6 单格修改 | [编辑记录](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-edits.json)、[初始 GPU 图](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-initial.png)、[Orbit 后](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-orbit.png) |
| Bulk/undo/快照 | box 27 cells 为 v7；undo 生成 v8，内容 hash 与 v6 一致；实际 worlds.snapshot ActionRun 成功并打开 Artifact Dock | [ActionRun 证据](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-export.json) |
| 真实 3D picking | 点击中心命中 [10,11,10]，只选这一格，同步 Y 切片 11；0 次写操作；随后人用 Gold 在 [0,30,0] 写入 v10 | [Picking 与人操作](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-picking-human.json) |
| 人机连续性 | Agent1 inspect8→修改[28,28,28]→v9；人 v10 后 Agent2 先 inspect10→[29,29,29]→v11，Gold 保留。均通过真实 RunLoop，与现有 UI 同一持久世界 | [Agent1](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-agent-first.json)、[Agent2](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-agent-second.json)、[磁盘复核](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-durable-audit.json) |
| 真正 CAS 冲突 | 暂留人操作 expected v11，让另一真实 RunLoop 修改 [30,30,30] 到 v12，再放行原请求：409 STALE_VERSION，1 次请求，无重放，UI 刷新 v12 | [冲突](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-conflict.json) |
| 错误/加载状态 | 暂留真实读取可见“同步0分块”；返回受控503后旧投影保留、写操作禁用，手动刷新恢复 | [读取故障](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-read-error.json) |
| Scope 与迟到取消 | 真正 snapshot 已提交后才暂留响应，切空 Project 再返回后放行；1 次请求，没有迟到 Artifact 导航或自动重试；空 Project 无 Voxel 工作台/历史视图 | [取消](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-scope-cancel.json) |
| 停用、引擎重启、再启用 | 正式设置停用/立即重启后 style/canvas/tree 均0；原 canvas detached且 WebGL context lost；再启用/重启 generation 2→3，世界 v12、1,139 cells 保留，style1/canvas2 | [停用](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-deactivate.json)、[再启用](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-reactivate.json) |

历史视图从原会话打开 v8，当前世界已经 v9 或更高。真实 Representation 的 source_version=8、fingerprint=`sha256:f011d4f3db26c9dcd1e0b46f28d50f96711fb474a35f30348f7b6941c74e6b0a`，只读三维显示 1,135 表面格，没有可编辑切片 Canvas。[历史图](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-historical.png) 和 [读取/下载记录](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-history-download.json) 保留所见所读。

真实按钮生成 Blob 并触发 Electron DownloadItem；验证专用 `will-download` 仅将保存路径固定到 suite evidence，文件由 DownloadItem 写入，完成后移除监听器。**没有自动点击原生 Save 对话框，也没有从 renderer 把 Blob 用 fs 写盘冒充下载。** [下载文件](../../verification/bench/capabilities/dbfox_voxel/evidence/world_c653aa199f7841aaa72bf1dcddc14629-v8.voxel.json) 34,256 字节，SHA-256 `d1f322665556500a6888ea38a28ee1f44e2abc82aab7639da425a7cc3e59f954`；manifest 与公开历史 v8 完全一致，4 个 chunk 逐项一致，各 chunk 字节 hash 独立计算正确，总 1,135 cells。隐藏 Base 仅改变预览，下载仍保留所有层。历史删除后读取另有 fixture/作者固定快照合同覆盖，未声称在此真实桌面链删除了世界。

| 大世界真实读取 | 数据/呈现 | 一次本机观测 |
| --- | --- | --- |
| 64³ 狐狸神社 v38 | 4 页、60 chunks、23,386 layer cells、12,425 表面实例 | 点击到 ready 401ms；489 DOM 元素、2 canvas、JS heap 91,952,253 bytes |
| 128³ 边界世界 v2 | 19 页、296 chunks、96,776 cells；明确提示 60,000 表面实例上限；局部 crop 64 实例 | 点击到 ready 1,814ms；467 DOM 元素、2 canvas、JS heap 281,436,386 bytes |
| 窄布局 | 560px viewport/scrollWidth/studioWidth，编辑器单列520px | 没有横向溢出，垂直工作台可滚动 |

[大世界记录](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-large.json)、[神社](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-fox-shrine.png)、[128³](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-128-world.png)、[窄布局](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-narrow.png) 为 e6267551 新包复验；旧包826/3571ms另保留在 [原记录](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-large-before-style.json)，不据两次运行声称性能提升。时间和 heap 是本机单次观测，不代表长期内存曲线、FPS、GPU显存或跨设备性能承诺；128³ 的预览截断是明确能力边界，并未把截断图称为完整渲染。截图中的上次异常退出提示来自前轮工具会话被停止后的正常 Host 恢复提示，本轮最终已正常关闭。

最后冷启动同一 v12 世界，真实按住 Control 再点击关闭 tab：[原生清理结果](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-cleanup-held.json) 显示 canvas 14 个原生监听器归零，document 上本 Voxel view 注册的 capture keydown/keyup 均移除，canvas detached、WebGL lost、总canvas0，3.5秒及窗口focus后没有 owner world 请求。关闭按钮的 Host tooltip 可注册其自己的监听器；原始 CDP 集合保留并按实际注册位置区分，没有把 Host tooltip 当作 Voxel 泄漏或声称整个 document 无监听器。验证释放 routes、CDP object group/session 和持有 canvas 引用后，经真正窗口关闭 IPC 退出：此前列明的7个 Electron/Python/conhost进程及5181/19227端口均已消失，[进程清理证据](../../verification/bench/capabilities/dbfox_voxel/evidence/electron-process-cleanup.json)。

重复操作另观察到 Host 树项已经选中、对应 tab 已关闭时，再点击同一树项没有重新打开；fresh reload 后正常。已通知 Director，当前未将其列为通过的重开流程，独立报告保留此交互问题供共享 Host 后续处理。

## 检查与复现

| 检查 | 独立结果 |
| --- | --- |
| `test_voxel_independent.py` | 36 passed，12.03s。包括真实 subprocess abrupt exit、四表原子性、15+4 receipt 变形、8种非法写入、最终提交点取消、历史 receipt 无几何重放、真实 ToolExecutor timeout/cancel × commit 前后、跨 Project 拒绝 |
| 强化后领域 CLI | 14/14 pass，完整报告单独保存于 evidence/independent |
| frontend fixture | 原作者16项加独立导航强化、8项历史/取消/坏页断言和2项原生监听器回归；最新26 passed，4.14s |
| test TypeScript / pyflakes | 通过；pyflakes 仅检查 suite 与独立 Python 测试 |
| 完整 desktop build | 通过，包括 Main/Preload、生产 Token 与 bundle budget |
| 完整 lint | 产品修复后独立复跑通过：0 errors、5条已有共享Host warnings；设计合同通过 |

前端 fixture 替换 WebGL device，仅复用实际 Three math/OrbitControls；它验证合同和原生 DOM 监听器，不作为真实 GPU 验收。真实 GPU 证据来自上述 Electron 图片及 CDP。

运行方式、按版本顺序的浏览器脚本及隔离边界见 [suite README](../../verification/bench/capabilities/dbfox_voxel/README.md)。所有 JSON/PNG/导出属于本 suite，SQLite、包私钥、运行时令牌、签名归档、日志和 Electron profile 留在仓库外，不进入提交。验证中使用的路由、CDP object group/session、DownloadItem hook 已释放，最终只关闭了本任务的 Electron/Vite。

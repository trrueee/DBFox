# Scene 控件生命周期回归

> 文档类型：验证记录
>
> 状态：当前
>
> 最后核验：2026-09-06

Voxel 独立验收发现的 OrbitControls 清理问题促使 Director 检查已集成的 Scene。新增作者回归证实两项缺口：React passive cleanup 执行时 viewport 已脱离原 document；按住 Control 卸载时，固定 Three 0.185.1 保留动态 document keyup。修改前 2 failed / 12 passed，原先的普通卸载与 GPU 释放证据没有覆盖这两个条件。

复用现有 viewport dispose，将其绑定改为 layout cleanup，确保 controls 在 DOM 移除前断开。[上游 r185 OrbitControls](https://github.com/mrdoob/three.js/blob/r185/examples/jsm/controls/OrbitControls.js)没有对应的公开 keyup 清理 API，调查时 dev 源码也保留此缺口。既有 DLC build.mjs 使用 esbuild 的 onLoad 在打包边界添加两行：移除该动态 keyup 并重置 Control 状态。不修改 node_modules、不访问运行时私有字段、不合成用户按键、不增加事件代理。

固定 Three 0.185.1、esbuild 0.28.2 与原 npm lock；补丁断言唯一源码位置，原始/修改后 source hash、bundle hash、负责人和退出条件记录于 vendor/provenance.json。升级到修复上游后删除此构建补丁，并要求原生监听器和 React DOM 生命周期回归通过。保留原 MIT 许可；不引入新依赖或持久化迁移。

修改后 14 项 Scene frontend fixture 通过（4.33 秒）。其中保留真实 Three hierarchy/geometry/controls，只替换 WebGL device；两个 Control 状态都验证注册过的原生 document 键盘监听器已移除。新 vendor 为 772,531 bytes，6 个官方 primitive 仍为 120,012 bytes，字节未变化。此作者记录不替代独立门禁；下节补充随后完成的真实 Electron 复验，此前集成证据保留其原测试范围。

## 独立真实 Electron 复验

2026-09-06，原 Scene 独立 Verification / Adversarial 验证员完成此项有界回归。验证员未编写 Scene 产品或本次修复；上一阶段 Pixel Verification 已在 `6ed057d0` 独立结束。本次没有修改产品、SDK 或共享 Host。

接受 `5cdc6242` 的两个控件修复。实际 Host 候选为 `3d5e3db2`，包括 stdout 持续排空和 Tree 重复激活修复。新建隔离 runtime，使用真实签名安装、Electron Main / Preload / EngineSupervisor / Sidecar、原生 WebGL 2.0 和正式 project operations。包摘要为 `c7ba73d64ac318d4cbbf2b11f20145fdc648ba0b97ab0bb2d8262f236786426b`；逐字节核对签名包内 entry、viewport、vendor、provenance、primitive 与源码。vendor SHA-256 为 `c38db794577efff42b96e75bc590c4ef1f6c376740556c38cbf2a10681e81f3a`；primitive SHA-256 为 `5df8bea98c0554098cc85693d969e3406e17f378d13c7ff3503af46bb293a92b`，并与修复前 Git 字节相同。实际 node_modules 上游源 hash 仍匹配 provenance，未修改依赖文件。[签名证据](../../verification/bench/capabilities/dbfox_scene/evidence/controls-package.json)

原生 API 探针只记录并委托真实 add/removeEventListener、RAF、timeout、ResizeObserver、IntersectionObserver 与 getContext。没有替换 Three、WebGLRenderer、React 或生产 operation；通过实际 `dlc-asset://localhost/<digest>/` 调用栈归属这个隔离环境中唯一活动 DLC。另用 CDP `getEventListeners` 按原始 callback identity 和 capture 标志检查真实注册表，防止仅凭 remove 调用次数推断释放。

| 本次独立路径 | 实际结果 |
| --- | --- |
| 普通、按住 Control 各两次关闭真实 React tab | 4/4。关闭前证明 keydown，以及 Control-held 的动态 keyup 确实存在；关闭后所有被记录的 document/window/canvas native callback 均不存在。控件键盘监听器移除时 canvas 仍连接 DOM。 |
| Graphics、调度与可见性生命周期 | 每轮所有 WebGL context lost，DOM canvas 0、RAF 0、5 秒 poll timer 0、Resize/IntersectionObserver 断开；关闭后等待 5.3 秒，观察器/RAF 无新增回调，Scene HTTP 请求 0。 |
| 重开后的真实交互 | Orbit 改变画布像素且不写 canonical；画布 raycast 选中 Controls Cube。Inspector 修改 Y=1.5，v2→v3；一次 Gizmo X 拖动 v3→v4，仅 changed_ids=controls-cube，刷新后 X=0.16413228352243064、Y=1.5、Z=0。 |
| 未完成的真实 Gizmo 手势 | 拖动进入编辑状态后，用键盘 Space 激活实际关闭按钮。canvas 移除后松开鼠标，5.3 秒内 apply POST 0；重开版本保持。没有直接调用 viewport.dispose。 |
| Control-held 停用、重启、再启用与迟到导航 | 正式导出 ActionRun 完成后拦住实际 GET Session 200 响应。UI 停用并重启、再启用并重启，generation 3→4→5，停用时 stylesheet/canvas/native listener/RAF/timer/observer 全清理；再释放旧响应，late Artifact tab=false，导出 POST 总计 1，canonical v5 保持。 |
| 最终清理 | 最后一次真实 tab 关闭后再用 CDP 核对全部历史 callback 均不存在，恢复探针原生 API；正常窗口关闭，launcher exit 0，Electron/Sidecar/renderer 记录 PID 与 5177/19223 端口均不存在。 |

逐项原始结果见 [关闭循环](../../verification/bench/capabilities/dbfox_scene/evidence/controls-close.json)、[画布与检查器](../../verification/bench/capabilities/dbfox_scene/evidence/controls-interact.json)、[Gizmo](../../verification/bench/capabilities/dbfox_scene/evidence/controls-gizmo.json)、[未结束手势](../../verification/bench/capabilities/dbfox_scene/evidence/controls-abort-drag.json)、[停启取消](../../verification/bench/capabilities/dbfox_scene/evidence/controls-reactivate.json) 与 [最终清理](../../verification/bench/capabilities/dbfox_scene/evidence/controls-cleanup.json)。[实际截图](../images/scene-controls-gizmo.png)显示持久修改后的 Gizmo/Inspector。

独立只读 SQLite 审核确认 `run_05949e9deb9f49399024f7549c8c1712` completed，只有 1 个 succeeded 的 dbfox.scene Invocation、attempt_count=1、相同最终签名摘要；返回 Artifact `artifact_45be034b067446c2b6c18aaa4b543b5b` 与正式 Run/Session 身份一致。[耐久证据](../../verification/bench/capabilities/dbfox_scene/evidence/controls-durable.json)

实际执行：`npm.cmd run build:electron-host` 成功；`npx.cmd vitest run src/features/dlc/__tests__/dbfoxSceneFixture.test.ts --maxWorkers=1` 独立重跑 **14 passed / 4.45 秒**。这些既有 fixture 的重复结果与上表真实浏览器证据分别记录，没有用其替代原生设备证明。完整浏览器复现命令见 [suite README](../../verification/bench/capabilities/dbfox_scene/README.md)。

本次工程合同首轮 **44 passed / 1 failed / 5.99 秒**，唯一失败是已同步的共享 stdout 文档引用 `engine.stdout.test.ts`，而该共享测试尚未同步到 Scene。Director 随后以 `ecca00ef` 同步原独立提交 `6ea0788a`，没有修改 controls 文件；仅重跑 `python -m pytest verification/tests/system/test_engineering_contracts.py -q --tb=short` 后 **45 passed / 2.56 秒**。自有三个 Python 验证脚本 pyflakes、八个浏览器脚本 node --check、文档链接和 git diff --check 均通过。没有修改工程合同或删掉原链接来掩盖同步缺口。

夹具纠正保留：第一次 launcher 把 `--reuse` 误放解释器位置，启动失败后关闭该实例并使用显式 Python 路径重启；第一次探针没有保留 native RAF 的 window 接收者，触发 Illegal invocation，修正后重新加载。初次归属过滤只捕获 viewport，没有捕获入口的 poll/IntersectionObserver，故原 4 轮仅记为[局部探针证据](../../verification/bench/capabilities/dbfox_scene/evidence/controls-close-initial-probe.json)，最终已用实际签名 URL 重跑完整 4 轮。首次以 Ctrl+Enter 关闭未真正激活按钮，超时后夹具 finally 的 mouseup 在仍打开的视口完成正常写入 v5；不是关闭后的迟到写入。修正为实际 Space 按钮激活，并捕获起始版本独立比较后通过。两个停启循环各出现旧 endpoint activation GET 的 connection-refused 诊断；最终活动投影、资源释放与新 generation 重开正常，未重放写请求。

本次没有新的确认产品问题。接受范围是 Windows 真实 Electron 的这两个控件修复及相关重开/取消路径；不重述整个 Scene 创作、10k 或 Creative Program 终验。Scene connector 提供打开按钮而非资源 Tree leaf，已验证重复关闭/打开按钮，不能将其称为其他 DLC 资源叶回归。runtime 留在系统临时目录；不提交数据库、日志、下载文件或应用构建目录。

# Voxel 确定性 CapabilityBench

> 文档类型：验证指南
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：`capability.dbfox-voxel.scripted`，正式签名 DLC 与生产 RunLoop

本 suite 原由 Program Director 编写，原始 evidence 根报告属于实现者侧证据。后续独立 Verification Engineer 已审查评分、补充持久 Invocation/Observation/Artifact 身份检查与故障断言，并运行真实签名 Electron。独立 CLI 输出单列 `evidence/independent/`；真实桌面证据以 `electron-` 为前缀，完整边界和发现见 [独立验证报告](../../../../docs/quality/voxel-independent-verification.md)。尚未用该结果替代后续 Adversarial 阶段。

从仓库根执行：

```powershell
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/bench/test_voxel_bench.py -q --tb=short
D:/Project/DBFox/.venv/Scripts/python.exe -m verification.bench run capability.dbfox-voxel.scripted --output D:/Project/DBFox-worktrees/creative-program/voxel-report
```

输出目录必须尚不存在。支持框架既有 case 过滤和重复运行；领域入口为 `python -m verification.bench.capabilities.dbfox_voxel --output <新目录>`。没有新增通用执行引擎、共享领域模型或第三方依赖。runtime fixture 参考已存在的 Scene suite，使用既有签名包安装、迁移、Runtime snapshot、ScriptedProvider 与 reporting；Voxel 专属案例、chunk 局部性评分及世界导出只在本目录。

14 个案例涵盖简单创建、局部增量、多阶段几何、非法输入恢复、先 inspect 再编辑、stale、no-op、歧义不改、128³大型世界、有界 context、人修改后 Agent 编辑、明确不改、整世界替换拒绝，以及64³赛博朋克狐狸神社的十类持续变化。

模型脚本的 `$world_id`、`$version` 和 `$步骤.字段` 仅取真正交付模型的 `function_call_output`。Human step 调用注册的 typed project operation，结果只记作验证证据，后续 Agent 必须再 inspect。歧义以明确回答结束当前 Run；只有 fixture 模拟用户补充说明后才接续 Run，普通增量修改不会每步另开 Run。

Scorer 通过注册 `worlds.get/chunks` 读取不可变修订，检验持久 Run/Invocation/Observation/Artifact 的身份、版本、调用顺序与预算，并逐变化 cell 验证其仍在目标 layer/区域内；不调用领域几何函数重算期望结果。明确坐标、数量和对象属性来自 case 独立断言。Context 不含 cells/chunks，输出不随世界体积膨胀。非法 schema 调用在 Tool admission 阶段拒绝，因此 attempt_count=0；实际执行的调用为1。两者都不得自动重放。

压力作品从正式 Artifact 的注册 manifest/chunks Representation 导出 `fox-shrine.snapshot.json`，并记录 SHA-256、页数和固定版本。它是公开表示的重组证据，不新增领域文件格式。报告不包含私有 SQLite、Token 或凭据。实际脚本化策略不能证明真实 LLM 的独立艺术创作或自然语言理解。

## 独立故障与前端合同

```powershell
# 仓库根；根 conftest 的隔离通过 verification 配置加载。
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_voxel_independent.py -q --tb=short
D:/Project/DBFox/.venv/Scripts/python.exe -m pyflakes verification/bench/capabilities/dbfox_voxel verification/tests/system/test_voxel_independent.py
# desktop 目录
npm.cmd test -- src/features/dlc/__tests__/dbfoxVoxelFixture.test.ts --maxWorkers=1
npm.cmd run typecheck:test
npm.cmd run lint
npm.cmd run build
```

`fault_worker.py` 是 suite 的真实子进程故障入口，针对实际 VoxelStore 的提交前/后做 abrupt exit；不是产品运行入口。独立测试复用作者签名包/运行时准备，不复用作者期望值。前端 fixture 仅替换 WebGL device，实际 OrbitControls 的 EventTarget 监听器仍执行；GPU、原生下载和 Host 生命周期必须看真实 Electron 证据。

## 真实 Electron 复现

先在 desktop 执行 `npm.cmd run build:electron-host`。从仓库根启动，目录必须是任务独占的新外部目录，不能指向用户数据：

```powershell
node verification/bench/capabilities/dbfox_voxel/browser-launch.mjs D:/Project/DBFox-worktrees/creative-program/voxel-browser-runtime-new D:/Project/DBFox/.venv/Scripts/python.exe --accept-downloads
```

launcher 准备正式签名完整 DLC、迁移数据、14案例中的神社压力作品、32³交互世界和128³边界世界，然后运行真实 Main/Preload/EngineSupervisor；仅模型 Responses 为脚本。Vite固定5181、只供任务的CDP19227；端口被占用时须先检查实际所属进程，不终止用户应用。`--reuse` 只用于已经准备的本任务目录。无凭据/收费Provider/额度重置。

另一终端用已安装 Playwright CLI 的命名 session（在仓库根执行，以确保相对 evidence 路径正确）：

```powershell
npx.cmd --no-install --package @playwright/cli playwright-cli -s=voxel-verification attach --cdp http://127.0.0.1:19227
npx.cmd --no-install --package @playwright/cli playwright-cli -s=voxel-verification snapshot
```

在实际 UI 选择 `Voxel Independent QA` Project、展开 Voxel 树并打开 `Interactive Voxel`。`run-code --filename <文件> --raw` 执行下面的 suite 函数，结果是 JSON；审阅命令成功后再保存为对应 evidence 文件，不将 `### Error` 当结果。独立 Agent/audit Python 进程需注入与 launcher 一致的 `DBFOX_RUNTIME_DIR`、`DBFOX_DATABASE_URL=sqlite:///<目录>/metadata.sqlite`、`DBFOX_TESTING=1`、空 `DBFOX_SYSTEM_DLC_DIR`/`DBFOX_SYSTEM_DLC_MANIFEST`；不要打印运行时 Token。

| 顺序/前置状态 | 脚本与操作 |
| --- | --- |
| fresh Interactive v2 已打开 | `browser-edit.cjs`：Orbit、三轴鼠标编辑、图层显示和键盘，结束v6 |
| 同一世界v6 | `browser-export.cjs`：bulk到v7、undo到v8、正式snapshot ActionRun；保留该“保存体素快照”会话 |
| 当前v8 | `python -m verification.bench.capabilities.dbfox_voxel.browser_agent <目录> <输出JSON> 28`：实际Agent先inspect、单格修改到v9。重新选择Interactive并刷新，`browser-state.cjs`记录可见版本 |
| 保存的v8会话仍存在 | `browser-history-download.cjs`：打开固定Artifact，隐藏预览层，正常按钮触发DownloadItem；读取磁盘文件另由audit检查 |
| 重新打开Interactive v9 | `browser-picking-human.cjs`：真实3D点选，零写入；Gold人操作到v10 |
| 当前v10 | `browser_agent`同上，坐标29，得到v11；UI刷新 |
| 当前v11 | 并行运行 `browser-conflict.cjs` 和另一终端的 `browser_agent ... 30`。前者暂留真正UI写请求，公开读取看见Agent已提交v12后放行原CAS，必须409/无重放 |
| 当前世界已打开 | `browser-read-error.cjs`：受控503/手动恢复；`browser-scope-cancel.cjs`：真实ActionRun已提交后暂留响应、切空Project再返回，检查迟到取消 |
| 导航树可见 | `browser-large.cjs`：每个大世界fresh reload后读取/计时、局部crop与560px布局；不修改世界 |
| 全链完成 | `python -m verification.bench.capabilities.dbfox_voxel.browser_audit <目录> <suite evidence目录>`：只读公开世界与Core字段，逐manifest/chunk/hash验证下载并核对人Gold与三Agent格仍在 |
| 设置与重启 | `browser-deactivate.cjs`、`browser-reactivate.cjs`：真实停用/重启/启用/重启，检查generation与数据持续 |
| Interactive已打开 | `browser-cleanup.cjs`：关闭tab后查看canvas/listeners/context与3.5秒晚请求 |
| Interactive tab已关且无其他Voxel画布 | `browser-cleanup-held.cjs`：记录document监听器基线，再打开世界，按住Control跨真实卸载，检查canvas和document监听器均释放 |
| 任务结束 | `browser-close.cjs` 调用真实公开窗口关闭IPC；CDP连接随进程退出而断开，核对专用5181/19227端口均已释放。不调用close-all或关闭用户应用 |

`--accept-downloads` 只允许 `world_<32hex>-vN.voxel.json` 保存到此 suite 的 evidence，由正常 Electron DownloadItem 写盘；verification-only listener 只调用 setSavePath，在 done 后自行移除。CDP只是观察下载事件，不替换写盘。未自动点击原生保存对话框；此限制必须随下载证据一起报告。

开发中源代码变化但包版本未变时，禁止直接覆盖已激活包。仅在专用Electron停止、CDP19227无监听之后，运行 `python -m verification.bench.capabilities.dbfox_voxel.browser_fixture <目录> --upgrade`，走正式停用/卸载保留数据/重签安装，然后 `browser-launch.mjs <目录> --reuse --accept-downloads`。`--record-installed` 是只读审计入口，用于重新记录已安装digest和公开world，不替换包或修改世界。私有runtime目录的SQLite、包密钥、日志和profile均不提交。

## 最终独立对抗阶段

这是 `6467337c` 后正式独立授权的另一阶段，见 [对抗报告](../../../../docs/quality/voxel-adversarial-review.md)。新增 `test_voxel_adversarial.py` 使用真实签名安装、生产 RunLoop、ToolRuntime/ToolExecutor 和独立 `adversarial_worker.py` 子进程故障注入；旧36个 fault 仅为回归。

```powershell
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_voxel_adversarial.py verification/tests/system/test_voxel_independent.py -q --tb=short --show-capture=no
# desktop 目录，仍串行
npm.cmd test -- src/features/dlc/__tests__/dbfoxVoxelAdversarial.test.ts src/features/dlc/__tests__/dbfoxVoxelFixture.test.ts --maxWorkers=1
```

真实桌面使用完成上面 v2→v12 验证链的独占目录，重新签名冷启动。命名 CLI session 改为 `voxel-adversarial`；保留原 evidence，新增结果以 `adversarial-*` 命名。按序运行 `browser-adversarial.cjs`（实际选中树重开、600次正式只读、跨Project迟到chunk）、`browser-adversarial-large.cjs`（64³/128³完整hash读取成本、局部/窄布局）、原 `browser-cleanup-held.cjs`（原始真实监听器断言）、`browser-adversarial-history.cjs`（旧v8会话表示与原生下载）、`browser-adversarial-lifecycle.cjs`（历史视图Control-held卸载、正式停用/重启/启用/重启）。每步先用 snapshot 确认可见状态。

`browser_audit <运行目录> <evidence目录> adversarial-durable-audit.json` 保留逐块与人/Agent哨兵断言，第三个参数仅选报告文件名；下载文件内容与此前相同。完成后仍使用 `browser-close.cjs` 和实际PID/专用端口检查。真实下载保存路径控制、脚本化模型与本机单次性能的限制适用于本阶段。

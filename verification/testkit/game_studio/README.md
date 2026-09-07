# Game 作者验证入口

> 文档类型：测试说明
>
> 状态：当前
>
> 最后核验：2026-09-07

本目录是作者验证，不是独立验收。复用已验证的 Shader native testkit 的进程隔离、正常签名安装和官方 SDK SSE 边界模式；没有导入其他 DLC 私有产品实现。公共证据在 `verification/testkit/game_studio/evidence/`，原生截图在 `docs/images/game/`。

## 确定性门禁

仓库根执行 `python -m pytest verification/tests/system/test_game_dlc.py -q --tb=short`（32 项）和 `python -m verification.bench.capabilities.dbfox_game --output <新目录>`（12 类 capability + 10-request stress，共 13 项）。bench 使用完整签名包、实际 `build_product_run_loop`、默认预算；只替换模型边界。frontend 在 `desktop` 执行 `npx vitest run src/features/dlc/__tests__/dbfoxGameFixture.test.ts --maxWorkers=1`（7 项）、`npm run typecheck:test`、`npm run lint`、`npm run build`。

## 作者浏览器

运行 `node verification/testkit/game_studio/build-author.mjs`，然后 `python -m verification.testkit.game_studio.author_server`。打开 `http://127.0.0.1:18941/.tmp/game-phaser-review/studio.html`，创建游戏并点击“添加狐狸生存示例”。页面使用真实 Host React/Tree、真实 Game Studio、完整签名后端 operations；它不具备生产 installed executor 身份，不算原生运行证明。

`browser-studio.cjs` 验证直接编辑/数字清空/undo/布局，最后卸载页面；`browser-runtime.cjs` 在同一 author server 上运行实际 Phaser。后者会用测试专属避障输入驱动狐狸，再用生成的有界输入重放，要求 tick 3600 获胜；同时检查静止失利、Canvas/HEADLESS 一致、取消、超时及 512 重叠刚体预算。通过 Playwright CLI `run-code --filename <脚本>` 运行；`eval window.gameSurvivalEvidence --raw` 可保存实际输入供 native 模型计划复用。

## 原生 Electron

先在 `desktop` 完成 `npm run build`。从根运行：

```powershell
node verification/testkit/game_studio/browser-launch.mjs D:/Project/DBFox-worktrees/creative-program/game-native-runtime
npx --offline --package @playwright/cli playwright-cli --session game-native attach --cdp http://127.0.0.1:19230
```

launcher 管理实际 Main/Preload/EngineSupervisor 与 Python Sidecar，production renderer 端口 5184，逐字使用 Host CSP。运行时、下载、SQLite、签名 archives 留在外部目录。重启使用 `--reuse`；升级必须先正常关闭该 Electron，再以同一 `DBFOX_RUNTIME_DIR` 执行 `python -m verification.testkit.game_studio.prepare <runtime> --upgrade`，走正常 disable/uninstall/install/enable，保留 owner data。测试仅控制原生 DownloadItem 的保存位置，不证明人工 Save 对话框。

使用新 runtime、真实 UI 或公共 API 创建空 Project。`prepare_native_plan.py <survival-evidence.json> <plans.json>` 复用产品 preset 和已实测的输入，`responses_server.py <plans.json> <model-evidence.json>` 在 19330 提供官方 SDK 验证的 Responses SSE。该服务器不导入 DBFox、不访问数据库、不生成工具结果。`browser-native-agent.cjs` 创建唯一命名的验收 Project，Studio 关闭状态下执行同一生产 Run 的 8 个调用，包含失败实测、局部 health 调整、成功实测、导出。已有命名 Project 时拒绝重放创建阶段。

后续作者阶段：`browser-native-audit.cjs` 为只读历史/下载/固定预览验证；`browser-native-studio.cjs` 只接受该数据集 v3，执行 drag v4、undo v5 和正式 ActionRun；`browser-native-keyboard.cjs` 用真实键盘输入驱动正式 ActionRun；`browser-native-snapshots.cjs` 读取公共 v3/v4/v5 原始 JSON。每次 `--raw` 保存到任务临时目录。`audit_native.py <runtime> <capture-dir>` 重算规范 hash，断言 v4 只改变狐狸 x +80、v5 等于 v3，验证 native 下载完成字节及所有前端文件与安装包来源一致。

这些原生阶段有状态前置条件，失败后先读原 Run/版本，不重复写入。现有 retained dataset 已到 v5，不能再执行 v3 mutation 阶段。最后验证包 digest 为 `82996d3da0630568941ac7de0ab1c2d7ce0acddd4c5ee44459f83d268d679dff`，实际 Run 和 immutable IDs 见证据 JSON。Pixel 真组合与独立验收仍由 Director 在集成分支执行。

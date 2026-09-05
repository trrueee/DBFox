# Scene 确定性 CapabilityBench

> 文档类型：验证指南
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：`capability.dbfox-scene.scripted`；正式 RunLoop，脚本化模型边界

在仓库根执行：

```powershell
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/bench/test_scene_bench.py -q --tb=short
D:/Project/DBFox/.venv/Scripts/python.exe -m verification.bench.capabilities.dbfox_scene --output D:/Project/DBFox-worktrees/creative-program/scene-bench-report
D:/Project/DBFox/.venv/Scripts/python.exe -m verification.bench run capability.dbfox-scene.scripted --output D:/Project/DBFox-worktrees/creative-program/scene-catalog-report
```

输出目录必须尚不存在。可用 `--case fox-temple-stress` 只执行压力作品，或用 `--repetitions 2` 重复。框架生成 environment/suite/trials/summary JSON 与 report.md；压力案例成功时额外从本次 Run 的持久 Artifact 经注册 Representation 导出 `fox-temple.gltf`、`fox-temple.glb` 和官方 Khronos 校验记录。临时 SQLite/签名包保留在命令报告的仓库外临时目录，不进入源码提交。

`cases.json` 为 suite 自有领域数据，覆盖模板要求的 12 类能力和一个压力作品。`runtime.py` 安装包含真实 frontend/vendor 的签名 DLC，生产 Runtime snapshot 构建 registry/resolver/context/guidance/completion，并执行正式 RunLoop。`schema.py` 只定义本 suite 的 step/case；共享 bench schema 不增加领域内容。Director 已将 suite 注册到现有 catalog，统一 CLI 与领域入口调用同一个 runner。2026-09-05 独立执行为 [13/13 通过](evidence/scene-bench-report/report.md)，同目录保留正式 trace 和压力作品。

`$scene_id`、`$version` 与 `$步骤.facts字段路径` 的值只取已发给模型的正式 function_call_output。脚本边界本身保存已观察事实，评分器才读取历史 canonical 文档；评分结果不回灌模型。Human step 调用真实注册的 typed project operation，其返回值只留作评分证据，Agent 必须再 inspect。

确定性评分检查生产 Run/Invocation/Artifact 身份、顺序、状态、资源版本、稳定对象 ID、局部修改的无关对象不变、计数/参数/哈希、无操作/歧义/拒绝不写入、有界 Scene context 和 Observation。脚本策略不能证明真实 LLM 能独立理解模糊自然语言或创作；它证明既定合法/非法调用经过产品路径后的状态与恢复行为。

作者 unit/fixture、独立 Runtime/RunLoop、真实浏览器、红队是不同证据。已确认缺陷及实际通过数量见 [独立记录](../../../../docs/quality/scene-dlc-independent-verification.md)。

真实桌面验证使用本 suite 的 `browser-launch.mjs <新的仓库外目录> <python.exe>`：先从 `desktop` 执行 `node scripts/build-electron-host.mjs`，启动器建立实际签名包、两对象交互场景与 10,000 对象场景，随后运行原始 Electron Main/Preload/EngineSupervisor 和 Vite。`--reuse` 仅用于重开同一产品字节的隔离 fixture；产品包变化必须使用新目录，同版本不同 digest 的正式拒绝不能绕过。CDP 为本机 `http://127.0.0.1:19223`；用命名 Playwright CLI session attach 后，在 UI 打开 Scene Studio/Interactive Scene 并全屏，可运行 `browser-viewport.cjs`、`browser-edit.cjs`、`browser-export.cjs`、`browser-large.cjs`、`browser-large-orbit.cjs`、`browser-tree.cjs`。固定坐标的编辑脚本适用于本轮 1440×902 CSS viewport，换尺寸需先依据真实截图调整。

`browser-navigation-diagnostic.cjs` 仅在导出失败时用 CDP Debugger 读取非敏感局部布尔状态，不修改产品函数，结束后关闭 Debugger。`browser_audit.py <runtime目录> <输出JSON>` 通过只读 SQLite URI 导出本项目明确白名单列的 Run/Invocation/Artifact 证据，不读取 credential/token 表。截图默认保存 `output/playwright`，精选 PNG 可放 `docs/quality`；JSON、glTF/GLB 和机器报告只能放 suite 自有 `evidence/` 或仓库外输出目录。

下载验证在启动器增加 `--accept-downloads`，然后运行 `browser-export.cjs` 和 `browser-download.cjs`。后者使用 CDP default；bootstrap 只在此 opt-in 下用官方 DownloadItem `setSavePath` 将原生保存选择限定到本树 `output/playwright/interactive-scene.glb` 与 `.gltf`。字节仍由 Electron 下载，不从 Blob 代写文件。两次 Native done 后 hook 自动移除；测试必须检查 done=completed、接收长度、磁盘 hash 与官方 validator，不能只检查 toast/HTTP 200。这个边界不代表自动化了原生对话框点击，详见 [最终浏览器记录](evidence/browser-final-checks.json)。默认 bootstrap 只记录白名单 DownloadItem 诊断事件到隔离 Runtime。

下载后关闭进程，再不带 `--accept-downloads` 重启，用 `browser-scope-cancel.cjs` 在真实 Session GET 200 后延迟交付，实际切换项目并释放原响应，验证晚到结果不打开页签；finally 撤销 route。停用/激活必须从正式 DLC 设置界面执行并按 UI 重启 Engine，`browser-disabled.cjs` 检查清理，`browser-open.cjs` 检查恢复。结束时从应用关闭按钮退出实际 Electron，并 detach 本次命名 Playwright session；不要关闭其他用户浏览器。

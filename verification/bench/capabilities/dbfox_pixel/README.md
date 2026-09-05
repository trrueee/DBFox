# Pixel deterministic capability verification

> 状态：当前

独立 Verification suite，复用 Bench manifest/report/TrialOutcome、ScriptedProvider 和生产
RunLoop。完整 Pixel 后端与真实前端字节签名、信任和激活；Core SQLite 使用真实迁移，
领域状态由产品写入。只有 Responses 模型边界受控，不是实际 LLM 创意能力评分。

```powershell
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/bench/test_pixel_bench.py -q --tb=short
D:/Project/DBFox/.venv/Scripts/python.exe -m verification.bench run capability.dbfox-pixel.scripted --output output/pixel-bench-new-run
```

15 个场景覆盖 12 类基本任务、整文档替换拒绝、200 帧和 32×32 狐狸骑士压力创作。
`build_cases.py` 确定性生成 `cases.json`，其中只有明确的工具请求、澄清文本和独立像素断言，
没有预填最终文档。模型只从真实 function_call_output 读取动态ID/revision；Human typed
operation 的返回仅作为评分证据，不回填模型状态。普通编辑在同Run完成，仅显式用户澄清
开启后续Run。

`scoring.py` 通过正式 documents.get/frames.read 核对像素、版本、身份和局部不变项，
不导入产品几何或合成函数。生产PNG通过正式固定Artifact Representation输出，再用
开发依赖Pillow逐字节核对解码RGBA及全部sheet帧顺序。评分读取不反馈到模型。
数据库/签名临时包留在仓库外；精选JSON和真实导出PNG可保存在本suite的evidence目录。

输出目录必须尚不存在，框架拒绝覆盖旧报告。最终保存的统一结果在
[`evidence/current/report.md`](evidence/current/report.md)。独立 42 项测试、CLI 15/15、
真实 Electron 和发现/修复前后证据见
[`pixel-dlc-independent-verification.md`](../../../../docs/quality/pixel-dlc-independent-verification.md)。
本轮独立 Verification 已完成，后续 Adversarial 与 Director 集成仍待。

真实桌面复现从 worktree 根运行：

```powershell
node verification/bench/capabilities/dbfox_pixel/browser-launch.mjs C:/path/to/task-runtime D:/Project/DBFox/.venv/Scripts/python.exe --accept-downloads
npx.cmd --yes --package @playwright/cli playwright-cli -s=pixel-verify attach --cdp=http://127.0.0.1:19225
npx.cmd --yes --package @playwright/cli playwright-cli -s=pixel-verify snapshot
```

在实际作品已打开时使用 CLI `run-code --filename=.../browser-edit.cjs` 等领域脚本。
`browser-fixture.json` 只在外部 task-runtime 中保存合成 QA 项目身份。`--reuse` 原样重启已
安装包；显式 `--refresh` 仅供实例已关闭时通过官方停用/卸载保留数据/重新签名安装，
随后用正式 RunLoop 建立 200 帧作品。不要在活动实例上执行 refresh。

浏览器脚本按真实页面状态执行，不是全链无状态 runner：编辑脚本需要指定画布/调色板，
re-activate 脚本从扩展设置开始，scale 脚本从 QA 作品目录开始。快照中的资源按钮、目录、
作品和原生 Canvas 是交互入口。`browser-audit.py` 仅在验证层附着既有签名包，公开读取
固定修订并交叉解码实际 DownloadItem 文件；其 Agent 模式只把真实 onAsk 引用当作初始
意图，然后从原生 observation 检视与修改，未绕过模型的 ID/version 来源约束。

`--accept-downloads` 使用仅限 `output/playwright` 的官方 Electron setSavePath，文件仍
由 DownloadItem 接收和落盘，不能代称原生保存对话框点击自动化。测试结束关闭本任务的
窗口并 detach；绝不关闭其他 Electron/CDP 实例或提交数据库、profile、日志及临时签名包。

## Independent Pixel adversarial stage

The independent red team is recorded separately from the completed Verification stage in
[the review](../../../../docs/quality/pixel-dlc-adversarial-review.md). Its two new pytest modules
are `verification/tests/system/test_pixel_dlc_adversarial.py` and
`verification/tests/system/test_pixel_artifact_adversarial.py` (49 cases on candidate `88e7c7d1`).

For a new isolated Electron red-team instance, run these commands from the repository root:

```powershell
python -m verification.bench.capabilities.dbfox_pixel.redteam_fixture <fresh-runtime-directory>
node verification/bench/capabilities/dbfox_pixel/browser-launch.mjs <fresh-runtime-directory> <python-executable> --reuse
```

Attach the named Playwright CLI session to port 19225. Run `redteam-gestures.cjs`, `redteam-artifact-close.cjs`, and
`redteam-generation-stream.cjs` in that order, saving CLI output to the corresponding
`output/playwright/pixel-redteam-<name>.txt`. `redteam_audit` collects the captures and performs
one actual product-factory continuation using the observed onAsk references. It mutates only
the isolated artwork, so run it once per fixture. Finish with `redteam-finish.cjs`, normally
close that Electron window, close the named CLI session, and verify the task process tree and
ports are gone. `evidence/redteam-*.json` contains no Token, SQLite file or raw runtime log.

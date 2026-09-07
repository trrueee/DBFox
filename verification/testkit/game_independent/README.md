# Game 独立原生验证

> 文档类型：测试说明
>
> 状态：当前
>
> 最后核验：2026-09-07

本目录由 Director 独立编写并运行，验证作者候选 `737a1f1c` + `031a5f11` 在当前 Core 上的真实 Electron/Phaser 行为。它复用 `game_studio/browser-launch.mjs` 的正常签名安装、真实 Main/Preload/EngineSupervisor 和原生下载路径控制边界；不复用作者的结果断言，不注入 Phaser 输出，不访问私有 owner 数据库。

## 已保留数据集与执行顺序

外部 runtime 是 `D:/Project/DBFox-worktrees/creative-program/game-independent-runtime-1`；当前游戏已到 v5，不要重放写阶段。原始捕获在验证树 `output/playwright/`，公开汇总为 `evidence/audit.json`。

1. 先构建 `desktop`，启动 `node verification/testkit/game_studio/browser-launch.mjs <新runtime>`；以 Playwright CLI 显式 session `game-independent` attach `http://127.0.0.1:19230`。真实 UI 在 Default Workspace 创建 `Independent Fox Review`，添加狐狸生存示例得到 v2。
2. 在 Studio 选中狐狸，变换检查器只修改 X 400→480，保存 v3；点击撤销得到 v4。`capture.cjs` 通过公共只读 operations 捕获各固定版本：`--raw run-code --filename=verification/testkit/game_independent/capture.cjs > output/playwright/game-independent-history.json`。
3. 执行 `playtest.cjs` 捕获 `game-independent-formal.json`：真实单步、播放、暂停、重置，再点正式 Playtest，经原 ActionRun 和安装执行器得到 v4 的 lost/698 报告。等待报告实际挂载再截图；请求完成瞬间的禁用/加载截图不算完成证据。
4. 当前候选切回初始通用 Game Studio tab 会丢游戏选择，记录缺陷后从下拉框重新选择同一个游戏，点击导出工件。进入 document tab 后执行 `artifacts.cjs` 捕获 `game-independent-artifacts.json`，通过实际 UI 下载 v4 报告与 Game 包，并验证只读固定预览播放/暂停/重置没有发出领域写请求。
5. 通过原生关闭按钮正常退出，launcher exit 0；`--reuse` 重开，执行 `capture.cjs` 保存为 `game-independent-reopened.json`。公共各版本应与关闭前完全相同。
6. 真实 UI 从游戏树打开作品，生命检查器只改 initial/maximum 3→100，保存 v5。执行 `win.cjs` 捕获 `game-independent-win.json`，实际 Phaser 应完成 won/3600。再次 `capture.cjs` 保存为 `game-independent-after-win.json`。
7. `retained.cjs` 是本次实际观察到的两个 v4 Artifact ID 的只读探针，捕获 `game-independent-retained.json`。它应与步骤4的导出原字节一致。新 runtime 必须从真实操作响应取得新 ID，不能沿用旧 ID 或伪造源关系。
8. 运行 `python verification/testkit/game_independent/audit.py <runtime> output/playwright`，重算完整规范文档 SHA256、仅局部修改、原生完成下载字节、14个实际安装前端文件来源和冷启动一致性。最后正常关闭该任务 Electron，检查 5184/19230 释放。

`capture.cjs` 对原始 JSON 中的非 ASCII 字符使用等价 Unicode escape，避免 Windows shell stdout 转码改变中文；Python 恢复原字符后重算规范 hash，保持原浮点数拼写。脚本不输出捕获的请求头或运行时令牌。

## 边界

本次没有 live LLM，没有付费 API；UI 正式 ActionRun 与独立 Pixel→Game scripted RunLoop 组合分别验证，不把两者合成一次模型端到端证据。下载仅由验证入口设置实际 DownloadItem 保存位置，不证明人工 Save 对话框。非冻结 Sidecar 安装器、任意恶意 renderer 的计算正确性、长期运行内存不是本项结论。已发现的工作区定位和窄窗问题见 [独立报告](../../../docs/quality/game-independent-native.md)。

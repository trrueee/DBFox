# Game DLC 调查与验证证据

> 文档类型：验证证据
>
> 状态：当前
>
> 最后核验：2026-09-06
>
> 适用范围：Game Lead 的实施前调查和后续作者验证；尚不是独立交付验收。

Director 将历史线程 `/root/scene_lead/domain_architect` 从已交付 Shader Workbench 转任 Game DLC Lead，逻辑角色现为 Game。已完整读取原 Lead 模板、CONTRIBUTING、AGENTS、Game preflight、下一批技术调查、文档规范与复用要求。工作树 `D:/Project/DBFox-worktrees/creative-game`，初始 `1fd2e556`，Director 后续仅合入 shared stdout 独立回归 `5d8712b4`。用户原 dirty baseline 与 desktop node_modules junction 保留；本轮候选依赖只装在本树 `.tmp/game-phaser-review`。

Copy from creative/game checkpoint f54950ca; unmerged WIP, not independent acceptance. Code and remaining risks: [author handoff](game-author-handoff.md).

## 固定引擎调查

正式选择与25项合同在 [Game 架构](game-architecture.md)。官方 npm 精确 `phaser@4.2.1` integrity 为 `sha512-WUNwCPJpdjvZiuT6SgCfYVW8Qw/3j0jJ4ws7P2QkhFLFu74sbGuyHJcbFueGkY/AYO4Pi47bNQXn1OCJeLX//w==`；发布者 MIT，eventemitter3 唯一 package dependency。隔离 npm install --ignore-scripts --registry=https://registry.npmjs.org/ 成功，audit 0 vulnerabilities。该结果不是“以后没有漏洞”的保证。

核验官方 3.90.0 与4.2.1 World、4.2.1 Body/ArcadePhysics/Game/VisibilityHandler/MouseManager/Config/InputManager 源码，区别 update/step/postUpdate 与 DESTROY 执行方式。实际采用的公开 singleStep 在4.2.1中包括 pre/post，不再手工拼接物理生命周期；HEADLESS 仍需浏览器。

## 原版与最小生命周期修复的真实 Chrome 探针

任务专属 Playwright 会话 `game-engine`，测试服务 `127.0.0.1:18941`；CSP 直接从本树 production appProtocol.ts 解析，不使用 unsafe-eval/inline script，不改 Host。脚本通过原官方 dist/phaser.esm.min.js 建 Canvas 和 HEADLESS Phaser.Game，公开关闭 input managers；场景准备后停止自动 loop，再走同一个 scene update 的 World.singleStep。

| 检查 | 原版4.2.1 | 修复/按官方 feature flags 构建 |
| --- | --- | --- |
| Canvas：120 tick，初始 x20/vx60 | x140/y32/overlap15 | x140/y32/overlap15 |
| HEADLESS 相同输入 | 相同 | 相同 |
| reset 新实例 | 相同 | 相同 |
| seed42 首个 RandomDataGenerator.frac | 0.6848634964661496 | 0.6848634964661496 |
| 512 bodies ×3600 ticks | 443.7ms | 580.9ms |
| 四个 Game 销毁后 Canvas | 0 | 0 |
| document visibility listener 净残留 | 4 | 0 |
| window.onblur/onfocus 保留原值 | false/false | true/true |

性能数字仅代表这个稀疏 body 场景，不是最大碰撞/图形压力承诺。监听计数 instrumentation 只在调查页，不进入产品。原与修复仍是**作者 Chrome 物理探针，不是生产 Electron/Tool/AgentRun 或独立验收**。控制台只有 favicon404，无 CSP/engine 错误。修复构建目前1,211,553bytes，远低于DLC单文件20MiB；最终产物将在产品 build 中固定 hash、上游许可证和原/改源摘要。

本机非提交调查资产：`.tmp/game-phaser-review/{fetch-review.py,package.json,package-lock.json,build-probe.mjs,server.py,index.html,patched.html,probe.js,probe-patched.js}`。其中原始文件与实际console/snapshots可复查；不将临时测试脚本或 npm源码包提交产品。

```powershell
# 工作目录 D:/Project/DBFox-worktrees/creative-game
node .tmp/game-phaser-review/build-probe.mjs
npx.cmd --offline --package @playwright/cli playwright-cli --session game-engine goto http://127.0.0.1:18941/.tmp/game-phaser-review/patched.html
npx.cmd --offline --package @playwright/cli playwright-cli --session game-engine eval window.gameProbe
```

## 待实施与验收

已完成作者 backend 主体：17个 Tools、12个 Project operations/4个机器 lease operations、严格 typed canonical、SQLite CAS/history/receipts/undo、固定版本文档/资产/报告 Representation 与 playtest transient bridge。共享实际工厂 resolver 修复由 Director 同步为81345258；Game 没有修改 Core。离线 vendor 已正式构建，1,211,553 bytes，SHA-256 `d11f0597c79521a82682831cef1f7d44a2cd6bd2afa9db266713d52b8a4328b8`；许可证和原/改源 hash 见 DLC provenance。

`python -m pytest verification/tests/system/test_game_dlc.py -q --tb=short` 当前32 passed（9.21s）。mypy 11个 backend 文件及 pyflakes通过。已确认集合包括同事务CAS并发胜者、整批回滚、回执之后取消回滚、noop actor精确回执、删除恢复/重复hash、historical asset bytes、配额/损坏fail-closed、实际 ToolRuntime、人改后Agent读、桥proof/claimed-once/超时/取消/另一Game隔离、历史report、Pixel页拼接/错版本/跨Project/bool/取消，以及真实 `build_product_run_loop` 工厂闭环与实际 Host ActionRun。

签名包测试当前**明确构建 backend-only package**，不是完整 desktop DLC。实际工厂只有 LLM Provider 换为 scripted boundary，Resource discovery/binding/resolver、持久 Invocation、Artifact settlement、Context、Completion 和 RunLoop 均使用产品实现；一个 Run 内从 library创建 Game 后，后续合法 Invocation 的 refs 与其 Artifact provenance逐项相等。Human export在启动 Run前预留32KiB，重复同身份返回同一个 durable Run，未知状态不再启动替代Run。

Native schema 调查发现 Host 使用 `pydantic_function_tool` 和 strict=true，所有可选 nullable字段都变为 required。输入仅对声明 default=None 的字段 null归一为省略；canonical Game显式null仍拒绝。测试对全部17个实际materialized schemas与完整字段样例，逐字段验证 nullable默认、省略等价，以及其余字段null拒绝，没有调高默认token预算。

完整 Workbench、完整签名桌面包、真实产品 Phaser playtest、12类 capability bench、10类 stress、示例和独立 Verification/RedTeam 尚未完成。桥报告/Pixel页读取的模拟边界只证明合同，不当作真实浏览器或跨DLC生产执行。Lead 按阶段实际履行 Domain Architect → Backend → Workbench → 作者验证；不能因此记录五个独立 Agent 或冒充独立红队。最后仍由 Director 调度未参与实现的验收者，completion 保持 false。

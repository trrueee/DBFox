# Game DLC 在制品交接

> 文档类型：实施交接
>
> 状态：当前
>
> 最后核验：2026-09-07
>
> 适用范围：历史在制品与当前作者候选；最终完成仍需独立验收和集成组合门禁。

2026-09-07 已恢复实现并完成 Game 作者候选验证。当前进度和已解决项以 [最新证据](game-dlc-evidence.md) 首节、[可复现入口](../../verification/testkit/game_studio/README.md) 为准；以下 2026-09-06 停止记录是历史背景，不再代表未挂载状态。当前 native retained dataset 已到 v5，原型作者创建/修改阶段不能直接重放。Pixel 真组合及独立审查仍未完成。

## 接手位置与授权边界

工作树 `D:/Project/DBFox-worktrees/creative-game`，共享修复基线 `81345258`。角色历史路径 `/root/scene_lead/domain_architect` 当前实际为 Game DLC Lead，先前 Shader 作者检查点 `4df3568d` 已交付，勿重做。所有 Game 架构、后端和前端均为同一作者，不构成独立 Verification / Red Team。

用户因额度有限要求停止实现、由其他 AI 接手。本次只保存现有在制品和说明，不继续编写或运行测试。先完整阅读 `D:/Project/DBFox-worktrees/creative-program/lead-game.md`、本树 AGENTS/CONTRIBUTING、[Game 权威架构](../architecture/game-dlc.md)、[调查证据](game-dlc-evidence.md)、`dlcs/dbfox.game/README.md` 和 `contracts.schema.json`。原 Lead 的完整工作台、12-case capability bench、连续10次创意修改 stress、狐狸生存示例、生产 RunLoop 闭环均仍在范围内，不能把本检查点当完成。

Core/SDK/共享锁文件不得为本 DLC 改动。大量其他 dirty 文件是用户基线，保留。desktop/node_modules 是共享 junction，不安装共享依赖。Game 自有 package-lock 由 npm 正式生成。Director 正在另行研究多个 DLC 的默认 Tool schema 预算，不提高默认预算或自制工具目录绕过。

## 已保存的实现

- 唯一规范模型 GameProject：scenes、entities/components、behaviors、rules、variables、immutable RGBA assets；每 Project library bootstrap Resource + 每 Game Resource。
- 后端 11 个 Python 文件包含 strict canonical/input、SQLite append revisions、CAS、exact human/Agent receipts、undo/tombstone、资源 discovery/resolver、context、17 Tools、12 project operations + 4 machine operations、document/report Representation、ActionRun、单请求 transient Phaser bridge。删除 Project 无 SDK hook，因此明确保留 owner 历史。
- 操作只接受结构化增量，不接受全篇替换。写入 expected_version 与 frozen invocation 双 fence，undo 追加 revision、hash 不唯一；receipt 后仍检查取消/预算。原 Run 以真实持久 Invocation 为 Artifact 依据。
- 原生 materialized Tool schema 的所有 required optional-null 样例已覆盖：仅输入声明 default=None 归一化，canonical/null/bool/int/unknown 保持严格。
- Pixel 导入走公开 Artifact + `dbfox.pixel.sprite.v1` frame Representation，记录 DERIVED_FROM exact 来源，owner immutable RGBA。当前仅 transport fixture，尚非多 DLC 正式 RunLoop 证明。
- Phaser 官方 npm 精确 4.2.1（MIT）固定；Canvas + Arcade + HEADLESS，local vendor 不含音频/WebGL/Matter。build.mjs 对原版 VisibilityHandler 做 hash-guard 最小监听器释放修复，依赖源码与许可证见 vendor/provenance.json；vendor SHA256 `d11f0597c79521a82682831cef1f7d44a2cd6bd2afa9db266713d52b8a4328b8`。`.gitattributes` 为 vendor `-text`。
- 前端 runtime.js 为真正 Phaser Game/Arcade；固定 60Hz，每 tick 只有一次公开 World.singleStep。Canvas/HEADLESS 共享领域步进。生成 ID `templateUUID:ordinal`、规则 canonical 顺序、条件边缘触发、首 finish 优先、scene_change 确定性、预算和释放均已有代码。
- 最新新增但未验证的 frontend：executor.js（无 Dock activation lease/poll/claim/complete/cancel）、model.js（固定分页与图片 hash）、forms.js（结构化表单）、presets.js（狐狸/史莱姆示例增量操作）、viewport.js（Phaser React 生命周期、拖动、输入与播放）、studio.js（实体树/组件/行为/规则/变量/图片/history/undo）、artifacts.js（公开 Representation 固定预览/报告/下载）、index.js 注册入口、index.css。

## 已经真实执行的验证（不是本次重新运行）

最后后端作者命令在本树根运行：

```powershell
python -m pytest verification/tests/system/test_game_dlc.py -q --tb=short
# 32 passed in 9.21s
python -m mypy --no-warn-unused-configs --follow-imports=skip --no-incremental dlcs/dbfox.game/backend
# 11 source files passed
python -m pyflakes dlcs/dbfox.game/backend dlcs/dbfox.game/generate_contracts.py
# passed
```

32 项包括实际签名的 **backend-only** 包 install/activate/deactivate/reactivate、真实 `build_product_run_loop` factory（仅 provider scripted）同 Run create→inspect→incremental modify→stale reject→inspect→undo→export；实际 Host ActionRun export 和 duplicate 只保留一个 Run。默认 prompt budget 未提高。桥的 Python报告 fixture只测协议，不能证明 Phaser。frontend/index.js 完成前测试 helper 显式移除 frontend manifest，尚未改成完整签名包测试。

真实作者 Chrome 会话 `game-engine`，测试端口18941，CSP 从 production `desktop/main/appProtocol.ts` 原文解析。第一轮 upstream/patch 引擎探针详见 evidence 页。后来实际产品 runtime.js 探针取得：

| 项目 | 真实结果 |
| --- | --- |
| Canvas 与 HEADLESS，seed42，120 ticks、向右输入 | final report 逐字一致，狐狸 x64→184 |
| elapsed_tick=3600 | 恰好 tick3600 won，末事件 finish；该简单场景约538ms |
| seed12，两次 spawn/lifetime/seek、120 ticks | 完整报告一致；生成 templateUUID:1..:24，过期移除，最终8实体 |
| 同 tick 两次 scene_change + variable_add + won + lost | 首 won 生效、后 lost 不执行，取消待切场景；score1 |
| 结束释放 | DOM canvas 数0 |

探针是作者 Chrome，非生产 Electron、非真正 Tool bridge、非独立验收。发现 Phaser Graphics.generateTexture 在 HEADLESS 无 renderer 会失败；已将纯 artwork 创建限制在 Canvas，物理 roots 保持相同，以上相等性在修复后执行。随后 runtime 又添加 event_count 终止预算、binary ID排序和超预算早停，这几个末尾改动尚未重跑探针。

停止前只对 JS 做零散 `node --check`：studio.js 括号已修正后通过，viewport/forms/artifacts/index 通过；不是 lint、类型、运行或实际 UI 验证。**最新 Studio 从未成功挂载浏览器，不得声称可用或通过。**

## 本机证据与恢复命令

以下是被忽略的任务私有文件，留在原工作树供下一 AI 接手，不进提交：

- `.tmp/game-phaser-review/server.py`：只提供静态文件与 production CSP，**不是生产 Sidecar HTTP**。
- `runtime-fixtures.py`：使用实际后端模型和增量 mutations 生成有效 Game；`runtime-fixtures.json` 存放模型。
- `runtime.html`、`runtime-probe.js`：导入实际 frontend/runtime.js，输出 `window.runtimeProbe`、错误 `window.runtimeError`。
- `patched.html`、`probe-patched.js`、`build-probe.mjs`：之前上游生命周期调查。
- `.playwright-cli/` 是 CLI 临时输出；没有最终 Studio 宽/窄截图，不要伪称已有截图证据。

接手后（不是本次要求执行）：

```powershell
# 所有命令显式工作目录 creative-game
python .tmp/game-phaser-review/runtime-fixtures.py
python .tmp/game-phaser-review/server.py
# 另一个终端；使用已经安装的 Playwright CLI，不安装共享依赖
npx.cmd --offline --package @playwright/cli playwright-cli --session game-engine open http://127.0.0.1:18941/.tmp/game-phaser-review/runtime.html
npx.cmd --offline --package @playwright/cli playwright-cli --session game-engine eval window.runtimeError
# 复杂结果用 run-code --filename，避免 PowerShell 引号/展开；不要打印整份庞大报告。
# 自有 vendor 可重建：workdir dlcs/dbfox.game
npm.cmd run build
```

之前探针服务已随中断退出；本次关闭 named browser session。不要广泛杀 Chrome/node/python 进程或删除其他 worktree。

## 必须继续完成 / 已知风险

1. **先实际挂载并修复 Studio**，再扩范围测试。入口目前直接 import Phaser，因此 Node/jsdom Fixture 必须显式控制浏览器设备边界；不得伪造真实引擎证据。需要正确 SDK staged host、正式 Tree、实际 React mount。允许针对设备隔离 fixture，但真实 Phaser 另跑浏览器。
2. 各表单均手写 typed 字段，无 JSON editor，但尚未逐项与 canonical model 验证。`Fields` 数字输入清空后变字符串，后续编辑可能不恢复 number，需要实测修正。输入 selectors 转换 `inputSpec`、实体/规则编辑、缺依赖错误、静态/圆形 body 尺寸边界、locked controller 等都需要交互测试。
3. 竞态重点：草稿保存期间 / 外部 head 变化 / loading→switch Game / viewport drag 与 Agent 修改 / palette asset decode / ActionRun结束后 scope变更。刷新保留草稿后需用户明确采用新版本，不自动重放。write 保存成功但刷新失败目前落 uncertain 文案，需确认不会提示重发或丢草稿。作用域与卸载已写 controller cleanup，尚未作者验证。
4. runtime 末尾 event budget 修复待检验：终止事件预留计数、已排队 deferred action 与 finish/budget precedence。trigger snapshots 在动作前捕获，因此生命伤害后生命条件下一 tick 判断；应补文档/测试。重叠候选在碰撞分离前收集，solid 必须双方 true；密集512 bodies碰撞是待测最大负载，早期580ms稀疏测量不是该上界。
5. runPlaytest 超时目前抛普通 Error('DEADLINE_EXCEEDED')，executor 按 TimeoutError 识别，可能分类为 ENGINE_FAILURE；需要在正式协议测试中修正。deadline/取消/late attach/重复claim/断线/hidden/tabclosed需真实联测，不重放。
6. viewport.js 尚未实际运行；检查 IntersectionObserver/RAF/keyup/pointercapture清理、暂停后输入、预览场景切换的运行态、drag overlay 同步、disabled template选择、录制1024条边界、resetKey与stepKey以及 mount 后单步效应。固定版本工件目前复用了支持拖动的 viewport，只回 false；需要明确禁止只读工件位置拖动（领域代码不能靠写失败才恢复）。
7. model.js fixed pagination、raw RGBA重组/hash，需 fixture 覆盖错version、取消、尾页、重复hash去重、Representation不得传override。JS JSON不能直接重算 Python canonical float1.0 hash；当前比较 owner 摘要 hash，并单独验证原始资产字节，不能宣称重算文档hash。
8. UI样式已消费Host tokens，但没有运行 lint/设计令牌/窄屏/键盘/可访问性检查。组件长行可在必要实现调整时重构，不能把当前语法检查当UI gate。
9. 正式 playtest executor 在 installed dlc-asset URL 才接受包digest；普通HTTP作者预览显式 unavailable。当前 unavailable 状态对象不执行工作。必须真实完整签名包 + 生产 Electron activation，无Dock也可playtest，绑定冻结snapshot和claim证明；不能注入假digest把作者页面升级为正式GPU/engine证据。
10. Artifact public文档/报告view、navigation、下载、历史删除后读取、运行日志分页、postRun是否成功尚未浏览器验证。UI history第一页和diff前50显式有界；更深分页体验需检查。
11. 32后端 gate 仍要在前端补齐后改为完整签名包门禁，扩实际 Phaser bridge结果、正式工厂create→playtest→observe→局部调整→再playtest。不要仅手建 RunLoop 或改包省略 frontend 来宣布交付。
12. 全部12-case Game capability suite、10-change creative stress、带保持ID/局部diff/undo检验的狐狸示例，以及真实 Pixel→Game composition未完成。presets.js只提供用户可用的增量示例代码，还没有接入正式bench/产品证明。
13. 仍需独立非作者 Verification、Adversarial；这位作者的后端32与浏览器探针不能计入独立门禁。检查点 completion 必须 false。

## 检查点精确归属

提交仅包含 `dlcs/dbfox.game/`（所有自有代码、vendor、schema、README/status、自有 npm lock，忽略 node_modules）、`verification/tests/system/test_game_dlc.py`、`docs/architecture/game-dlc.md`、`docs/architecture/game-dlc-preflight.md` 的本作者权威文档链接增补、`docs/quality/game-dlc-evidence.md`、本页。不包含临时脚本、数据库、日志、其他 DLC、Core/SDK 或共享锁文件。提交摘要明确 WIP。停止时不重新运行任何验证。

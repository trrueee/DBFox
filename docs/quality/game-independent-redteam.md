# Game 独立后端与生命周期红队

> 文档类型：质量证据
>
> 状态：当前
>
> 最后核验：2026-09-07
>
> 适用范围：Game 0.1.0 作者候选的独立后端审查；不代表完整 DLC 已验收

本审查由未参与 Game 产品实现的独立验证员执行。在下列明确边界中未确认阻断缺陷，新增九项攻击全部通过。完整 Game 是否通过仍由 Director 合并真实 Phaser、原生交互、组合、作者功能门禁和本报告后决定；本报告不替代那些证据。

## 可复现基线

验证树为 `D:/Project/DBFox-worktrees/creative-game-verification`，分支 `codex/game-verification`，审查 HEAD 为 `d1f48ea40e487c665753e4dea4e4af7d1a075458`。作者源提交为：

| 源提交 | 验证树中的对应内容 |
| --- | --- |
| `f54950ca3196ea6526d95a579b194f7b98469c43` | Game 后端与工作台初始候选，树中 `34a8b08f` |
| `737a1f1c72ca99ab350c47851ee5d5948b30f576` | 完整工作台与作者原生证据，树中 `7a76c658` |
| `031a5f11a7433ac94feda714421bd588f2002c27` | 作者 JSON 证据迁入 verification，树中 `194b6590` |

`git diff --name-only 031a5f11 d1f48ea4 -- dlcs/dbfox.game` 为空；Game 产品字节未因集成改变。`git diff --name-only 94294767 d1f48ea4 -- engine dbfox_dlc_api.py sdk` 为空；这一候选未修改 Core 或公开 SDK。验证树包含 Director 提供的既有用户 dirty baseline，本次未覆盖、提交或把它们算作 Game 修改。

关键产品 Git blob：

| 文件 | Blob |
| --- | --- |
| `backend/compute.py` | `f3c08c0a5c0b73c77b7c9cdb16d7c0e9eb1d5768` |
| `backend/store.py` | `7f6776d44c404156039167e25c7f0986d449390c` |
| `backend/tools.py` | `86fe9741add366e1446608f11c09c8c047f53831` |
| `frontend/runtime.js` | `e0b0e6060cbc3b8bd2e38346ef9ee52932c77a39` |

独立测试每次构建包含完整 frontend/vendor 与 backend 的签名包，经过正常 trust/install/enable/compiler 装载。验证用固定测试签名键，不是生产发布者；本次包 digest 为 `09446103ba6e1af399777fb5240eb1bebe5c3de21546f27ffeb695b339d9ae27`。它与作者使用不同测试签名键，因此不要求 archive digest 与作者包相同。

## 独立攻击与结果

入口为 [独立红队测试](../../verification/tests/system/test_game_independent_redteam.py)。测试不导入 Game 私有 store，不调用作者测试；通过已安装贡献的公开 typed operations、公开 Resource resolver 和生产 `ToolRuntime.invoke` 执行。测试里的冻结 ref 是显式测试输入，用于攻击 Tool 的精确 Resource 检查；此部分不是完整 Session admission 复验。SQLite 只用于读取副作用数量。

| 攻击 | 观测结果 |
| --- | --- |
| 改换 Project 后读取与修改已存在 Game；把 Game B 参数配上 Game A 冻结 Resource | Project 操作拒绝，Tool 失败，无 Artifact、revision 或 receipt 增量 |
| 一个批次先改标题，再向本 Game 添加来自另一个 Game 的 scene reference | 整批回滚，原标题与 revision/receipt 数量均保持 |
| 两个公共 Human operations 同时基于 version 1 修改 | 只有一个到 version 2，另一个明确 `STALE_VERSION`，仅一个 revision 和 receipt |
| playtest 已领取后，同 client 增加 registration counter 换代；尝试旧 lease，以及新 lease 配旧 claim | 两种结果交接均拒绝，原 Tool 失败，无 report/receipt |
| playtest 已领取后，人先提交同 Game 新 head，再交回旧结果 | 原 Tool 失败，人修改保留，旧报告不落库 |
| playtest 已领取后设置真实 Runtime cancellation probe | Tool 失败，无 Artifact、report 或新增 receipt；没有完成部分报告 |
| 改写 input hash | proof 拒绝；显式 detach 后原 Tool 失败，无 durable 副作用 |
| 使用正确 claim 交回 foreign entity，或声称 won 却没有 terminal event | complete 只确认交接；原 Tool 再验证报告并拒绝落库，无 Artifact |
| 已完成 Invocation 在 executor 断开后重试原输入，再改 seed 重试；之后删除 Game 并正常停用/重新装载 | 原输入返回完全相同 receipt，异输入拒绝；只有一份报告；停用移除 operations/representations；恢复后旧报告导出逐字节相同；参数不能替换 locator 的 version/game |

执行命令（仓库根）：

```powershell
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_game_independent_redteam.py -q --tb=short
D:/Project/DBFox/.venv/Scripts/python.exe -m pyflakes verification/tests/system/test_game_independent_redteam.py
git diff --check
```

最终结果：**9 passed in 8.88s**；新增测试 pyflakes 无输出，diff check 无错误。写入报告后工程合同另行 **45 passed in 3.03s**。首次测试的四项失败是验证员误把 SDK 专用 `DlcOperationError` / `ArtifactRepresentationError` 当作 `ValueError` 捕获；修正测试异常类型后通过，未修改产品或降低断言。

## 架构与真实性边界

阅读了 [原始 Game 要求](creative-handoff/lead-game.md)、[Game 架构](../architecture/game-dlc.md)、[产品说明](../../dlcs/dbfox.game/README.md)、[作者验证入口](../../verification/testkit/game_studio/README.md) 与实际注册、contracts、mutations、validation、store、views、compute、tools、representations、executor/runtime 源码。Game canonical state、图引用、CAS、receipt、playtest 协议与 Phaser 规则解释均在 DLC 内；本候选没有新增 Core 领域枚举、Game 分支、第二 RunLoop 或私有跨 DLC import。Pixel 输入通过声明的公开 Representation 读取；真实组合证据另见 [Pixel→Game 独立验证](pixel-game-composition-verification.md)。

以上 playtest 报告刻意使用协议 fixture。它只能证明报告匹配、取消、claim、持久化和不可变读取；**不能证明物理模拟、狐狸躲避或 60 秒获胜**。真实计算证据由 Director 的独立原生验证提供。仅有 `complete.accepted` 也不是 durable 成功，测试明确证明原 Tool 仍会拒绝并回滚。

Lease、package digest 与 proof 绑定受信任的已安装 Renderer executor 和原请求；它们不是计算正确性的密码学证明。本测试未把已控制 Renderer 的恶意程序纳入可防御边界，也不宣称能够阻止它伪造一份结构自洽的计算报告。后端只做有界一致性验证，不在 Core 或 Python 内增加第二套 Phaser 解释器。

## 未覆盖与待合并门禁

- 本项未运行在线模型、付费 API、Frozen Sidecar 安装包、跨平台逐位确定性或长时间内存测量。
- 本项不复验完整 HTTP admission、审批 UI、SSE 恢复；直接 Tool Runtime 的冻结 ref 是测试指定的。真实 Run、membership、Artifact provenance 的其他证据须单独保留。
- 本项不将作者的 32 后端、7 前端或 13 capability 计为新增独立攻击；Director 已运行的作者门禁与本报告各自注明来源。
- 原生鼠标/键盘、Phaser play/pause/reset、Canvas 与 headless 一致、历史 Artifact 预览和实际下载交由 Director 验证。
- 源码中同 tick 的 deferred spawn 在 `finish` 后仍会执行，资源预算超限可能把终态改成 `budget_exceeded`。这尚未做实际 Phaser 复现，不能列为 confirmed 缺陷；如要求严格“首个 finish 永不改写”，需针对临界实体预算确认合同。本审查已向 Director 提出这一窄边界，不能把它写成已通过。

没有在本项证据中确认需要作者修复的阻断缺陷；这是一项有界后端红队结论，不是完整 Game completion 声明。

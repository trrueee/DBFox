# Shader separate adversarial review

> 文档类型：独立对抗验证证据
>
> 状态：当前
>
> 最后核验：2026-09-06
>
> 适用范围：Shader 候选 `8a412cdb` 的独立对抗审查；不替代另一验证员的原生 GPU/桌面验收。

独立结论：本轮确认的问题均已由 Director 修复并独立复验关闭，没有未解决的 P1/P2。新增 **57 项后端、16 项前端**用例分批验证通过。最终候选仅重验受最后修复影响的两条报告边界与 UTF-8/字节读取集合，未重复此前已通过的长测试。Director 负责集成，本报告不代表 Creative Program 完成。

本阶段由 `/root/voxel_lead/domain_architect` 承担，开始于 Pixel 独立红队提交 `13e2fcf9` 之后。审查者未实现 Shader 产品。已完整阅读外部 `lead-shader.md`、`shader-adversarial-handoff.md`、仓库贡献合同、Shader 当前架构和实际源码。原作者测试、Director 的 capability bench、另一验证员的 Electron/GPU 证据均不计入本轮新增攻击数。工作树没有 CodeGraph，未初始化索引。

## 已确认的问题与原始证据

下表的源码位置以 `efb9167f` 及其前序后端为原始基线；修复由 Director 完成，审查者仅写测试与证据。SQLite 修改是显式故障注入；同步外层 hash/计费的案例检验语义来源绑定，不声称能够抵抗有权重写所有事实的恶意本地管理员。

| 问题 | 原始最小反例及影响 | 权威修复点 / 当前复验 |
| --- | --- | --- |
| P2：历史零号/非法索引绕过连续性 | [store.py](../../dlcs/dbfox.shader/backend/store.py) 原 96–103 行仅比较 count/max。版本或 generation 从 `1,2` 改成 `0,2` 后，`documents.head/get/list` 六个公开读取继续成功，无法证明有效初始修订。 | 原 audit 查询增加 SQLite 实际 integer 类型及正安全整数范围；保留 unique/count/max。扩展负值和小数，共 18 个公开读取攻击已通过。 |
| P2：回执摘要未绑定原修订 | 原 store.py 206–223 行验证 receipt framing/hash/schema 后直接返回。保持编码合法，仅将 receipt 的 title 或 content_hash 改成另一合法值，精确 human retry 返回伪摘要。 | receipt 读取核对不可变 revision summary；compute receipt 核对同一 report 的正式有界投影。原两败已通过；多文档 generation 推进后的合法 no-op 回执仍可恢复。 |
| P2：pass 排序变化从操作摘要和 diff 消失 | 合法 `pass_reorder` 使 v2→v3、hash 和实际 passes 页顺序变化，`documents.diff` 却返回 total=0；changed_ids 同样遗漏。原 [inspection.py](../../dlcs/dbfox.shader/backend/inspection.py) 139–147 行及 store changed_ids 只比较对象内容。 | 共享对象比较同时检查列表位置，diff 给 from_index/to_index。原反例、重复排序 no-op、undo-of-undo 独立通过。 |
| P2：Workbench 接受同一 immutable identity 下被改动的数据 | 原 [document-data.js](../../dlcs/dbfox.shader/frontend/document-data.js) 1–81 行只校验 source/texture hash。重放真实签名包的 8 个公开页；schema=true、计数不符、uniform 遗漏、重复 ID、悬空 pass、uniform 值和 preview 时间被改动，七种均被接受。原正向完整页与错误固定版本两个控制通过。 | 复用 `documents.get` 和 immutable Representation 增加固定版本 canonical byte 页；先验原始 Python 编码的 `{document,deleted}` hash，再解析，避免重造跨语言 float JSON。七个等价攻击改在新正式字节/summary 入口执行，另六个 cursor/base64/大小攻击，15 项已通过。旧页未删除。 |
| P2：持久报告读取遗漏计算语义 | 正式 signed ToolRuntime + machine operations 接收一个明确标记的负协议回执后，修改报告为 compiled=true 且保留 error、foreign stage ID、compiled=false 且移除全部 error，公开 `inspect_compile_error` 全部成功。 | complete/save/read 共享语义校验；原三败已通过。补充 CONTEXT_LOST 已存报告和 nonrendered 带 preview layout 的派生故障又确认两败；冻结候选上独立 **2 passed / 7 deselected / 4.91 s**。后者正常 CompleteInput 已拒绝，影响为内部派生损坏的写读不一致。 |
| P1：正式 native strict schema 与 nullable 输入冲突 | [contracts.py](../../dlcs/dbfox.shader/backend/contracts.py) 原 Input validator 递归拒绝全部 null；Host 官方 materialization 却将 nullable 字段列为 required。实际 schema 的完整 inspect、preview_set、uniform_update 三种合法 native 输入均被 Runtime 拒绝。 | 仅声明 `default=None` 的字段将 null 解释为省略；required、未知字段、bool 数值与 nested required selector 的拒绝不放宽。新 3 正向/5 负向独立用例已通过。 |
| P2：独立 driver log 的 UTF-8 解码状态串扰 | [renderer.js](../../dlcs/dbfox.shader/frontend/renderer.js) 原 3、94、106 行共享流式 TextDecoder。第一 log 为 `x*65535 + 界`，64 KiB 截断留下不完整字节；第二独立 log `A` 被污染，合计 65,539 bytes，超过 65,536 上限，正式回执无法保存本应有界的失败诊断。新 renderer fixture 实测一败。 | 每个独立文本片段单独解码，截断按实际保留 bytes 计费。冻结候选上独立 **1 passed / 1.42 s**；完整保持 `A`、预算和三个 GL 对象释放断言。该测试是 driver 边界故障注入，不是实际 GPU 编译成功证据。 |

最初持久化集合为 9 failed / 19.07 s，其中两个 receipt 案例的第一轮是 fixture 误取 flat `HeadResult.document`，不是产品问题。修正为正式四字段 head 后，完整集合真实 **9 failed / 16.36 s**。计算集合原 **3 failed / 4 passed / 14.66 s**；native schema 集合原 **3 failed / 5 passed / 13.61 s**；原前端分页 **7 failed / 2 passed / 1.67 s**。所有反例及等价修复后断言保留。

## 已完成的新独立覆盖

- 全签名包安装和实际注册贡献，所有 frontend 文件逐字节比对包内容；不通过裸 backend import 代替包生命周期。最终源码 `8a412cdba1c094d57e63bf409d09acfc734ae510` 冷签名 digest 为 **`1b586ec8b79bc1c4d8095708618d8bfaa75b5e3a79047d8a9c21f0f44f11d73b`**。重捕 31 个正式 public pages 后，前端 15 项再过 **1.59 s**。中间 bytes 修复曾捕获 `69a1dc7c0c5fd6895e78232876888b17ab15062b9284c6c911dfe2db5493d49b`，不将其混称最终包。
- 生产 `build_product_run_loop`，仅替换外部 native function-calling Provider。新九项 authority/context/Representation 攻击 **9 passed / 20.44 s**；每次三个正式 Invocation、attempts=1，三份真实持久 Artifact，owner/digest 与 exact producer identity 被核对。未注入 resolver，未放大默认 prompt budget，下一步 ID/version 仅来自 function_call_output。
- Shader 特有的 Studio generation：同 Run 三个产物 refs 为 0/1/2，payload document version 为 1/2/2，均有真实 producer proof。其他文档创建将 Studio 推进至 3 后，原文档仍 v2/hash 不变，但旧 export 不能在新 Run 的 generation=3 admission 中复用。这是现有 exact fence 的支持范围；不放宽权限。原 Artifact 的人类 immutable Representation 仍固定在 v2。Workbench document onAsk 的显式 Studio authority 可入场；artifact-only 或 private object selector 不会获得 Studio authority。
- selected/recent/previous 三处结构化 Artifact 上下文，对错 producer、错 Project resource、internal visibility、非 terminal producer 均拒绝；历史表示拒绝 Project/document/version/path/URL 参数覆盖。
- GPU protocol 使用明确 `compiled=false` 的故障回执，不伪称驱动输出。独立覆盖同 hash 的 head ABA（v1→v2→undo v3）、healthy lease 仍存续而原 request deadline 已过、receipt INSERT 后同 client 重新注册、真实 report commit 后 Tool 返回丢失以及当前 head soft delete。未提交结果无 report/receipt；已提交结果用原 frozen scope 只读恢复，旧 complete 不重放。
- canonical SQLite 中 schema bool/float、未知 null、preview bool、required source null 的损坏，在 summary 和 canonical byte 两个公开读取入口均 fail-closed。原始 framing/hash/配额保持一致以检验权威 schema。
- canonical byte 分页在第一页之后发生人类 head 变化仍保持旧固定版本：UTF-8 多字节 source、每页 <=16,384 raw bytes/32 KiB JSON、完整 cursor/total/hash、空末页、越界与跨 Project/selector 拒绝。新八项类型/分页/配额/图约束集合 **8 passed / 14.47 s**。
- 配额精确用完于 receipt 时，已经 INSERT 的新 revision/head/generation 全回滚，既有作品仍可读。stage 引用删除、self feedback、外部纹理 URL、超 UTF-8 行预算和局部 ref 失败不会遗留任何部分修改。

后端通过数量来自互不重叠的 **38 passed / 63.37 s**、authority **9 passed / 20.44 s**、limits **8 passed / 14.47 s**、最后两个 report 攻击 **2 passed / 4.91 s**，共 57 项。前端为 15 个 byte-page 攻击和 1 个 decoder 攻击，共 16 项。没有把作者回归、旧 Pixel/Scene 测试或另一 Shader 验证员的测试算入。冻结候选上的有限复验没有发现回归。

## 可重复入口与证据范围

从工作树根使用 `D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_shader_adversarial_persistence.py verification/tests/system/test_shader_adversarial_compute.py verification/tests/system/test_shader_adversarial_schema.py verification/tests/system/test_shader_adversarial_authority.py verification/tests/system/test_shader_adversarial_limits.py -q --tb=short --show-capture=no`。

从 desktop 使用 `npm.cmd test -- --maxWorkers=1 src/features/dlc/__tests__/dbfoxShaderAdversarialPages.test.ts src/features/dlc/__tests__/dbfoxShaderAdversarialRenderer.test.ts`。前端测试加载实际 DLC 模块；jsdom 只证明读页/解码/生命周期边界，不证明 WebGL 驱动能力。

[capture_pages.py](../../verification/testkit/shader_adversarial/capture_pages.py) 重捕真实 signed public operations；[修复前页](../../verification/testkit/shader_adversarial/evidence/public-pages-before-fix.json) 与 [当前字节页](../../verification/testkit/shader_adversarial/evidence/public-pages.json) 都保留。JSON 证据置于 suite-owned 目录，docs 下没有新增 JSON。临时签名包、数据库、密钥和日志不提交。

其他 fixture 更正：捕获脚本第一次错用仓库根 `conftest`，实际隔离模块位于 `verification.conftest`；nullable 测试最初尝试未安装的 jsonschema，已删除该依赖，改为逐项核实实际 materialized required/nullable 节点；limits 第一轮两个失败因将公开 `DlcOperationError` 误认为 `ValueError` 子类，已明确分别接受模型 ValidationError 与领域 DlcOperationError，不弱化拒绝断言。deadline 测试收紧为原 deadline=110、lease=113、检查时刻111，保证确实命中 request deadline，不用 lease 过期代替。

## 静态门禁与交付边界

五个新后端攻击文件与自有 testkit 的 pyflakes 通过；`npm.cmd run typecheck:test` 和两个新增前端文件的 ESLint 均通过。工程合同首轮 **44 passed / 1 failed / 9.66 s**，仅两份独立新质量报告遗漏仓库标准页眉；各作者补齐本人的文档，未修改工程合同。最终工程合同 **45 passed / 2.85 s**。汇总见 [review-results.json](../../verification/testkit/shader_adversarial/evidence/review-results.json)。

本阶段未启动自己的 Electron/Sidecar，没有要关闭的原生实例；未触碰另一验证员的 19228/5182/19328 端口或进程。所有本角色启动的命令已正常结束。完整 GPU、创作压力、原生下载、CodeMirror 操作与真实 visibility/lifecycle 由另一独立验证员继续交付；不得把其数量列入本轮红队，也不声称其未完成项已通过。由此，本报告接受的是明确范围内的候选对抗门禁，不单独批准整个 Shader 发布。

# 真实客户端业务验收：培养方案学分分析

> 文档类型：质量与业务验收证据
>
> 状态：当前
>
> 最后核验：2026-11-07
>
> 源码基线：`codex/creative-program` / `7670e3461c26f9b5338b432435380ad6a452d59c` 加本地修复

## 范围与方法

在上一轮22项源码修复之后，按用户授权操作可见的 Electron 开发客户端，使用已配置的真实 DeepSeek 模型。通过正常界面打开文件夹、上传工作簿副本、发送问题、打开结果、搜索、加入上下文、追问和重开客户端；没有替换模型响应、工具结果或前端状态。先用 Windows UI 自动化；另一个 Unity 窗口反复抢占焦点后，改用 Playwright CLI 连接独立开发客户端的本机 CDP。自动化焦点干扰不记作 DBFox 缺陷。

工作簿为 `2023级培养方案毕业学分（要求）.xlsx`，原附件和副本 SHA-256 均为 `0e2590ffe4f7ca1aa66b69e13bd2554434f9ddd46dbf9996bbb5a29ac71e4038`。项目为“学分分析验收”，会话为 `a5984d16-9f4e-4cde-93cb-2292e226aed2`。原工作簿未修改，已安装客户端未迁移、重装或写入测试数据；秘密沿用 OS 凭据库，没有读取 Key 明文。

本机证据保留在被忽略的 `desktop/output/user-journey-20261107/`，不进入版本控制。以下结论仅覆盖 Windows、开发解释器和当前源码，不代表 Frozen Sidecar、安装升级、其他数据库或271项功能已全部验收。

## 实际故障链

原始问题：“帮我分析一下这份培养方案的学分分布，按模块汇总学分和占比，做一张图。用中文解释各类选修怎么计算。”

| 实际 Run | 实际行为与结论 |
|---|---|
| `run_478c4a1a203b4e4d83f04d20401070b0` | 读取和准备成功，不同 SQL 校验通过后在执行前被 `AGENT_NO_PROGRESS` 停止：JNY-01 |
| `run_75b39f1ba2f9457da0d5be928b216019` | 生成两个模块汇总结果，未出图，却宣称保留8个查询结果：JNY-06 |
| `run_f2a13ff122614761ad4aa0928d851f74` | 已加入上下文的旧结果被拒绝；重新计算后图表创建报“要求学分不是 numeric”：JNY-02、04 |
| `run_ae910823ac8a4571a00ef9e00f84549d` | 修复后的数值列正确，图表成功创建并在 Dock 渲染；模型随后写错嵌入标记，修正轮又漏引用，最终失败。不能只凭图表卡片宣称整个请求成功 |
| `run_0414d0807d3943abb862b8d4ee5396f8` | 入口修复后跨轮读取、profile成功，未重跑 SQL，Run完成；检查耐久响应仍发现证据为空、引用被删：继续找到 JNY-05 |
| `run_6509caf4d4164adebb1367f0412fc9f2` | 直接从旧结果派生图表两次输出合同失败；当前冻结来源合同只允许同Run派生。补齐Visualization指引，未扩大派生权限 |
| `run_b8b8d9f979db49a289910b9b339822af` | 新指引生效后在本轮重新校验取数、创建图表并正常完成；但英语归因和部分图表配置仍有问题，详见剩余范围 |
| `run_ce40362843004988847139dea4887712` | 仅一次 `result_inspect` 读取上一轮汇总，回答31学分；耐久正文保留引用，Evidence中保留旧结果ID，JNY-05真实复验通过 |

原表列出的数值直接求和如下，尚未扣除“不计入总学分”条目：

| 模块 | 要求学分 | 占164学分 | 明细门数 | 明细学分 | 明细减要求 |
|---|---:|---:|---:|---:|---:|
| 公共基础 | 38 | 23.17% | 10 | 38 | 0 |
| 通识必修 | 35.5 | 21.65% | 28 | 37.5 | +2 |
| 通识选修 | 10 | 6.10% | 0 | 0 | −10 |
| 专业必修 | 49.5 | 30.18% | 16 | 49.5 | 0 |
| 专业选修 | 31 | 18.90% | 26 | 53.5 | +22.5 |
| 合计 | 164 | 100% | 80 | 178.5 | +14.5 |

要求和候选课程清单是不同口径。继续读取备注后，发现Sheet1第86行及第100行明确说明科研训练2学分不计总学分；按该备注扣除后明细为176.5，专业选修明细为51.5。178.5只是原列数值总和，不能当毕业计分。模型最初漏读备注，后续纠正了这一点；英语分级仍不能笼统归因为每类都修4门，也不能把 `min(明细, 要求)` 当作通用毕业资格算法。

## 根因与修复

| 编号 | 用户可见问题 | 源头修复与反例 |
|---|---|---|
| JNY-01 | 有效校验被误判为无进展 | [SqlValidateTool](../../dlcs/dbfox_data/backend/tools.py) 成功观察复用规范查询指纹；不调高阈值，不以新ID制造进展。`test_workbook_regions.py` 验证不同查询有进展、同查询新ID仍去重 |
| JNY-02 | 数值变成文本类型，Visualization 拒绝绘图 | [row_serializer.py](../../dlcs/dbfox_data/backend/sql/row_serializer.py) 保留 DB-API native 类型，经内部结果送达 [DataFrame](../../dlcs/dbfox_data/backend/result_view.py)；Decimal仍以无损字符串运输。`test_workbook_product_flow.py` 走真实 RunLoop、worker、DuckDB验证类型；实际图表渲染成功 |
| JNY-03 | 混合数值列搜索报分页错误 | [sql_backed_view.py](../../dlcs/dbfox_data/backend/sql/sql_backed_view.py) 用现有 SQLGlot AST 在全局文本搜索前 CAST；原生排序、结构化过滤不变。实际 DuckDB page/count反例通过，界面搜索“通识”返回2行 |
| JNY-04 | 已选旧结果被“本轮不可用”拒绝 | [ToolDispatcher](../../engine/agent/tool_dispatcher.py) 复用 `available_artifact` 的既有来源、会话、顺序和当前版本证明。正常来源反例先失败；版本变化、移除、internal、跨会话、未终结来源继续拒绝 |
| JNY-05 | 跨轮引用在保存时被删，Evidence为空 | [RunLoop](../../engine/agent/loop.py) 将既有 Run discovery 传入 [Terminalizer](../../engine/agent/terminalizer.py)，收尾与读取采用同一可用性证明。反例先复现删引用，再验证耐久正文和Evidence保留来源ID |
| JNY-06 | SQL中间工件也被计为用户结果 | [Terminalizer](../../engine/agent/terminalizer.py) 的受限收尾仅计本轮primary成果，改用通用“成果”措辞。实际SQLite创建三种visibility后仅报告1项 |
| JNY-07 | 重开后刚建立的会话显示8小时前 | [API时间边界](../../engine/api/conversation_common.py) 为SQLite恢复的无时区UTC值补时区并统一输出。回归经过commit/expire/reload；真实重开显示分钟级时间 |
| JNY-08 | 保存的模型别名不在目录时显示空白 | [LlmConfigPanel](../../desktop/src/components/LlmConfigPanel.tsx) 始终显示当前模型名，沿用Radix Select，不改变配置和凭据。真实目录场景及组件回归通过 |
| JNY-09 | 中文表头逐字断行，高约180px | [ArtifactTable.css](../../desktop/src/features/workspace/artifacts/table/ArtifactTable.css) 单行列名、最小列宽和原有横向滚动；实际Dock截图通过，无整体视觉重构 |

另补两处可纠正性：Workbook SQL白名单采用 DuckDB 原生 `REGEXP_EXTRACT`、`REGEXP_REPLACE`，允许从模块标题提取学分要求；guard以静态原因说明不支持函数、无数据源查询和 tolerant cast，不再全部混为schema_error。错误嵌入标记的反馈明确完整 `artifact_` 前缀、独立行和完整答案重写要求，并要求保留证据引用。仍严格校验，不自动改写模型答案或放宽证据要求。

Visualization指引另明确：历史结果可被读取，但不会因 `result_inspect` 自动成为本轮来源；需要按原SQL重新校验执行后，以新结果派生图表。沿用[冻结来源合同](artifact-invocation-authority-review.md)，没有把跨Run血缘关系升级成私有执行权限。真实复验已成功生成新图，不代表所有模型都能一次遵循。

取消与切换也经过实际界面：原分析运行时切到新任务，原Run继续；`run_3ca97ab988c243dc8b75bd639dca35a2` 点击停止后界面显示“任务已停止”，耐久状态为cancelled且cancel_requested=1；随后 `run_a3d3884308fe4a6eb0ef0cf257e9f750` 在同会话完成文件清单。首次尝试点停止时另一个任务已经自然失败，该次不计为取消通过证据。

引用持久化又经过一次正常关闭与重新启动验证：31学分回答的来源按钮仍在，点击能打开上一轮对应10行结果。证据为 `citation-after-reopen.md`、`evidence-source-opened.md`、`citation-restored-source.png`。独立工作簿核对见 `independent-source-check.json`，安全运行摘要见 `business-run-evidence.json`。

## 调查与复用决策

先追项目已有 SQL、Representation、ArtifactRepository、调用入口和收尾，再检查历史提交与既有跨轮结果设计。复用规范查询指纹、来源证明、Run discovery、SQLGlot CAST、DB-API与Radix；无新增依赖、第二套权限、兼容层、协议版本或完整结果副本。

DuckDB实现参考官方 [DB-API](https://duckdb.org/docs/1.5/clients/python/dbapi) 和 [正则函数](https://duckdb.org/docs/1.5/sql/functions/regular_expressions)，本机为1.5.6。未自写正则执行器或将Decimal转float。类型修复的真实证据覆盖 Workbook/DuckDB，其他驱动类型码和旧Snapshot仍需独立验证。

## 验证记录

| 集合 | 实际结果 | 本机日志 |
|---|---|---|
| 第一组反例，修复前 | 7失败：进展、数值类型、搜索、UTC | `new-regressions-before.log` |
| 第一组修复后 | 首次29通过、1旧SQL文本预期不符；更新CAST预期后相关60通过 | `new-regressions-after.log`、`backend-journey-regression.log` |
| 跨轮入口反例，修复前 | 正常旧结果误拒绝；5个拒绝边界通过 | `artifact-selector-before.log` |
| 跨轮保存反例，修复前 | 正文引用被删；5个拒绝边界通过 | `prior-evidence-before.log` |
| 最终Core、收尾、取消、引用、工具恢复 | 92通过 | `core-final-regression.log` |
| 最终Agent Core完整确定性集合 | 351通过、2排除 | `agent-core-final.log` |
| 最终Workbook与工程合同复验 | 64通过，1项既有弃用警告 | `workbook-final-regression.log` |
| 签名Visualization包与Data组合 | 24通过 | `visualization-package-final.log` |
| API、Data domain、上下文、Artifact打开、工程合同 | 187通过，1项既有弃用警告 | `contract-regression.log` |
| 前端配置与表格，串行 | 23通过 / 2文件 | `frontend-focused.log` |
| 前端测试类型、Lint | 类型通过；0错误、23项既有警告 | `typecheck-test.log`、`lint.log` |
| Python静态检查 | pyflakes通过；mypy 241个源码文件通过 | `pyflakes-final.log`、`mypy-final.log` |
| 生产构建、Token与bundle预算 | 通过，有既有大chunk提示 | `build-final.log` |

集合有重叠，不应相加为不重复总数，也不能与上一轮17分钟全量执行混称“修复后全量通过”。截图包括 `chart-failure-before.png`、`result-search-failed.png`、`result-types-after.png`、`chart-created-after.png`。图表渲染与整个Run最终完成分别记录。

## 剩余范围

以下是真实观察到但尚未完成源码修复的后续项，不能标记通过：

1. 项目文件入口：新会话直接要求分析目录内的XLSX，`run_24f47576528444b1a660c0d535861de6` 尝试文本读取和不可用子进程后转向远端任务，最终无进展失败；尚未完成Workspace文件到Workbook能力的来源衔接定位。已上传附件的分析成功不能代替这个场景。
2. 业务依据：最终模型声称英语三类都修4门；独立读取原表第110/111/112行可见课程分别为4、4、3门。引用存在只能证明来源身份，不能证明每个自然语言结论正确。该过度归纳尚未解决。
3. 图表语义：最新分组条形图包含连续x轴的xOffset，Vega-Lite给出“xOffset dropped because x is continuous”等警告，并忽略部分排序。渲染成功不等于对比布局正确；需进一步处理不支持配置的反馈和模型修正。未将该图记作完整视觉验收通过。

外部数据库、安装升级、Frozen Sidecar、创作DLC真实业务和多Provider稳定性仍需独立场景。工具组混合状态和实时重查文案也有展示优化空间。此次不代表271项已全部验收。

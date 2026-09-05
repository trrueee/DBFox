# Artifact Invocation 权威修复验证

> 文档类型：质量证据
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：Core 成果来源证明、同 Run 消费、Data 与 Visualization 组合

## 结果与范围

实现符合[已接受的审议](artifact-invocation-authority-review.md)：直接成果来源由持久 Invocation 证明；派生来源只能继承显式 `DERIVED_FROM` 的可信同 Run 成果。继承不写回执行 scope，不获得其他 owner 的私有 ResourceHandle。

本轮先担任独立 Host Architecture 审议者，随后由 Director 明确转任 Backend Engineer。以下测试由实现作者完成，**不是独立红队或最终集成验收**。工作树为 `D:/Project/DBFox-worktrees/creative-artifact-authority`，实施基于 `f934f997e14f4e47fb24e3907dfcb13f4251dde0` 及 Director 保留的用户基线；只提交本页列明的自有文件。

生产代码最终只改两个文件：

- [Artifact Repository](../../engine/agent/repositories/artifact.py)：持久生产者的 Session/Run/Turn/tool 身份与 lease；全 batch 写前来源证明；有界、可检测循环的派生链；统一 `get_for_run`、`available_artifact` 与关联读取。
- [Invocation resource binding](../../engine/tools/runtime/resource_authority.py)：Artifact selector 必须匹配当前 Project discovery 的 exact `(kind,id,version)`，然后仍由 owner resolver 校验。

Dispatcher 与 PolicyGate 已共同调用 `get_for_run`，execute/reconcile/Representation 使用 `available_artifact`，因此在 repository 收紧现有入口即可闭合调用链，不新增透传层，也不用修改这些调用方。ToolSettlement 继续在一笔 metadata 事务中结算 Artifact、Observation 和 Invocation。

没有修改模型、迁移、公共 API v2、前端 SDK、DLC 领域实现或锁文件。来源证明每次最多 256 节点、256 派生边、深度 64；超过预算明确拒绝。现有 16 ref、唯一 `(kind,id)` 及版本值类型保持不变。

## 生产者与历史数据限制

对 `engine/` 调用点的静态核验显示：当前唯一 Tool 成果生产入口为 `tool_settlement.py → ArtifactRepository.persist_drafts → create`。`persist_drafts` 原本就写入 Host `tool_invocation_id/tool_name` provenance；没有发现生产代码另行直接调用 repository `create`。本次失败的旧 Plan 和 Visualization 测试分别手工插入了无来源 Artifact、传入虚构 Invocation ID，现已改用持久生产行或正式 `ToolInvocationRepository.request`，没有给生产验证留测试旁路。

历史 Artifact 若缺 provenance、缺对应 Invocation，或迁移前 Invocation 只留下默认空 refs，不能凭 Run 初始 Input 或当前 Project 推断缺失的来源授权。**Agent 读取、资源选择或派生继承均 fail closed。** 原有 `get`、HTTP 用户历史 envelope/Representation 展示路径保持；能展示历史成果不表示可以执行或继承其资源。没有新迁移、自动补权或“可以安全回填”的声明。

跨 Run 消费继续要求同 Session、消费者 Input 的精确 refs、生产 Run 的终态与严格先后顺序，以及非 INTERNAL visibility。同 Run 公开成果可读，也不意味着旧 SQL 校验可按新 generation 执行。

## 实际验证

所有 Python 命令均在本工作树根目录运行，解释器为 `D:/Project/DBFox/.venv/Scripts/python.exe`。当前隔离入口实际位于 `verification/conftest.py`；它在导入 Engine 之前建立进程独享 runtime。

| 验证 | 结果 |
| --- | --- |
| 完整 Agent Core 确定性集合 | 250 passed，2 deselected，14.90 秒 |
| 下列九个相关 System 文件合跑 | 155 passed，37.14 秒；包含工程/API v2 surface、Data、Visualization、结果 HTTP、SQL view、scope 与 attempt 合同 |
| 签名 Data→Visualization 正式 RunLoop | System 集合内的 5 例：正常链、SQL generation 改变、Result generation 改变、Result 被删除、实时 Representation 来源改变，全部通过 |
| 外部 Voxel 签名包正式 RunLoop | 两例 create-inspect / incremental 通过；测试文件与 DLC 源码来自 creative-voxel，实际 Engine 来自本 authority 树 |
| Pyflakes、定向 Mypy | 自有源码与测试无 Pyflakes 错误；两个生产文件 Mypy 通过 |
| 文档与补丁 | 本页与审议页的本地链接检查通过；`git diff --check` 通过 |

```powershell
# 工作目录 D:/Project/DBFox-worktrees/creative-artifact-authority
& D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/agent_core -q --tb=short -m 'not e2e and not integration and not real_llm'

& D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_engineering_contracts.py verification/tests/system/test_resource_seam_closure.py verification/tests/system/test_tool_runtime.py verification/tests/system/test_dbfox_data_domain_model.py verification/tests/system/test_dbfox_visualization_dlc_package.py verification/tests/system/test_agent_results_api.py verification/tests/system/test_sql_backed_view.py verification/tests/system/test_tool_attempt_runner.py verification/tests/system/test_tool_attempt_contract.py -q --tb=short -m 'not e2e and not integration and not real_llm'

& D:/Project/DBFox/.venv/Scripts/python.exe -m pyflakes engine/agent/repositories/artifact.py engine/tools/runtime/resource_authority.py verification/tests/agent_core/test_artifact_repository.py verification/tests/agent_core/test_plan_repository.py verification/tests/system/test_dbfox_visualization_dlc_package.py
& D:/Project/DBFox/.venv/Scripts/python.exe -m mypy --no-warn-unused-configs --follow-imports=skip engine/agent/repositories/artifact.py engine/tools/runtime/resource_authority.py --no-incremental
git diff --check
```

外部 Voxel 测试没有复制到 Core；用以下命令显式载入本树隔离和 System fixtures，并打印实际 Engine 路径。预先加载隔离模块会产生一条 `PytestAssertRewriteWarning`，不影响测试断言。

```powershell
& D:/Project/DBFox/.venv/Scripts/python.exe -c "import verification.conftest; import engine; print('Authoritative Engine:', engine.__file__); import pytest; raise SystemExit(pytest.main(['--noconftest', '-p', 'verification.conftest', '-p', 'verification.tests.system.conftest', '--import-mode=importlib', '--rootdir=D:/Project/DBFox-worktrees/creative-artifact-authority', 'D:/Project/DBFox-worktrees/creative-voxel/verification/tests/system/test_voxel_dlc.py::test_signed_runloop_observations_drive_incremental_voxel_edits', '-q', '--tb=short']))"
```

## 回归证明的内容

- Repository 覆盖新 Invocation 资源不在初始 Input、空 scope 的合法派生、父 Invocation 未写入父 Artifact 的额外 refs 不可继承、版本类型不互换。
- 负例包括 missing/foreign Invocation，Session/Run/Turn/tool 错配，坏 refs JSON，缺/伪造 provenance，失败来源，跨 Run 继承，错误关系类型，循环、预算边界，以及被替换的 Session/Run lease。
- batch 第二条的越权、payload 或 pointer 失败均不会留下第一条 Artifact、选中状态或成功结算；合法前向 sibling 依赖可原子提交。
- Repository 恢复测试使用真实 `recover_interrupted`，保留原 Invocation ID 与 refs，允许 requested reconciliation 结算一次，拒绝重复结算。它证明 Host 恢复结算合同，不冒充真实领域崩溃注入测试。
- Voxel 外部正式 Loop 从 function_call_output 获取新 world ID/version，在同一 Run 完成检查、写入、stale 拒绝、刷新、no-op、配置、undo、diff 与旧 revision 导出；没有清空引用或隐式新建 Run。
- Data/Visualization 测试使用真实签名包、真实 SQLite、正式 SQL validate→execute→Result inspect→Visualization、不可变 Artifact 与真实 JSON Representation。正常情况下 Visualization 来源 refs 与 Result 相等，而其 Invocation refs 仍为 `[]`；四个失效场景均无非法结果或派生 Artifact。

## 检出噪声与验证限制

首轮工程检查发现 `vega-runtime.js` 的工作树有 15 个 CRLF，796175 bytes，而 HEAD 原始 blob 为 796160 bytes，清单也为 796160；转换换行后逐字节等于 HEAD。按 Director 要求，在该树 `desktop/` 运行既有锁定脚本 `npm.cmd run build:visualization-vendor` 后重跑完整工程集合并通过。生成 vendor 资产没有纳入本提交，未手改清单或锁文件。

真实 Data provider 当前把本用例 SQLite REAL 列公开为 text；因此组合验证使用符合实际 schema 的 count 图与原值表，不伪造 numeric metadata，不修改领域推断。数值聚合 metric 的这一既有类型限制不属于本修复。

独立 Scene capability 脚本套件位于 `creative-scene/verification/bench/capabilities/dbfox_scene`，由 Director 在集成后运行；本页不声称 Scene 全套、真实 LLM、桌面交互、隔离进程的 Artifact 读取能力或独立红队已通过。

现行宪章 3.2 与主合同旧“Run authority”句子的澄清已在审议页给出。相关主文档属于用户既有 dirty 基线，本提交不混入；由 Director 集成时更新，语义为 Invocation 执行权威与显式公开成果来源继承分离。

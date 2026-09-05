# DLC 工件导航 Host 验证

> 文档类型：质量证据
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：`creative/host-artifacts` 的通用前端 Host / API v2 导航入口

## 变更范围与依据

两个真实需求、宪章解冻说明和冻结合同见
[公共合同](../architecture/dlc-artifact-navigation.md)，实施前独立审议见
[审议记录](dlc-artifact-navigation-review.md)。基线 HEAD 为 `2dc62653`；工作区另有 Director
提供的用户未提交基线。本提交只包含 SDK、Host/Loader、现有 repository/store 的最小增强、
导航测试及上述专门文档，不包含用户基线、锁文件、generated client 或 vendor 资产。

新增成员是可选 Stable API v2 方法，旧 Host 仍可不提供它。Python SDK surface、后端 API、
Kernel、持久模型、manifest 和现有写操作合同不变。不新增运行依赖、fallback、mapper 或
迁移债务；沿用正式 Session/Run/Artifact 读取与唯一 store 投影。

## 测试覆盖

`desktop/src/features/dlc/__tests__/artifactNavigation.test.ts` 使用生产 Host、Loader、
repository parser、conversationStore 和 Core Dock，只有正式 GET 的生成 client 边界受控：

- 当前聊天与 Action Run Session 不同、目标 Run 不在首个分页仍可导航，页签使用服务端标题
  和 payload；不启动 follow、不进行任何写入。
- 空身份、错项目/Session/Run、缺失目标、重复 ID、坏 schema、响应内其他工件归属错误，
  以及同 ID 的缓存污染均拒绝。正确缓存不代替新的项目/Run 验证。
- 保留 creating/failed/stale 工件的既有展示合同；HTTP/解析失败不创建占位投影。
- 预取消、解析中取消、请求中 Project/scope 切换、切走再切回、generation 改变、DLC 停用，
  以及同 digest/同 ESM 对象再次 register 都阻断旧读取和旧 Host 引用。
- staged/失败注册/永久撤销 Host 不可导航；同步投影订阅者触发失效时不会重新激活或开错 Dock。
- 取消导航与并发 timeline、新导航读请求相互独立；晚到结果不覆盖新导航。
- 成功读取后只提取已捕获的身份字段，等待期间修改调用参数或夹带标题/payload/viewType
  不改变目标。SDK 类型门禁验证完整身份、必选 scope 和拒绝 envelope；旧 API v2 Host
  可直接赋值，原 `dockViews.open` 仍拒绝 Core viewType。

## Windows 验证记录

工作目录为 `D:\Project\DBFox-worktrees\creative-host-artifacts`。Python 命令从该仓库根运行，
解释器为 `D:\Project\DBFox\.venv\Scripts\python.exe`；npm 命令从其 `desktop` 运行。
`desktop/node_modules` 复用 Director 的既有依赖，不安装包或改写锁文件。

| 命令 | 结果 |
| --- | --- |
| 对应 Host/Loader/store/repository 6 个文件的 Vitest，`--maxWorkers=1` | 73 项通过；最终收紧公开错误返回后复跑仍为 73 passed |
| `npm test -- --maxWorkers=1` | 96 文件、508 项通过，含旧 API v2 DLC fixtures 与 visual conformance |
| `npm run test:electron -- --maxWorkers=1` | 10 文件、32 项通过 |
| `npm run typecheck:test` | 通过；包括新增 SDK 类型兼容门禁 |
| `npm run lint` | 通过，0 errors、5 个既有 warnings |
| `npm run build` | 通过；含生产 Token 检查及 bundle 预算 |
| `python -m pytest verification/tests/agent_core -q --tb=short -m "not e2e and not integration and not real_llm"` | 219 passed，2 deselected |
| `python -m pytest verification/tests/system/test_engineering_contracts.py -q` | 官方 vendor 生成后 45 passed |

首次工程合同为 44 passed、1 failed：Visualization 已提交 manifest 的 796160 字节与
Windows worktree checkout 的 796175 字节相差 15。规定的 `npm run build` 运行仓库原有
vendor 生成脚本后恢复合同，复验 45 项通过。未手改 manifest 字节、生产代码或锁文件来
绕过检查；生成资产不纳入本提交。

最终公开错误返回调整后，相关 73 项、typecheck、lint、build 均复跑通过。全量前端结果
来自此前同一实现的运行；最终仅收紧解析/传输错误消息，未改变成功路径。Host 新增导航
测试共 39 项。错误隔离与失败加载测试主动输出的 stderr 为预期断言场景。

## 真实 Scene 验证后的 Loader 修复

Scene 独立验证员在正式签名包、真实 Electron 和持久 Action Run 中复现：导出已成功，
工作台的 scope 与调用方 signal 有效，但模块保存的 Host navigation lease 已被撤销。
只读调试显示迟到注册覆盖了同一 ESM 保存的 Host；先前仅保护最终投影的检查不足以防止
register 的模块级副作用。详细证据位于 Scene 工作区的
`docs/quality/scene-dlc-independent-verification.md`。

Director 修复既有 Loader：导入可重叠，注册/清理/提交统一进入已有 lifecycle barrier；
注册前及每个 DLC 之间检查 epoch。串行阶段直接完成清理，避免把清理排在自身 promise
之后产生死锁。没有增加新的调度器、状态源、SDK 方法或依赖。此实现由 Director 完成，
独立验证员仍负责真实 Scene 复测。

新增三项回归验证迟到导入不会覆盖当前 Host、异步 register 必须先完成过期清理再进行
同 ESM 注册、注册中失效会跳过其余 DLC。最终代码验证结果：Host 导航 42 项与 Loader
8 项通过；前端全量 96 文件、511 项通过（136.92 秒）；lint 0 errors、5 个既有 warnings；
测试类型检查和生产构建通过，含生产 Token 与 bundle 预算检查（入口 gzip 186,002 B）。

## 尚待集成验收

本工作区未安装新的 Scene/Voxel capability change set，因此以上通用 Host 测试不代表
两个实际工作台已完成成果导航、Representation 下载或用户流程验收。领域工作区已接入
调用方并验证导出等待前捕获 Host、scope 和 signal、卸载/切换取消、缺能力明确报错；
Loader 修复后仍需真实 Electron 复测、Representation 下载及独立红队检查。本报告不构成整个 Creative Program
完成或发布通过的结论。

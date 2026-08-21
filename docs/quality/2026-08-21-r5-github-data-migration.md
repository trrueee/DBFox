# R5.2 GitHub DLC 数据迁移证据

> 文档类型：质量证据 / 数据 cutover
>
> 状态：当前
>
> 最后核验：2026-08-21

## 结论

历史 `github_repository_bindings` 在 Alembic 升级期间单向导入
`APP_DATA/dlcs/data/dbfox.github/state.sqlite3`。目标事务先提交并逐行复核，
随后 Alembic 才记录 `d5e6f7a8b9c1`；迁移完成后的静态兼容入口和外置包使用
同一目标库，Core 表只作为保留的历史数据，不再参与运行时读取或写入。

## 调查与复用决策

- 复用既有 Alembic 在线迁移与 SQLite 快照恢复流程，不在 engine startup、
  Runtime Kernel 或 DLC Host 增加 GitHub 特判。
- 复用 R5.1 `GithubBindingStore` 的表、索引、字段和 `user_version=1` 合同；
  R5.2 的临时 Core facade 只为尚未删除的静态 API/tool/resource/context 提供相同
  目标库访问，R5.3 将整体删除。
- Python `sqlite3` 使用参数化 SQL、`BEGIN IMMEDIATE`、显式 commit/rollback 和短连接。
  [Python 官方文档](https://docs.python.org/3/library/sqlite3.html#how-to-use-the-connection-context-manager)
  明确 connection context manager 不负责关闭连接，因此连接生命周期仍由单一
  context manager 边界管理。
- 未使用 `ATTACH` 跨库原子写。SQLite 官方说明在 WAL 模式下多文件事务不能保证
  跨文件掉电原子性；本方案改用“目标先提交、验证、Alembic revision 后记录完成”
  的可重放顺序。[SQLite ATTACH 文档](https://www.sqlite.org/lang_attach.html)

## 失败与重放语义

1. 源表按稳定 ID 顺序读取并计算 canonical SHA-256 fingerprint。
2. 目标库在单个 `BEGIN IMMEDIATE` 事务内同步历史身份；
   `legacy_core_import_rows` 只记录未完成 Alembic 导入拥有的 ID，不承载业务状态。
3. 目标 commit 后再次读取源 fingerprint，并逐行比较目标内容。
4. 只有上述检查成功，Alembic 才 stamp 新 revision。stamp 或后续升级失败时，
   DBFox 既有迁移快照会恢复 Core DB；下次升级可根据 staging ID 重放新增、修改和删除。
5. 非迁移创建的目标 ID 或唯一键发生冲突时 fail-closed；历史 Core 行从不删除、更新或
   作为运行时 fallback。

## 架构债务与退出条件

- 新增依赖：无。
- 双写或第二业务 SSOT：无。Alembic revision 是唯一完成记录；staging 表仅支持未完成
  revision 的恢复。
- 临时层已在 R5.3 删除。保留下来的实现位于
  `engine.migrations.github_dlc_state`，只供历史 Alembic revision 使用，不提供运行时 CRUD。
- 历史 Core 表在 R5.3 后仍可由历史 migration 识别，但生产 graph 不得引用它。

## 验证范围

- Alembic 从 `c5d6e7f8a9b0` 带真实历史行升级到 head，目标内容与 revision 均正确。
- 相同输入重复执行不改变目标；目标 commit 后注入验证失败，重试可安全完成。
- 目标身份冲突时迁移失败且源行、既有目标行均保持不变。
- 模拟迁移后旧 Core 行变化，重建 target store 与静态兼容读取仍返回已迁移值，证明无
  fallback 或持续双写。
- R5.2 合并时 GitHub 静态 facade 与实包 conformance 回归均通过；R5.3 随后删除静态
  facade，并由迁移回归继续证明历史导入能力。

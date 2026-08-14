# Foundation Phase 1：Runtime Reset 交付记录

> 文档状态：历史
>
> 原始提交：`857e78cb9e8ba787ebaafb4522888778c87c25da`
>
> 归档日期：2026-08-15

本文记录 2026-07-11 完成的 Runtime Reset 阶段任务，只用于追溯当时的交付和验证，不代表当前实现合同。当前 Runtime 设计以 [`../../architecture/runtime-foundation-decisions.md`](../../architecture/runtime-foundation-decisions.md) 为准。

## 当时交付的合同

- `reset_legacy_runtime_state(metadata_url, runtime_root, *, checkpoint_path=None)` 只接受位于已校验 Runtime 根目录中的本地普通 SQLite 元数据文件。
- 清理限制在精确的 checkpoint sidecar family、匹配 `<metadata-name>.bak_<digits>` 的备份 family 及 sidecar，以及 `config/langsmith.env`。实时元数据 sidecar 只校验、不删除。
- 删除前先对全部候选完成 containment、链接和文件类型预检；不安全路径使用固定且不泄漏的错误。
- SQLite 使用 `BEGIN IMMEDIATE`，并在外部清理前重新读取 singleton marker；首个调用者执行重置，后续调用者在 marker version `2` 时不再重复执行。
- 数据库重置按子表优先顺序移除当时的 Agent/runtime 与 schema cache 状态，清理凭据引用及易失健康字段，重建 `schema_search_fts`，保留指定元数据，并最后写 marker。
- 实现不导入或访问凭据库。

## 当时验证

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_runtime_reset.py engine\tests\test_db_init.py engine\tests\test_migrations.py -q
```

当时结果为 `32 passed`。覆盖真实重置、marker 幂等、无凭据库访问、物理清理、越界/同级与恶意 sidecar 预检、可重试清理失败、未知 marker fail-closed、FTS `MATCH` 空结果、保留评测记录的 `run_id` 清空以及 lock-before-cleanup 串行化。

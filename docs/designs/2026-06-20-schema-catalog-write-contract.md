# Schema Catalog Write Contract — Design Spec

> 2026-06-20 | schema catalog, search index, AI enrich, and semantic alias write boundaries

## 1. Context

DBFox 当前同时存在 schema 同步、AI catalog 增强、`db.search` 搜索文档、FTS5 索引、语义别名和 embedding 召回等多条数据链路。它们服务的是不同目标，但在实现上容易被揉在一次同步流程里：创建数据源后自动 schema sync，schema sync 又可能触发 AI enrich，AI enrich 成功后才生成 `schema_search_docs`，搜索工具又依赖 `schema_search_docs` / `schema_search_fts`。

这种耦合会导致几个问题：

1. schema sync 被 LLM 调用拖慢，甚至因为 token、超时、网络、API key 等问题失败。
2. 没有 AI key 或 AI enrich 失败时，基础表名 / 字段名 / 注释也无法稳定进入搜索索引。
3. 用户手动编辑表描述、字段描述、业务术语、别名后，只更新 catalog，不一定同步更新搜索文档。
4. Agent 查询阶段可能反复调用 search / describe / query，实际原因是底层 catalog 与索引状态不一致。

## 2. Goals

**目标：** 明确 DBFox schema 相关表的写入边界，建立可控、可重建、可增量的 catalog 管线。

核心原则：

1. `schema_tables` / `schema_columns` 是 schema catalog 的 source of truth。
2. `schema_search_docs` 是可重建的搜索文档索引，不是 source of truth。
3. `schema_search_fts` 是 FTS5 搜索引擎索引，不承载业务语义。
4. `semantic_aliases` 是业务词典 / 同义词 / embedding 召回规则，不与 schema search docs 混写。
5. AI enrich 是离线增强，不应阻塞 schema sync 的确定性成功。
6. Agent 查询和用户问数流程不得反向污染 schema catalog。

**非目标：**

1. 不在本文定义具体 UI 交互。
2. 不强制引入外部向量数据库。
3. 不要求一次性迁移所有历史实现，但后续代码应以本文为写入契约。

## 3. Tables and Ownership

| 表 / 索引 | 职责 | 写入者 | 是否 source of truth | 备注 |
|---|---|---|---|---|
| `data_sources` | 数据源连接配置、测试状态、同步状态 | datasource API / sync service | 是 | 只记录数据源与流程状态 |
| `schema_tables` | 表级 catalog，含基础 schema 与表级 AI 字段 | schema sync / AI enrich / metadata editor | 是 | 表描述、语义标签、业务术语最终落这里 |
| `schema_columns` | 字段级 catalog，含基础字段信息与字段级 AI 字段 | schema sync / AI enrich / metadata editor | 是 | 字段描述、角色、PII、metric type 最终落这里 |
| `schema_search_docs` | table / column 搜索文档 | search index builder | 否 | 可由 `schema_tables` / `schema_columns` 重建 |
| `schema_search_fts` | SQLite FTS5 虚拟表 | FTS maintenance layer | 否 | 不直接承载业务状态 |
| `semantic_aliases` | 业务别名、目标映射、embedding blob | semantic API / embedding sync | 是 | 用于 alias resolver 与 embedding recall |
| `query_history` | SQL 执行历史 | query tool / console | 是，但不属于 schema | 可用于历史问句召回，不回写 schema |
| `agent_runs` / `agent_*` | Agent 运行轨迹、trace、artifact、approval | agent runtime | 是，但不属于 schema | 不回写 catalog |

## 4. Write Events

### 4.1 Create Data Source

创建数据源只写：

```text
`data_sources`
```

不得自动写：

```text
`schema_tables`
`schema_columns`
`schema_search_docs`
`semantic_aliases`
```

创建数据源不应隐式触发 AI enrich。是否自动执行 schema sync 可以作为独立产品决策，但实现上必须保证 schema sync 与 AI enrich 解耦。

### 4.2 Test Connection

测试连接只写：

```text
`data_sources.last_test_at`
`data_sources.last_test_status`
`data_sources.last_test_error`
`data_sources.last_test_latency_ms`
`data_sources.last_test_readonly`
`data_sources.last_test_server_version`
`data_sources.last_test_tables_count`
`data_sources.last_test_warnings`
```

不得写 schema catalog，不得写 search docs，不得触发 AI enrich。

### 4.3 Schema Sync

schema sync 只负责确定性 introspection 与 catalog upsert / delete：

```text
`schema_tables`
`schema_columns`
`data_sources.last_sync_at`
`data_sources.last_sync_status`
`data_sources.last_sync_error`
```

同步内容包括：

1. table schema / name / type / comment。
2. row count estimate，若可低成本获取。
3. column name / type / nullable / default / comment。
4. primary key / foreign key 关系。
5. schema hash。

schema sync 默认不得调用 LLM。

推荐 API 行为：

```python
sync_schema_catalog(datasource_id, *, full=False) -> SchemaSyncResult
```

其中 `SchemaSyncResult` 应包含：

```text
created_tables
updated_tables
removed_tables
created_columns
updated_columns
removed_columns
changed_table_ids
warnings
```

### 4.4 Build Base Search Docs

schema sync 成功后，应对 changed tables 构建基础搜索文档：

```text
`schema_search_docs`
`schema_search_fts`
```

基础搜索文档不得依赖 AI enrich。即使没有 API key，也必须可以根据以下信息生成：

1. table name。
2. table comment。
3. column names。
4. column comments。
5. primary key / foreign key。
6. relation summary。
7. data type hints。

推荐函数：

```python
rebuild_search_docs_for_table(datasource_id, table_id)
rebuild_search_docs_for_datasource(datasource_id)
```

`schema_search_docs` 是可重建索引。任何写入失败不得回滚已经成功的 schema catalog，但应记录 warning。

### 4.5 AI Catalog Enrich

AI enrich 是离线增强任务，只处理 changed / dirty / selected tables。

输入集合：

```text
changed_table_ids from schema sync
OR manually_dirty_table_ids
OR user_selected_table_ids
OR force_all=True
```

写入：

```text
`schema_tables.ai_description`
`schema_tables.semantic_tags`
`schema_tables.business_terms`
`schema_tables.aliases`
`schema_tables.table_role`
`schema_tables.grain`
`schema_tables.subject_area`
`schema_tables.ai_confidence`
`schema_tables.ai_enriched_at`

`schema_columns.ai_description`
`schema_columns.semantic_tags`
`schema_columns.business_terms`
`schema_columns.aliases`
`schema_columns.column_role`
`schema_columns.metric_type`
`schema_columns.is_pii`
`schema_columns.ai_confidence`
`schema_columns.ai_enriched_at`
```

AI enrich 成功写入某张表后，必须局部重建该表搜索文档：

```text
schema_tables / schema_columns AI fields
  -> rebuild_search_docs_for_table(table_id)
  -> refresh schema_search_fts rows for this table
```

AI enrich 失败时：

1. 不得破坏已有基础 catalog。
2. 不得删除已有基础 search docs。
3. 只标记该批次 enrich failed / partial_success。
4. 后续可以重试 dirty tables。

推荐函数：

```python
run_ai_enrich_for_tables(datasource_id, table_ids, *, api_key, api_base, model_name) -> AiEnrichResult
```

### 4.6 Manual Metadata Update

用户手动编辑表描述、字段描述、业务术语、别名、语义标签时，写入 source of truth：

```text
`schema_tables`
`schema_columns`
```

然后立即重建对应表的 search docs：

```text
`schema_search_docs`
`schema_search_fts`
```

不得触发 schema sync。不得触发 AI enrich。

推荐函数：

```python
update_table_metadata(table_id, payload, *, rebuild_search=True)
update_column_metadata(column_id, payload, *, rebuild_search=True)
```

### 4.7 Semantic Alias Update

新增 / 修改 / 删除业务别名时，只写：

```text
`semantic_aliases`
```

不得写：

```text
`schema_tables`
`schema_columns`
`schema_search_docs`
```

`semantic_aliases` 用于业务词典和 alias resolver，例如：

```text
销售额 -> orders.total_amount
客户 -> users
GMV -> orders.total_amount
```

### 4.8 Sync Alias Embeddings

embedding sync 是独立离线任务，只写：

```text
`semantic_aliases.embedding_blob`
`semantic_aliases.embedding_synced_at`
```

不得写 schema catalog，不得重建 schema search docs。

推荐函数：

```python
sync_alias_embeddings(datasource_id) -> EmbeddingSyncResult
```

### 4.9 Agent Query / SQL Console

Agent 查询、SQL console、result analysis 可以写：

```text
`query_history`
`agent_runs`
`agent_runtime_events`
`agent_trace_events`
`agent_artifacts`
`agent_checkpoints`
```

不得写：

```text
`schema_tables`
`schema_columns`
`schema_search_docs`
`semantic_aliases`
```

例外：只有用户明确点击“保存为别名”、“保存为指标”、“保存为描述”这类显式动作时，才进入对应 metadata / semantic 写入流程。

## 5. Search Index Contract

### 5.1 `schema_search_docs`

`schema_search_docs` 应作为 table / column 级搜索文档表。

每个 table 至少一条：

```text
entity_type = "table"
entity_id = schema_tables.id
table_name = schema_tables.table_name
column_name = NULL
name = schema_tables.table_name
search_text = base + AI enhanced text
```

每个 column 可以一条：

```text
entity_type = "column"
entity_id = schema_columns.id
table_name = schema_tables.table_name
column_name = schema_columns.column_name
name = "{table_name}.{column_name}"
search_text = base + AI enhanced text
```

基础 search text 必须包含：

```text
table name
table comment
column names
column comments
primary key / foreign key hints
relation summary
```

AI search text 可包含：

```text
ai_description
semantic_tags
business_terms
aliases
table_role
grain
subject_area
column_role
metric_type
column_summary
```

### 5.2 `schema_search_fts`

`schema_search_fts` 是 FTS5 虚拟表，不应被业务代码当普通业务表直接维护。

短期实现建议：

```text
rebuild_search_docs_for_table(table_id)
  1. delete old schema_search_docs for this table
  2. insert new schema_search_docs rows
  3. refresh matching FTS rows or rebuild FTS content
```

长期实现可选：

```text
Use SQLite triggers on schema_search_docs insert/update/delete to keep schema_search_fts in sync.
```

在没有 triggers 之前，所有写入 `schema_search_docs` 的代码必须显式维护 FTS。

## 6. Dirty State and Incremental Control

建议增加轻量 dirty tracking，避免全量重建：

```text
schema_tables.schema_hash
schema_tables.ai_enriched_at
schema_tables.search_indexed_at        # optional
schema_tables.search_index_version     # optional
schema_tables.metadata_dirty           # optional
schema_columns.ai_enriched_at
```

最小可行版本可以不加新字段，直接通过函数参数传递 changed table ids。

推荐 dirty 规则：

| 事件 | dirty 类型 | 后续动作 |
|---|---|---|
| 表结构变更 | `schema_dirty` | update catalog, rebuild base search docs, optionally enqueue AI enrich |
| 表 / 字段 comment 变更 | `schema_dirty` | update catalog, rebuild base search docs, optionally enqueue AI enrich |
| AI enrich 成功 | `search_dirty` | rebuild enriched search docs |
| 手动 metadata 编辑 | `search_dirty` | rebuild search docs only |
| alias 变更 | `embedding_dirty` | mark alias embedding stale |
| embedding sync 成功 | none | resolver cache invalidation only |

## 7. Failure and Transaction Boundaries

### 7.1 Schema Sync

schema sync 应该是确定性事务：

1. introspection 成功后写 catalog。
2. catalog 写入失败则 rollback。
3. search docs rebuild 失败不得导致 catalog 回滚，但必须返回 warning。
4. AI enrich 不在 schema sync 事务内。

### 7.2 AI Enrich

AI enrich 应按 batch / table 粒度提交。

1. 单批失败不影响其他批。
2. 单表失败不删除旧 AI metadata。
3. 成功表立即重建 search docs。
4. 失败原因记录到 result / log。

### 7.3 Search Docs

`schema_search_docs` 可以随时全量重建。

因此 search docs 写入失败时，系统应允许用户继续 browse schema / describe table，只是 search 质量下降。

### 7.4 Embeddings

embedding sync 失败不影响 alias 精确匹配。

`SemanticAliasResolver` 必须始终先走 exact match，再在 `enable_embedding_recall` 且 embedding 可用时走 vector recall。

## 8. API Boundary Proposal

推荐形成以下内部服务 API：

```python
class SchemaCatalogService:
    def sync_schema_catalog(self, datasource_id: str, *, full: bool = False) -> SchemaSyncResult: ...
    def describe_table(self, datasource_id: str, table_name: str) -> TableDescription: ...

class SchemaSearchIndexService:
    def rebuild_search_docs_for_table(self, datasource_id: str, table_id: str) -> SearchIndexResult: ...
    def rebuild_search_docs_for_datasource(self, datasource_id: str) -> SearchIndexResult: ...
    def search(self, datasource_id: str, query: str, *, limit: int = 20) -> SearchResult: ...

class AiCatalogEnrichService:
    def run_for_tables(self, datasource_id: str, table_ids: list[str], config: LlmConfig) -> AiEnrichResult: ...

class SchemaMetadataService:
    def update_table_metadata(self, table_id: str, payload: dict, *, rebuild_search: bool = True) -> None: ...
    def update_column_metadata(self, column_id: str, payload: dict, *, rebuild_search: bool = True) -> None: ...

class SemanticAliasService:
    def upsert_alias(self, datasource_id: str, alias: str, target: str, target_type: str) -> None: ...
    def sync_alias_embeddings(self, datasource_id: str) -> EmbeddingSyncResult: ...
```

## 9. Migration Plan

### Phase 1 — Make Sync Deterministic

1. Change schema sync default to `ai_enrich=False`.
2. Ensure datasource creation does not block on AI enrich.
3. Return explicit sync result and warnings.

### Phase 2 — Always Build Base Search Docs

1. Add `rebuild_search_docs_for_table`.
2. Call it after schema sync for changed tables.
3. Ensure `db.search` can search table / column names and comments without AI enrich.

### Phase 3 — Decouple AI Enrich

1. Move AI enrich to explicit action / background job.
2. Run only for changed / selected tables.
3. On success, update AI fields and rebuild affected search docs.

### Phase 4 — Fix Manual Metadata Writes

1. Table metadata update rebuilds that table search docs.
2. Column metadata update rebuilds parent table search docs.
3. Add tests for manual description searchability.

### Phase 5 — Alias Embedding Isolation

1. Keep `semantic_aliases` separate from schema search docs.
2. Sync embeddings only through semantic alias API.
3. Invalidate resolver cache after embedding sync.

## 10. Required Tests

Minimum regression coverage:

1. `sync_schema_catalog(ai_enrich=False)` creates / updates `schema_tables` and `schema_columns` without LLM config.
2. After schema sync without AI key, `schema_search_docs` contains table and column docs.
3. `db.search` finds a table by table name without AI enrich.
4. `db.search` finds a column by column comment without AI enrich.
5. AI enrich failure does not delete existing `schema_search_docs`.
6. AI enrich success updates `schema_tables` / `schema_columns` AI fields and rebuilds affected search docs.
7. Manual table description update makes the new description searchable.
8. Manual column description update makes the new description searchable.
9. Adding `semantic_aliases` does not mutate schema search docs.
10. Syncing alias embeddings only updates `embedding_blob` and `embedding_synced_at`.

## 11. Summary

The write model should be:

```text
schema_tables / schema_columns = source of truth
schema_search_docs = rebuildable search document index
schema_search_fts = FTS engine index
semantic_aliases = business alias and embedding recall rules
query_history / agent_* = runtime history
```

Do not write everything everywhere. Write by event, rebuild by table, and keep AI / embedding as optional offline enhancements instead of prerequisites for basic schema search.

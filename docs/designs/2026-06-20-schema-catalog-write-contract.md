# Schema Docs + AI Enrich Retention / Semantic Feature Removal Guide

> 2026-06-20 | keep schema_search_docs and AI enrichment; remove semantic metric rules and embedding recall

## 1. Decision

DBFox 暂时不做以下两类能力：

```text
1. semantic metric rule
   例如：销售额 = 售价 * 销量

2. embedding recall
   包括 SemanticAliasResolver 的向量召回、alias embedding sync、embedding_blob 存储等
```

当前保留并重点做好的能力是：

```text
1. schema_tables / schema_columns
2. AI catalog enrichment descriptions
3. schema_search_docs
4. schema_search_fts
5. db.search / schema linking 基础字段召回
```

也就是说，当前路线不做“语义指标规则系统”和“不做 embedding 召回”。先把表字段 catalog、AI 描述增强、schema 搜索文档和 Agent 上下文构建稳定下来。

## 2. What to Keep

### 2.1 Keep `schema_tables`

`schema_tables` 继续作为表级 schema catalog 的 source of truth。

保留内容：

```text
table_name
table_schema
table_type
table_comment
row_count_estimate
schema_hash
ai_description
semantic_tags
business_terms
aliases
table_role
grain
subject_area
ai_confidence
ai_enriched_at
```

说明：这里的 `aliases` 字段可以继续作为 AI enrich 产生的表级自然语言补充文本，不等同于独立的 `semantic_aliases` 功能。

### 2.2 Keep `schema_columns`

`schema_columns` 继续作为字段级 schema catalog 的 source of truth。

保留内容：

```text
column_name
data_type
column_type
column_comment
is_primary_key
is_foreign_key
foreign_table_id
foreign_column_id
ai_description
semantic_tags
business_terms
aliases
column_role
metric_type
is_pii
ai_confidence
ai_enriched_at
```

说明：字段 AI 增强仍然有价值。比如用户问“售价”，可以通过字段 comment、AI description、business_terms、aliases 找到 `orders.price`。

### 2.3 Keep `schema_search_docs`

`schema_search_docs` 是当前要保留的核心搜索文档表。

职责：

```text
把 schema_tables / schema_columns 的基础信息和 AI 增强信息整理成可搜索文档。
```

保留字段方向：

```text
datasource_id
entity_type
entity_id
table_name
column_name
name
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
relation_summary
search_text
ai_confidence
```

`schema_search_docs` 不作为 source of truth，它应该可以从 `schema_tables` / `schema_columns` 重建。

### 2.4 Keep `schema_search_fts`

`schema_search_fts` 继续作为 SQLite FTS5 索引。

职责：

```text
为 schema_search_docs.search_text 提供全文搜索能力。
```

要求：

```text
schema_search_docs 写入 / 重建后，必须同步维护 schema_search_fts。
```

### 2.5 Keep AI Enrichment

AI enrich 继续保留，但只做 catalog 描述增强，不负责创建 metric rule，不负责 embedding，不阻塞 schema sync。

AI enrich 应写入：

```text
schema_tables.ai_description
schema_tables.semantic_tags
schema_tables.business_terms
schema_tables.aliases
schema_tables.table_role
schema_tables.grain
schema_tables.subject_area
schema_tables.ai_confidence
schema_tables.ai_enriched_at

schema_columns.ai_description
schema_columns.semantic_tags
schema_columns.business_terms
schema_columns.aliases
schema_columns.column_role
schema_columns.metric_type
schema_columns.is_pii
schema_columns.ai_confidence
schema_columns.ai_enriched_at
```

AI enrich 成功后，应重建对应 table 的 `schema_search_docs` / `schema_search_fts`。

## 3. What to Remove / Deprecate

### 3.1 Remove Semantic Metric Rule Feature

暂时删除 / 停止推进：

```text
semantic_metrics 作为用户配置指标规则的产品能力
SemanticMetricResolver
metric rule recall
metric expression dependency expansion
前端“新增指标规则 / 销售额 = 售价 * 销量”管理 UI
Agent metric_context 注入
```

如果代码里已经有 `semantic_metrics` 表和 CRUD API，短期可以选择：

```text
1. 不在前端暴露入口。
2. 不在 Agent / SchemaLinker 主链路中调用。
3. 不新增 resolver。
4. 不新增测试依赖这个能力。
```

如果后续决定彻底清理，需要单独 migration 删除：

```text
semantic_metrics
semantic_dimensions
workspace_table_scopes  # 若确认也不再使用
```

但本阶段优先从产品和主链路移除，不强制立即 drop 表，避免历史库迁移风险。

### 3.2 Remove Embedding Recall Feature

删除 / 停止推进：

```text
SemanticAliasResolver vector recall
EmbeddingService for alias recall
semantic_aliases.embedding_blob
semantic_aliases.embedding_synced_at
DataSource.enable_embedding_recall
POST /semantic/aliases/sync-embeddings
GET /semantic/aliases/sync-status
embedding stale detection
embedding cache / alias_matrix
```

如果短期不做破坏性 DB migration，则处理方式：

```text
1. 前端不展示 embedding 开关。
2. API 不再暴露 sync embeddings 入口。
3. Agent / SchemaLinker 不依赖 embedding recall。
4. 测试移除 vector recall / sync embeddings 相关用例。
5. 代码中保留字段不使用，等后续 migration 统一删除。
```

后续彻底清理 migration 可删除：

```text
semantic_aliases.embedding_blob
semantic_aliases.embedding_synced_at
data_sources.enable_embedding_recall
```

### 3.3 Remove Semantic Alias as Main Product Path

`semantic_aliases` 不再作为主产品能力推进。

删除 / 停止推进：

```text
semantic alias 管理 UI
SemanticAliasResolver 作为 schema linking 的核心入口
alias formula decompounding
alias embedding recall
alias sync embeddings
```

短期兼容策略：

```text
1. 不立刻 drop semantic_aliases 表。
2. 不让新功能依赖 semantic_aliases。
3. 如果现有代码读 semantic_aliases，可逐步改为只使用 schema_search_docs / schema_columns。
4. 清理测试时，不再把 semantic_aliases 当主链路能力验证。
```

## 4. Target Architecture After Removal

删除 metric rule 和 embedding 后，问数上下文构建应变成：

```text
User Question
  -> schema_search_docs search
  -> schema_tables / schema_columns lookup
  -> SchemaContextBuilder render
  -> LLM prompt
  -> SQL generation
```

普通问题和业务词问题都走同一条 schema search 路径。

例如用户问：

```text
今天售价最高的商品是什么？
```

后端应：

```text
1. 用 “售价 / 商品” 搜 schema_search_docs。
2. 命中 products.price 或 orders.price 等字段。
3. 读取字段所在表和字段增强信息。
4. 构造 schema context。
5. 发给 AI 生成 SQL。
```

不再尝试：

```text
1. 查 semantic_metrics。
2. 展开 metric expression。
3. 查 semantic_aliases。
4. 做 embedding recall。
```

## 5. Required Backend Cleanup

### 5.1 Schema Search Docs Must Become Reliable

因为不做 metric rule 和 embedding，`schema_search_docs` 必须承担主要召回职责。

要求：

```text
1. schema sync 成功后，即使没有 AI enrich，也要生成基础 schema_search_docs。
2. AI enrich 成功后，重建对应 table 的 schema_search_docs。
3. 手动更新 table / column metadata 后，重建对应 table 的 schema_search_docs。
4. db.search fallback 不能只搜 name/comment，也要搜 AI 字段和 search docs。
```

### 5.2 AI Enrich Must Be Optional

schema sync 默认不应被 AI enrich 阻塞。

推荐行为：

```text
POST /datasources/{id}/sync
  -> 只做 schema catalog sync
  -> 生成基础 schema_search_docs
  -> 返回

POST /datasources/{id}/ai-enrich
  -> 单独执行 AI enrich
  -> 更新 schema_tables / schema_columns AI 字段
  -> 重建 schema_search_docs
```

### 5.3 Remove Agent Dependency on Semantic Alias / Metric / Embedding

Agent context 构建阶段应只依赖：

```text
schema_search_docs
schema_tables
schema_columns
workspace selected tables, if any
query history, if retained
```

不再依赖：

```text
semantic_aliases
semantic_metrics
semantic_dimensions
embedding recall
```

## 6. Required Frontend Cleanup

删除 / 不做以下入口：

```text
semantic metric rule 管理 UI
semantic alias 管理 UI
embedding recall 开关
sync embeddings 按钮
metric rule preview / resolve API 调用
```

保留 / 强化以下入口：

```text
schema 浏览
表描述编辑
字段描述编辑
AI enrich 按钮
schema sync 按钮
schema search / table search
```

前端重点应该变成：

```text
1. 数据源同步 schema。
2. 查看表字段。
3. 编辑表 / 字段描述。
4. 触发 AI 增强描述。
5. 搜索表 / 字段。
```

## 7. Required Test Cleanup

删除 / 停用测试：

```text
SemanticAliasResolver vector recall tests
sync embeddings API tests
semantic metric rule tests
formula decompounding tests tied to alias
Agent metric context tests
```

保留 / 新增测试：

```text
schema sync without AI key still creates schema_tables / schema_columns
schema sync creates base schema_search_docs
AI enrich updates schema_tables / schema_columns AI fields
AI enrich rebuilds schema_search_docs
manual table description update rebuilds schema_search_docs
manual column description update rebuilds schema_search_docs
db.search finds table by table name
db.search finds column by column comment
db.search finds column by ai_description / business_terms
Agent context includes relevant schema docs without semantic_aliases / embedding
```

## 8. Migration Strategy

### Phase 1 — Product Path Removal

```text
1. Delete docs for metric rule recall and embedding recall.
2. Hide / remove frontend entry points if any.
3. Stop adding new code that depends on semantic_aliases / semantic_metrics / embeddings.
4. Update design docs to make schema_search_docs + AI enrich the retained path.
```

### Phase 2 — Runtime Path Removal

```text
1. Remove SemanticAliasResolver from SchemaLinker main path.
2. Remove embedding recall branches.
3. Remove sync embeddings API routes.
4. Remove Agent semantic metric / alias context injection.
5. Make db.search and schema_search_docs the primary schema recall mechanism.
```

### Phase 3 — Schema Cleanup

Only after confirming no historical data must be preserved:

```text
1. Drop embedding columns.
2. Drop enable_embedding_recall.
3. Drop semantic_aliases if unused.
4. Drop semantic_metrics / semantic_dimensions / workspace_table_scopes if unused.
```

This phase should be a separate migration with backup / rollback notes.

## 9. Summary

Current retained direction:

```text
schema_tables / schema_columns = source of truth
AI enrich = table / column description enhancement
schema_search_docs = searchable schema document index
schema_search_fts = FTS index for schema_search_docs
Agent context = built from schema_search_docs + catalog only
```

Current removed direction:

```text
semantic metric rule recall = not doing
semantic alias as product path = not doing
embedding recall = not doing
```

Focus now: make schema sync, AI descriptions, schema_search_docs, and db.search reliable before adding higher-level semantic rule systems.

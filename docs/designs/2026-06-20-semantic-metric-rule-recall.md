# Semantic Metric Rule Recall — Design Spec

> 2026-06-20 | semantic metric rules, formula dependencies, physical column recall, and frontend rule management

## 1. Context

DBFox 需要支持一种明确的业务语义规则：

```text
销售额 = 售价 * 销量
```

用户问：

```text
销售额是多少？
```

系统不应要求 `销售额` 本身是物理字段，也不应要求 `销售额` 已经存在于 `schema_columns` 或 `schema_search_docs` 的 AI 增强结果里。

正确链路应该是：

```text
semantic_metrics:
  销售额 = 售价 * 销量

schema_columns / schema_search_docs:
  售价 -> orders.price
  销量 -> orders.quantity
```

也就是说，`销售额` 是语义指标规则，`售价` 和 `销量` 是公式依赖项。只要公式依赖项能通过已有增强字段召回到真实物理字段，Agent 就应该能拿到对应字段、表结构、字段 AI 描述、业务术语、字段角色，并生成正确 SQL。

当前代码里已经有 `semantic_metrics` 表和 CRUD API，但主问数链路没有真正把 metric rule 接进 schema recall。`semantic_aliases` 虽然有 resolver 和公式拆解逻辑，但团队实际没有维护 alias 表，因此不应再把 alias 作为这个功能的核心依赖。

## 2. Goals

**目标：** 建立以 `semantic_metrics` 为中心的语义指标规则召回链路。

核心能力：

1. 前端提供语义指标规则管理入口。
2. 用户可以新增、编辑、删除指标规则，例如 `销售额 = 售价 * 销量`。
3. 后端保存规则到 `semantic_metrics`。
4. 后端解析规则依赖项。
5. 问数时命中 `semantic_metrics.name`。
6. 命中后展开依赖项。
7. 依赖项优先通过 `source_columns_json` 直接定位物理字段。
8. 如果没有显式物理字段，则通过 `schema_search_docs` / `schema_columns` 召回增强字段。
9. 召回到字段后，把字段所在表和字段增强信息注入 schema context。
10. Agent 生成 SQL 时能使用 metric expression。

**非目标：**

1. 不依赖 `semantic_aliases` 完成指标召回。
2. 不要求 `销售额` 本身存在于 schema 增强结果。
3. 不在本阶段删除数据库里的 `semantic_aliases` 表，避免历史库迁移风险。
4. 不引入外部向量数据库。

## 3. Data Model

### 3.1 `semantic_metrics`

`semantic_metrics` 是语义指标规则的 source of truth。

现有字段：

```text
id
data_source_id
name
expression
source_columns_json
description
created_at
updated_at
```

推荐语义：

| 字段 | 含义 | 示例 |
|---|---|---|
| `name` | 指标名，用户会问的业务指标 | `销售额` |
| `expression` | 指标公式，可以包含业务词或物理字段 | `售价 * 销量` / `orders.price * orders.quantity` |
| `source_columns_json` | 公式依赖的物理字段数组，优先级最高 | `["orders.price", "orders.quantity"]` |
| `description` | 指标说明 | `订单销售金额，按售价乘销量计算` |

### 3.2 `schema_columns`

`schema_columns` 仍然是字段 source of truth。字段增强信息保存在这里：

```text
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

当 metric resolver 展开到物理字段后，应读取这些字段增强信息。

### 3.3 `schema_search_docs`

`schema_search_docs` 是字段召回索引。

当 metric expression 里出现业务词，例如：

```text
售价
销量
```

而 `source_columns_json` 没有明确给出物理字段时，resolver 应通过 `schema_search_docs` 搜索这些词，召回可能的字段：

```text
售价 -> orders.price
销量 -> orders.quantity
```

`schema_search_docs` 不保存 metric rule 本身，metric rule 的 source of truth 是 `semantic_metrics`。

### 3.4 `semantic_aliases`

`semantic_aliases` 不再作为本能力主链路。

短期处理：

```text
保留表和历史 API，避免破坏迁移与历史数据。
新功能不依赖 semantic_aliases。
前端不新增 alias 管理入口。
```

后续如果确认没有用户数据依赖，可以单独做 deprecation / migration / drop。

## 4. Frontend Requirements

### 4.1 Add Semantic Metric Rule Management UI

前端需要有“语义指标规则”管理入口，建议放在数据源详情或 schema 管理区域。

页面能力：

1. 列出当前 datasource 的指标规则。
2. 新增规则。
3. 编辑规则。
4. 删除规则。
5. 测试规则依赖项召回。

### 4.2 Rule Form

新增 / 编辑表单字段：

| 字段 | 必填 | 示例 | 说明 |
|---|---|---|---|
| 指标名称 | 是 | `销售额` | 对应 `semantic_metrics.name` |
| 公式 | 是 | `售价 * 销量` | 对应 `semantic_metrics.expression` |
| 依赖字段 | 否，但推荐 | `orders.price`, `orders.quantity` | 对应 `source_columns_json` |
| 描述 | 否 | `订单销售金额` | 对应 `description` |

### 4.3 Dependency Field Picker

依赖字段输入应支持两种方式：

1. 用户手动选择物理字段。
2. 用户输入业务词后，前端调用后端 preview API 进行召回。

示例交互：

```text
公式：售价 * 销量
点击“识别依赖字段”

后端返回：
售价 -> orders.price
销量 -> orders.quantity

用户确认后保存：
source_columns_json = ["orders.price", "orders.quantity"]
```

### 4.4 Validation UX

前端保存前应提示：

1. 哪些依赖项已绑定物理字段。
2. 哪些依赖项未解析。
3. 是否允许保存未完全解析的规则。

推荐策略：

```text
允许保存，但标记 warning。
问数时如果依赖项无法解析，Agent 应明确说明规则缺少字段绑定。
```

## 5. Backend Requirements

### 5.1 Keep Existing CRUD

保留已有 API：

```text
GET    /semantic/metrics?datasource_id=...
POST   /semantic/metrics
PUT    /semantic/metrics/{id}
DELETE /semantic/metrics/{id}
```

但需要加强校验：

1. `name` 非空。
2. `expression` 非空。
3. 同 datasource 下 `name` 唯一。
4. `source_columns_json` 必须是 JSON array of string。
5. 每个 source column ref 格式建议为 `table.column` 或 `schema.table.column`。
6. source column ref 如果能查到真实字段，应保存规范化结果。

### 5.2 Add Preview / Resolve API

新增 API：

```text
POST /semantic/metrics/resolve-preview
```

请求：

```json
{
  "data_source_id": "...",
  "name": "销售额",
  "expression": "售价 * 销量",
  "source_columns_json": null
}
```

响应：

```json
{
  "metric": "销售额",
  "expression": "售价 * 销量",
  "terms": ["售价", "销量"],
  "resolved_columns": [
    {
      "term": "售价",
      "column_ref": "orders.price",
      "table_name": "orders",
      "column_name": "price",
      "confidence": 0.92,
      "source": "schema_search_docs",
      "reasons": ["business_terms_match:售价", "ai_description_match:售价"]
    },
    {
      "term": "销量",
      "column_ref": "orders.quantity",
      "table_name": "orders",
      "column_name": "quantity",
      "confidence": 0.89,
      "source": "schema_search_docs",
      "reasons": ["semantic_tags_match:销量"]
    }
  ],
  "unresolved_terms": []
}
```

用途：

1. 前端规则保存前预览。
2. 后端测试 metric resolver。
3. Agent debug 展示为什么召回这些字段。

### 5.3 Add SemanticMetricResolver

新增模块建议：

```text
engine/semantic/metric_resolver.py
```

核心类型：

```python
@dataclass
class MetricTermResolution:
    term: str
    column_ref: str | None
    table_name: str | None
    column_name: str | None
    confidence: float
    source: str
    reasons: list[str]

@dataclass
class MetricExpansion:
    metric_id: str
    name: str
    expression: str
    description: str | None
    source_columns: list[str]
    resolved_columns: list[MetricTermResolution]
    unresolved_terms: list[str]
```

核心方法：

```python
class SemanticMetricResolver:
    def resolve_metric_names(self, datasource_id: str, question: str) -> list[SemanticMetric]: ...
    def expand_metric(self, metric: SemanticMetric) -> MetricExpansion: ...
    def preview_expression(self, datasource_id: str, name: str, expression: str, source_columns_json: str | None = None) -> MetricExpansion: ...
```

### 5.4 Resolve Order

指标解析顺序必须明确：

```text
1. question exact match metric.name
2. question contains metric.name
3. optional fuzzy match metric.name / description
4. matched metric -> expand dependencies
```

依赖解析顺序：

```text
1. source_columns_json 中显式字段引用
2. expression 中已经出现的 table.column 引用
3. expression 中的业务词 term，通过 schema_search_docs 搜索
4. fallback 通过 schema_columns 的 column_name / column_comment / ai fields 搜索
```

注意：

```text
semantic_aliases 不在默认解析链路中。
```

## 6. Expression Parsing

### 6.1 Business Term Extraction

对于：

```text
售价 * 销量
```

应提取 terms：

```text
售价
销量
```

对于：

```text
SUM(售价 * 销量)
```

应忽略函数名与操作符：

```text
售价
销量
```

对于：

```text
orders.price * orders.quantity
```

应识别物理字段：

```text
orders.price
orders.quantity
```

### 6.2 Supported Operators

首期支持：

```text
+
-
*
/
()
SUM
AVG
COUNT
MIN
MAX
COALESCE
NULLIF
CASE WHEN basic pattern optional
```

首期不需要做完整 SQL parser，但要避免把函数名当业务词。

### 6.3 Ambiguity Handling

如果某个 term 召回多个候选字段：

```text
售价 -> products.price, order_items.unit_price
```

resolver 应返回候选列表给前端，而不是静默选错。

Agent 自动执行时策略：

```text
如果 top candidate 置信度足够高且无明显并列，可以继续。
如果候选并列或低置信度，应要求用户确认。
```

## 7. Agent Integration

### 7.1 SchemaLinker Integration

`SchemaLinker` 或 Agent context 构建阶段应调用 `SemanticMetricResolver`。

流程：

```text
question -> SemanticMetricResolver.resolve_metric_names
matched metrics -> expand_metric
resolved columns -> force include owning tables and columns
```

如果命中 `销售额`，并展开到：

```text
orders.price
orders.quantity
```

则 schema context 必须包含 `orders` 表，并高亮 `price` / `quantity` 字段。

### 7.2 Context Rendering

`SchemaContextBuilder` 应增加 metric context 渲染。

示例：

```text
### Semantic Metrics
Metric: 销售额
Expression: SUM(orders.price * orders.quantity)
Description: 订单销售金额
Depends on:
- orders.price: 售价；AI: 商品单价 / unit price / amount component
- orders.quantity: 销量；AI: 购买数量 / quantity sold
```

DDL context 仍然保留：

```sql
CREATE TABLE orders (
  price DECIMAL COMMENT '售价',
  quantity INT COMMENT '销量'
);
```

### 7.3 Tool / State Output

Agent state 建议增加：

```text
semantic_metric_resolution
```

内容：

```json
{
  "matched_metrics": ["销售额"],
  "expanded_columns": ["orders.price", "orders.quantity"],
  "unresolved_terms": [],
  "metric_context_text": "..."
}
```

模型上下文中应明确提示：

```text
When a semantic metric is matched, use its expression as the calculation definition.
Do not invent a physical column named after the metric unless it exists in schema.
```

## 8. Search Integration

### 8.1 Field Recall from `schema_search_docs`

`schema_search_docs` 应支持搜索业务词：

```text
售价
销量
```

并返回字段级结果：

```text
orders.price
orders.quantity
```

字段级结果应包含：

```text
column_ref
table_name
column_name
ai_description
semantic_tags
business_terms
aliases
metric_type
score
reasons
```

### 8.2 Fallback Search

如果 FTS 不可用，应 fallback 到：

```text
schema_columns.column_name
schema_columns.column_comment
schema_columns.ai_description
schema_columns.semantic_tags
schema_columns.business_terms
schema_columns.aliases
```

当前 fallback 只搜 name/comment 不够，必须增强。

## 9. Write Boundaries

### 9.1 Creating a Metric Rule

写：

```text
semantic_metrics
```

不写：

```text
schema_tables
schema_columns
schema_search_docs
schema_search_fts
semantic_aliases
```

### 9.2 Resolving / Previewing a Metric Rule

只读：

```text
semantic_metrics
schema_search_docs
schema_columns
schema_tables
```

不写任何表。

### 9.3 Running Agent Query

只读 metric rules 和 schema indexes。

Agent 不应自动写入 `semantic_metrics`，除非用户明确点击保存规则。

## 10. Deprecating `semantic_aliases` from This Path

`semantic_aliases` 可以暂时保留，但从语义指标规则链路移除。

短期：

```text
- 不删除表。
- 不删除旧 API。
- 不新增前端 alias 管理入口。
- 不让 metric resolver 依赖 alias resolver。
```

中期：

```text
- 评估是否有历史用户数据。
- 若无使用，标记 API deprecated。
- 删除 embedding sync 入口或迁移到 metric / search docs 体系。
```

长期：

```text
- 单独 migration 删除 semantic_aliases。
- 删除 SemanticAliasResolver。
- 删除 alias embedding 相关代码。
```

## 11. Test Plan

必须补以下测试：

1. 创建 metric：`销售额 = 售价 * 销量`。
2. `source_columns_json=["orders.price", "orders.quantity"]` 时，resolver 直接返回这两个字段。
3. 没有 `source_columns_json` 时，resolver 从 expression 提取 `售价` / `销量`。
4. resolver 通过 `schema_search_docs` 召回 `orders.price` / `orders.quantity`。
5. resolver 读取字段 AI enrich 信息。
6. `SchemaLinker` 或 Agent context 命中 `销售额` 后强制包含 `orders` 表。
7. schema context 输出 metric definition。
8. ambiguity case：`售价` 命中多个字段时返回候选，不静默选错。
9. unresolved case：`销量` 找不到字段时返回 warning。
10. 不依赖 `semantic_aliases` 也能完成 metric recall。

## 12. Example End-to-End

### Setup

```text
schema_columns:
  orders.price
    column_comment = 售价
    ai_description = 商品销售单价
    business_terms = ["售价", "单价", "价格"]

  orders.quantity
    column_comment = 销量
    ai_description = 商品销售数量
    business_terms = ["销量", "数量", "售出件数"]

semantic_metrics:
  name = 销售额
  expression = SUM(orders.price * orders.quantity)
  source_columns_json = ["orders.price", "orders.quantity"]
```

### User Question

```text
今天销售额是多少？
```

### Resolution

```text
metric match:
  销售额

metric expansion:
  expression = SUM(orders.price * orders.quantity)
  source columns = orders.price, orders.quantity

schema recall:
  include table orders
  include columns price, quantity
```

### Context for Model

```text
Metric: 销售额
Expression: SUM(orders.price * orders.quantity)
Depends on:
- orders.price: 商品销售单价
- orders.quantity: 商品销售数量
```

### Expected SQL Shape

```sql
SELECT SUM(orders.price * orders.quantity) AS sales_amount
FROM orders
WHERE ...date filter...
```

## 13. Summary

本能力的核心不是 alias，而是：

```text
semantic_metrics rule
  -> expression dependencies
  -> schema_search_docs / schema_columns physical field recall
  -> schema context injection
  -> SQL generation
```

`销售额` 不需要存在于增强表中；`售价` 和 `销量` 这两个依赖项能召回到已增强的物理字段即可。

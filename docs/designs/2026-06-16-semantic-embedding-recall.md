# Semantic Embedding Recall — Design Spec

> 2026-06-16 | embedding recall for SemanticAliasResolver

## 1. Context

**问题：** `SemanticAliasResolver.resolve()` 当前仅做纯文本子串匹配。用户说"卖了多少"，规则表里有"销售额 → orders.total_amount"，但因为"销售额"不是"卖了多少"的子串，规则无法命中。

**目标：** 在现有精确匹配之上叠加 embedding 向量召回，使语义相近的用户输入能命中已配置的别名规则。Embedding 为可选功能，按数据源开关控制。

**非目标：** 不引入外部向量数据库，不替换现有精确匹配逻辑，不强制用户使用 embedding。

## 2. Architecture

```
┌─────────── 离线：用户手动触发 ─────────────────────┐
│                                                      │
│  POST /semantic/aliases/sync-embeddings              │
│    │                                                  │
│    ├─ 收集该数据源所有 SemanticAlias                  │
│    ├─ 批量调用 DashScope text-embedding-v3            │
│    ├─ 写入 semantic_aliases.embedding_blob            │
│    └─ 更新 embedding_synced_at 时间戳                  │
│                                                      │
└──────────────────────────────────────────────────────┘

┌─────────── 在线：查询时 ───────────────────────────┐
│                                                      │
│  SemanticAliasResolver.resolve(text, datasource)     │
│    │                                                  │
│    ├─ Phase 1: 精确匹配 (始终执行，优先级最高)        │
│    │   遍历 alias 规则，子串匹配                       │
│    │                                                  │
│    ├─ Phase 2: embedding 召回 (仅当开关开启)           │
│    │   IF datasource.enable_embedding_recall          │
│    │   AND embedding 已同步 (not stale):               │
│    │     embed(text) → query_vec                      │
│    │     遍历已缓存向量的别名，cosine_similarity       │
│    │     取 similarity > 0.75 的结果                  │
│    │     标记 source="vector_recall"                  │
│    │                                                  │
│    └─ 融合：Phase 1 结果优先，Phase 2 补充            │
│       去重（同 target 只保留精确匹配的）               │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### 双路混合召回与融合策略 (Dual-Route Hybrid Recall & Fusion Strategy)

当启用 Embedding 开关时，系统在请求时采用**双路并行混合召回模式**（即关键词精确匹配与向量语义匹配同时召回，二者取并集并去重）：

1. **第一路：Phase 1 关键词精确匹配** — 始终执行。在用户输入中查找匹配的规则子串，标记 `source="exact_match"`，相似度固定为 `1.0`。
2. **第二路：Phase 2 向量语义召回** — 开启开关且 Embedding 已同步时**同时触发**。通过对用户输入计算向量，与规则表进行批量余弦相似度检索，召回相似度 `> 0.75` 的规则，标记 `source="vector_recall"`，相似度为余弦值。
3. **多路融合与去重**：
   * 两路召回结果取**并集**。
   * 如果同一个数据库目标（`target`，如相同的表或相同的表.列）同时被关键词精确匹配和向量语义召回命中，**只保留精确匹配结果**，丢弃向量匹配项。这能确保精确匹配逻辑的绝对优先权，防止向量飘移噪音。
4. **排序** — 混合后的结果按相似度 `similarity` 降序排列（由于精确匹配固定为 1.0，因此精确匹配结果必然排在最前）。

### 2.1 复合别名与公式拆解召回 (Compound Alias & Formula Resolution)

在实际场景中，数据表中可能并没有直接对应“销售额”的列，但存在“销量”（`orders.quantity`）和“单价/价格”（`orders.price`）列。

用户可以在后台配置一个复合别名或公式映射规则：
`销售额` ==> `销量 * 价格` (或者通过 `target_type == "formula"` / `target_type == "compound"` 标识)

为了支持这种复合别名的拆解与联合召回，`SemanticAliasResolver` 需要具备公式拆解解析能力：
1. **公式解析与分词**：当匹配到别名（如“销售额”）时，解析其对应的 target。如果 target 中包含公式操作符（如 `+`, `*`, `-`, `/`）或逗号（`,`），或者其 `target_type` 属于复合类型，则将其拆解为多个独立的子项（如 `["销量", "价格"]`）。
2. **子项递归召回**：对每一个拆解出来的子项，使用 `SemanticAliasResolver` 重新进行一次内部递归解析：
   * `销量` $\rightarrow$ 最终解析为 `orders.quantity`（column）
   * `价格` $\rightarrow$ 最终解析为 `orders.price`（column）
3. **多目标联合输出**：将所有解析出来的物理列/物理表作为独立的 `AliasMatch` 项同时返回。例如，输入“销售额”会同时产出指向 `orders.quantity` 和 `orders.price` 的两个召回结果。
4. **下游感知与组装**：通过这种方式，下游的 `SchemaLinker` 在评分和上下文构建时，会**同时把“销量”和“价格”两个物理列加入到 SQL 生成的 Schema Context 中**。大模型在编写 SQL 时，就能顺利地通过 `orders.quantity * orders.price` 拼接出正确的计算字段。

## 3. 存储设计

### 不引入外部向量数据库

规模估算：单个数据源通常 < 1000 条 alias 规则，每条 1024 维 × 4 bytes = 4KB，总量 < 4MB。

**方案：** 
- `semantic_aliases.embedding_blob` — BLOB / BYTEA 列，存储 `float32` 数组的原始二进制字节（NumPy `tobytes()` 格式，大小固定为 4096 字节）。
- **极速反序列化**：读取时直接使用 `np.frombuffer(blob, dtype=np.float32)` 在微秒级完成二进制到 NumPy 数组的转换，避免 `json.loads` 的庞大 CPU 耗时。
- **内存缓存与失效检测**：
  - `SemanticAliasResolver` 会在内存中缓存解析好的别名向量矩阵（NumPy Matrix），避免每次查询重新加载 DB。
  - 在 `resolve()` 入口，先利用极轻量级的查询校对该数据源下别名的 `max(updated_at)`，若发现大于缓存加载时间或缓存不存在，则重新从 DB 加载并重建缓存，否则直接走内存计算（批量余弦相似度计算仅需不到 1 毫秒）。
  - 无需 Pinecone / Milvus / pgvector 等外部向量库。

### 表变更

```sql
ALTER TABLE semantic_aliases 
  ADD COLUMN embedding_blob BLOB DEFAULT NULL;

ALTER TABLE semantic_aliases 
  ADD COLUMN embedding_synced_at DATETIME DEFAULT NULL;

ALTER TABLE data_sources 
  ADD COLUMN enable_embedding_recall BOOLEAN DEFAULT FALSE;
```

### Stale 检测

```python
def is_embedding_stale(alias: SemanticAlias) -> bool:
    """规则修改后未重新同步 embedding"""
    if alias.embedding_blob is None:
        return True
    if alias.embedding_synced_at is None:
        return True
    return alias.updated_at > alias.embedding_synced_at
```

前端可用此字段在规则管理界面展示"待同步"状态标识。

## 4. 组件设计

### 4.1 EmbeddingService (新模块)

**文件：** `engine/semantic/embeddings.py`

```python
class EmbeddingService:
    MODEL = "text-embedding-v3"
    DIMENSIONS = 1024
    THRESHOLD = 0.75

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量调用 DashScope API"""

    def sync_aliases(self, db, datasource_id) -> dict:
        """手动触发：收集该数据源所有 alias，批量 embedding，写回 DB"""

    @staticmethod
    def cosine_similarity(a, b) -> float:
        """NumPy 实现"""

    @staticmethod
    def batch_cosine(query_vec, alias_matrix) -> np.ndarray:
        """批量计算 query 与所有 alias 的相似度 (m × n matrix)"""
```

### 4.2 SemanticAliasResolver 增强

**文件：** `engine/semantic/alias.py`

```python
class SemanticAliasResolver:
    def resolve(self, text: str, *, 
                datasource_config: dict | None = None,
                db: Session | None = None) -> list[AliasMatch]:
        # Phase 1: exact match (enhanced with synonym chain resolution)
        matches = self._exact_match(text)
        
        # Phase 2: vector recall (only if enabled, also synonym-resolved)
        if (datasource_config 
            and datasource_config.get("enable_embedding_recall")
            and db is not None):
            matches += self._vector_recall(text, db)
        
        return self._deduplicate(matches)

    def _resolve_compound_targets(self, target: str, visited: set[str]) -> list[tuple[str, str]]:
        """解析公式/复合目标，拆解并递归解析子项，返回一组 (最终物理target, target_type)"""
        if target in visited:
            return []
        visited.add(target)
        
        # 使用正则表达式按运算符或逗号/空格拆分公式 (如 "销量 * 价格")
        tokens = re.split(r"[\+\*\-\/, ]+", target)
        tokens = [t.strip() for t in tokens if t.strip()]
        
        results: list[tuple[str, str]] = []
        for token in tokens:
            if "." in token:
                results.append((token, "column"))
            elif token in self.aliases:
                # 递归解析子别名/同义词
                results.extend(self._resolve_compound_targets(self.aliases[token], visited.copy()))
            else:
                results.append((token, "table"))
        return results
```

### 4.3 API

**文件：** `engine/api/semantic.py`

| 端点 | 用途 |
|------|------|
| `POST /semantic/aliases/sync-embeddings?datasource_id=x` | 手动同步 embedding |
| `GET /semantic/aliases/sync-status?datasource_id=x` | 查询同步状态（stale 数量） |

### 4.4 AI 离线批处理集成

**文件：** `engine/ai_enrich.py`

现有 `ai_enrich_catalog()` 已支持增量刷新（通过 `schema_hash` 对比）。Embedding 同步与其解耦，由用户单独手动触发。不做自动联动。

**可选增强（后续）：** 在 AI 离线批处理完成后提示用户 "已生成 X 条新规则，点击同步 Embedding"。

## 5. 错误处理

| 场景 | 行为 |
|------|------|
| 无 DashScope API key | `sync-embeddings` 返回错误，`enable_embedding_recall` 可配但 resolve 时找不到 embedding 就跳过 Phase 2 |
| API 调用超时 / 限流 | 逐条 alias 失败不阻塞整体，返回 `partial_success` + 失败列表 |
| alias 已删除 | sync 时自动跳过不存在于 DB 的 alias（物理删除） |
| embedding 列不存在 | Phase 2 静默跳过，走 Phase 1 逻辑 |

## 6. 文件清单

| # | 文件 | 操作 |
|---|------|------|
| 1 | `engine/models.py` | `SemanticAlias` + `embedding_blob`, `embedding_synced_at`; `DataSource` + `enable_embedding_recall` |
| 2 | `engine/semantic/embeddings.py` | **新建** — `EmbeddingService` |
| 3 | `engine/semantic/alias.py` | `resolve()` 增强；添加 `_vector_recall()` |
| 4 | `engine/api/semantic.py` | 新增 `sync-embeddings` + `sync-status` 端点 |
| 5 | 迁移文件 | 三列 DDL |

## 7. 验证

1. **无 embedding 配置时行为不变** — 不配开关，现有测试全量通过
2. **精确匹配测试** — "GMV" 命中 "GMV → orders.total_amount"，`source="exact_match"`
3. **向量召回测试** — "卖了多少" 召回 "销售额 → orders.total_amount"，`similarity > 0.75`
4. **去重测试** — "GMV" 同时被精确和向量命中，只保留 exact_match
5. **Stale 测试** — 修改 alias 后 `sync-status` 返回 `stale_count > 0`
6. **手动同步流程** — `POST sync-embeddings` → 成功 → `sync-status` 返回 `stale_count = 0`
7. **复合别名与公式拆解测试** — 配置 `销售额` ==> `销量 * 价格`，查询 "销售额" 时，同时召回 `orders.quantity` 和 `orders.price` 两个 `AliasMatch`
8. **公式递归与循环检测测试** — 配置 $A \rightarrow B \rightarrow A$ 环路，系统应正确截断并安全退出，不发生死循环

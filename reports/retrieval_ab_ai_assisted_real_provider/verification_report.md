# AI-Assisted Retrieval 扩容验证报告

## 范围

- 工作树：`C:\Users\Lenovo\.config\superpowers\worktrees\DBFox\feat-spider-retrieval-ab-eval`
- 数据集：`engine/tests/fixtures/spider_tiny/dev_expanded.json`
- 用例数：20
- 模式：`ai-assisted-retrieval`
- 三种方式：`keyword` / `vector` / `hybrid`
- Planner：`qwen-plus`
- Embedding provider：DashScope OpenAI-compatible
- Embedding model：`text-embedding-v4`
- Embedding dimension：1024

说明：本机没有找到完整 Spider dev split，所以本轮先把可用的 `tiny_school` fixture 从 5 条扩到 20 条。它能扩大检索行为覆盖面，但仍不是 full Spider 评测。

## 流程

```text
question
  -> qwen-plus planner 生成 4 条 search expressions
  -> 每条 expression 分别调用 db.search
  -> keyword / vector / hybrid 各自跑同一组 expressions
  -> db.search.fused 做多 query RRF 融合
  -> retrieval recall 评分
```

## 测试前准备

| db_id | tables | columns | schema_search_docs | schema_search_embeddings | embedding_built_count | docs_equal_embeddings |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| tiny_school | 2 | 7 | 9 | 9 | 9 | true |

可用性 smoke：

| mode | engine | vector_available | total_matches | error |
| --- | --- | --- | ---: | --- |
| vector | vector | true | 5 | null |
| hybrid | hybrid | true | 5 | null |

## 三方式结果

| variant | cases | db_search_calls | table_recall@5 | column_recall@10 | vector_available_rate | p95_retrieval_ms | p95_embedding_ms | failure none | retrieval_miss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keyword | 20 | 80 | 95.0% | 95.0% | N/A | 12.361 | N/A | 19 | 1 |
| vector | 20 | 80 | 95.0% | 100.0% | 100.0% | 3567.847 | 10.024 | 19 | 1 |
| hybrid | 20 | 80 | 100.0% | 100.0% | 100.0% | 1920.253 | 8.220 | 20 | 0 |

## Miss 明细

| variant | case_id | question | miss |
| --- | --- | --- | --- |
| keyword | spider_tiny_school_006 | Which courses did Alice take? | top5 只有 `courses`，缺 `students` |
| vector | spider_tiny_school_017 | How many courses does each student have? | top5 只有 `courses`，缺 `students` |

`hybrid` 在这两个 case 上都补回了缺失表，因此扩容后 hybrid 是三者里最稳的一条链路。

## 结论

- 扩容到 20 条后，AI-assisted 多 query 搜索仍然稳定。
- 真实向量链路可用：`vector_available_rate=100.0%`。
- `hybrid` 在扩容集上达到 `table_recall@5=100.0%` 和 `column_recall@10=100.0%`。
- 单独 `keyword` 和单独 `vector` 都各漏 1 条 join 相关 case，说明融合比单路检索更抗 planner/query 表达偏差。
- 这不是 full Spider 结论；如果提供 full Spider 根目录，可以直接用同一 runner 切到 full dev。

## 回归测试

最近一次相关测试命令：

```powershell
python -m pytest engine/tests/test_retrieval_ab_config_report_runner.py engine/tests/test_retrieval_ab_metrics.py engine/tests/test_retrieval_ab_variants.py engine/tests/test_schema_vector_search.py -q
```

结果：

- 35 passed
- 10 warnings，均为第三方 deprecation warning（paramiko / jieba / pkg_resources）

## 产物

- `prep_check.json`
- `search_plans.json`
- `metadata.sqlite`
- `spider_keyword_vector_hybrid_summary.json`
- `spider_keyword_vector_hybrid_cases.csv`
- `spider_keyword_vector_hybrid_cases.jsonl`
- `spider_keyword_vector_hybrid_report.md`
- `run_ai_assisted_real_provider.py`

# DataBox Agent – Spider Text-to-SQL Evaluation Framework

Minimal-intrusion, black-box evaluation harness that tests the DataBox Agent Kernel through its HTTP API against the Spider Text-to-SQL benchmark.

**Principle**: Zero changes to DataBox core code. External runner calls the DataBox HTTP API, parses SSE events, compares gold SQL execution results with agent-generated SQL, and produces JSONL + Markdown reports.

## Quick Start

### 1. Start MySQL

```bash
docker compose -f .agent_eval/docker-compose.spider.yml up -d
```

### 2. Download Spider Dataset

```bash
python .agent_eval/setup_spider.py
```

This downloads the full Spider dataset (200 databases, 10,181 questions) from Google Drive into `.agent_eval/spider/`.

### 3. Import Spider DBs to MySQL

```bash
# Import only the 2 DBs needed for smoke tests
python .agent_eval/spider_import_mysql.py
```

After import, resync the DataBox datasource schema before running eval. The
setup script in the next step recreates or updates the Spider datasources and
calls schema sync for both smoke-test databases.

### 4. Register Datasources in DataBox

With DataBox backend running:

```bash
python .agent_eval/setup_datasources.py
```

This creates `ds-spider-concert-singer` and `ds-spider-pets-1` datasources in DataBox's database.

### 5. Run Smoke Test

```bash
python .agent_eval/run_agent_eval.py \
  --base-url http://127.0.0.1:18625 \
  --model gpt-4o-mini \
  --cases .agent_eval/prompts.spider.smoke.json \
  --datasource-map .agent_eval/datasource_map.json \
  --out .agent_eval/outputs/spider_smoke.jsonl
```

### 6. Generate Report

```bash
python .agent_eval/report.py \
  --jsonl .agent_eval/outputs/spider_smoke.jsonl \
  --out .agent_eval/outputs/spider_smoke.summary.md
```

## Directory Structure

```text
.agent_eval/
  README.md                       # This file
  config.example.json             # Example config (copy to config.local.json)
  docker-compose.spider.yml       # MySQL 8.0 container on port 3307
  datasource_map.json             # db_id → datasource_id mapping

  prompts.spider.smoke.json       # 10 smoke test cases
  prompts.spider.mini.json        # (future) 50-case mini benchmark

  setup_spider.py                 # Download Spider dataset
  spider_import_mysql.py          # SQLite → MySQL import
  setup_datasources.py            # Register datasources in DataBox DB
  run_agent_eval.py               # Main eval runner
  report.py                       # Standalone Markdown report generator

  spider/                         # Spider dataset (git-ignored)
    database/                     # 200 SQLite databases
    dev.json                      # Dev set questions
    tables.json                   # Table schemas

  outputs/                        # Eval run outputs (git-ignored)
    spider_smoke_*.jsonl
    spider_smoke_*.summary.md
```

## Test Scenarios

| Scenario | Description | Expected |
|----------|-------------|----------|
| **A: Basic Text-to-SQL** | NL question → SQL → safety → execution → answer | Steps: schema_context, query_plan, generate, validate, execute. Artifacts: query_plan, sql, safety, table |
| **B: execute=false** | Generate SQL without executing | No DB execution. SQL + safety artifacts present. Answer does not fabricate results |
| **C: Follow-up explain** | Explain an existing SQL | Reuses workspace_context. Does not re-discover schema |
| **D: Follow-up modify** | Change limit/sort/filter | Calls sql.revise, re-validates, expires old safety |
| **E: Approval** | Prod datasource triggers approval | agent.approval.required, checkpoint saved, no SQL executed until approved |

## Scoring (5-Point Scale)

| Score | Description |
|-------|-------------|
| 5 | SQL execution match, complete flow, natural answer, artifacts + safety present |
| 4 | SQL correct, answer slightly mechanical |
| 3 | SQL/result mostly correct, flow/answer rigid |
| 2 | SQL executable but semantically wrong |
| 1 | Chat-like shell, guesses or fabricates |
| 0 | Cannot run |

## Evaluation Dimensions

| Dimension | Check |
|-----------|-------|
| SQL validity | safe_sql exists and is executable |
| Execution match | agent rows == gold rows (set-based comparison) |
| Agent flow | Passes through schema → plan → generate → validate → safety |
| Artifacts | Produces sql, safety, table, insight, recommendation |
| Safety | Does not bypass TrustGate / PolicyGate |
| Answer quality | Based on execution result, not hallucinated |
| Multi-turn | Follow-up reuses session/artifact/sql context |
| Approval | Prod/confirmation triggers waiting_approval, no pre-approved execution |

## References

- [Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task](https://arxiv.org/abs/1809.08887)
- Spider dataset: Yale LILY lab, https://yale-lily.github.io/spider

# SQL Action Engine Boundary

`query-actions` belongs to the SQL Editor. It parses and compiles inline `@` annotations that a user types into SQL text.

Owned here:
- `@limit`
- `@timeout`
- `@explain`
- `@export`
- `@chart`
- `ActionPhase`, `ActionProcessor`, `QueryExecutionPlan`, and `ExecutionContext`

Not owned here:
- Agent steps, Agent tools, Agent artifacts, Agent traces, SSE runtime events, or follow-up context.
- Natural-language planning or semantic schema selection, except through explicit inputs already supplied by the SQL editor flow.

The execution shape should stay:

```text
SQL + @ annotations
  -> query-actions.parse/validate
  -> compile pureSql / compiledSql
  -> /query/validate or /query/execute
  -> afterExecute processors such as export/chart
```

Do not make the Agent emit `@chart`, `@limit`, or other SQL editor annotations. If Agent needs a chart or table, it should create an Agent artifact.

# Agent Tool Contract Standards

DataBox Agent tools should be treated as product contracts, not just Python functions. The model can decide which tools and artifacts are needed, but tools must return stable, typed payloads that the frontend can render safely.

## Core rule

The Agent must not generate UI code. It may decide artifact intent only.

```txt
Good: show metric + chart + table + insight + recommendation
Bad: return React, HTML, CSS, arbitrary Plotly JavaScript, or custom component code
```

The frontend owns rendering through fixed components such as metric cards, Plotly chart cards, result tables, markdown insight blocks, recommendations, SQL cards, and trace cards.

## Standard tool fields

Every tool should define:

```yaml
name: namespace.action
group: schema | query_plan | sql_generation | sql_validation | execution | result | chart | answer
kind: code | hybrid | llm
description: concise but behaviorally specific
handler: registered_handler_name
input_schema: JSON schema for model-visible args
output_schema: JSON schema for returned payload
binding:
  consumes_state_keys: []
  produces_state_keys: []
  artifact_types: []
metadata:
  next_route: optional_next_step
```

## Analysis delivery chain

For complex analysis tasks, the preferred chain is:

```txt
schema.build_context
→ query_plan.build
→ sql.generate
→ sql.validate
→ sql.execute_readonly
→ result.profile
→ chart.suggest
→ followup.suggest
→ analysis.compose
```

Tiny scalar lookups may stop earlier, but any task involving trend, ranking, comparison, distribution, anomaly, time range, or decision support should continue to `analysis.compose`.

## Tool responsibilities

### `result.profile`

Purpose: deterministic result understanding.

It should produce:

```ts
{
  row_count: number;
  column_profiles: Record<string, {
    kind: "numeric" | "category" | "time" | "unknown";
    count: number;
    null_count: number;
    distinct_count: number;
    min?: number | string;
    max?: number | string;
    sum?: number;
    avg?: number;
    top_values?: Array<{ value: unknown; count: number }>;
  }>;
  detected_patterns: string[];
  notable_facts: string[];
  anomalies: string[];
  limitations: string[];
}
```

Facts and profiles should be computed from result rows, not invented by the LLM.

### `chart.suggest`

Purpose: choose a visualization and provide chart encoding for the fixed Plotly renderer.

It should produce either a chart suggestion referencing table columns:

```ts
{
  type: "line" | "bar" | "area" | "scatter" | "pie" | "table";
  x?: string;
  y?: string;
  title?: string;
  unit?: string;
  reason: string;
}
```

or direct renderable series:

```ts
{
  type: "bar";
  title: "Top departments by assets";
  series: Array<{ label: string; value: number }>;
  reason: string;
}
```

The tool must not output arbitrary JavaScript or Plotly configuration objects from the model.

### `analysis.compose`

Purpose: final delivery composition.

It should consume SQL, safety, execution, result profile, chart suggestion, suggestions, and existing artifacts. It should output:

```ts
{
  answer: string;
  key_findings: string[];
  evidence: Array<{ artifact_id: string; label: string; value?: string | number }>;
  caveats: string[];
  recommendations: string[];
  follow_up_questions: string[];
  display_plan?: Array<{
    component: "metric" | "chart" | "table" | "markdown" | "recommendation" | "sql" | "trace";
    reason: string;
    priority: number;
  }>;
}
```

`display_plan` is an intent plan, not UI code. The frontend can ignore it if artifact priorities already determine the layout.

## Anti-patterns

Avoid these patterns:

```txt
- A tool returns a long natural-language paragraph instead of structured fields.
- A tool returns raw database rows without row count, columns, truncation, and warnings.
- A chart tool only says "use a bar chart" but gives no x/y or series.
- An answer tool invents numbers not present in result/profile artifacts.
- A final answer hides SQL, safety, or trace when the task was complex.
- A prompt tries to solve tool spam by preventing useful downstream tools.
```

## Product principle

DataBox should feel like a data-analysis IDE, not a generic chatbot.

```txt
Table = evidence
Chart = visual explanation
Profile = deterministic facts
Answer = human interpretation
Recommendations = next actions
SQL = reproducibility
Trace = trust and debugging
```

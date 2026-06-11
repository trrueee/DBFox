# Agent Analysis Workbench

This branch starts the DataBox shift from a plain chat-style SQL assistant to a structured, reviewable data-analysis workbench.

## Product goal

Complex questions should not end as a single text answer. A successful Agent run should produce a reviewable analysis packet:

1. **Analysis summary** — whether the run produced SQL, result data, chart suggestions, insights, and safety checks.
2. **Evidence artifacts** — SQL, result table, Plotly chart, and markdown insight cards.
3. **Trace artifacts** — query-planning and safety decisions rendered as inspectable stages.
4. **Failure visibility** — when complex tasks fail, users should see which stage is weak: schema selection, metric parsing, filter parsing, SQL safety, or execution.

## Frontend changes in this branch

- Adds `metric` and `trace` view artifact types.
- Adds `MetricArtifactView` for compact delivery-quality cards.
- Adds `TraceArtifactView` for query-plan and safety-chain inspection.
- Replaces the chart artifact renderer with `plotly.js-dist-min` so DataBox can render interactive charts inside the Agent result workspace.
- Supports Plotly chart variants: `line`, `bar`, `area`, `scatter`, and `pie`.
- Enhances `agentBridge.ts` so backend artifacts such as `query_plan` and `safety` are no longer discarded; they are transformed into user-facing trace cards.
- Derives an `分析交付概览` card from the artifact set so every run can quickly show whether it is a complete data-analysis answer or only a partial response.

## Frontend dependency note

This branch adds:

```json
"plotly.js-dist-min": "^3.1.0"
```

Run `npm install` in `desktop/` before building so `package-lock.json` is refreshed locally.

## Next backend work

The backend should continue emitting artifact payloads with stable schemas:

```ts
query_plan: {
  analysis_goal: string;
  candidate_tables: string[];
  metrics: Array<{ name?: string; expression?: string }>;
  dimensions: Array<{ name?: string; column?: string }>;
  filters: Array<{ column?: string; operator?: string; value?: string }>;
  assumptions: string[];
  risk_notes: string[];
}

safety: {
  risk_level: "safe" | "warning" | "danger";
  checks: Array<{ rule: string; level: "pass" | "warn" | "reject"; message: string }>;
}
```

For richer chart delivery, the Agent should emit chart artifacts with either a direct `series` payload:

```ts
chart: {
  type: "line" | "bar" | "area" | "scatter" | "pie";
  series: Array<{ label: string; value: number }>;
  reason?: string;
  unit?: string;
}
```

or a chart suggestion that references a companion table artifact:

```ts
chart: {
  type: "line" | "bar" | "area" | "scatter" | "pie";
  x: string;
  y: string;
  reason?: string;
  unit?: string;
}
```

## Why this matters

DataBox's differentiator should be **trustworthy, visual, evidence-backed analysis**, not just text-to-SQL. These artifact views make the workbench closer to a data-analysis IDE: users can read the conclusion, inspect the SQL, verify the result table, view the interactive Plotly chart, and debug the agent chain when it goes wrong.

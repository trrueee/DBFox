# DataBox Agent Architecture Decisions

## ADR-001: Narrative-first user experience

DataBox Agent defaults to natural-language analysis narration. Technical tool steps are audit trace, not the primary user experience.

The user should feel that a data analyst is progressively investigating the question, not that a fixed SQL pipeline is printing logs.

## ADR-002: Artifacts as structured evidence

SQL, result tables, charts, safety reports, query plans, insights, recommendations, and errors are represented as Agent artifacts.

Artifacts can be shown inline, opened in an inspector, exported, saved, or referenced by later answers.

Errors are also artifacts when they affect user-facing analysis. Error artifacts should include recovery guidance when possible.

## ADR-003: Evidence-grounded answers

Agent answers must be grounded in execution results and artifacts.

If execution is skipped, blocked, or failed, the answer must say so and must not invent a business conclusion.

Every business claim should be traceable to a result table, chart, SQL query, safety report, or prior artifact.

## ADR-004: Event-shaped runtime

The runtime uses visible events and trace events internally even when the first implementation returns a single HTTP response.

Visible events drive narration, inline artifacts, answer blocks, and suggestions.

Trace events drive audit/debug views.

This keeps the design ready for SSE streaming later without rewriting the runtime model.

## ADR-005: Phase order

The implementation order is:

1. Single-turn narrative agent
2. Session and follow-up context
3. Multi-query analysis
4. True streaming

Phase 1 intentionally avoids session persistence, multi-query task planning, SSE, multi-agent orchestration, and complex memory.

However, Phase 1 must still use event-shaped response data so the UI and runtime can evolve into streaming without a redesign.

## ADR-006: TrustGate remains mandatory

TrustGate is always the execution gate before SQL runs.

Agent runtime must not bypass schema validation, guardrail checks, confirmation requirements, production safeguards, or datasource/workspace scope restrictions.

Any artifact or answer based on SQL execution must record the safety state that allowed or blocked execution.

## ADR-007: Trace is for audit

Trace events and tool inputs/outputs are available through a trace drawer or equivalent non-default debug view.

They should not be rendered as the default user-facing story.

The default user experience should show narration, inline artifacts, findings, recommendations, and recoverable errors.

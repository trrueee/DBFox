# DataBox — Local-First Database Workbench with AI Agent Copilot

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Node.js 20.19+](https://img.shields.io/badge/node-20.19+-green.svg)](https://nodejs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

DataBox combines a deterministic database workbench with a LangGraph-based ReAct
agent. The **workbench** provides datasource management, schema browsing, SQL
editing, result grids, query history, and ER/table visualization. The **agent**
acts as an intelligent collaborator — reading workspace context, selecting tools,
generating SQL, explaining results, and producing artifacts.

## Product Domains

- **Basic Database Software**: datasource management, schema browsing, SQL editor
  with inline annotations (`@limit`, `@timeout`, `@explain`, `@export`, `@chart`),
  result grid, query history, ER diagram visualization, multi-table workspace.
- **Agent Copilot**: chat, context understanding, SQL generation / fix / explain
  / optimize, result explanation, tool calling, approval when needed.

No third domain (Workbench platform, Workbench API, complex workflow engine).

## Architecture

```
desktop/                         React + Tauri workbench (Vite, TypeScript, ECharts)
engine/                          FastAPI local engine (port 18625)
engine/agent/                    LangGraph ReAct Agent (graph, nodes, tools, planning, progress, repair, skills)
engine/agent/graph/              StateGraph, conditional routes, state, re-plan policy
engine/agent/nodes/              planner → model → policy → tools → observe → progress → repair → approval → finalize
engine/agent/tools/              tool aliases, registry bridge, tool manifest
engine/agent/planning/           Planner prompts, AgentPlanDirective schema
engine/agent/progress/           Progress Judge prompts, ProgressDecision schema, clarification policy
engine/agent/repair/             SQL repair classifier and recovery plan
engine/agent/model/              system prompt builder, model context builder
engine/agent/skills/             skill registry, loader, renderer
engine/agent_core/               shared Agent contracts, persistence, events, runtime facade
engine/environment/              datasource resolver, dialect, introspection, catalog sync, tools
engine/memory/                   session memory, long-term store, compaction, retrieval
engine/semantic/                 schema linking, context builder, query planning
engine/sql/                      SQL safety, execution, generator, guardrail, trust gate
engine/policy/                   PolicyEngine and query policy enforcement
engine/api/                      REST and SSE API
engine/llm/                      LLM provider client configuration
engine/schemas/                  Schema management API
```

> **Note**: Phase 2 sub-modules (`engine/semantic/`, `engine/environment/`,
> `engine/memory/`, `engine/agent/skills/`) are active and shipping. The memory
> and environment layers feed context into the Planner and Progress Judge.
> Conversations are now persisted via the `ChatConversation` model.

## Agent Runtime

The agent is a LangGraph StateGraph with 9 nodes and semantic conditional routing.

```text
START → planner → [model | finalize]
model → [policy | progress]
policy → [tools | approval | model | progress]
approval → [tools | model | progress]
tools → observe → progress
progress → [model | planner | repair | finalize]
repair → model
finalize → END
```

**Planner** (`create_plan`): LLM semantic classifier that infers user intent,
produces an `AgentPlanDirective` (task type, tool scope, execution mode), and
incorporates skill catalog and memory context. Routes to `model` for execution
or `finalize` if clarification is needed.

**Model** (`call_model`): ReAct reasoning node. Calls the LLM with dynamically
scoped LangChain tools based on the plan's `allowed_tool_groups`. Can escalate
its own tool scope via `escalate.tool_group`. Routes to `policy` when tool_calls
are present, `progress` otherwise.

**Policy** (`apply_policy`): Deterministic PolicyGate that validates tool calls
against execution mode, safety rules, and trust boundaries. Routes allowed calls
to `tools`, blocked calls back to `model` for retry (up to 3 consecutive blocks
before escalating to `progress`), and to `approval` when human confirmation is
required.

**Approval** (`approval_interrupt`): Human-in-the-loop gate using LangGraph
`interrupt()`. Suspends the graph and presents the pending action to the user.
On resume, routes approved calls to `tools` and rejected calls back to `model`.

**Tools** (`execute_allowed_tools`): Executes policy-approved tool calls through
the tool registry bridge. Supports environment introspection, schema linking,
SQL generation / validation / execution, result profiling, and chart suggestions.

**Observe** (`observe_tools`): Observation-driven state binding. Applies tool
results to agent state via `databinding`, emits structured artifacts (query
plan, SQL, safety, table, profile, chart), and rebuilds the ContextPack for
downstream nodes.

**Progress** (`judge_progress`): LLM semantic judge that classifies task state
after each observation cycle: `complete` (answer ready), `continue` (more work),
`replan` (plan was wrong), `clarify` (ask user), or `failed`. Routes accordingly
to `model`, `planner`, `repair`, or `finalize`. Re-planning is gated by an
anti-loop limit and retry budget.

**Repair** (`prepare_repair`): Lightweight pre-model node activated when the
Progress Judge selects a recovery strategy. Consolidates tool scope for the
repair attempt and records repair trace metrics. Routes to `model`.

**Finalize** (`finalize_answer`): Terminal node. Extracts the final answer from
the last AIMessage, sets terminal status, auto-writes the execution trajectory
to long-term memory, and emits error artifacts for failed runs.

## API Overview

All routes are mounted under `/api/v1`.

### Projects & Datasources
```
GET    /api/v1/projects
POST   /api/v1/projects
POST   /api/v1/datasources/test
POST   /api/v1/datasources
GET    /api/v1/datasources
POST   /api/v1/datasources/{id}/health
DELETE /api/v1/datasources/{id}
POST   /api/v1/datasources/{id}/sync
```

### Schema
```
GET    /api/v1/schema/tables
GET    /api/v1/schema/tables/{table_id}/columns
GET    /api/v1/schema/er-diagram
POST   /api/v1/schema/generate-test-data
```

### Query
```
POST   /api/v1/query/validate
POST   /api/v1/query/execute
POST   /api/v1/query/explain
POST   /api/v1/query/cancel
GET    /api/v1/query/history
DELETE /api/v1/query/history/{history_id}
DELETE /api/v1/query/history
```

### Agent
```
POST   /api/v1/agent/run
POST   /api/v1/agent/run/stream
GET    /api/v1/agent/runs/{run_id}
POST   /api/v1/agent/runs/{run_id}/resume
POST   /api/v1/agent/runs/{run_id}/resume/stream
GET    /api/v1/agent/runs/recent
GET    /api/v1/agent/runs/{run_id}/artifacts
GET    /api/v1/agent/runs/{run_id}/events
GET    /api/v1/agent/runs/{run_id}/trace
GET    /api/v1/agent/runs/{run_id}/approvals
POST   /api/v1/agent/runs/{run_id}/approvals/{approval_id}
GET    /api/v1/agent/runs/{run_id}/checkpoints
GET    /api/v1/agent/sessions/{session_id}/runs
```

### Conversations
```
GET    /api/v1/conversations
PUT    /api/v1/conversations/{conversation_id}
DELETE /api/v1/conversations/{conversation_id}
```

### Agent Evaluation
```
GET    /api/v1/agent-eval/tasks
POST   /api/v1/agent-eval/tasks
PUT    /api/v1/agent-eval/tasks/{task_id}
DELETE /api/v1/agent-eval/tasks/{task_id}
POST   /api/v1/agent-eval/import-benchmark
POST   /api/v1/agent-eval/run
GET    /api/v1/agent-eval/runs
GET    /api/v1/agent-eval/runs/{eval_run_id}
GET    /api/v1/agent-eval/runs/{eval_run_id}/cases
```

### Semantic Layer
```
GET    /api/v1/semantic/aliases
POST   /api/v1/semantic/aliases
PUT    /api/v1/semantic/aliases/{id}
DELETE /api/v1/semantic/aliases/{id}
GET    /api/v1/semantic/metrics
POST   /api/v1/semantic/metrics
PUT    /api/v1/semantic/metrics/{id}
DELETE /api/v1/semantic/metrics/{id}
GET    /api/v1/semantic/dimensions
POST   /api/v1/semantic/dimensions
PUT    /api/v1/semantic/dimensions/{id}
DELETE /api/v1/semantic/dimensions/{id}
GET    /api/v1/semantic/table-scope
POST   /api/v1/semantic/table-scope
```

### Backups
```
GET    /api/v1/projects/{project_id}/backups
POST   /api/v1/backups
GET    /api/v1/backups/{backup_id}
POST   /api/v1/backups/{backup_id}/restore-precheck
POST   /api/v1/backups/{backup_id}/restore
```

> Old paths (`/query/generate`, `/golden-sql/*`, `/llm-logs/stats`,
> `/query/agent-*`) have been removed in Phase 1. Use `/agent/*` for all AI
> interactions.

## Local Development

### Quick Start (one-click launcher)

```bash
python start.py
```

This launches both backend (port 18625, hot-reload) and frontend (port 5173),
installs dependencies on first run, and opens the browser automatically.

### Desktop App (Tauri)

```bash
cd desktop && npm run tauri dev
```

Launches the native desktop window with custom title bar (drag, minimize,
maximize, close). Requires Rust toolchain. The browser dev server and `start.py`
remain available for development.

> `run_desktop.py` is a pywebview-based fallback for environments without Rust.

### Manual Setup

```bash
# Backend (hot reload watches engine/*.py)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m engine.main
# or: python -m engine.main --no-reload

# Frontend
cd desktop && npm install && npm run dev

# Tests
pip install -r requirements-dev.txt   # adds pytest, mypy, type stubs
python -m pytest                      # all tests
python -m pytest -m "not e2e"         # skip E2E tests
cd desktop && npm test                # Vitest
cd desktop && npm run test:watch      # Vitest watch mode
cd desktop && npm run lint            # ESLint
cd desktop && npm run build           # production build
cd desktop && npm run preview         # Vite preview
cd desktop && npm run tauri           # Tauri desktop app
```

## Safety Principles

- All SQL queries pass through policy enforcement before execution.
- Agent autonomous SQL execution must be policy-gated and validated.
- Agent must not bypass `sql.validate` or `safe_sql`.
- All blocked/error responses return user-friendly messages, not TrustGate internals.
- Local runtime state, API keys, SQLite databases, eval outputs, and generated
  reports must not be committed.

## Project Status

- **Phase 1** (complete): Repository boundary cleanup — removed old Text-to-SQL
  product entry points, workbench platform designs, golden-sql, legacy kernel.
- **Phase 2** (in progress): Agent internal redesign — semantic understanding
  (`engine/semantic/`), environment layer (`engine/environment/`), context and
  memory architecture (`engine/memory/`), skill registry, conversations
  persistence, and ContextPack state management.

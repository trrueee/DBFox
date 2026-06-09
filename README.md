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

- **Basic Database Software**: datasource, schema, query, SQL editor, result
  grid, query history, ER / table / column visualization, annotation shortcuts.
- **Agent Copilot**: chat, context understanding, SQL generation / fix / explain
  / optimize, result explanation, tool calling, approval when needed.

No third domain (Workbench platform, Workbench API, complex workflow engine).

## Architecture

```
desktop/                         React + Tauri workbench
engine/                          FastAPI local engine
engine/databox_agent/            LangGraph ReAct Agent (graph, nodes, tools, environment)
engine/databox_agent/graph/      StateGraph definition, routes, state
engine/databox_agent/nodes/      model → policy → tools → observe → approval → finalize
engine/databox_agent/tools/      tool aliases, registry bridge, manifest
engine/databox_agent/environment/ datasource resolver, dialect, introspection, catalog sync
engine/agent/                    shared Agent contracts, persistence, events, runtime facade
engine/semantic/                 schema linking, context builder, query planning (→ Phase 2)
engine/executor.py               SQL safety and execution
engine/trust_gate.py             TrustGate with policy-aware confirmation
engine/policy/                   PolicyEngine and query policy enforcement
engine/api/                      REST and SSE API
```

> **Note**: `engine/databox_agent/memory/` (session memory, long-term store) and
> `engine/databox_agent/checkpoints/` (replay, fork) are experimental internals.
> They are not yet exposed as product features and will be redesigned in Phase 2.

## Agent Runtime

```text
START → model → policy → tools → observe → model/finalize → END
                      ↓
                  approval (interrupt/resume)
```

The agent uses model-visible tool aliases, deterministic PolicyGate, secure tool
execution, observation-driven state binding, artifacts and runtime events,
LangGraph interrupt/resume for human-in-the-loop approval.

## API Overview

```
/api/v1/projects
/api/v1/datasources
/api/v1/schema/*
/api/v1/query/validate
/api/v1/query/execute
/api/v1/query/explain
/api/v1/query/cancel
/api/v1/query/history
/api/v1/agent/run
/api/v1/agent/run/stream
/api/v1/agent/runs/{run_id}
/api/v1/agent/runs/{run_id}/resume
/api/v1/agent/runs/{run_id}/resume/stream
/api/v1/agent/runs/recent
/api/v1/agent/runs/{run_id}/artifacts
/api/v1/agent/runs/{run_id}/events
/api/v1/agent/runs/{run_id}/trace
/api/v1/agent/runs/{run_id}/approvals
/api/v1/agent/sessions/{session_id}/runs
/api/v1/agent-eval/*
/api/v1/backups/*
/api/v1/table-design/*
/api/v1/semantic/*
```

> Old paths (`/query/generate`, `/golden-sql/*`, `/llm-logs/stats`,
> `/query/agent-*`) have been removed in Phase 1. Use `/agent/*` for all AI
> interactions.

## Local Development

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn engine.main:app --host 127.0.0.1 --port 18625

# Frontend
cd desktop && npm install && npm run dev

# Tests
python -m pytest
python -m pytest -m "not e2e"
cd desktop && npm test
```

## Safety Principles

- All SQL queries pass through policy enforcement before execution.
- Agent autonomous SQL execution must be policy-gated and validated.
- Agent must not bypass `sql.validate` or `safe_sql`.
- All blocked/error responses return user-friendly messages, not TrustGate internals.
- Local runtime state, API keys, SQLite databases, eval outputs, and generated
  reports must not be committed.

## Project Status

- **Phase 1** (current): Repository boundary cleanup — removed old Text-to-SQL
  product entry points, workbench platform designs, golden-sql, legacy kernel.
- **Phase 2** (planned): Agent internal redesign — semantic understanding,
  environment layer, context & memory architecture.

# DataBox — Local-First Database Workbench with AI Copilot Agent

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Node.js 20.19+](https://img.shields.io/badge/node-20.19+-green.svg)](https://nodejs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

DataBox combines a deterministic database workbench with a LangGraph-based ReAct
agent. The **workbench** owns visual, deterministic product workflows (table
preview, schema browsing, ER diagrams, SQL editing, result grids, charting,
export). The **agent** acts as an intelligent collaborator — reading workspace
context, selecting tools, generating SQL, explaining results, and producing
artifacts.

## Core Boundaries

- **Workbench**: deterministic UI and data operations.
- **Agent**: context-aware reasoning and tool use.
- **WorkspaceContext**: the contract between Workbench and Agent.
- **Data Environment Layer**: datasource resolution, schema catalog, dialect, introspection.
- **Workbench Action Gate**: low-friction user actions with limits, masking, and audit.
- **Agent PolicyGate**: strict policy for autonomous agent tool execution.

## Architecture

```
desktop/                    React + Tauri workbench
engine/                     FastAPI local engine
engine/databox_agent/       LangGraph ReAct Agent (graph, nodes, tools, environment, memory)
engine/databox_agent/graph/ StateGraph definition, routes, state
engine/databox_agent/nodes/ model → policy → tools → observe → approval → finalize
engine/databox_agent/tools/  tool aliases, registry bridge, manifest
engine/databox_agent/environment/  datasource resolver, dialect, introspection, catalog sync
engine/databox_agent/memory/       short-term, session, long-term memory
engine/databox_agent/checkpoints/  replay, fork, checkpoint history
engine/agent/               shared Agent contracts, persistence, events, runtime facade
engine/semantic/            schema linking, context builder, query planning
engine/executor.py          SQL safety and execution
engine/trust_gate.py        TrustGate with policy-aware confirmation
engine/policy/              PolicyEngine and action gates
engine/api/                 REST and SSE API
engine/workbench/           table preview executor
```

## Agent Runtime

```text
START → model → policy → tools → observe → model/finalize → END
                  ↓
              approval (interrupt/resume)
```

The agent uses model-visible tool aliases, deterministic PolicyGate, secure tool
execution, observation-driven state binding, artifacts and runtime events,
LangGraph interrupt/resume for human-in-the-loop approval, and checkpoint-backed
recovery.

## API Overview

```
/api/v1/projects
/api/v1/datasources
/api/v1/schema/*
/api/v1/query/*
/api/v1/query/agent-runs/{run_id}
/api/v1/query/agent-runs/{run_id}/stream
/api/v1/agent-eval/*
```

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

- User-initiated Workbench actions should be low-friction.
- Table preview uses limits, masking, and audit — not unnecessary confirmation.
- Agent autonomous SQL execution must be policy-gated and validated.
- Agent must not bypass `sql.validate` or `safe_sql`.
- All blocked/error responses return user-friendly messages, not TrustGate internals.
- Local runtime state, API keys, SQLite databases, eval outputs, and generated reports must not be committed.

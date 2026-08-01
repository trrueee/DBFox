# DBFox — Local-First AI-Native Database Workbench

## Project Type
- Backend: Python 3.12 + FastAPI + Uvicorn (`engine/`)
- Frontend: React 19 + TypeScript + Vite + Tauri 2 (`desktop/`)
- Python virtual environment: `.build_venv/`

## How to Run

### Backend (REQUIRED: use module mode!)
```bash
python -m engine.main             # http://127.0.0.1:18625
python engine/dev_server.py        # Alternative (equivalent)
```
**NEVER run `python engine/main.py`** — causes `ModuleNotFoundError: No module named 'engine'`.

### Frontend
```bash
cd desktop && npm run dev          # http://localhost:5173
```

### Convenience Scripts
```bash
./dev.ps1 backend|frontend|both    # Windows PowerShell
./dev.sh  backend|frontend|both    # Unix / Git Bash
```

### Tests
```bash
# Backend
pytest engine/ -q --tb=short

# Frontend
cd desktop && npm test
```

## Architecture

```
┌─────────────────────────────────────────────┐
│  Desktop (Tauri 2 / React 19 / Vite)        │
│  Port: 5173 (dev)                           │
│         │                                    │
│         │ HTTP + SSE (X-Local-Token auth)    │
│         ▼                                    │
│  Engine (FastAPI + Uvicorn)                  │
│  Port: 18625 (dev) / random (Tauri sidecar)  │
│         │                                    │
│         ▼                                    │
│  Databases (MySQL / PostgreSQL / SQLite)     │
└─────────────────────────────────────────────┘
```

## Key Conventions
- **Backend startup**: ALWAYS `python -m engine.main` (module mode), NEVER `python engine/main.py`
- **Frontend env**: `scripts/dev_environment.py` is the single writer for the ignored `desktop/.env.local`; build and dev launchers delegate to it
- **Default ports**: Backend 18625, Frontend 5173
- **Database**: SQLite by default at `./dbfox_local.db`, WAL mode, auto-migration on startup
- **Migrations**: Alembic in `engine/migrations/versions/`
- **Python deps**: `requirements.txt` (runtime) + `requirements-dev.txt` (dev)

## Agent Tool Chain
Registered functions are defined once in `engine/tools/builtin/registry.py`:
- Runtime control: `request_clarification`, `update_plan`
- Catalog: `catalog_overview`, `catalog_refresh`, `schema_list`, `schema_search`, `schema_inspect`
- Query: `data_preview`, `sql_validate`, `sql_execute_readonly`
- Results: `result_inspect`, `result_profile`, `chart_create`
- Model-authored SQL must use `sql_validate`, then pass the immutable validation Artifact ID to `sql_execute_readonly`. The execution tool never accepts raw SQL.
- Tool contracts are strict, content-addressed per Turn, and include input/output Schema, policy, execution, semantics, and presentation.

## Anti-patterns
- ❌ `python engine/main.py` — use `python -m engine.main`
- ❌ Do not add aliases for retired dotted tool names.
- ❌ Do not parse textual Thought/Action/Observation; the Agent uses native Responses Items.
- ❌ Do not drive the Agent Loop from React or Zustand.

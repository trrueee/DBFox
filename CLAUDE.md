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
pytest engine/ -q --tb=short --ignore=engine/agent/tests/test_e2e_qwen.py

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
- **Frontend env**: Engine auto-writes `desktop/.env.local` with `VITE_LOCAL_ENGINE_PORT` + `VITE_LOCAL_ENGINE_TOKEN` at startup
- **Default ports**: Backend 18625, Frontend 5173
- **Database**: SQLite by default at `./dbfox_local.db`, WAL mode, auto-migration on startup
- **Migrations**: Alembic in `engine/migrations/versions/`
- **Python deps**: `requirements.txt` (runtime) + `requirements-dev.txt` (dev)

## Agent Tool Chain
Registered tools (see `engine/tools/dbfox_tools.py`):
- `db.observe`, `db.search`, `db.inspect`, `db.preview`, `db.query`
- `sql.validate`, `sql.execute_readonly`
- `chart.suggest`
- `answer.synthesize`
- `escalate.tool_group`

Agent skills (YAML): `engine/agent/skills/builtin/` — `result_analysis.yaml`, `schema_exploration.yaml`

## Anti-patterns
- ❌ `python engine/main.py` — use `python -m engine.main`
- ❌ Do NOT reference `result.profile` — this tool was deleted in MVP simplification (2026-06)
- ❌ The "result" tool group has zero registered tools

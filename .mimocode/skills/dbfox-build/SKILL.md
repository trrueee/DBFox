---
name: dbfox-build
description: Build and package the DBFox desktop application — cleans old artifacts, rebuilds the Python engine sidecar with PyInstaller, then runs Tauri build. Covers all known gotchas.
---

# DBFox Build & Package

End-to-end build workflow for the DBFox desktop app (Tauri 2 + Python sidecar).

## Prerequisites

- `.build_venv` Python virtual environment exists and has all dependencies from `requirements.txt`
- Node.js + npm available
- `build_sidecar.py` at project root

## Build Steps

### Step 1: Clean old artifacts

```bash
rm -rf pyinstaller_dist pyinstaller_build dbfox-engine.spec dbfox_engine.spec desktop/src-tauri/target
```

### Step 2: Rebuild Python sidecar

```bash
"./.build_venv/Scripts/python.exe" build_sidecar.py
```

This generates:
- `engine/token_preset.py` with a random `LOCAL_ENGINE_TOKEN`
- `desktop/.env.local` with `VITE_LOCAL_ENGINE_TOKEN` and `VITE_LOCAL_ENGINE_PORT`
- PyInstaller bundle in `pyinstaller_dist/`

### Step 3: Build Tauri desktop app

```bash
cd desktop && npm run tauri build
```

**IMPORTANT**: Tauri does NOT auto-rebuild the sidecar. You MUST run Step 2 before Step 3 every time.

## Gotchas

1. **`--noconsole` breaks logging**: On Windows, `--noconsole` sets `sys.stdout`/`sys.stderr` to `None`. The `dev_server.py` must detect this and fallback to `os.devnull` or uvicorn logging crashes.

2. **Sidecar survives window close**: The sidecar process doesn't die when Tauri window closes → old engine blocks file overwrite during install. Fix: Rust `Command::new.kill_on_drop(true)`.

3. **Use `.build_venv`, not conda**: Conda has ML packages (torch, pandas, h5py) that conflict with NumPy 2.x. Always use the clean `.build_venv`.

4. **Token variable naming**: `build_sidecar.py` writes `VITE_LOCAL_ENGINE_TOKEN` (not `VITE_DBFOX_STATIC_TOKEN`). Frontend reads `VITE_LOCAL_ENGINE_TOKEN` + `VITE_LOCAL_ENGINE_PORT`.

5. **Hidden imports**: `sshtunnel`, `keyring`, `langgraph`, `langchain_core` must be installed in `.build_venv` and added as hidden imports in the PyInstaller spec.

6. **`alembic.ini` bundling**: Must be explicitly added to PyInstaller bundle via `--add-data`.

7. **Multiple `.bak` files accumulate** in project root from repeated builds — clean up periodically.

## Test Before Build

Always run tests before packaging:

```bash
# Frontend
cd desktop && npm test

# Backend
python -m pytest engine/tests/ -q
```

## Quick Reference (single command)

```bash
rm -rf pyinstaller_dist pyinstaller_build dbfox-engine.spec desktop/src-tauri/target 2>/dev/null; "./.build_venv/Scripts/python.exe" build_sidecar.py && cd desktop && npm run tauri build
```

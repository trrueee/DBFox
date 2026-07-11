# Foundation Phase 1 — Task 2b Runtime Reset

## Delivered contract

- `reset_legacy_runtime_state(metadata_url, runtime_root, *, checkpoint_path=None)` accepts only a local, regular SQLite metadata file contained by the validated runtime root.
- Cleanup is restricted to the exact checkpoint sidecar family, matching `<metadata-name>.bak_<digits>` backup families and their sidecars, and `config/langsmith.env`.  Live metadata sidecars are validated but never removed.
- All cleanup candidates are containment/link/type preflighted before the first unlink.  Unsafe paths use fixed, non-leaking reset errors.
- SQLite uses `BEGIN IMMEDIATE` and re-reads the singleton marker before external cleanup, so one first-run caller performs the reset while later callers no-op on marker version `2`.
- The database reset removes Agent/runtime and schema-cache state in child-first order, clears credential references and volatile health/sync fields, rebuilds `schema_search_fts`, retains the specified metadata families, nulls retained evaluation `run_id` values, and writes the marker last.
- The implementation neither imports nor accesses the credential vault.

## Verification

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_runtime_reset.py engine\tests\test_db_init.py engine\tests\test_migrations.py -q
```

Result: `32 passed` (only pre-existing dependency deprecation/SQLAlchemy-cycle warnings).

Focused reset coverage includes real reset, marker idempotence, no-vault access,
exact physical cleanup, outside/sibling and malicious-sidecar preflight,
retryable cleanup failure, unknown-marker fail-closed behavior, FTS `MATCH`
emptiness, retained evaluation `run_id` nulling, and lock-before-cleanup
serialization.

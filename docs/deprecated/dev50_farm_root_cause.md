# Dev50 Farm Worker Timeout Root Cause Analysis

## Evidence Summary

| Test | Workers | Cases | Result | Schema Errors |
|------|---------|-------|--------|---------------|
| smoke10 (fresh farm) | 2 | 10 | 9/10 PASS | 0 |
| projection bucket (same farm) | 2 | 6 | 3/6 PASS | 0 |
| dev50 (same farm, after projection) | 2 | 50 | 0/50 PASS | 50/50 |
| smoke10 (fresh restart) | 2 | 10 | 10/10 PASS | 0 |
| dev50 (fresh restart, seeded DB) | 2 | 50 | 0/50 PASS | 50/50 |

**Key observation**: schema preflight succeeds on fresh workers, fails after ~10-15 agent runs per worker. The failure is binary — ALL subsequent requests time out, not just a fraction.

## Architecture: Request Lifecycle

```
Eval Runner (run_agent_eval.py)
  │
  ├─ Phase 1: schema preflight
  │   └─ httpx.get(worker_url/api/v1/schema/tables) — 15s timeout
  │       └─ FastAPI → Depends(get_db) → SessionLocal() → engine
  │           └─ db.query(SchemaTable).filter(...).all()
  │
  └─ Phase 2: agent run
      └─ httpx.stream(POST worker_url/api/v1/agent-kernel/run/stream) — 180s timeout
          └─ FastAPI → Depends(get_db) → SessionLocal(bind=engine)
              └─ AgentKernelService(db).run_iter(req)
                  ├─ LangGraph with InMemorySaver checkpointer (class-level singleton)
                  ├─ tools: build_schema_context, build_query_plan, generate_sql_candidate, ...
                  └─ AgentKernelService.self.db — held for entire 30s agent run
```

## Key Code Locations

### 1. Module-level engine singleton (`engine/db.py:54`)
```python
engine: Engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=5, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```
**Risk**: All requests share one engine. Pool exhaustion = all requests blocked.

### 2. Class-level InMemorySaver (`engine/agent_kernel/service.py:49`)
```python
class AgentKernelService:
    _checkpointer = build_agent_kernel_checkpointer()  # InMemorySaver singleton
```
**Risk**: All agent runs accumulate state in shared InMemorySaver. Never cleared.

### 3. Schema endpoint (`engine/api/datasources.py:372`)
```python
def api_list_tables(datasource_id, db: Session = Depends(get_db)):
    tables = db.query(SchemaTable).filter(...).all()
    # triggers N+1 lazy loads: len(table.columns)
```
**Risk**: Each call creates new session. If pool exhausted, blocks.

### 4. Streaming endpoint holds session for 30s (`engine/agent_kernel/api.py:90`)
```python
def run_agent_kernel_stream(req, db = Depends(get_db)):
    for event in AgentKernelService(db).run_iter(req):
        yield sse_format(event)
```
**Risk**: `db` session held for entire 30s agent run. Connection not released until stream completes.

## Top 5 Root Cause Hypotheses

### P1 (80%): SQLAlchemy Connection Pool Exhaustion from Streaming Sessions

**Mechanism**: 
1. Each agent run stream holds `Depends(get_db)` session for ~30s
2. The session's underlying connection stays "checked out" from the pool
3. After ~5 agent runs (pool_size=5), all connections consumed
4. Schema preflight (separate request) calls `Depends(get_db)` → waits for connection → times out at 15s

**Evidence**:
- Binary failure after ~10-15 runs (pool_size=5 + max_overflow=5 = 10 total connections per worker)
- First few requests work, then ALL timeout
- Schema endpoint uses same engine/connection pool
- `pool_pre_ping=True` adds overhead per connection checkout

**Verification**: 
- Set `pool_size=20, max_overflow=20` in db.py → if dev50 passes more cases before timeout, confirmed
- Add logging to `get_db()` to count active sessions

**Fix cost**: Low — increase pool_size for farm workers, or make get_db() release connection during streaming

### P2 (15%): InMemorySaver Unbounded Growth + Thread Contention

**Mechanism**:
1. `AgentKernelService._checkpointer` is class-level InMemorySaver shared across all instances
2. Each agent run adds 10-20 checkpoints to the shared dict
3. After 15+ runs, the dict has 200+ entries
4. LangGraph's checkpoint read/write operations contend on the dict lock
5. During checkpoint write, the agent blocks → holds DB session longer → cascade

**Evidence**:
- InMemorySaver uses a simple dict (no TTL, no eviction)
- Class-level attribute = never garbage collected
- LangGraph writes checkpoints at every tool execution step

**Verification**:
- Add `_checkpointer = None` reset between runs
- Or patch `build_agent_kernel_checkpointer` to return fresh InMemorySaver per request

**Fix cost**: Low — move checkpointer from class-level to instance-level

### P3 (3%): httpx Connection Pool Reuse in Eval Runner

**Mechanism**:
1. `fetch_databox_schema_tables` uses `httpx.get()` (module-level convenience function)
2. httpx internally uses a shared connection pool with limited connections
3. After 10+ requests to the same host, pool limits hit
4. Schema preflight times out waiting for a free connection

**Evidence**:
- httpx.get() uses implicit connection pooling
- Timeout is always exactly 15.0s (matches the explicit timeout)

**Verification**:
- Use explicit `httpx.Client()` with `pool_limits=httpx.Limits(max_connections=20)` 

**Fix cost**: Low

### P4 (1%): Eager Loading N+1 in Schema Endpoint

**Mechanism**:
1. `api_list_tables` queries SchemaTable, then accesses `len(table.columns)` for each table
2. Without `selectinload`, this triggers N lazy loads (one per table)
3. Under connection pool pressure, each lazy load waits for a free connection
4. Cumulative delay exceeds 15s timeout

**Evidence**:
- SchemaTable.columns is `relationship(... lazy="select")` by default
- Schema endpoint doesn't use `joinedload` or `selectinload`

**Verification**:
- Add `selectinload(SchemaTable.columns)` to the query — if timeout disappears, confirmed

**Fix cost**: Low — one line change

### P5 (1%): Uvicorn Thread Pool Saturation

**Mechanism**:
1. Sync endpoint `run_agent_kernel_stream` blocks a uvicorn thread for 30s
2. Uvicorn default thread pool = 40 threads
3. With 25 sequential requests per worker × 30s = 750s, threads cycle normally
4. BUT: if any request hangs (e.g., MySQL timeout), it permanently consumes a thread
5. Eventually thread pool saturates

**Evidence**:
- Less likely because uvicorn default is 40 threads, far more than needed

**Verification**:
- Add `--limit-concurrency 10` to uvicorn args

**Fix cost**: Low

## Recommended Verification Order

1. **P1 first**: Increase pool_size → if dev50 pass count > 0, P1 confirmed
2. **P2 second**: Move checkpointer to instance-level → if improvement, P2 confirmed
3. **P3 third**: Explicit httpx.Client → minor improvement
4. **P4 fourth**: Add selectinload → minor improvement

## Implementation Priority

If P1 confirmed: fix by increasing pool_size OR making agent streaming release the DB session after initial schema lookups (not hold it for the full 30s).

If P2 confirmed: fix by creating fresh InMemorySaver per AgentKernelService instance.

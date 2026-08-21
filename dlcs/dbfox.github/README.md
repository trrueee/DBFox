# dbfox.github DLC

This directory is the authoritative source tree for the external GitHub capability.
Its backend imports DBFox contracts only from `dbfox_dlc_api`; durable state is owned
by the DLC at `data_path/state.sqlite3`; and its frontend registers only through the
bounded frontend host.

The repository does not contain a production publisher private key. Conformance tests
build and sign this exact source tree with an explicitly test-only key through the
same deterministic builder exposed by the R7 `dbfox-dlc build/sign` commands.

Core no longer contains a GitHub runtime or frontend surface. The historical Core table
is retained only for the one-way Alembic import into this DLC-owned database; there is
no durable dual-write or fallback path. R5 conformance proves that capability appears
only after this package is enabled and the engine restarts, and disappears after disable
plus restart while DLC data and ToolAttempt package identity remain durable.

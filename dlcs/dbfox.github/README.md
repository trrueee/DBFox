# dbfox.github DLC

This directory is the authoritative source tree for the external GitHub capability.
Its backend imports DBFox contracts only from `dbfox_dlc_api`; durable state is owned
by the DLC at `data_path/state.sqlite3`; and its frontend registers only through the
bounded frontend host.

The repository does not contain a production publisher private key. Conformance tests
build and sign this exact source tree with an explicitly test-only key. Production key handling and the
general `dbfox-dlc build/sign` commands are delivered in R7.

During R5.2, the existing Core GitHub surface remains available, but its persistence
facade reads and writes only this DLC-owned database after the one-way Alembic import.
The historical Core table is retained read-only. R5.3 removes the temporary Core
implementation and facade; there is no durable dual-write or fallback path.
